"""Download the OCR models at image build time: ``python -m dlux.ocr.fetch_models``.

The ``ocr`` service must run offline, so the scaffold Dockerfile runs this after
installing ``django-lux[ocr]``, into ``INDRA_OCR_MODEL_DIR``. ``--if-installed``
does nothing when the extra is not installed, so one Dockerfile serves projects
with and without OCR.
"""

import argparse
import os
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--if-installed', action='store_true', help='Do nothing when django-lux[ocr] is not installed.')
    args = parser.parse_args(argv)
    try:
        from huggingface_hub import snapshot_download
        from indra_ocr.models import FILES, HF_REPO, HF_REVISION, MATH_FILES
    except ImportError:
        if args.if_installed:
            print('django-lux[ocr] is not installed; no OCR models to download.')
            return 0
        raise
    target = os.environ.get('INDRA_OCR_MODEL_DIR')
    if not target:
        sys.exit('Set INDRA_OCR_MODEL_DIR to the folder the ocr service reads its models from.')
    revision = os.environ.get('INDRA_OCR_MODEL_REVISION') or HF_REVISION
    snapshot_download(
        HF_REPO, revision=revision, local_dir=target,
        allow_patterns=['*.onnx', 'meta.json', 'lm.npz', 'lm_*.npz', 'LICENSE*', 'README*'],
        ignore_patterns=list(MATH_FILES),
    )
    missing = [name for name in FILES if not os.path.exists(os.path.join(target, name))]
    if missing:
        sys.exit(f'Model download is missing {missing}')
    print(f'Indra OCR models {revision} in {target}: {sorted(os.listdir(target))}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
