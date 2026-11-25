# dlux/management/commands/dlux_stack_contract.py
"""
Print the DjangoLux stack contract as JSON.

Run in the app container, it prints the contract of the dlux release actually
running (generated `manage.py` resolves the runtime-active release before
Django loads). Nothing compares a deployed compose.yml with it. See
dlux/contracts/stack.py.
"""
import json

from django.core.management.base import BaseCommand

from dlux.contracts import stack as stack_contract


class Command(BaseCommand):
    help = "Print the DjangoLux stack contract (services/networks/mounts) as JSON"

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(stack_contract.load_contract(), indent=2))
