#!/bin/bash
# composer-wrapper: 8
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
# It is read with the rule composer uses: the first non-empty line, stripped at
# its ends (and of a byte-order mark), must match the pattern whole; nothing
# inside it is removed. A malformed lock falls back to the channel tag in both
# places.
# COMPOSER_SELF_IMAGE still beats it.
composer_lock_file="${script_dir}/.composer-image"
composer_lock_pattern='^debeski/composer:v[0-9]+(\.[0-9]+){1,2}((a|b|rc)[0-9]+)?@sha256:[0-9a-f]{64}$'
read_composer_lock() {
  composer_lock_image=""
  local line=""
  if [[ -r "${composer_lock_file}" ]]; then
    while IFS= read -r line || [[ -n "${line}" ]]; do
      line="${line#$'\xef\xbb\xbf'}"
      line="${line#"${line%%[! $'\t\r\v\f']*}"}"
      line="${line%"${line##*[! $'\t\r\v\f']}"}"
      if [[ -n "${line}" ]]; then
        composer_lock_image="${line}"
        break
      fi
    done < "${composer_lock_file}"
  fi
  if [[ ! "${composer_lock_image}" =~ ${composer_lock_pattern} ]]; then
    composer_lock_image=""
  fi
}
read_composer_lock
composer_self_image="${COMPOSER_SELF_IMAGE:-${composer_lock_image:-${composer_channel_image}}}"

# Secrets reach every composer run, the pin included: validating the Compose
# edit interpolates the same variables a deploy does. The first file that exists
# is used; one that leaves out keys a later file holds is a stray copy shadowing
# the real one, and is refused rather than deployed on compose defaults.
secret_keys_of() {
  awk -F= '/^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=/{key=$1; gsub(/^[[:space:]]+/, "", key); print key}' "$1" |
    paste -sd, -
}
secret_flags=()
secret_keys=""
secret_source=""
for candidate in .env secrets/.env .secrets/.env; do
  secret_path="${script_dir}/${candidate}"
  if [[ ! -f "${secret_path}" ]]; then
    continue
  fi
  if [[ ! -r "${secret_path}" ]]; then
    echo "Secrets file exists but is not readable by the current host user: ${secret_path}" >&2
    exit 1
  fi
  if [[ -n "${secret_source}" ]]; then
    missing=""
    for key in $(secret_keys_of "${secret_path}" | tr ',' ' '); do
      case ",${secret_keys}," in
        *",${key},"*) ;;
        *) missing="${missing:+${missing}, }${key}" ;;
      esac
    done
    if [[ -n "${missing}" ]]; then
      echo "Two secrets files: ${secret_source} is used, but ${candidate} holds keys it does not (${missing})." >&2
      echo "A stray ${secret_source} would deploy on compose defaults. Move the one you do not use into .xclude/, or merge them." >&2
      exit 1
    fi
    continue
  fi
  # Docker reads the file as --env-file: KEY=value lines, no `export`, no spaces around `=`.
  bad_line="$(awk '/^[[:space:]]*export[[:space:]]/ || /^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]+=/ {print NR; exit}' "${secret_path}")"
  if [[ -n "${bad_line}" ]]; then
    echo "Secrets file ${secret_path}, line ${bad_line}: write KEY=value, with no 'export' and no spaces around '=' (Docker reads this file with --env-file)." >&2
    exit 1
  fi
  secret_keys="$(secret_keys_of "${secret_path}")"
  if [[ -z "${secret_keys}" ]]; then
    echo "Secrets file contains no environment values: ${secret_path}" >&2
    exit 1
  fi
  secret_source="${candidate}"
  secret_flags=(
    --env-file "${secret_path}"
    -e "COMPOSER_INHERITED_SECRET_KEYS=${secret_keys}"
  )
done

# The deployer sees only the project directory, so a Compose file linked from
# outside it cannot be read there.
compose_candidates="compose.yml docker-compose.yml"
compose_named=""
compose_dev=0
next_is_file=0
for argument in "$@"; do
  if [[ ${next_is_file} -eq 1 ]]; then
    compose_named="${argument}"
    next_is_file=0
    continue
  fi
  case "${argument}" in
    -f|--file) next_is_file=1 ;;
    --file=*) compose_named="${argument#--file=}" ;;
    -d|--dev) compose_dev=1 ;;
  esac
done
if [[ -n "${compose_named}" ]]; then
  compose_candidates="${compose_named}"
elif [[ ${compose_dev} -eq 1 ]]; then
  compose_candidates="${compose_candidates} compose.dev.yml"
fi
project_physical="$(cd -P -- "${script_dir}" && pwd)"
for compose_name in ${compose_candidates}; do
  case "${compose_name}" in
    /*) compose_path="${compose_name}" ;;
    *) compose_path="${script_dir}/${compose_name}" ;;
  esac
  if [[ ! -L "${compose_path}" ]]; then
    continue
  fi
  link_target="$(readlink "${compose_path}")"
  case "${link_target}" in
    /*) ;;
    *) link_target="$(dirname -- "${compose_path}")/${link_target}" ;;
  esac
  target_dir="$(cd -P -- "$(dirname -- "${link_target}")" 2>/dev/null && pwd || true)"
  case "${target_dir}/" in
    "${project_physical}/"*) ;;
    *)
      echo "${compose_name} is a symbolic link to ${link_target}, outside the project directory ${script_dir}." >&2
      echo "The Composer container mounts only the project directory, so it cannot read that file: copy it into the project, or link to a file inside it." >&2
      exit 1
      ;;
  esac
done

# Compose variables come from the secrets file only: one set in this shell
# never reaches Composer, so say so rather than deploy without it.
shell_only=""
for compose_name in ${compose_candidates}; do
  case "${compose_name}" in
    /*) compose_path="${compose_name}" ;;
    *) compose_path="${script_dir}/${compose_name}" ;;
  esac
  [[ -r "${compose_path}" ]] || continue
  for name in $(grep -oE '\$\{[A-Za-z_][A-Za-z0-9_]*' "${compose_path}" 2>/dev/null | cut -c3- | sort -u); do
    case "${name}" in
      COMPOSER_*|HOME|USER|PATH|PWD|SHELL|TERM|HOSTNAME|UID|GID) continue ;;
    esac
    case ",${secret_keys}," in
      *",${name},"*) continue ;;
    esac
    case " ${shell_only} " in
      *" ${name} "*) continue ;;
    esac
    if [[ -n "${!name+x}" ]]; then
      shell_only="${shell_only:+${shell_only} }${name}"
    fi
  done
done
if [[ -n "${shell_only}" ]]; then
  echo "Warning: ${shell_only// /, } set in this shell, not in ${secret_source:-a secrets file}: Composer reads Compose variables from the secrets file only, so this run does not use the shell's value. Put it in ${secret_source:-.secrets/.env} to use it." >&2
fi

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
    "${resolver}" update self --pin || {
      echo "The Composer pin could not be resolved with ${resolver}. If it printed only a usage line, that release predates this route: run './start.sh agent update', which moves the pin with the resident pair." >&2
      return 1
    }
  read_composer_lock
  if [[ -z "${composer_lock_image}" ]]; then
    # Nothing to pin yet (composer said why): keep the deployer just installed.
    composer_self_image="${resolver}"
    return 0
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
  -e COMPOSER_HEALTH_SETTLE_SECONDS \
  -v "${script_dir}:${script_dir}" \
  -w "${script_dir}" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  "${composer_self_image}" "$@"
