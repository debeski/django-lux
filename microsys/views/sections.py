# Fundemental imports
import json
import inspect

from django import forms
from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.views import View
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from django_tables2 import RequestConfig

# Project imports
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
    log_user_action,
    setup_filter_helper,
    has_submit_button,
)
from ..translations import get_strings

User = get_user_model()


# Section Management — Main dynamic CRUD view for all section and subsection models
@login_required
def core_models_view(request):
    """
    Manages section models dynamically discovered from the app.
    Uses ?model= query param with session fallback for tab persistence.
    """
    # Discover section models dynamically
    section_models = discover_section_models(app_name=None, include_children=False)
    
    # Build map for easy lookup
    models_map = {sm['model_name']: sm for sm in section_models}
    
    # Get model from query param or session fallback
    default_model = section_models[0]['model_name'] if section_models else None
    model_param = request.GET.get('model') or request.session.get('last_active_model', default_model)
    
    # Fallback to first discovered model if invalid
    if model_param not in models_map:
        model_param = default_model
    
    if not model_param or not models_map:
        return render(request, 'microsys/sections/manage_sections.html', {
            'error': 'لا توجد موديلات متاحة.',
        })
    
    # Store in session only when user explicitly changes tab via GET param
    if request.GET.get('model'):
        request.session['last_active_model'] = model_param
    
    selected_data = models_map[model_param]
    selected_model = selected_data['model']
    
    # Get classes from discovery result
    FormClass = selected_data['form_class']
    TableClass = selected_data['table_class']
    FilterClass = selected_data['filter_class']
    
    if not FormClass or not TableClass:
        return render(request, 'microsys/sections/manage_sections.html', {
            'error': 'هناك خطأ في تحميل المودل.',
            'active_model': model_param,
            'models': [{'name': sm['model_name'], 'ar_names': sm['verbose_name_plural'], 'count': sm['model'].objects.count()} for sm in section_models],
        })
    
    # Check for edit mode
    instance_id = request.GET.get('id')
    instance = None
    if instance_id:
        try:
            instance = selected_model.objects.get(pk=instance_id)
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

    # Create form
    form = FormClass(request.POST or None, instance=instance)
    # Auto-create a crispy helper if the form doesn't define one (marks it for layout generation later)
    if not hasattr(form, "helper") or form.helper is None:
        form.helper = FormHelper()
        form.helper.form_tag = False
        form._auto_helper = True
    else:
        form.helper.form_tag = False
        if not getattr(form.helper, "inputs", None):
            form.helper.add_input(Submit("submit", "حفظ", css_class="btn btn-primary rounded-pill"))

    user_scope = None
    if hasattr(request.user, 'profile') and getattr(request.user.profile, 'scope', None):
        user_scope = request.user.profile.scope
    elif hasattr(request.user, 'scope') and getattr(request.user, 'scope', None):
        user_scope = request.user.scope

    if is_scope_enabled() and user_scope and not request.user.is_superuser:
        scope_field = form.fields.get('scope')
        if scope_field:
            scope_field.initial = user_scope
            scope_field.disabled = True
            scope_field.widget = forms.HiddenInput()
            scope_field.required = False
    
    # Create filter and queryset
    queryset = selected_model.objects.all()
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
    translations = get_strings()
    if accepts_model_name:
        table = TableClass(queryset, model_name=model_param, translations=translations, request=request)
    else:
        table = TableClass(queryset, translations=translations, request=request)
        if not hasattr(table, "model_name"):
            table.model_name = model_param
    RequestConfig(request, paginate={'per_page': 10}).configure(table)

    # Merge 'scope' into existing excludes without duplicates for scoped non-superusers
    if is_scope_enabled() and user_scope and not request.user.is_superuser:
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
                queryset=child_model.objects.all(),
                required=False,
                label=sub['verbose_name_plural'],
                widget=forms.CheckboxSelectMultiple(),
            )
        else:
            # Field exists - ensure it has the right queryset and widget
            form.fields[related_field].queryset = child_model.objects.all()
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
             child_form_instance.helper.add_input(Submit("submit", "حفظ", css_class="btn btn-primary rounded-pill"))

        if is_scope_enabled() and user_scope and not request.user.is_superuser:
            child_scope_field = child_form_instance.fields.get('scope')
            if child_scope_field:
                child_scope_field.initial = user_scope
                child_scope_field.disabled = True
                child_scope_field.widget = forms.HiddenInput()
                child_scope_field.required = False
        
        subsection_forms.append({
            'name': child_model_name,
            'verbose_name': sub['verbose_name'],
            'form': child_form_instance
        })

    # Handle POST (after subsection fields are injected)
    if request.method == 'POST':
        if form.is_valid():
            saved_instance = form.save(commit=False)
            # created_by/updated_by auto-populated by ScopedModel.save()
            # Enforce scope for non-superusers with assigned scope
            if is_scope_enabled() and user_scope and not request.user.is_superuser and hasattr(saved_instance, 'scope'):
                saved_instance.scope = user_scope
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
        
        # Identify visible fields (excluding subsections which are handled separately)
        visible_fields = [
            f for f in form.fields 
            if f not in subsection_field_names 
            and not isinstance(form.fields[f].widget, forms.HiddenInput)
        ]
        
        layout_components = []
        
        # Add hidden fields first
        hidden_fields = [
            f for f in form.fields 
            if isinstance(form.fields[f].widget, forms.HiddenInput)
        ]
        for hf in hidden_fields:
            layout_components.append(Field(hf))
            
        # Helper to chunk fields
        def chunked(iterable, n):
            return [iterable[i:i + n] for i in range(0, len(iterable), n)]
            
        field_chunks = chunked(visible_fields, 2)
        total_chunks = len(field_chunks)
        
        for i, chunk in enumerate(field_chunks):
            is_last_chunk = (i == total_chunks - 1)
            
            if is_last_chunk:
                # Last chunk: Add fields + Buttons
                row_content = []
                for field_name in chunk:
                    row_content.append(Column(Field(field_name), css_class="col"))
                
                # Build Buttons HTML
                if cancel_url:
                    buttons_html = f"""
                    <div class="d-flex">
                        <button type="submit" class="btn btn-primary rounded-start-pill rounded-end-0">حفظ</button>
                        <a href="{cancel_url}" class="btn btn-outline-warning rounded-end-pill rounded-start-0">إلغاء</a>
                    </div>
                    """
                else:
                    buttons_html = '<button type="submit" class="btn btn-primary rounded-pill">حفظ</button>'
                
                row_content.append(
                    Column(
                        HTML(buttons_html), 
                        css_class="col-auto align-self-end mb-3"
                    )
                )
                layout_components.append(Row(*row_content))
            else:
                # Normal chunk: 2 columns
                row_content = [Column(Field(field_name), css_class="col-md-6") for field_name in chunk]
                layout_components.append(Row(*row_content))
                
        # If no visible fields but we have actions (rare edge case), just show buttons
        if not visible_fields:
            if cancel_url:
                buttons_html = f"""
                <div class="d-flex">
                    <button type="submit" class="btn btn-primary rounded-start-pill rounded-end-0">حفظ</button>
                    <a href="{cancel_url}" class="btn btn-outline-warning rounded-end-pill rounded-start-0">إلغاء</a>
                </div>
                """
            else:
                buttons_html = '<button type="submit" class="btn btn-primary rounded-pill">حفظ</button>'
            layout_components.append(Row(Column(HTML(buttons_html), css_class="col-auto")))

        form.helper.layout = Layout(*layout_components)

    # Build context
    context = {
        'active_model': model_param,
        'models': [
            {
                'name': sm['model_name'], 
                'ar_names': sm['verbose_name_plural'],
                'count': sm['model'].objects.count()
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
    
    return render(request, 'microsys/sections/manage_sections.html', context)

# Section Management — AJAX: adds a new subsection (child model) via modal
@login_required
def add_subsection(request):
    """
    Generic view to handle adding a new Subsection (child model) via modal.
    Expects ?model=child_model_name&parent=parent_model_name
    """
    child_model_name = request.GET.get('model')
    parent_model_name = request.GET.get('parent')
    parent_id = request.GET.get('parent_id')
    parent_field = request.GET.get('parent_field')
    
    if not child_model_name:
         messages.error(request, "معرف القسم الفرعي مفقود.")
         return redirect('manage_sections')

    # Resolve child model class
    model = resolve_model_by_name(child_model_name)
    if not model:
        messages.error(request, "القسم الفرعي غير موجود.")
        return redirect('manage_sections')
        
    # Resolve Form Class (consistent with discovery logic)
    form_class = resolve_form_class_for_model(model)
    
    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            # created_by/updated_by auto-populated by ScopedModel.save()
            # Ensure scope is set for scoped models
            if is_scope_enabled() and hasattr(instance, 'scope'):
                try:
                    user_scope = getattr(getattr(request.user, 'profile', None), 'scope', None)
                    if not user_scope and hasattr(request.user, 'scope'):
                        user_scope = request.user.scope
                    if user_scope:
                        if not request.user.is_superuser:
                            instance.scope = user_scope
                        elif not getattr(instance, 'scope', None):
                            instance.scope = user_scope
                except Exception:
                    pass
            instance.save()

            if parent_model_name and parent_id and parent_field:
                try:
                    parent_model = resolve_model_by_name(parent_model_name)
                    if parent_model:
                        parent_instance = parent_model.objects.get(pk=parent_id)
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
            
            # AJAX Response
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'id': instance.pk, 'name': str(instance)})
                
            messages.success(request, f"تم إضافة {model._meta.verbose_name}: {instance}")
        else:
            # Fallback: try creating from raw POST data if form validation fails (e.g. simple name-only models)
            instance, missing = _create_minimal_instance_from_post(model, request.POST, request)
            if instance:
                if parent_model_name and parent_id and parent_field:
                    try:
                        parent_model = resolve_model_by_name(parent_model_name)
                        if parent_model:
                            parent_instance = parent_model.objects.get(pk=parent_id)
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

                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'id': instance.pk, 'name': str(instance)})
                messages.success(request, f"تم إضافة {model._meta.verbose_name}: {instance}")
            else:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                     err = form.errors.as_text()
                     if missing:
                         err = f"Missing required fields: {', '.join(missing)}"
                     return JsonResponse({'success': False, 'error': err})
                messages.error(request, f"خطأ في إضافة {model._meta.verbose_name}.")
    
    # Redirect back to parent tab
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
    child_model_name = request.GET.get('model', 'subaffiliate')
    parent_model_name = request.GET.get('parent', 'affiliate')
    
    model = resolve_model_by_name(child_model_name)
    if not model:
        messages.error(request, "القسم الفرعي غير موجود.")
        return redirect('manage_sections')
    try:
        instance = model.objects.get(pk=pk)
    except model.DoesNotExist:
        messages.error(request, "القسم الفرعي غير موجود.")
        return redirect('manage_sections')
    
    # Resolve Form Class (consistent with discovery logic)
    form_class = resolve_form_class_for_model(model)
    
    if request.method == 'POST':
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            saved = form.save(commit=False)
            # created_by/updated_by auto-populated by ScopedModel.save()
            saved.save()
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'id': saved.pk, 'name': str(saved)})
                
            messages.success(request, f"تم تعديل {model._meta.verbose_name}: {saved}")
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': form.errors.as_text()})
            messages.error(request, f"خطأ في تعديل {model._meta.verbose_name}.")
    
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
    child_model_name = request.GET.get('model', 'subaffiliate')
    parent_model_name = request.GET.get('parent', 'affiliate')
    
    model = resolve_model_by_name(child_model_name)
    if not model:
        messages.error(request, "القسم الفرعي غير موجود.")
        return redirect('manage_sections')
    try:
        instance = model.objects.get(pk=pk)
    except model.DoesNotExist:
        messages.error(request, "القسم الفرعي غير موجود.")
        return redirect('manage_sections')
    
    if request.method == 'POST':
        # Check if locked (has related records)
        if has_related_records(instance, ignore_relations=['affiliates', 'affiliatedepartment_set']):
            messages.error(request, "لا يمكن حذف هذا العنصر لارتباطه بسجلات أخرى.")
        else:
            name = str(instance)
            instance.delete()
            messages.success(request, f"تم حذف {model._meta.verbose_name}: {name}")
    
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
    
    model = resolve_model_by_name(model_name)
    if not model:
        return JsonResponse({'success': False, 'error': 'القسم غير موجود'}, status=404)
    
    try:
        instance = model.objects.get(pk=pk)
    except model.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'العنصر غير موجود'}, status=404)
    
    # Check if has related records (protect from deletion)
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
        instance.delete()
    except ProtectedError as e:
        # Fallback if collect_related_objects missed something
        return JsonResponse({
            'success': False, 
            'error': 'لا يمكن حذف هذا العنصر لارتباطه بسجلات محمية أخرى (لم يتم اكتشافها تلقائياً).',
            'details': str(e)
        }, status=200)
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'error': f'حدث خطأ أثناء الحذف: {str(e)}'
        }, status=200)
    
    return JsonResponse({'success': True, 'message': f"تم حذف: {name}"})


# Section Management — AJAX: Smart View returns section details and related objects
@login_required
def get_section_details(request):
    """
    Get section details and related objects via AJAX (Smart View).
    Returns JSON with fields and related lists.
    """
    try:
        model_name = request.GET.get('model')
        pk = request.GET.get('pk')
        
        if not model_name or not pk:
            return JsonResponse({'success': False, 'error': 'معلومات ناقصة'}, status=400)
        
        model = resolve_model_by_name(model_name)
        if not model:
            return JsonResponse({'success': False, 'error': 'القسم غير موجود'}, status=404)
        
        try:
            instance = model.objects.get(pk=pk)
        except model.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'العنصر غير موجود'}, status=404)
        
        # 1. Collect Fields
        fields_data = {}
        exclude_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at', 'deleted_by', 'scope', 'polymorphic_ctype', 'password']
        
        for field in model._meta.fields:
            if field.name not in exclude_fields:
                try:
                    val = getattr(instance, field.name)
                    # Handle choices
                    if hasattr(instance, f"get_{field.name}_display"):
                         val = getattr(instance, f"get_{field.name}_display")()
                    fields_data[str(field.verbose_name)] = str(val) if val is not None else ""
                except:
                    pass

        # 2. Collect Related Objects
        related_objects = collect_related_objects(instance)
        
        return JsonResponse({
            'success': True,
            'title': str(instance),
            'fields': fields_data,
            'related': related_objects
        })
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        })


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

            # Pass user if explicitly named as a parameter
            if 'user' in params:
                extra.setdefault('user', self.request.user)

            # Pass request when explicitly named
            if 'request' in params:
                extra.setdefault('request', self.request)

        return extra

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
        
        # 1. Check kwargs from URL capture
        app_label = self.kwargs.get('app_label')
        model_name = self.kwargs.get('model_name')
        if app_label and model_name:
            try:
                return apps.get_model(app_label, model_name)
            except (LookupError, ValueError):
                pass
        
        # 2. Fallback to query param
        model_name = self.request.GET.get('model')
        if model_name:
            return resolve_model_by_name(model_name)
        return None

    def get(self, request, *args, **kwargs):
        model = self.get_model()
        if not model:
            return JsonResponse({'error': 'Model not found'}, status=404)

        # 1. Resolve Classes
        classes = get_model_classes(model._meta.model_name, app_label=model._meta.app_label)
        if not classes:
            return JsonResponse({'error': 'Failed to resolve classes'}, status=500)

        # 2. Handle List (Table)
        table = None
        f = None
        
        # Action override
        action = request.GET.get('action')
        show_table = self.show_table if action != 'view' else False
        show_form = self.show_form if action != 'view' else False

        if show_table:
            queryset = model.objects.all()
            # Filter (optional)
            if classes['filter']:
                f = classes['filter'](request.GET, queryset=queryset)
                from microsys.utils import setup_filter_helper
                setup_filter_helper(f, request)
                queryset = f.qs

            table = classes['table'](queryset, request=request)
            # Marker for templates to know it's a modal context
            table.is_dynamic_modal = True
            
            RequestConfig(request, paginate={'per_page': 10}).configure(table)

        # 3. Resolve instance (always — needed for form, detail, or table-edit)
        instance = None
        pk = kwargs.get('pk') or request.GET.get('id')
        if pk and pk != 'new':
            instance = get_object_or_404(model, pk=pk)

        # 4. Handle Form (Edit or Create)
        form = None
        if show_form:
            form_class = self.form_class or classes['form']
            form = self._build_form(form_class, instance=instance)
        
        # 5. Render
        context = {
            'model': model,
            'table': table,
            'form': form,
            'filter': f,
            'instance': instance,
            'object': instance,  # Django convention alias
            'MS_TRANS': get_strings(),
            'hide_form_buttons': getattr(form, "_auto_helper", False) or has_submit_button(form),
        }

        # Auto-merge model-defined modal context (convention: get_modal_context)
        if instance and hasattr(instance, 'get_modal_context'):
            extra = instance.get_modal_context()
            if isinstance(extra, dict):
                context.update(extra)
        
        tpl = self.template_name
        
        # 6. Fallback to AutoDetail View if form/table are disabled and no template is provided
        if not show_form and not show_table and not tpl:
            from microsys.utils import _build_generic_detail_context
            context['auto_detail_fields'] = _build_generic_detail_context(instance, request)
            tpl = 'microsys/helpers/dynamic_modal_detail.html'
            
        if not tpl:
            tpl = 'microsys/helpers/dynamic_modal_combined.html'
            
        html = render_to_string(tpl, context, request=request)
        return JsonResponse({'html': html})

    def post(self, request, *args, **kwargs):
        model = self.get_model()
        if not model:
            return JsonResponse({'error': 'Model not found'}, status=404)

        instance = None
        pk = kwargs.get('pk') or request.GET.get('id')
        if pk and pk != 'new':
            instance = get_object_or_404(model, pk=pk)

        classes = get_model_classes(model._meta.model_name, app_label=model._meta.app_label)
        form_class = self.form_class or classes['form']
        form = self._build_form(form_class, request.POST, request.FILES, instance=instance)

        if form.is_valid():
            # Forms with handles_save=True manage their own save cycle
            if getattr(form, 'handles_save', False):
                obj = form.save(commit=True)
            else:
                obj = form.save(commit=False)
                # created_by/updated_by auto-populated by ScopedModel.save()
                
                # Scope forced for non-superusers
                if is_scope_enabled() and hasattr(obj, 'scope'):
                    user_scope = getattr(getattr(request.user, 'profile', None), 'scope', None)
                    if user_scope and not request.user.is_superuser:
                        obj.scope = user_scope
                
                obj.save()
                form.save_m2m()
            
            # Log action
            log_user_action(request, "UPDATE" if pk else "CREATE", instance=obj, model_name=model._meta.model_name)
            
            return JsonResponse({
                'success': True,
                'refresh_parent': getattr(form, 'refresh_parent', False)
            })
        
        # Form invalid, return form HTML with errors
        context = {
            'model': model,
            'form': form,
            'instance': instance,
            'MS_TRANS': get_strings(),
            'hide_form_buttons': getattr(form, "_auto_helper", False) or has_submit_button(form),
        }
        # Render combined view for validation failure
        html = render_to_string('microsys/helpers/dynamic_modal_combined.html', context, request=request)
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
            # 1. Check kwargs from URL capture
            app_label = kwargs.get('app_label')
            model_name = kwargs.get('model_name')
            if app_label and model_name:
                try:
                    model_class = apps.get_model(app_label, model_name)
                except (LookupError, ValueError):
                    pass
            
            # 2. Fallback to query param
            if not model_class:
                model_name = request.GET.get('model')
                model_class = resolve_model_by_name(model_name)
        
        pk = kwargs.get('pk')
        if not model_class or not pk:
            return JsonResponse({'error': 'Missing parameters'}, status=400)
            
        instance = get_object_or_404(model_class, pk=pk)
        
        # Protection check (Generic helper from utils)
        related = collect_related_objects(instance)
        if related:
            return JsonResponse({
                'success': False, 
                'error': get_strings().get('delete_error_related', 'لا يمكن الحذف لارتباطه بسجلات أخرى.')
            })
            
        name = str(instance)
        log_user_action(request, "DELETE", instance=instance, model_name=model_class._meta.model_name)
        instance.delete()
        
        return JsonResponse({'success': True, 'message': f"Deleted {name}"})
