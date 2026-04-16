from django import template
from microsys.translations import get_strings

register = template.Library()

from microsys.middleware import get_current_request

@register.filter
def translate_log(value, prefix=''):
    """
    Translates a log value (action, model_name) using the microsys translation system.
    Usage: {{ log.action|translate_log:'action' }} -> looks for 'action_LOGIN' (lowercase)
    Usage: {{ log.model_name|translate_log:'model' }} -> looks for 'model_user' (lowercase)
    """
    if not value:
        return ""
        
    request = get_current_request()
    ms_trans = get_strings()
        
    # Construct key: e.g. 'action_login', 'model_user'
    key = f"{prefix}_{str(value).lower()}" if prefix else str(value).lower()
    
    # Look up
    return ms_trans.get(key, value)

@register.simple_tag
def format_log_details(details):
    """
    Format the details JSON into a readable HTML string.
    """
    if not details or not isinstance(details, dict):
        return ""
        
    html_parts = []
    
    # Check for specific types
    if 'filename' in details:
        # Download/Export
        fname = details.get('filename')
        count = details.get('count', 1)
        html_parts.append(f'<i class="bi bi-file-earmark-arrow-down me-1"></i> {fname} <span class="badge bg-light text-dark ms-1">{count} items</span>')
        
    else:
        # Update Diffs
        for field, changes in details.items():
            # Security Masking
            if field in ['password', 'backup_codes', 'token', 'secret']:
                 html_parts.append(f'<span class="badge bg-secondary me-1">{field}: ********</span>')
                 continue

            if isinstance(changes, dict) and 'old' in changes and 'new' in changes:
                old_val = changes['old']
                new_val = changes['new']
                
                # Truncate long values
                if old_val and len(str(old_val)) > 20: old_val = str(old_val)[:20] + "..."
                if new_val and len(str(new_val)) > 20: new_val = str(new_val)[:20] + "..."
                
                if not old_val:
                    # Set
                    html_parts.append(f'<span class="badge bg-success me-1 text-white">{field}: {new_val}</span>')
                elif not new_val:
                    # Unset
                    html_parts.append(f'<span class="badge bg-danger me-1 text-white">{field}: {old_val} <i class="bi bi-x"></i></span>')
                else:
                    # Change
                    html_parts.append(f'<span class="badge bg-light text-dark border me-1">{field}: <span class="text-secondary">{old_val}</span> <i class="bi bi-arrow-right mx-1"></i> <strong>{new_val}</strong></span>')
            else:
                # Generic key-value
                html_parts.append(f'<span class="badge bg-secondary me-1">{field}: {changes}</span>')

    return "".join(html_parts)
