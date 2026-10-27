#!/bin/bash
# composer-wrapper: 5
set -euo pipefail

# Closing the terminal must not abort a run in flight. The ignored disposition
# is inherited by `docker run`, so the client is not killed by the hangup and
# the container keeps going; Ctrl+C still reaches composer and cancels.
trap '' HUP

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# The wrapper resolves its own image before any composer code can run, so the
# channel has to be readable from here. `.composer-channel` holds one word,
# written by `composer check --beta` / `--stable`.
#
# COMPOSER_SELF_IMAGE still wins. An operator who pinned an exact image asked
# for that image; a channel is a default, and a default must never quietly
# discard an explicit pin.
composer_channel="stable"
if [[ -r "${script_dir}/.composer-channel" ]]; then
  read -r composer_channel < "${script_dir}/.composer-channel" || composer_channel="stable"
  composer_channel="$(printf '%s' "${composer_channel}" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"
fi
case "${composer_channel}" in
  beta) composer_channel_image="debeski/composer:beta" ;;
  *)    composer_channel_image="debeski/composer:latest" ;;
esac
composer_self_image="${COMPOSER_SELF_IMAGE:-${composer_channel_image}}"

# The deployer can only be refreshed here: a composer already running from
# this image cannot replace it. `update self` refreshes only the deployer;
# `update` with no named services refreshes it first, so the stack update
# that follows runs on the new deployer. Named services skip the refresh.
composer_image_version() {
  docker run --rm --entrypoint cat "${composer_self_image}" /app/VERSION 2>/dev/null || true
}

refresh_deployer() {
  local before="" after=""
  if docker image inspect "${composer_self_image}" >/dev/null 2>&1; then
    before="$(composer_image_version)"
  fi
  echo "Updating the Composer deployer (${composer_self_image})..."
  if ! docker pull "${composer_self_image}"; then
    return 1
  fi
  after="$(composer_image_version)"
  if [[ -n "${before}" && "${before}" == "${after}" ]]; then
    echo "Composer deployer is up to date (${after})."
  else
    echo "Composer deployer: ${before:-not installed} -> ${after}"
  fi
}

# bash 3.2 has no safe empty-array expansion under `set -u`, so classify the
# arguments by shifting a copy rather than slicing an array.
classify_invocation() {
  invocation=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -d|--dev|--file=*) shift ;;
      -f|--file) shift; if [[ $# -gt 0 ]]; then shift; fi ;;
      *) break ;;
    esac
  done
  if [[ $# -eq 0 ]]; then
    return 0
  fi
  local command="$1"
  shift
  if [[ "${command}" == "self" && $# -eq 1 && "$1" == "update" ]]; then
    invocation="self_update"
    return 0
  fi
  if [[ "${command}" != "update" ]]; then
    return 0
  fi
  if [[ $# -eq 1 && "$1" == "self" ]]; then
    invocation="update_self"
    return 0
  fi
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help) return 0 ;;
      -f|--file|-a|--app|--status-file) shift ;;
      -*) ;;
      *) return 0 ;;
    esac
    if [[ $# -gt 0 ]]; then
      shift
    fi
  done
  invocation="update_all"
}

classify_invocation "$@"
case "${invocation}" in
  self_update)
    echo "Note: 'self update' is deprecated; use './start.sh update self'." >&2
    refresh_deployer || exit 1
    exit 0
    ;;
  update_self)
    refresh_deployer || exit 1
    exit 0
    ;;
  update_all)
    if ! refresh_deployer; then
      echo "Warning: could not refresh the Composer deployer; updating the stack with the installed one." >&2
    fi
    echo ""
    ;;
esac

# Announce the first-run download instead of letting `docker run` pull an
# unnamed image while the command appears to hang.
if ! docker image inspect "${composer_self_image}" >/dev/null 2>&1; then
  echo "Composer image not installed locally — fetching ${composer_self_image}..."
  docker pull "${composer_self_image}"
  echo ""
fi

# Attach stdin unconditionally, so a pipe (`echo yes | ./start.sh run -m web
# migrate`) reaches the container instead of the container getting no stdin at
# all. Allocate a TTY only when there is one; `-t` on a redirected stream fails.
docker_flags=(-i --rm)
if [[ -t 0 && -t 1 ]]; then
  docker_flags+=(-t)
fi

secret_flags=()
for candidate in .env secrets/.env .secrets/.env; do
  secret_path="${script_dir}/${candidate}"
  if [[ ! -f "${secret_path}" ]]; then
    continue
  fi
  if [[ ! -r "${secret_path}" ]]; then
    echo "Secrets file exists but is not readable by the current host user: ${secret_path}" >&2
    exit 1
  fi
  secret_keys="$(
    awk -F= '/^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=/{key=$1; gsub(/^[[:space:]]+|[[:space:]]+$/, "", key); print key}' "${secret_path}" |
      paste -sd, -
  )"
  if [[ -z "${secret_keys}" ]]; then
    echo "Secrets file contains no environment values: ${secret_path}" >&2
    exit 1
  fi
  secret_flags=(
    --env-file "${secret_path}"
    -e "COMPOSER_INHERITED_SECRET_KEYS=${secret_keys}"
  )
  break
done

# macOS ships bash 3.2, where `set -u` rejects an empty array expansion, so a
# project with no secrets file cannot use the plain "${secret_flags[@]}" form.
docker run "${docker_flags[@]}" \
  ${secret_flags[@]+"${secret_flags[@]}"} \
  -v "${script_dir}:${script_dir}" \
  -w "${script_dir}" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  "${composer_self_image}" "$@"
