"""Project and app scaffolding for ``python -m dlux``.

Facade over the scaffold package: every name importable from the old
`dlux.scaffold` module is re-exported here.

* :mod:`~dlux.scaffold.project` — ``startproject``
* :mod:`~dlux.scaffold.app` — ``startapp`` and its project registration
* :mod:`~dlux.scaffold.legacy` — the deprecated ``enable_updater`` /
  ``enable_agent`` Compose migrations, removed wholesale in 1.9.0
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
from .legacy import (  # noqa: F401
    POST_START_LABEL,
    POST_START_MIGRATOR,
    UPDATER_COMPOSE_END,
    UPDATER_COMPOSE_START,
    _bootstrap_backup_root,
    _compose_service,
    _enable_updater_compose,
    _enable_updater_dev_compose,
    _enable_updater_nginx,
    _migrate_manage_py,
    _migrate_smtp_relay_compose,
    _replace_compose_service,
    _replace_once,
    _updater_service_block,
    enable_agent,
    enable_updater,
)
from .project import create_project  # noqa: F401
