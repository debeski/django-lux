"""Shared primitives for the JSON endpoints under ``sys/api/``."""
import logging
import re

from ..system.constants import SAFE_NAMESPACE_RE

logger = logging.getLogger('dlux')

_SAFE_NAMESPACE = re.compile(SAFE_NAMESPACE_RE)
