"""Values every forms sub-module needs. Kept deliberately tiny: anything
that grows here belongs in a real module instead."""

import json
import logging
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from ..themes import get_theme_choices
from ..fonts import get_font_choices


User = get_user_model()


logger = logging.getLogger(__name__)


_LEGACY_HOME_URL = '/sys/'


THEME_CHOICES = get_theme_choices()


FONT_CHOICES = get_font_choices()


def _json_dump(value, **kwargs):
    return json.dumps(value, cls=DjangoJSONEncoder, **kwargs)
