#!/bin/bash
# composer-wrapper: 7
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

# `.composer-image` holds the digest the last verified update pinned, written by
# composer itself (`update self`, `agent update`, `check --beta` / `--stable`).
# It is read with the same pattern composer uses, so a malformed lock falls back
# to the channel tag in both places. COMPOSER_SELF_IMAGE still beats it.
composer_lock_file="${script_dir}/.composer-image"
composer_lock_pattern='^debeski/composer:v[0-9]+(\.[0-9]+){1,2}((a|b|rc)[0-9]+)?@sha256:[0-9a-f]{64}$'
read_composer_lock() {
  composer_lock_image=""
  if [[ -r "${composer_lock_file}" ]]; then
    read -r composer_lock_image < "${composer_lock_file}" || true
    composer_lock_image="$(printf '%s' "${composer_lock_image}" | tr -d '[:space:]')"
  fi
  if [[ ! "${composer_lock_image}" =~ ${composer_lock_pattern} ]]; then
    composer_lock_image=""
  fi
}
read_composer_lock
composer_self_image="${COMPOSER_SELF_IMAGE:-${composer_lock_image:-${composer_channel_image}}}"

# Secrets reach every composer run, the pin included: validating the Compose
# edit interpolates the same variables a deploy does.
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

# The deployer can only be refreshed here: a composer already running from
# this image cannot replace it. `update self` refreshes only the deployer;
# `update` with no named services refreshes it first, so the stack update
# that follows runs on the new deployer. Named services skip the refresh.
composer_image_id() {
  docker image inspect --format '{{.Id}}' "${composer_self_image}" 2>/dev/null || true
}

composer_image_version() {
  docker run --rm --entrypoint cat "$1" /app/VERSION 2>/dev/null || true
}

composer_can_pin() {
  [[ "$(docker image inspect --format '{{ index .Config.Labels "org.dlux.composer.image-pin" }}' "$1" 2>/dev/null || true)" == "1" ]]
}

# The installed deployer resolves the channel's newest release, verifies its
# signed digest and writes the lock; only then is that digest pulled, so the
# registry cannot swap what arrives. With no lock yet, the first pin trusts the
# channel tag once, exactly as every update did before pinning existed.
pin_deployer() {
  local resolver="${composer_lock_image:-${composer_channel_image}}"
  if [[ -z "${composer_lock_image}" ]]; then
    docker pull "${composer_channel_image}" || return 1
  elif ! docker image inspect "${resolver}" >/dev/null 2>&1; then
    docker pull "${resolver}" || return 1
  fi
  if ! composer_can_pin "${resolver}"; then
    echo "This Composer predates digest pinning; the deployer stays on ${composer_channel_image}."
    composer_self_image="${composer_channel_image}"
    return 0
  fi
  docker run --rm \
    ${secret_flags[@]+"${secret_flags[@]}"} \
    -e COMPOSER_ALLOW_UNVERIFIED_COMPOSER \
    -v "${script_dir}:${script_dir}" \
    -w "${script_dir}" \
    -v /var/run/docker.sock:/var/run/docker.sock \
    "${resolver}" update self --pin || return 1
  read_composer_lock
  if [[ -z "${composer_lock_image}" ]]; then
    echo "The deployer reported a pin, but ${composer_lock_file} is unreadable." >&2
    return 1
  fi
  composer_self_image="${composer_lock_image}"
  if ! docker image inspect "${composer_self_image}" >/dev/null 2>&1; then
    docker pull "${composer_self_image}" || return 1
  fi
}

# A rebuilt tag can keep its version string, so compare image IDs, and start
# a container for a version only when there is one to report. The replaced
# image stays readable by ID after the pull.
refresh_deployer() {
  local before_id="" after_id="" before=""
  before_id="$(composer_image_id)"
  if [[ -n "${COMPOSER_SELF_IMAGE:-}" ]]; then
    echo "Updating the Composer deployer (${composer_self_image})..."
    if ! docker pull "${composer_self_image}"; then
      return 1
    fi
  else
    echo "Updating the Composer deployer (${composer_channel} channel)..."
    if ! pin_deployer; then
      return 1
    fi
  fi
  after_id="$(composer_image_id)"
  if [[ -n "${before_id}" && "${before_id}" == "${after_id}" ]]; then
    echo "Composer deployer is up to date ($(composer_image_version "${composer_self_image}"))."
    return 0
  fi
  if [[ -n "${before_id}" ]]; then
    before="$(composer_image_version "${before_id}")"
  fi
  echo "Composer deployer: ${before:-not installed} -> $(composer_image_version "${composer_self_image}")"
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
  # `update self` takes only the global -f/-d options, in any position, like
  # composer itself; anything else is left for composer to reject.
  local selves=0 options=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help) return 0 ;;
      self) selves=$((selves + 1)) ;;
      -d|--dev|--file=*) ;;
      -f|--file) if [[ $# -gt 1 ]]; then shift; fi ;;
      -a|--app|--status-file) options=1; if [[ $# -gt 1 ]]; then shift; fi ;;
      -*) options=1 ;;
      *) return 0 ;;
    esac
    shift
  done
  if [[ ${selves} -eq 0 ]]; then
    invocation="update_all"
  elif [[ ${selves} -eq 1 && ${options} -eq 0 ]]; then
    invocation="update_self"
  fi
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

# macOS ships bash 3.2, where `set -u` rejects an empty array expansion, so a
# project with no secrets file cannot use the plain "${secret_flags[@]}" form.
docker run "${docker_flags[@]}" \
  ${secret_flags[@]+"${secret_flags[@]}"} \
  -e COMPOSER_ALLOW_UNVERIFIED_COMPOSER \
  -v "${script_dir}:${script_dir}" \
  -w "${script_dir}" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  "${composer_self_image}" "$@"
