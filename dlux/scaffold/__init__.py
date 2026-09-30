"""Project and app scaffolding for ``python -m dlux``.

Facade over the scaffold package: every name importable from the old
`dlux.scaffold` module is re-exported here.

* :mod:`~dlux.scaffold.project` — ``startproject``
* :mod:`~dlux.scaffold.app` — ``startapp`` and its project registration
* :mod:`~dlux.scaffold._shared` — paths, prompts, template rendering
"""

from ._shared import (  # noqa: F401
    PACKAGE_ROOT,
    TEMPLATES_ROOT,
    ScaffoldError,
    _normalize_identifier,
    _normalize_repo_slug,
    _prepare_root,
    _prompt,
    _render_template,
    _resolve_project_files,
    _write_rendered,
    split_image_reference,
)
from .app import (  # noqa: F401
    _camel_case,
    _ensure_url_imports,
    _register_app,
    _upsert_list_block,
    create_app,
)
from .project import create_project  # noqa: F401
