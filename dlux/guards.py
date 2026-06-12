from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

from .translations import get_strings


def require_current_password(request, redirect_name='user_profile', field_name='current_password'):
    """
    Enforce current-password confirmation for a POST action.

    Usage:
        if failure_response := require_current_password(request):
            return failure_response
    """
    current_password = str(request.POST.get(field_name) or '')
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    s = get_strings()

    if not current_password:
        message = s.get('current_password_required', 'Please enter your current password.')
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': message}, status=400)
        messages.error(request, message, fail_silently=True)
        return redirect(redirect_name)

    if not request.user.check_password(current_password):
        message = s.get('current_password_incorrect', 'Current password is incorrect.')
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': message}, status=400)
        messages.error(request, message, fail_silently=True)
        return redirect(redirect_name)

    return None
