"""Dlux reports.

Facade over the reports package: every name importable from the old
`dlux.reports` module is re-exported here.
"""

from ._shared import (  # noqa: F401
    REPORT_ACTIVITY_CATEGORY,
    logger,
)
from .config import (  # noqa: F401
    LOG_NOISE_MODEL_NAMES,
    REPORT_ENTRIES_ROW_LIMIT,
    _normalized_config_set,
    _reports_config,
    exclude_log_noise,
    get_report_entries_row_limit,
    get_reports_overview_cache_seconds,
)
from .windows import (  # noqa: F401
    REPORT_WINDOWS,
    _parse_report_date,
    _report_period_details,
    _week_start_index,
    get_previous_period_bounds,
    get_previous_week_bounds,
    get_report_window_bounds,
    normalize_backup_window,
    normalize_report_window,
)
from .eligibility import (  # noqa: F401
    _CELERY_REPORT_APP_LABELS,
    _CELERY_REPORT_MODEL_KEYS,
    _DLUX_REPORT_EXCLUDED_KEYS,
    _EXCLUDED_APP_LABELS,
    _is_celery_report_identity,
    _is_celery_report_model,
    _model_is_section,
    _model_keys,
    get_report_eligible_models,
    is_report_eligible_activity_model_name,
    is_report_eligible_model,
)
from .queries import (  # noqa: F401
    _BACKUP_TIMESTAMP_CANDIDATES,
    _aggregation_queryset,
    _backup_model_queryset,
    _backup_timestamp_field,
    _base_activity_queryset,
    _count_grouped,
    _iter_queryset_by_pk,
    _scope_model_queryset,
    _visible_user_queryset,
    activity_report_key,
    apply_report_scope,
    apply_report_window,
    filter_report_eligible_activity,
    get_visible_report_activity,
    log_report_key,
)
from .filters import (  # noqa: F401
    _apply_report_builder_filters,
    _filter_values,
    _report_filter_catalog,
)
from .overview import (  # noqa: F401
    REPORT_OVERVIEW_CACHE_SCHEMA_VERSION,
    _build_reports_overview_stats,
    _format_actions,
    _format_model_actions,
    _overview_cache_scope,
    _overview_stats_cache_key,
    _safe_cache_get,
    _safe_cache_set,
    build_activity_windows,
    build_reports_overview,
)
from .charts import (  # noqa: F401
    REPORT_CHART_CATEGORICAL_TOP_N,
    REPORT_CHART_TOP_N,
    _chart_series,
    build_report_chart_data,
)
from .export import (  # noqa: F401
    _EXPORT_SENSITIVE_FIELD_PARTS,
    _XLSX_ILLEGAL_CHARS,
    _XLSX_MAX_CELL_LENGTH,
    _XLSX_MAX_COLUMN_WIDTH,
    _XLSX_SHEET_TITLE_INVALID,
    _configured_export_exclusions,
    _entry_export_queryset,
    _export_field_value,
    _is_sensitive_export_field,
    _models_for_report_criteria,
    _unique_sheet_title,
    _xlsx_cell_value,
    _xlsx_text,
    build_model_entries_xlsx,
    get_report_entry_fields,
)
# Moved to dlux.utils.archive (shared with dlux.backup); re-exported so the
# historical `from dlux.reports import ...` surface is unchanged.
from ..utils.archive import (  # noqa: F401
    _CursorlessJSONSerializer,
    _model_natural_key_fields,
    _safe_archive_segment,
    stream_model_into_zip,
)
from .archive import (  # noqa: F401
    backup_record_folder,
    build_relation_schema,
    REPORT_ZIP_WORKBOOK_NAME,
    _BACKUP_LABEL_FIELD_CANDIDATES,
    _backup_label_field,
    _prune_report_backups,
    _report_backup_model,
    build_backup_zip,
    dispatch_report_backup,
    get_backup_storage_prefix,
    report_backup_celery_available,
    run_report_backup,
    write_backup_zip,
)

__all__ = [
    'LOG_NOISE_MODEL_NAMES',
    'REPORT_ACTIVITY_CATEGORY',
    'REPORT_CHART_CATEGORICAL_TOP_N',
    'REPORT_CHART_TOP_N',
    'REPORT_ENTRIES_ROW_LIMIT',
    'REPORT_OVERVIEW_CACHE_SCHEMA_VERSION',
    'REPORT_WINDOWS',
    'REPORT_ZIP_WORKBOOK_NAME',
    'activity_report_key',
    'apply_report_scope',
    'apply_report_window',
    'backup_record_folder',
    'build_activity_windows',
    'build_backup_zip',
    'build_model_entries_xlsx',
    'build_relation_schema',
    'build_report_chart_data',
    'build_reports_overview',
    'dispatch_report_backup',
    'exclude_log_noise',
    'filter_report_eligible_activity',
    'get_backup_storage_prefix',
    'get_previous_period_bounds',
    'get_previous_week_bounds',
    'get_report_eligible_models',
    'get_report_entries_row_limit',
    'get_report_entry_fields',
    'get_report_window_bounds',
    'get_reports_overview_cache_seconds',
    'get_visible_report_activity',
    'is_report_eligible_activity_model_name',
    'is_report_eligible_model',
    'log_report_key',
    'logger',
    'normalize_backup_window',
    'normalize_report_window',
    'report_backup_celery_available',
    'run_report_backup',
    'stream_model_into_zip',
    'write_backup_zip',
]
