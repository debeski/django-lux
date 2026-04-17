#!/bin/bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Auto-update decrypter image before running
docker pull debeski/decrypter:compose >/dev/null 2>&1 || true

docker run -it --rm \
  -v "${script_dir}:${script_dir}" \
  -w "${script_dir}" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  debeski/decrypter:compose "$@"
