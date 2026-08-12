from django import forms

from ..translations import get_strings
from ..widgets import DluxFileInput


class BackupUploadForm(forms.Form):
    backup_file = forms.FileField()

    def __init__(self, *args, **kwargs):
        max_bytes = kwargs.pop('max_bytes', None)
        super().__init__(*args, **kwargs)
        strings = get_strings()
        label = strings.get('sysbackup_upload', 'Upload Backup File')
        attrs = {'accept': '.dlb,application/octet-stream'}
        if max_bytes:
            attrs['data-max-file-bytes'] = str(max_bytes)
        self.fields['backup_file'].label = label
        self.fields['backup_file'].widget = DluxFileInput(
            field_label=label,
            attrs=attrs,
        )
