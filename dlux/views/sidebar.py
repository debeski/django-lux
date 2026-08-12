"""Sidebar view.

`toggle_sidebar` is a view — it takes a request and returns a JsonResponse — but
it lived in `dlux/utils/navigation.py` until 1.8.0, which meant `urls.py` had to
import the whole `dlux.utils` package for this one route. The sidebar's *other*
concerns are correctly layered already: settings schema in `dlux.system`, the
form group in `dlux.forms.system_settings_groups.sidebar`, structure building in
`dlux.discovery`, and preference resolution in `dlux.utils.navigation`.
"""
from django.http import JsonResponse


def toggle_sidebar(request):
    if request.method == "POST" and request.user.is_authenticated:
        collapsed = request.POST.get("collapsed") == "true"
        
        # 1. Update Session
        request.session["sidebarCollapsed"] = collapsed
        
        # 2. Update Profile Preferences if profile exists
        if hasattr(request.user, 'profile'):
            profile = request.user.profile
            if not profile.preferences:
                profile.preferences = {}
            
            # Ensure it's a dict
            if isinstance(profile.preferences, str):
                import json
                try:
                    profile.preferences = json.loads(profile.preferences)
                except:
                    profile.preferences = {}
            
            # Use a copy to ensure Django detects changes
            prefs = dict(profile.preferences)
            prefs['sidebar_collapsed'] = collapsed
            profile.preferences = prefs
            profile.save(update_fields=['preferences'])

        return JsonResponse({"status": "success"})
    return JsonResponse({"status": "error"}, status=400)
