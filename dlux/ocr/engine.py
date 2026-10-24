"""OCR engine adapters for ``python -m dlux.ocr.serve``.

DjangoLux only sees the JSON contract produced by ``Engine.convert``; replacing
Indra OCR with Tesseract or another engine means adding an adapter here and
selecting it with ``OCR_ENGINE``. Engines import their packages lazily: they come
from the optional ``django-lux[ocr]`` extra, and only the ``ocr`` service loads them.
"""

import os
import threading


class EngineError(Exception):
    """The input cannot be read (corrupt, locked or unsupported)."""


class Engine:
    name = ''
    version = ''
    model_version = ''

    def convert(self, path, mode='auto', max_pages=0, threads=2):
        """Return {"pages": [page, ...]} where each page has index, source,
        markdown, text, lines [{box, text, conf}], blocks, rotation, skew, note
        and timings (milliseconds)."""
        raise NotImplementedError


class IndraEngine(Engine):
    name = 'indra-ocr'

    def __init__(self):
        import indra_ocr
        from indra_ocr.models import HF_REVISION

        self._indra = indra_ocr
        self.version = indra_ocr.__version__
        self.model_version = os.environ.get('INDRA_OCR_MODEL_REVISION', HF_REVISION)
        self.dpi = float(os.environ.get('OCR_DPI', '200'))
        self._idle = []
        self._lock = threading.Lock()

    def _take(self, threads):
        """A loaded model set for ``threads``; loading one takes about a second, so sets are reused."""
        with self._lock:
            for index, (count, ocr) in enumerate(self._idle):
                if count == threads:
                    return self._idle.pop(index)[1]
            for count, stale in self._idle:
                if stale.pool is not None:
                    stale.pool.shutdown(wait=False)
            self._idle = []
        from indra_ocr.models import model_dir
        return self._indra.OrtOCR(model_dir(), threads=threads)

    def _give_back(self, threads, ocr):
        with self._lock:
            self._idle.append((threads, ocr))

    def convert(self, path, mode='auto', max_pages=0, threads=2):
        from indra_ocr.document import Converter

        ocr = self._take(threads)
        converter = Converter(ocr, dpi=self.dpi, mode=mode)
        pages = []
        try:
            for index, page in converter.convert(path, max_pages=max_pages):
                pages.append({
                    'index': index,
                    'source': page.source,
                    'markdown': page.markdown or '',
                    'text': page.text,
                    'lines': [{'box': [round(v, 1) for v in line.box], 'text': line.text, 'conf': round(float(line.conf), 4)} for line in page.lines],
                    'blocks': page.blocks,
                    'rotation': page.rotation,
                    'skew': round(float(page.skew), 3),
                    'note': page.note,
                    'timings': {key: round(float(value), 1) for key, value in page.timings.items()},
                })
        except self._indra.InputError as exc:
            raise EngineError(str(exc)) from exc
        finally:
            self._give_back(threads, ocr)
        return {'pages': pages}


ENGINES = {'indra': IndraEngine}


def load(name=None):
    name = name or os.environ.get('OCR_ENGINE', 'indra')
    try:
        engine_class = ENGINES[name]
    except KeyError:
        raise SystemExit(f'Unknown OCR_ENGINE {name!r}; available: {", ".join(ENGINES)}')
    return engine_class()
