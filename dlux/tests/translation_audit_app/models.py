from django.db import models


class Gadget(models.Model):
    name = models.CharField(max_length=20)

    class Meta:
        app_label = 'translation_audit_app'
        permissions = [('use_gadget', 'Can use gadget')]
