# Fundemental imports
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.module_loading import import_string
from django.views.decorators.http import require_POST
from django_tables2 import RequestConfig

# Project imports
from ..utils import (
    can_manage_group_preset,
    get_visible_group_presets,
)

User = get_user_model()


def _require_manage_groups(request):
    """Gate: superuser or holders of the dlux.manage_groups permission."""
    user = request.user
    if not (getattr(user, 'is_superuser', False) or user.has_perm('dlux.manage_groups')):
        raise PermissionDenied


def _visible_presets_with_counts(request):
    """Visible preset Groups annotated with member/permission counts."""
    visible_ids = get_visible_group_presets(request.user).values_list('id', flat=True)
    return (
        Group.objects.filter(id__in=list(visible_ids))
        .select_related('dlux_profile', 'dlux_profile__scope')
        .annotate(
            member_count=Count('user', distinct=True),
            permission_count=Count('permissions', distinct=True),
        )
        .order_by('name')
    )


def _render_manager(request):
    GroupPresetTable = import_string('dlux.tables.GroupPresetTable')
    rows = list(_visible_presets_with_counts(request))
    for row in rows:
        # Per-row flag so the actions template hides edit/members on presets the
        # actor may see (for assignment) but not manage (e.g. global presets).
        row.dlux_can_manage = can_manage_group_preset(request.user, row)
    table = GroupPresetTable(rows, request=request)
    RequestConfig(request).configure(table)
    return render_to_string(
        'dlux/groups/_group_manager.html',
        {'table': table, 'ribbon': _manager_ribbon(request)},
        request=request,
    )


def _manager_ribbon(request):
    """The modal's header, as a Ribbon: title, description and the Add button."""
    from ..ribbon import build_action, build_ribbon
    from ..translations import get_current_language_code, get_strings

    s = get_strings(get_current_language_code(request))
    return build_ribbon(
        None,
        request=request,
        title=s.get('manage_groups_label', 'Manage Groups'),
        subtitle=s.get('manage_groups_desc', ''),
        title_icon='bi bi-people-fill',
        actions=[build_action({
            'label': s.get('add_group', 'Add Group'),
            'icon': 'bi bi-plus-lg',
            'css_class': 'btn btn-success rounded-pill js-group-nav',
            'attrs': {'data-url': reverse('get_group_form')},
        }, request=request)],
    )


# Group Management — AJAX modal: returns the preset table (manage_groups gated)
@login_required
def manage_groups(request):
    _require_manage_groups(request)
    return JsonResponse({'html': _render_manager(request)})


# Group Management — AJAX: returns the add/edit preset form partial
@login_required
def get_group_form(request, pk=None):
    _require_manage_groups(request)
    GroupPresetForm = import_string('dlux.forms.GroupPresetForm')

    group = None
    if pk:
        group = get_object_or_404(Group, pk=pk)
        if not can_manage_group_preset(request.user, group):
            raise PermissionDenied
        form = GroupPresetForm(instance=group, user=request.user)
    else:
        form = GroupPresetForm(user=request.user)

    html = render_to_string(
        'dlux/groups/group_form.html', {'form': form, 'group_id': pk}, request=request
    )
    return JsonResponse({'html': html})


# Group Management — AJAX: create/update a preset, return the refreshed table
@login_required
def save_group(request, pk=None):
    _require_manage_groups(request)
    GroupPresetForm = import_string('dlux.forms.GroupPresetForm')

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})

    group = None
    if pk:
        group = get_object_or_404(Group, pk=pk)
        if not can_manage_group_preset(request.user, group):
            raise PermissionDenied
        form = GroupPresetForm(request.POST, instance=group, user=request.user)
    else:
        form = GroupPresetForm(request.POST, user=request.user)

    if form.is_valid():
        form.save()
        return JsonResponse({'success': True, 'html': _render_manager(request)})

    html = render_to_string(
        'dlux/groups/group_form.html', {'form': form, 'group_id': pk}, request=request
    )
    return JsonResponse({'success': False, 'html': html})


def _render_members(request, group, form=None):
    GroupMembersForm = import_string('dlux.forms.GroupMembersForm')
    GroupMembershipTable = import_string('dlux.tables.GroupMembershipTable')
    GroupMembership = import_string('dlux.models.GroupMembership')

    if form is None:
        form = GroupMembersForm(group=group, user=request.user)

    history = (
        GroupMembership.objects.filter(group=group)
        .select_related('user', 'assigned_by')
        .order_by('-assigned_at')
    )
    table = GroupMembershipTable(history, request=request)
    RequestConfig(request).configure(table)
    return render_to_string(
        'dlux/groups/group_members.html',
        {'form': form, 'table': table, 'group': group, 'group_id': group.pk},
        request=request,
    )


# Group Management — AJAX modal: manage a preset's membership + view history
@login_required
def group_members(request, pk):
    _require_manage_groups(request)
    group = get_object_or_404(Group, pk=pk)
    if not can_manage_group_preset(request.user, group):
        raise PermissionDenied
    return JsonResponse({'html': _render_members(request, group)})


# Group Management — AJAX: apply a membership diff, return refreshed members view
@login_required
def save_group_members(request, pk):
    _require_manage_groups(request)
    GroupMembersForm = import_string('dlux.forms.GroupMembersForm')
    group = get_object_or_404(Group, pk=pk)
    if not can_manage_group_preset(request.user, group):
        raise PermissionDenied

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})

    form = GroupMembersForm(request.POST, group=group, user=request.user)
    if form.is_valid():
        form.save()
        return JsonResponse({'success': True, 'html': _render_members(request, group)})

    return JsonResponse({'success': False, 'html': _render_members(request, group, form=form)})


@login_required
@require_POST
def toggle_group_public_registration_default(request, pk):
    _require_manage_groups(request)
    group = get_object_or_404(Group, pk=pk)
    if not can_manage_group_preset(request.user, group):
        raise PermissionDenied
    GroupProfile = import_string('dlux.models.GroupProfile')
    profile, _created = GroupProfile.objects.get_or_create(group=group)
    profile.is_public_registration_default = not bool(profile.is_public_registration_default)
    profile.updated_by = request.user
    profile.save(update_fields=['is_public_registration_default', 'updated_by', 'updated_at'])
    return JsonResponse({
        'success': True,
        'is_default': profile.is_public_registration_default,
        'html': _render_manager(request),
    })
