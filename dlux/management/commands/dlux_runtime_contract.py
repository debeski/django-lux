# dlux/management/commands/dlux_runtime_contract.py
"""
Print the DjangoLux runtime-volume contract as JSON.

Composer execs this in the app container to fetch the contract for the dlux
release that is actually running (generated `manage.py` resolves the
runtime-active release before Django loads), then checks a deployed volume
against it. See dlux/runtime_contract.py.
"""
import json

from django.core.management.base import BaseCommand

from dlux.contracts import runtime as runtime_contract


class Command(BaseCommand):
    help = "Print the DjangoLux runtime-volume contract (layout, active.json, writers) as JSON"

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(runtime_contract.load_contract(), indent=2))
