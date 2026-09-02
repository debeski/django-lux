from django import forms

from ..translations import get_strings
from ..widgets import DluxFileInput


class BackupUploadForm(forms.Form):
    backup_file = forms.FileField()

    def __init__(self, *args, **kwargs):
        max_bytes = kwargs.pop('max_bytes', None)
        super().__init__(*args, **kwargs)
        strings = get_strings()
        # The card names the thing; the submit button names the act. Both reading
        # "Upload Backup File" put the same words on two controls of very different
        # size sitting side by side.
        label = strings.get('sysbackup_upload_field', 'Backup file')
        attrs = {'accept': '.dlb,application/octet-stream'}
        if max_bytes:
            attrs['data-max-file-bytes'] = str(max_bytes)
        self.fields['backup_file'].label = label
        self.fields['backup_file'].widget = DluxFileInput(
            field_label=label,
            attrs=attrs,
        )
