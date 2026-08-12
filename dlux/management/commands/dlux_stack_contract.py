# dlux/management/commands/dlux_stack_contract.py
"""
Print the DjangoLux stack contract as JSON.

Composer's `composer check` drift-diff execs this in the app container to fetch
the contract for the dlux release that is actually running (generated
`manage.py` resolves the runtime-active release before Django loads), then
compares the deployment's compose.yml against it. See dlux/stack_contract.py.
"""
import json

from django.core.management.base import BaseCommand

from dlux.contracts import stack as stack_contract


class Command(BaseCommand):
    help = "Print the DjangoLux stack contract (services/networks/mounts) as JSON"

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(stack_contract.load_contract(), indent=2))
