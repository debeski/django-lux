# Fundemental imports
from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import FieldDoesNotExist
from django.utils.module_loading import import_string
from django.views.generic.detail import DetailView
from django_tables2 import SingleTableView
from django_filters.views import FilterView

# Project imports
from ..utils import get_user_scope, is_scope_enabled, translate_activity_log_model_name, user_can_view_activity_log
from ..translations import get_strings


# Activity Log View — Paginated, filterable list of user activity with scope support
class UserActivityLogView(LoginRequiredMixin, UserPassesTestMixin, FilterView, SingleTableView):
    model = apps.get_model('microsys', 'UserActivityLog')
    table_class = import_string('microsys.tables.UserActivityLogTable')
    filterset_class = import_string('microsys.filters.UserActivityLogFilter')
    template_name = "microsys/activitylog/activity_log.html"

    def get_paginate_by(self, queryset):
        # Let django-tables2 own pagination. FilterView/ListView pagination here
        # would slice object_list first, then the table would try to paginate the
        # sliced subset again, which breaks page > 1 when per_page is smaller
        # than the full result count.
        return None

    def test_func(self):
        return user_can_view_activity_log(self.request.user)
    
    def get_queryset(self):
        # Order by timestamp descending by default
        # Using .all() ensures we use the ScopedManager which handles scope filtering automatically.
        # exclude_log_noise() drops historical presence/device tracking rows (these models are no
        # longer logged at all — see signals.EXCLUDED_MODELS — but old rows may still exist).
        from ..reports import exclude_log_noise
        qs = exclude_log_noise(
            super().get_queryset()
            .select_related('created_by__profile__scope')
        ).order_by('-created_at')
        
        # When scopes are disabled, defer the scope column to avoid loading unused data
        if not is_scope_enabled():
            try:
                self.model._meta.get_field('scope')
                qs = qs.defer('scope')
            except FieldDoesNotExist:
                pass
                
        if not self.request.user.is_superuser:
            # Still exclude superuser actions if non-superuser, 
            # as these are often sensitive system-level configurations.
            qs = qs.exclude(created_by__is_superuser=True)
            
        return qs

    def get_table(self, **kwargs):
        table = super().get_table(**kwargs)
        if not is_scope_enabled():
            table.exclude = ('scope',)
        elif get_user_scope(self.request.user):
            table.exclude = ('scope',)
        return table

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        kwargs['translations'] = get_strings()
        kwargs['request'] = self.request
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Standardize Filter Layout
        from ..utils import setup_filter_helper
        activity_filter = self.get_filterset(self.filterset_class)
        setup_filter_helper(activity_filter, self.request)

        context['filter'] = activity_filter
        return context



# Activity Log View — Detail modal for a single activity log entry
class ActivityLogDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = apps.get_model('microsys', 'UserActivityLog')
    context_object_name = 'log'
    template_name = 'microsys/activitylog/activity_log_detail_modal.html'

    def test_func(self):
        return user_can_view_activity_log(self.request.user)

    def get_queryset(self):
        qs = super().get_queryset().select_related('created_by__profile__scope')
        if not self.request.user.is_superuser:
            qs = qs.exclude(created_by__is_superuser=True)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        log = self.object
        
        # Attempt to resolve the related object
        related_object = None
        if log.model_name and log.object_id:
            try:
                # Try to find model by name
                target_model = None
                # Check for explicit app.model format
                if '.' in log.model_name:
                    try:
                        target_model = apps.get_model(log.model_name)
                    except LookupError:
                        pass
                
                # If not found, iterate all models to match verbose_name or object_name
                if not target_model:
                    import unicodedata
                    def normalize(s):
                        return unicodedata.normalize('NFKD', s).casefold() if s else ""
                        
                    log_model_norm = normalize(log.model_name)
                    
                    for model in apps.get_models():
                        if normalize(model._meta.verbose_name) == log_model_norm or \
                           normalize(model._meta.object_name) == log_model_norm:
                            target_model = model
                            break
                            
                if target_model:
                    try:
                        related_object = target_model._default_manager.get(pk=log.object_id)
                    except target_model.DoesNotExist:
                        pass
            except Exception:
                pass
                
        context['related_object'] = related_object
        raw_model_name = related_object._meta.verbose_name if related_object else (log.model_name or "-")
        context['related_object_model'] = translate_activity_log_model_name(raw_model_name, strings=get_strings())
        return context
