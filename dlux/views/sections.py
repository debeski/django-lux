import json
import inspect
import logging

from django import forms
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.views import View
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from django_tables2 import RequestConfig

from ..notifications import notify
from ..utils import (
    is_scope_enabled,
    discover_section_models,
    resolve_model_by_name,
    resolve_form_class_for_model,
    has_related_records,
    collect_related_objects,
    get_model_classes,
    _get_m2m_through_defaults,
    _create_minimal_instance_from_post,
    can_manage_target_user,
    get_user_scope,
    setup_filter_helper,
    has_submit_button,
    user_has_model_permission,
    user_has_section_manage_permission,
    user_has_section_view_permission,
    resolve_detail_field_label,
)
from ..system.constants import SETUP_STEP_COUNT
from ..translations import get_strings

User = get_user_model()
logger = logging.getLogger('dlux')


def _section_permission_denied(*, json_response=False):
    if json_response:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    raise PermissionDenied


def _notify_section_error(request, key, action):
    s = get_strings()
    notify.error(
        s.get(key),
        request=request,
        action=action,
        category='sections',
        metadata={'message_key': key},
    )


def _normalize_section_model_token(value):
    raw = str(value or '').strip().lower()
    if not raw:
        return ''
    return raw


def _scope_filtered_modal_queryset(model, user):
    queryset = model._default_manager.all()
    if not is_scope_enabled() or getattr(user, 'is_superuser', False):
        return queryset
    try:
        model._meta.get_field('scope')
    except Exception:
        return queryset
    user_scope = get_user_scope(user)
    if user_scope is None:
        return queryset.none()
    return queryset.filter(scope=user_scope)


def _definition_matches_model_token(definition, token):
    if not definition or not token:
        return False
    model = definition['model']
    candidates = {
        _normalize_section_model_token(definition.get('model_name')),
        _normalize_section_model_token(model._meta.label_lower),
        _normalize_section_model_token(model.__name__),
    }
    return token in candidates


def _get_section_registry():
    sections_by_token = {}
    subsections_by_token = {}
    subsection_fields_by_parent = {}

    for definition in discover_section_models(app_name=None, include_children=False):
        model = definition['model']
        section_tokens = {
            _normalize_section_model_token(definition['model_name']),
            _normalize_section_model_token(model._meta.label_lower),
            _normalize_section_model_token(model.__name__),
        }
        for token in section_tokens:
            if token:
                sections_by_token[token] = definition

        field_map = {}
        for subsection in definition.get('subsections', []):
            child_model = subsection['model']
            child_tokens = {
                _normalize_section_model_token(subsection['model_name']),
                _normalize_section_model_token(child_model._meta.label_lower),
                _normalize_section_model_token(child_model.__name__),
            }
            for token in child_tokens:
                if token:
                    subsections_by_token.setdefault(token, subsection)
            field_map[subsection['related_field']] = subsection

        for token in section_tokens:
            if token:
                subsection_fields_by_parent[token] = field_map

    return sections_by_token, subsections_by_token, subsection_fields_by_parent


def _resolve_allowed_section_definition(model_name):
    token = _normalize_section_model_token(model_name)
    sections_by_token, _, _ = _get_section_registry()
    return sections_by_token.get(token)


def _resolve_allowed_subsection_definition(model_name, parent_model_name=None, parent_field=None):
    token = _normalize_section_model_token(model_name)
    if not token:
        return None

    sections_by_token, subsections_by_token, subsection_fields_by_parent = _get_section_registry()
    parent_token = _normalize_section_model_token(parent_model_name)
    if parent_token:
        parent_definition = sections_by_token.get(parent_token)
        if not parent_definition:
            return None

        field_map = subsection_fields_by_parent.get(parent_token, {})
        if parent_field:
            subsection = field_map.get(parent_field)
            if subsection and _definition_matches_model_token(subsection, token):
                return subsection
            return None

        for subsection in field_map.values():
            if _definition_matches_model_token(subsection, token):
                return subsection
        return None

    return subsections_by_token.get(token)


# Section Management — Main dynamic CRUD view for all section and subsection models
@login_required
def core_models_view(request):
    """
    Manages section models dynamically discovered from the app.
    Uses ?model= query param with session fallback for tab persistence.
    """
    if request.method == 'POST':
        if not user_has_section_manage_permission(request.user):
            return _section_permission_denied()
    elif not user_has_section_view_permission(request.user):
        return _section_permission_denied()

    section_models = discover_section_models(app_name=None, include_children=False)
    
    models_map = {sm['model_name']: sm for sm in section_models}
    
    default_model = section_models[0]['model_name'] if section_models else None
    model_param = request.GET.get('model') or request.session.get('last_active_model', default_model)
    
    if model_param not in models_map:
        model_param = default_model
    
    if not model_param or not models_map:
        return render(request, 'dlux/sections/manage_sections.html', {
            'error': 'لا توجد موديلات متاحة.',
        })
    
    # Store in session only when user explicitly changes tab via GET param
    if request.GET.get('model'):
        request.session['last_active_model'] = model_param
    
    selected_data = models_map[model_param]
    selected_model = selected_data['model']
    ui_strings = get_strings()
    save_label = ui_strings.get('save', 'Save')
    cancel_label = ui_strings.get('cancel', 'Cancel')
    
    FormClass = selected_data['form_class']
    TableClass = selected_data['table_class']
    FilterClass = selected_data['filter_class']
    
    if not FormClass or not TableClass:
        return render(request, 'dlux/sections/manage_sections.html', {
            'error': 'هناك خطأ في تحميل المودل.',
            'active_model': model_param,
            'models': [{'name': sm['model_name'], 'ar_names': sm['verbose_name_plural'], 'count': sm['model'].objects.count()} for sm in section_models],
        })
    
    instance_id = request.GET.get('id')
    instance = None
    if instance_id:
        try:
            instance = selected_model._default_manager.get(pk=instance_id)
        except selected_model.DoesNotExist:
            instance = None

    # Build a cancel URL that preserves current filters/sort but drops the edit ID
    cancel_url = None
    if 'id' in request.GET:
        params = request.GET.copy()
        params.pop('id', None)
        cancel_url = reverse('manage_sections')
        if params:
            cancel_url = f"{cancel_url}?{params.urlencode()}"
    
    subsection_field_names = set()

    form = FormClass(request.POST or None, instance=instance)
    # Auto-create a crispy helper if the form doesn't define one (marks it for layout generation later)
    if not hasattr(form, "helper") or form.helper is None:
        form.helper = FormHelper()
        form.helper.form_tag = False
        form._auto_helper = True
    else:
        form.helper.form_tag = False
        if not getattr(form.helper, "inputs", None):
            form.helper.add_input(Submit("submit", save_label, css_class="btn btn-primary rounded-pill"))

    # Soft-deleted rows are handled by the scoped manager itself: it includes
    # them transparently while a superadmin has the "show soft-deleted" review
    # mode on, and hides them otherwise. No view-level branch needed.
    queryset = selected_model._default_manager.all()
    if FilterClass:
        filter_obj = FilterClass(request.GET or None, queryset=queryset)
        setup_filter_helper(filter_obj, request)
        queryset = filter_obj.qs
    
    # Introspect table __init__ to see if it accepts model_name kwarg or **kwargs
    try:
        sig = inspect.signature(TableClass.__init__)
        params = sig.parameters
        accepts_model_name = (
            "model_name" in params
            or any(p.kind == p.VAR_KEYWORD for p in params.values())
        )
    except (TypeError, ValueError):
        accepts_model_name = False

    # Pass model_name to constructor if supported, otherwise inject it as an attribute
    translations = ui_strings
    if accepts_model_name:
        table = TableClass(queryset, model_name=model_param, translations=translations, request=request)
    else:
        table = TableClass(queryset, translations=translations, request=request)
        if not hasattr(table, "model_name"):
            table.model_name = model_param
    RequestConfig(request).configure(table)

    # Merge 'scope' into existing excludes without duplicates for non-superusers
    if is_scope_enabled() and not request.user.is_superuser:
        existing_exclude = getattr(table, "exclude", None) or ()
        merged = list(dict.fromkeys(list(existing_exclude) + ["scope"]))
        table.exclude = tuple(merged)
    
    # Handle Subsections (Child Models)
    subsection_forms = []
    subsection_selects = []
    for sub in selected_data.get('subsections', []):
        child_model_name = sub['model_name']
        related_field = sub['related_field']
        child_model = sub['model']

        if related_field not in form.fields:
            # Use the normal manager which applies scope filtering when enabled
            form.fields[related_field] = forms.ModelMultipleChoiceField(
                queryset=child_model._default_manager.all(),
                required=False,
                label=sub['verbose_name_plural'],
                widget=forms.CheckboxSelectMultiple(),
            )
        else:
            # Field exists - ensure it has the right queryset and widget
            form.fields[related_field].queryset = child_model._default_manager.all()
            form.fields[related_field].widget = forms.CheckboxSelectMultiple()
        
        # Sync widget choices with the field's queryset so CheckboxSelectMultiple renders correctly
        form.fields[related_field].widget.choices = form.fields[related_field].choices

        form.fields[related_field].modal_target = f"addSubsectionModal_{child_model_name}"

        if instance:
            try:
                rel_manager = getattr(instance, related_field, None)
                if rel_manager is not None:
                    form.fields[related_field].initial = list(
                        rel_manager.values_list('pk', flat=True)
                    )
            except Exception:
                pass

        # Determine which subsection items are "locked" (have dependencies elsewhere)
        locked_ids = []
        if instance:
            try:
                rel_manager = getattr(instance, related_field, None)
                if rel_manager is not None:
                    # Get the reverse accessor name so we can ignore the parent→child M2M itself
                    accessor = None
                    try:
                        field_obj = selected_model._meta.get_field(related_field)
                        accessor = field_obj.remote_field.get_accessor_name()
                    except Exception:
                        accessor = None

                    ignore = [accessor] if accessor else []
                    for child in rel_manager.all():
                        if has_related_records(child, ignore_relations=ignore):
                            locked_ids.append(str(child.pk))
            except Exception:
                locked_ids = []

        subsection_selects.append({
            'field': form[related_field],
            'locked_ids': locked_ids,
            'parent_model': model_param,
            'parent_id': instance.pk if instance else '',
            'parent_field': related_field,
            'child_model': child_model_name,
            'add_url': reverse('add_subsection'),
            'edit_url_template': reverse('edit_subsection', args=[0]).replace('/0/', '/{id}/'),
            'delete_url_template': reverse('delete_subsection', args=[0]).replace('/0/', '/{id}/'),
        })
        subsection_field_names.add(related_field)
        
        ChildForm = sub['form_class']
        child_form_instance = ChildForm()
        
        # Override form action to generic add_subsection view
        target_url = reverse('add_subsection')
        if not hasattr(child_form_instance, 'helper') or child_form_instance.helper is None:
             child_form_instance.helper = FormHelper()
             child_form_instance.helper.form_tag = True
        else:
             child_form_instance.helper.form_tag = True
        child_form_instance.helper.form_action = f"{target_url}?model={child_model_name}&parent={model_param}"
        if not getattr(child_form_instance.helper, "inputs", None):
             child_form_instance.helper.add_input(Submit("submit", save_label, css_class="btn btn-primary rounded-pill"))

        subsection_forms.append({
            'name': child_model_name,
            'verbose_name': sub['verbose_name'],
            'form': child_form_instance
        })

    # Handle POST (after subsection fields are injected)
    if request.method == 'POST':
        if form.is_valid():
            saved_instance = form.save(commit=False)
            saved_instance._dlux_notify_source = 'generic_crud'
            saved_instance._dlux_notify_surface = 'sections'
            saved_instance._dlux_notify_route = request.resolver_match.url_name if request.resolver_match else ''
            saved_instance.save()
            if hasattr(form, 'save_m2m'):
                form.save_m2m()
            # Manually set M2M subsection relations (with through_defaults for scoped through tables)
            for field_name in subsection_field_names:
                if field_name in form.cleaned_data:
                    try:
                        rel_manager = getattr(saved_instance, field_name)
                        through_defaults = _get_m2m_through_defaults(selected_model, field_name, request)
                        if through_defaults:
                            rel_manager.set(form.cleaned_data[field_name], through_defaults=through_defaults)
                        else:
                            rel_manager.set(form.cleaned_data[field_name])
                    except Exception:
                        pass
            return redirect('manage_sections')

    # For auto-generated helpers, build a custom 2-column layout with inline buttons
    if getattr(form, "_auto_helper", False):
        from crispy_forms.layout import Layout, Row, Column, Field, HTML, Div

        def build_form_actions_html(cancel_href=None):
            save_button = f"""
                <button type="submit" class="dlux-form-action dlux-form-action-primary" aria-label="{save_label}" title="{save_label}">
                    <span class="dlux-form-action-icon"><i class="bi bi-check-lg" aria-hidden="true"></i></span>
                    <span class="visually-hidden">{save_label}</span>
                </button>
            """

            if cancel_href:
                cancel_button = f"""
                    <a href="{cancel_href}" class="dlux-form-action dlux-form-action-neutral" aria-label="{cancel_label}" title="{cancel_label}">
                        <span class="dlux-form-action-icon"><i class="bi bi-x-lg" aria-hidden="true"></i></span>
                        <span class="visually-hidden">{cancel_label}</span>
                    </a>
                """
                return f'<div class="dlux-form-actions">{save_button}{cancel_button}</div>'

            return f'<div class="dlux-form-actions">{save_button}</div>'
        
        # Identify visible fields (excluding subsections which are handled separately)
        visible_fields = [
            f for f in form.fields 
            if f not in subsection_field_names 
            and not isinstance(form.fields[f].widget, forms.HiddenInput)
        ]
        
        layout_components = []
        
        hidden_fields = [
            f for f in form.fields 
            if isinstance(form.fields[f].widget, forms.HiddenInput)
        ]
        for hf in hidden_fields:
            layout_components.append(Field(hf))
            
        def chunked(iterable, n):
            return [iterable[i:i + n] for i in range(0, len(iterable), n)]
            
        field_chunks = chunked(visible_fields, 2)
        total_chunks = len(field_chunks)
        
        for i, chunk in enumerate(field_chunks):
            is_last_chunk = (i == total_chunks - 1)
            
            if is_last_chunk:
                row_content = []
                for field_name in chunk:
                    row_content.append(Column(Field(field_name), css_class="col"))
                
                buttons_html = build_form_actions_html(cancel_url)
                
                row_content.append(
                    Column(
                        HTML(buttons_html), 
                        css_class="col-auto align-self-end mb-3"
                    )
                )
                layout_components.append(Row(*row_content))
            else:
                row_content = [Column(Field(field_name), css_class="col-md-6") for field_name in chunk]
                layout_components.append(Row(*row_content))
                
        # If no visible fields but we have actions (rare edge case), just show buttons
        if not visible_fields:
            buttons_html = build_form_actions_html(cancel_url)
            layout_components.append(Row(Column(HTML(buttons_html), css_class="col-auto")))

        form.helper.layout = Layout(*layout_components)

    context = {
        'active_model': model_param,
        'models': [
            {
                'name': sm['model_name'], 
                'ar_names': sm['verbose_name_plural'],
                'count': sm['model']._default_manager.count()
            } 
            for sm in section_models
        ],
        'form': form,
        'filter': filter_obj,
        'table': table,
        'id': instance_id,
        'hide_form_buttons': getattr(form, "_auto_helper", False) or has_submit_button(form),
        'show_cancel': 'id' in request.GET, # Kept for other uses if any
        'cancel_url': cancel_url,
        'ar_name': selected_data['verbose_name'],
        'ar_names': selected_data['verbose_name_plural'],
        'subsection_forms': subsection_forms, # subsection forms for modals (kept outside main form)
        'subsection_selects': subsection_selects,
        'has_subsections': len(subsection_selects) > 0,
    }
    
    return render(request, 'dlux/sections/manage_sections.html', context)

# Section Management — AJAX: adds a new subsection (child model) via modal
@login_required
def add_subsection(request):
    """
    Generic view to handle adding a new Subsection (child model) via modal.
    Expects ?model=child_model_name&parent=parent_model_name
    """
    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'
    )

    if not user_has_section_manage_permission(request.user):
        return _section_permission_denied(
            json_response=is_ajax
        )

    child_model_name = request.GET.get('model')
    parent_model_name = request.GET.get('parent')
    parent_id = request.GET.get('parent_id')
    parent_field = request.GET.get('parent_field')
    
    if not child_model_name:
        _notify_section_error(request, 'err_subsection_id_missing', 'subsection_model_missing')
        return redirect('manage_sections')

    subsection_definition = _resolve_allowed_subsection_definition(
        child_model_name,
        parent_model_name=parent_model_name,
        parent_field=parent_field,
    )
    if not subsection_definition:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Subsection not found'}, status=404)
        _notify_section_error(request, 'err_subsection_not_found', 'subsection_not_found')
        return redirect('manage_sections')
    model = subsection_definition['model']
        
    # Resolve Form Class (consistent with discovery logic)
    form_class = resolve_form_class_for_model(model)
    
    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            instance._dlux_notify_source = 'generic_crud'
            instance._dlux_notify_surface = 'subsection_modal'
            instance._dlux_notify_route = request.resolver_match.url_name if request.resolver_match else ''
            instance._dlux_notify_flash = False
            # created_by/updated_by auto-populated by ScopedModel.save()
            instance.save()

            if parent_model_name and parent_id and parent_field:
                try:
                    parent_definition = _resolve_allowed_section_definition(parent_model_name)
                    if parent_definition:
                        parent_model = parent_definition['model']
                        parent_instance = parent_model._default_manager.get(pk=parent_id)
                        try:
                            rel_manager = getattr(parent_instance, parent_field)
                            through_defaults = _get_m2m_through_defaults(parent_model, parent_field, request)
                            if through_defaults:
                                rel_manager.add(instance, through_defaults=through_defaults)
                            else:
                                rel_manager.add(instance)
                        except Exception:
                            pass
                except Exception:
                    pass
            
            if is_ajax:
                return JsonResponse({'success': True, 'id': instance.pk, 'name': str(instance)})
                
            notify.success(f"تم إضافة {model._meta.verbose_name}: {instance}", request=request, obj=instance, action='subsection_create', category='sections', persist=False)
        else:
            if is_ajax:
                return JsonResponse({'success': False, 'error': form.errors.as_text()})
            notify.error(f"خطأ في إضافة {model._meta.verbose_name}.", request=request, action='subsection_create_invalid', category='sections')
    
    redirect_url = reverse('manage_sections')
    if parent_model_name:
        redirect_url += f"?model={parent_model_name}"
        
    return redirect(redirect_url)


# Section Management — AJAX: edits a subsection (child model) by pk
@login_required
def edit_subsection(request, pk):
    """
    Edit a subsection (child model) by pk.
    Expects ?model=child_model_name&parent=parent_model_name
    """
    if not user_has_section_manage_permission(request.user):
        return _section_permission_denied()

    child_model_name = request.GET.get('model', 'subaffiliate')
    parent_model_name = request.GET.get('parent', 'affiliate')
    
    subsection_definition = _resolve_allowed_subsection_definition(
        child_model_name,
        parent_model_name=parent_model_name,
    )
    if not subsection_definition:
        _notify_section_error(request, 'err_subsection_not_found', 'subsection_not_found')
        return redirect('manage_sections')
    model = subsection_definition['model']
    try:
        instance = model._default_manager.get(pk=pk)
    except model.DoesNotExist:
        _notify_section_error(request, 'err_subsection_not_found', 'subsection_not_found')
        return redirect('manage_sections')
    
    # Resolve Form Class (consistent with discovery logic)
    form_class = resolve_form_class_for_model(model)
    
    if request.method == 'POST':
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            saved = form.save(commit=False)
            saved._dlux_notify_source = 'generic_crud'
            saved._dlux_notify_surface = 'subsection_modal'
            saved._dlux_notify_route = request.resolver_match.url_name if request.resolver_match else ''
            saved._dlux_notify_flash = False
            # created_by/updated_by auto-populated by ScopedModel.save()
            saved.save()
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'id': saved.pk, 'name': str(saved)})
                
            notify.success(f"تم تعديل {model._meta.verbose_name}: {saved}", request=request, obj=saved, action='subsection_update', category='sections', persist=False)
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': form.errors.as_text()})
            notify.error(f"خطأ في تعديل {model._meta.verbose_name}.", request=request, action='subsection_update_invalid', category='sections')
    
    redirect_url = reverse('manage_sections')
    if parent_model_name:
        redirect_url += f"?model={parent_model_name}"
    return redirect(redirect_url)


# Section Management — AJAX: deletes a subsection with related-record safety check
@login_required
def delete_subsection(request, pk):
    """
    Delete a subsection (child model) by pk.
    Checks for related records before deletion.
    """    
    if not user_has_section_manage_permission(request.user):
        return _section_permission_denied()

    child_model_name = request.GET.get('model', 'subaffiliate')
    parent_model_name = request.GET.get('parent', 'affiliate')
    
    subsection_definition = _resolve_allowed_subsection_definition(
        child_model_name,
        parent_model_name=parent_model_name,
    )
    if not subsection_definition:
        _notify_section_error(request, 'err_subsection_not_found', 'subsection_not_found')
        return redirect('manage_sections')
    model = subsection_definition['model']
    try:
        instance = model._default_manager.get(pk=pk)
    except model.DoesNotExist:
        _notify_section_error(request, 'err_subsection_not_found', 'subsection_not_found')
        return redirect('manage_sections')
    
    if request.method == 'POST':
        if has_related_records(instance, ignore_relations=['affiliates', 'affiliatedepartment_set']):
            s = get_strings()
            notify.error(
                s.get('err_cannot_delete_related'),
                request=request,
                obj=instance,
                action='subsection_delete_blocked',
                category='sections',
                metadata={'message_key': 'err_cannot_delete_related'},
            )
        else:
            name = str(instance)
            instance._dlux_notify_source = 'generic_crud'
            instance._dlux_notify_surface = 'subsection_modal'
            instance._dlux_notify_route = request.resolver_match.url_name if request.resolver_match else ''
            instance._dlux_notify_flash = False
            instance.delete()
            notify.success(f"تم حذف {model._meta.verbose_name}: {name}", request=request, action='subsection_delete', category='sections', persist=False)
    
    redirect_url = reverse('manage_sections')
    if parent_model_name:
        redirect_url += f"?model={parent_model_name}"
    return redirect(redirect_url)


# Section Management — AJAX: deletes a main section model by pk
@login_required
def delete_section(request):
    """
    Delete a section (main model) by pk via AJAX.
    Returns JSON response.
    """
    if not user_has_section_manage_permission(request.user):
        return _section_permission_denied(json_response=True)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'طريقة غير مسموحة'}, status=405)
    
    try:
        data = json.loads(request.body)
        model_name = data.get('model')
        pk = data.get('pk')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'بيانات غير صالحة'}, status=400)
    
    if not model_name or not pk:
        return JsonResponse({'success': False, 'error': 'معلومات ناقصة'}, status=400)
    
    section_definition = _resolve_allowed_section_definition(model_name)
    if not section_definition:
        return JsonResponse({'success': False, 'error': 'القسم غير موجود'}, status=404)
    model = section_definition['model']
    
    try:
        instance = model._default_manager.get(pk=pk)
    except model.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'العنصر غير موجود'}, status=404)
    
    # Use generic helper to find WHAT is related
    related_objects = collect_related_objects(instance)
    
    if related_objects:
        return JsonResponse({
            'success': False, 
            'error': 'لا يمكن حذف هذا العنصر لارتباطه بسجلات أخرى.',
            'related': related_objects # Structured dict of blocking items
        }, status=200)
    
    name = str(instance)
    try:
        instance._dlux_notify_source = 'context_menu'
        instance._dlux_notify_surface = 'section_delete'
        instance._dlux_notify_route = request.resolver_match.url_name if request.resolver_match else ''
        instance.delete()
    except ProtectedError:
        logger.exception("Protected delete blocked for section %s pk=%s", model_name, pk)
        # Fallback if collect_related_objects missed something
        return JsonResponse({
            'success': False, 
            'error': 'لا يمكن حذف هذا العنصر لارتباطه بسجلات محمية أخرى (لم يتم اكتشافها تلقائياً).',
        }, status=200)
    except Exception:
        logger.exception("Unexpected section delete failure for %s pk=%s", model_name, pk)
        return JsonResponse({
            'success': False, 
            'error': 'حدث خطأ أثناء الحذف.'
        }, status=200)
    
    return JsonResponse({'success': True, 'message': f"تم حذف: {name}"})


# Section Management — AJAX: Smart View returns section details and related objects
@login_required
def get_section_details(request):
    """
    Get section details and related objects via AJAX (Smart View).
    Returns JSON with fields and related lists.
    """
    if not user_has_section_view_permission(request.user):
        return _section_permission_denied(json_response=True)

    try:
        model_name = request.GET.get('model')
        pk = request.GET.get('pk')
        
        if not model_name or not pk:
            return JsonResponse({'success': False, 'error': 'معلومات ناقصة'}, status=400)
        
        section_definition = _resolve_allowed_section_definition(model_name)
        if not section_definition:
            return JsonResponse({'success': False, 'error': 'القسم غير موجود'}, status=404)
        model = section_definition['model']
        
        try:
            instance = model._default_manager.get(pk=pk)
        except model.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'العنصر غير موجود'}, status=404)
        
        fields_data = {}
        exclude_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at', 'deleted_by', 'scope', 'polymorphic_ctype', 'password']
        
        for field in model._meta.fields:
            if field.name not in exclude_fields:
                try:
                    val = getattr(instance, field.name)
                    if hasattr(instance, f"get_{field.name}_display"):
                         val = getattr(instance, f"get_{field.name}_display")()
                    label = resolve_detail_field_label(instance, field, request=request)
                    fields_data[str(label)] = str(val) if val is not None else ""
                except:
                    pass

        related_objects = collect_related_objects(instance)
        
        return JsonResponse({
            'success': True,
            'title': str(instance),
            'fields': fields_data,
            'related': related_objects
        })
    except Exception:
        logger.exception("Unexpected section details failure")
        return JsonResponse({
            'success': False,
            'error': 'Unable to load section details.',
        }, status=500)


# Dynamic Modal CRUD — Universal class-based view for managing any model via AJAX modals
class DynamicModalManagerView(LoginRequiredMixin, View):
    """
    Universal Class-based View for managing any model via AJAX Modals.
    Returns JSON with rendered HTML for list and form.
    """
    model = None
    form_class = None  # Optional: override the form discovered by get_model_classes
    show_table = True  # Set False to render form-only (no table/filter)
    show_form = True   # Set False to render table-only (no form)
    template_name = None  # Optional: override the default combined template

    def _get_form_kwargs(self, form_class):
        """Introspect form __init__/__new__ and pass user/request if accepted."""
        import inspect
        extra = {}

        # Check both __init__ and __new__ (UserModalForm uses __new__)
        for method in (form_class.__init__, getattr(form_class, '__new__', None)):
            if method is None:
                continue
            try:
                sig = inspect.signature(method)
            except (ValueError, TypeError):
                continue

            params = sig.parameters
            accepts_var_kwargs = any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in params.values()
            )

            # Pass user if explicitly named as a parameter
            if 'user' in params or accepts_var_kwargs:
                extra.setdefault('user', self.request.user)

            # Pass request ONLY when explicitly named (not via **kwargs to avoid breaking forms)
            if 'request' in params:
                extra.setdefault('request', self.request)

        return extra

    def _resolve_route_name(self):
        match = getattr(self.request, 'resolver_match', None)
        return getattr(match, 'url_name', None)

    def _resolve_modal_surface(self, model):
        action = self.request.GET.get('action')
        show_table = self.show_table if action != 'view' else False
        show_form = self.show_form if action != 'view' else False

        if self._is_system_settings_model(model):
            show_table = False
            show_form = True

        return action, show_table, show_form

    def _is_user_model(self, model):
        return bool(
            model
            and model._meta.app_label == User._meta.app_label
            and model._meta.model_name == User._meta.model_name
        )

    def _is_profile_model(self, model):
        return bool(
            model
            and model._meta.app_label == 'dlux'
            and model._meta.model_name == 'profile'
        )

    def _resolve_target_user(self, model, instance=None):
        if instance is None:
            return None
        if self._is_user_model(model):
            return instance
        if self._is_profile_model(model):
            return getattr(instance, 'user', None)
        return None

    def _has_special_modal_access(self, model, instance=None):
        route_name = self._resolve_route_name()
        if self._is_system_settings_model(model):
            return self.request.user.is_superuser

        if route_name == 'modal_profile_edit':
            return bool(instance and instance.pk == self.request.user.pk)
        if route_name in {'modal_user', 'modal_user_edit', 'modal_user_permissions'} or self._is_user_model(model):
            return can_manage_target_user(self.request.user, instance)

        target_user = self._resolve_target_user(model, instance=instance)
        if target_user is not None:
            return can_manage_target_user(self.request.user, target_user)

        return None

    def _guard_model_access(self, model, instance=None, *, show_table=False, show_form=False, action=None):
        special_access = self._has_special_modal_access(model, instance=instance)
        if special_access is not None:
            return special_access

        required_actions = set()
        if show_table or action == 'view' or (not show_form and not show_table):
            required_actions.add('view')
        if show_form:
            required_actions.add('change' if instance else 'add')

        return all(user_has_model_permission(self.request.user, model, perm_action) for perm_action in required_actions)

    def _build_form(self, form_class, *args, **kwargs):
        """
        Safely instantiate a form, injecting user/request only when accepted.
        Falls back to instantiation without extra kwargs if they cause errors.
        """
        extra_kwargs = self._get_form_kwargs(form_class)
        merged = {**kwargs, **extra_kwargs}
        try:
            return form_class(*args, **merged)
        except TypeError:
            # Form doesn't accept the extra kwargs — retry without them
            return form_class(*args, **kwargs)

    def get_model(self):
        if self.model:
            return self.model
        
        app_label = self.kwargs.get('app_label')
        model_name = self.kwargs.get('model_name')
        if app_label and model_name:
            try:
                return apps.get_model(app_label, model_name)
            except (LookupError, ValueError):
                pass
        
        model_name = self.request.GET.get('model')
        if model_name:
            return resolve_model_by_name(model_name)
        return None

    def _is_system_settings_model(self, model):
        return bool(model and model._meta.app_label == 'dlux' and model.__name__ == 'SystemSettings')

    def _get_wizard_initial_step(self, model):
        if not self._is_system_settings_model(model):
            return None

        raw_step = self.request.GET.get('step')
        try:
            step = int(raw_step)
        except (TypeError, ValueError):
            return None

        if 0 <= step < SETUP_STEP_COUNT:
            return step
        return None

    def get(self, request, *args, **kwargs):
        model = self.get_model()
        if not model:
            return JsonResponse({'error': 'Model not found'}, status=404)

        pk = kwargs.get('pk') or request.GET.get('id')
        instance = None
        if pk and pk != 'new':
            instance = get_object_or_404(_scope_filtered_modal_queryset(model, request.user), pk=pk)

        action, show_table, show_form = self._resolve_modal_surface(model)
        if not self._guard_model_access(model, instance=instance, show_table=show_table, show_form=show_form, action=action):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        classes = get_model_classes(model._meta.model_name, app_label=model._meta.app_label)
        if not classes:
            return JsonResponse({'error': 'Failed to resolve classes'}, status=500)

        table = None
        f = None
        
        if show_table:
            queryset = _scope_filtered_modal_queryset(model, request.user)
            if classes['filter']:
                f = classes['filter'](request.GET, queryset=queryset)
                from dlux.utils import setup_filter_helper
                setup_filter_helper(f, request)
                queryset = f.qs

            table = classes['table'](queryset, request=request)
            # Marker for templates to know it's a modal context
            table.is_dynamic_modal = True
            
            RequestConfig(request).configure(table)

        form = None
        if show_form:
            form_class = self.form_class or classes['form']
            form = self._build_form(form_class, instance=instance)
        
        context = {
            'model': model,
            'table': table,
            'form': form,
            'filter': f,
            'instance': instance,
            'object': instance,  # Django convention alias
            'DLUX_STRINGS': get_strings(),
            'hide_form_buttons': getattr(form, "_auto_helper", False) or has_submit_button(form),
            'wizard_initial_step': self._get_wizard_initial_step(model),
            # Sticky-forms markers. Create only: refilling an existing record
            # from a different one would be data loss. Template variables cannot
            # read `_meta` (leading underscore), so resolve them here.
            'sticky_app_label': '' if instance else model._meta.app_label,
            'sticky_model_name': '' if instance else model._meta.model_name,
        }

        # Auto-merge model-defined modal context (convention: get_modal_context)
        if instance and hasattr(instance, 'get_modal_context'):
            extra = instance.get_modal_context()
            if isinstance(extra, dict):
                context.update(extra)
        
        tpl = self.template_name
        
        # 6. Fallback to AutoDetail View if form/table are disabled and no template is provided
        if not show_form and not show_table and not tpl:
            from dlux.utils import _build_generic_detail_context
            context['auto_detail_fields'] = _build_generic_detail_context(instance, request)
            tpl = 'dlux/helpers/dynamic_modal_detail.html'
            
        if not tpl:
            tpl = 'dlux/helpers/dynamic_modal_combined.html'
            
        html = render_to_string(tpl, context, request=request)
        return JsonResponse({'html': html})

    def post(self, request, *args, **kwargs):
        model = self.get_model()
        if not model:
            return JsonResponse({'error': 'Model not found'}, status=404)

        instance = None
        pk = kwargs.get('pk') or request.GET.get('id')
        if pk and pk != 'new':
            instance = get_object_or_404(_scope_filtered_modal_queryset(model, request.user), pk=pk)

        if not self._guard_model_access(model, instance=instance, show_form=True):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        classes = get_model_classes(model._meta.model_name, app_label=model._meta.app_label)
        form_class = self.form_class or classes['form']
        form = self._build_form(form_class, request.POST, request.FILES, instance=instance)

        if form.is_valid():
            # Forms with handles_save=True manage their own save cycle
            if getattr(form, 'handles_save', False):
                obj = form.save(commit=True)
            else:
                obj = form.save(commit=False)
                obj._dlux_notify_source = 'generic_crud'
                obj._dlux_notify_surface = 'dynamic_modal'
                obj._dlux_notify_route = request.resolver_match.url_name if request.resolver_match else ''
                # created_by/updated_by auto-populated by ScopedModel.save()
                
                # Scope forced for non-superusers
                if is_scope_enabled() and hasattr(obj, 'scope'):
                    user_scope = getattr(getattr(request.user, 'profile', None), 'scope', None)
                    if user_scope and not request.user.is_superuser:
                        obj.scope = user_scope
                
                obj.save()
                form.save_m2m()
            
            return JsonResponse({
                'success': True,
                'refresh_parent': getattr(form, 'refresh_parent', False),
                'add_more': getattr(form, 'add_more', False),
            })
        
        context = {
            'model': model,
            'form': form,
            'instance': instance,
            'DLUX_STRINGS': get_strings(),
            'hide_form_buttons': getattr(form, "_auto_helper", False) or has_submit_button(form),
            'wizard_initial_step': self._get_wizard_initial_step(model),
            # Sticky-forms markers. Create only: refilling an existing record
            # from a different one would be data loss. Template variables cannot
            # read `_meta` (leading underscore), so resolve them here.
            'sticky_app_label': '' if instance else model._meta.app_label,
            'sticky_model_name': '' if instance else model._meta.model_name,
        }
        if self._is_system_settings_model(model):
            logger.warning(
                "SystemSettings modal validation failed on step %s: %s",
                request.GET.get('step'),
                form.errors.get_json_data(),
            )
        html = render_to_string('dlux/helpers/dynamic_modal_combined.html', context, request=request)
        return JsonResponse({'success': False, 'html': html})


# Dynamic Modal CRUD — Generic AJAX delete with related-object protection
class DynamicModalDeleteView(LoginRequiredMixin, View):
    """
    Generic view for deleting records via AJAX inside dynamic modals.
    Checks for related object protection.
    """
    model = None

    def post(self, request, *args, **kwargs):
        model_class = self.model
        if not model_class:
            app_label = kwargs.get('app_label')
            model_name = kwargs.get('model_name')
            if app_label and model_name:
                try:
                    model_class = apps.get_model(app_label, model_name)
                except (LookupError, ValueError):
                    pass
            
            if not model_class:
                model_name = request.GET.get('model')
                model_class = resolve_model_by_name(model_name)
        
        pk = kwargs.get('pk')
        if not model_class or not pk:
            return JsonResponse({'error': 'Missing parameters'}, status=400)
        if (
            (
                model_class._meta.app_label == User._meta.app_label
                and model_class._meta.model_name == User._meta.model_name
            )
            or (
                model_class._meta.app_label == 'dlux'
                and model_class._meta.model_name == 'systemsettings'
            )
        ):
            return JsonResponse({'error': 'Permission denied'}, status=403)
        if not user_has_model_permission(request.user, model_class, 'delete'):
            return JsonResponse({'error': 'Permission denied'}, status=403)
            
        instance = get_object_or_404(_scope_filtered_modal_queryset(model_class, request.user), pk=pk)
        
        # Protection check (Generic helper from utils)
        related = collect_related_objects(instance)
        if related:
            return JsonResponse({
                'success': False, 
                'error': get_strings().get('delete_error_related', 'لا يمكن الحذف لارتباطه بسجلات أخرى.')
            })
            
        name = str(instance)
        instance._dlux_notify_source = 'generic_crud'
        instance._dlux_notify_surface = 'dynamic_modal_delete'
        instance._dlux_notify_route = request.resolver_match.url_name if request.resolver_match else ''
        instance.delete()
        
        return JsonResponse({'success': True, 'message': f"Deleted {name}"})
