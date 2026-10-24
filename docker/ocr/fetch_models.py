"""Build-time model download, so the running service never needs the network."""

import os
import sys

from huggingface_hub import snapshot_download
from indra_ocr.models import FILES, HF_REPO, HF_REVISION, MATH_FILES

target = os.environ['INDRA_OCR_MODEL_DIR']
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
