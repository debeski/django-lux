from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import re
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import InvalidVersion, Version

from . import UPDATER_SCHEMA_VERSION, UpdaterError


PYPI_SIMPLE_URL = "https://pypi.org/simple/django-lux/"
PYPI_PROJECT_REPOSITORY = "https://github.com/debeski/django-lux"
PYPI_PROJECT_REPOSITORY_NAME = "debeski/django-lux"
# PyPI's integrity API exposes the configured GitHub workflow as its basename,
# even though the trusted-publisher repository path is .github/workflows/release.yml.
PYPI_RELEASE_WORKFLOW = "release.yml"
ALLOWED_DOWNLOAD_HOSTS = frozenset({"pypi.org", "files.pythonhosted.org"})
MAX_INDEX_BYTES = 4 * 1024 * 1024
MAX_WHEEL_BYTES = 64 * 1024 * 1024
MANIFEST_PATH = "dlux/release-manifest.json"


@dataclass(frozen=True)
class ReleaseCandidate:
    version: str
    filename: str
    url: str
    sha256: str
    requires_python: str = ""

    def as_dict(self):
        return asdict(self)


def _validated_https_url(url, *, allowed_hosts=ALLOWED_DOWNLOAD_HOSTS):
    parsed = urlparse(str(url or ""))
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise UpdaterError("The update source returned an unapproved download URL.")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise UpdaterError("The update source returned an unsafe download URL.")
    return parsed.geturl()


def _read_bounded(response, limit):
    declared = response.headers.get("Content-Length")
    if declared:
        try:
            if int(declared) > limit:
                raise UpdaterError("The update response is larger than the allowed limit.")
        except ValueError:
            pass
    payload = response.read(limit + 1)
    if len(payload) > limit:
        raise UpdaterError("The update response is larger than the allowed limit.")
    return payload


def fetch_simple_index(*, opener=urllib.request.urlopen):
    request = urllib.request.Request(
        PYPI_SIMPLE_URL,
        headers={
            "Accept": "application/vnd.pypi.simple.v1+json",
            "User-Agent": "django-lux-updater/1",
        },
    )
    try:
        with opener(request, timeout=20) as response:
            _validated_https_url(response.geturl())
            payload = _read_bounded(response, MAX_INDEX_BYTES)
    except UpdaterError:
        raise
    except Exception as exc:
        raise UpdaterError("Could not reach the official PyPI update index.") from exc
    try:
        result = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdaterError("PyPI returned an invalid update index.") from exc
    if not isinstance(result, dict) or not isinstance(result.get("files"), list):
        raise UpdaterError("PyPI returned an incomplete update index.")
    return result


def select_latest_candidate(index, current_version, skip_versions=None):
    try:
        current = Version(str(current_version))
    except InvalidVersion as exc:
        raise UpdaterError("The installed DjangoLux version is invalid.") from exc

    # Versions the admin permanently skipped are never offered; compared on the
    # canonical Version so "1.4.7"/"v1.4.7"/"1.4.7.0" all match.
    skip = set()
    for raw in (skip_versions or []):
        try:
            skip.add(Version(str(raw).lstrip("vV")))
        except InvalidVersion:
            continue

    candidates = []
    for item in index.get("files", []):
        if not isinstance(item, dict) or item.get("yanked"):
            continue
        filename = str(item.get("filename") or "")
        try:
            distribution, version, _build, tags = parse_wheel_filename(filename)
        except Exception:
            continue
        if canonicalize_name(distribution) != "django-lux":
            continue
        if version.is_prerelease or version.is_devrelease or version <= current:
            continue
        if version in skip:
            continue
        if {str(tag) for tag in tags} != {"py3-none-any"}:
            continue
        hashes = item.get("hashes") if isinstance(item.get("hashes"), dict) else {}
        digest = str(hashes.get("sha256") or "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            continue
        url = _validated_https_url(item.get("url"))
        if unquote(urlparse(url).path.rsplit("/", 1)[-1]) != filename:
            continue
        candidates.append((version, ReleaseCandidate(
            version=str(version),
            filename=filename,
            url=url,
            sha256=digest,
            requires_python=str(item.get("requires-python") or ""),
        )))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def download_wheel(candidate, destination, *, opener=urllib.request.urlopen):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(candidate.url, headers={"User-Agent": "django-lux-updater/1"})
    try:
        with opener(request, timeout=60) as response:
            _validated_https_url(response.geturl())
            payload = _read_bounded(response, MAX_WHEEL_BYTES)
    except UpdaterError:
        raise
    except Exception as exc:
        raise UpdaterError("Could not download the DjangoLux update wheel.") from exc
    actual = hashlib.sha256(payload).hexdigest()
    if actual != candidate.sha256:
        raise UpdaterError("The downloaded wheel does not match PyPI's SHA-256 digest.")
    temporary = destination.with_name(f".{destination.name}.part")
    temporary.write_bytes(payload)
    temporary.replace(destination)
    return destination


def verify_pypi_attestation(candidate, *, runner=subprocess.run, opener=urllib.request.urlopen):
    if importlib.util.find_spec("pypi_attestations") is None:
        raise UpdaterError("PyPI attestation verification is unavailable in this project image.")
    try:
        completed = runner(
            [
                sys.executable,
                "-m",
                "pypi_attestations",
                "verify",
                "pypi",
                "--repository",
                PYPI_PROJECT_REPOSITORY,
                candidate.url,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as exc:
        raise UpdaterError("Could not verify the wheel's PyPI attestation.") from exc
    if completed.returncode != 0:
        raise UpdaterError("The wheel's PyPI Trusted Publisher attestation is invalid.")
    provenance_url = (
        "https://pypi.org/integrity/django-lux/"
        f"{quote(candidate.version, safe='')}/{quote(candidate.filename, safe='')}/provenance"
    )
    try:
        request = urllib.request.Request(
            provenance_url,
            headers={"Accept": "application/vnd.pypi.integrity.v1+json"},
        )
        with opener(request, timeout=20) as response:
            _validated_https_url(response.geturl())
            provenance = json.loads(_read_bounded(response, MAX_INDEX_BYTES).decode("utf-8"))
        bundles = provenance.get("attestation_bundles")
        if not isinstance(bundles, list) or not bundles:
            raise ValueError("missing attestation bundles")
        for bundle in bundles:
            publisher = bundle.get("publisher") if isinstance(bundle, dict) else None
            if not isinstance(publisher, dict):
                raise ValueError("missing publisher")
            if (
                publisher.get("kind") != "GitHub"
                or publisher.get("repository") != PYPI_PROJECT_REPOSITORY_NAME
                or publisher.get("workflow") != PYPI_RELEASE_WORKFLOW
            ):
                raise ValueError("unexpected publisher identity")
    except Exception as exc:
        raise UpdaterError(
            "The wheel attestation does not match the official DjangoLux release workflow."
        ) from exc
    return True


def inspect_wheel(wheel_path):
    try:
        with zipfile.ZipFile(wheel_path) as archive:
            manifest = json.loads(archive.read(MANIFEST_PATH).decode("utf-8"))
            metadata_name = next(
                name for name in archive.namelist()
                if name.endswith(".dist-info/METADATA") and "/" in name
            )
            metadata = BytesParser().parsebytes(archive.read(metadata_name))
    except (KeyError, StopIteration, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdaterError("The wheel is missing valid DjangoLux release metadata.") from exc
    return manifest, metadata


def validate_release_manifest(manifest, expected_version):
    if not isinstance(manifest, dict):
        raise UpdaterError("The release manifest must be a JSON object.")
    required = {
        "schema_version", "version", "inline_safe", "minimum_updater_schema",
        "migration_policy", "summary", "release_url",
    }
    if required.difference(manifest):
        raise UpdaterError("The release manifest is missing required fields.")
    if type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1:
        raise UpdaterError("The release manifest schema is not supported.")
    if not isinstance(manifest.get("version"), str):
        raise UpdaterError("The release manifest has an invalid version field.")
    try:
        if Version(str(manifest.get("version"))) != Version(str(expected_version)):
            raise UpdaterError("The release manifest version does not match the wheel.")
    except InvalidVersion as exc:
        raise UpdaterError("The release manifest contains an invalid version.") from exc
    if not isinstance(manifest.get("inline_safe"), bool):
        raise UpdaterError("The release manifest has an invalid inline-safe flag.")
    if (
        type(manifest.get("minimum_updater_schema")) is not int
        or manifest.get("minimum_updater_schema") < 1
    ):
        raise UpdaterError("The release manifest has an invalid updater schema requirement.")
    if manifest.get("migration_policy") not in {"backward_compatible", "image_rebuild"}:
        raise UpdaterError("The release manifest has an invalid migration policy.")
    if not isinstance(manifest.get("summary"), str) or not isinstance(manifest.get("release_url"), str):
        raise UpdaterError("The release manifest has invalid display metadata.")
    release_url = urlparse(str(manifest.get("release_url") or ""))
    expected_release_path = f"/debeski/django-lux/releases/tag/v{Version(str(expected_version))}"
    if (
        release_url.scheme != "https"
        or release_url.hostname != "github.com"
        or release_url.port not in (None, 443)
        or release_url.username
        or release_url.password
        or release_url.path.rstrip("/") != expected_release_path
        or release_url.query
        or release_url.fragment
    ):
        raise UpdaterError("The release manifest contains an invalid release URL.")
    manifest["summary"] = manifest.get("summary", "")[:1000]
    # Optional curated release highlights (short bullet points shown in the
    # update modal, so it doesn't render the whole prose summary and grow tall).
    # Fully optional + back-compatible: older manifests omit it; older updaters
    # ignore it. Normalize defensively — cap count and per-line length.
    highlights = manifest.get("highlights")
    if highlights is not None:
        if not isinstance(highlights, list):
            raise UpdaterError("The release manifest has invalid highlights.")
        cleaned = []
        for item in highlights[:8]:
            text = str(item or "").strip()[:160]
            if text:
                cleaned.append(text)
        manifest["highlights"] = cleaned
    # Optional inline-update floor: the most recent version that required a
    # project image rebuild. An inline (Python-only) update is only safe onto a
    # baked image at or above this version, so a box several releases behind
    # cannot skip an image-required release by jumping to a later inline-safe
    # one. Absent = no floor (older manifests, or releases with no image
    # dependency). Validated as a canonical PEP 440 version; empty drops it.
    image_baseline = manifest.get("image_baseline")
    if image_baseline is not None:
        baseline_text = str(image_baseline).strip()
        if not baseline_text:
            manifest.pop("image_baseline", None)
        else:
            try:
                Version(baseline_text)
            except InvalidVersion as exc:
                raise UpdaterError("The release manifest has an invalid image baseline.") from exc
            manifest["image_baseline"] = baseline_text
    return manifest


def _check_dependencies(metadata):
    failures = []
    for raw in metadata.get_all("Requires-Dist", []):
        try:
            requirement = Requirement(raw)
        except Exception:
            failures.append("The release contains invalid dependency metadata.")
            continue
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        try:
            installed = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            failures.append(f"Required dependency {requirement.name} is not installed.")
            continue
        if requirement.specifier and not requirement.specifier.contains(installed, prereleases=True):
            failures.append(
                f"Installed {requirement.name} {installed} does not satisfy {requirement.specifier}."
            )
    return failures


def _normalized_requirements(metadata):
    normalized = set()
    for raw in metadata.get_all("Requires-Dist", []) or []:
        requirement = Requirement(raw)
        normalized.add((
            canonicalize_name(requirement.name),
            str(requirement.specifier),
            tuple(sorted(requirement.extras)),
            str(requirement.marker or ""),
            str(requirement.url or ""),
        ))
    return normalized


def _check_dependency_contract(metadata):
    try:
        installed_metadata = importlib.metadata.metadata("django-lux")
        current = _normalized_requirements(installed_metadata)
        candidate = _normalized_requirements(metadata)
    except Exception:
        return ["The installed DjangoLux dependency contract could not be verified."]
    if candidate != current:
        return ["This release changes the DjangoLux dependency contract."]
    return []


def assess_wheel(candidate, wheel_path, baked_version=None):
    manifest, metadata = inspect_wheel(wheel_path)
    manifest = validate_release_manifest(manifest, candidate.version)
    reasons = []
    if not manifest["inline_safe"]:
        reasons.append("This release requires a project image rebuild.")
    # Enforce the inline-update floor. Fails closed: when a release declares an
    # image baseline, an inline update is refused unless the baked image is a
    # comparable version at or above that baseline. This stops a box that is
    # several releases behind from skipping an image-required release by jumping
    # straight to a later inline-safe one.
    baseline = manifest.get("image_baseline")
    if baseline:
        baked_text = str(baked_version or "").strip()
        image_message = f"This release needs the v{baseline} project image; update the project image first."
        try:
            if not baked_text or Version(baked_text) < Version(baseline):
                reasons.append(image_message)
        except InvalidVersion:
            reasons.append(image_message)
    if manifest["minimum_updater_schema"] > UPDATER_SCHEMA_VERSION:
        reasons.append("This release requires a newer updater bootstrap.")
    if manifest["migration_policy"] != "backward_compatible":
        reasons.append("This release contains migrations that are not inline-safe.")
    requires_python = candidate.requires_python or str(metadata.get("Requires-Python") or "")
    if requires_python and not SpecifierSet(requires_python).contains(
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        prereleases=True,
    ):
        reasons.append(f"This release requires Python {requires_python}.")
    reasons.extend(_check_dependency_contract(metadata))
    reasons.extend(_check_dependencies(metadata))
    reason = " ".join(reasons)
    if reason:
        reason = f"Project image rebuild required. {reason}"
    return {
        "compatible": not reasons,
        "reason": reason,
        "manifest": manifest,
        "requires_python": requires_python,
    }


def validate_local_release_manifest(package_root=None):
    # The release manifest is the single source of truth for the version (the
    # package version derives from it), so validate it against its own version.
    # This still enforces schema, types, and that release_url matches the version.
    package_root = Path(package_root or Path(__file__).resolve().parents[1])
    manifest = json.loads((package_root / "release-manifest.json").read_text(encoding="utf-8"))
    version = str(manifest.get("version") or "").strip()
    return validate_release_manifest(manifest, version)
