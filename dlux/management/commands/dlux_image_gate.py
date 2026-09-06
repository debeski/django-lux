"""
Decide what a candidate project image does to the running DjangoLux release.

Composer execs this in the app container before recreating onto a new image. It
answers the question its own label-only gate cannot: whether an image that bakes
an older DjangoLux than the active one is safe to move to, because the active
release lives on the runtime volume and keeps running regardless of what the
image bakes. See `assess_image_candidate`.
"""
import json

from django.core.management.base import BaseCommand

from dlux.updater.image_update import assess_image_candidate


class Command(BaseCommand):
    help = "Report whether a candidate image adopts, keeps, or blocks the active DjangoLux release"

    def add_arguments(self, parser):
        parser.add_argument(
            "--baked-dlux-version",
            required=True,
            help="The DjangoLux version baked into the candidate image (its dlux_baked_version label).",
        )

    def handle(self, *args, **options):
        verdict = assess_image_candidate(options["baked_dlux_version"])
        self.stdout.write(json.dumps(verdict, indent=2))
