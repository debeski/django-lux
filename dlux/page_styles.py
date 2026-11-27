"""The stylesheet ``base.html`` links for registry-driven rules.

Every registered font's ``@font-face`` rules, the font picker samples, the custom
theme swatches and the default ``--dlux-main-font``/``--dlux-font-fallback``
values. They depend only on the font and theme registries, so one cacheable file
serves every page and the page needs no inline ``<style>``: projects can send
``style-src 'self'``. A face is only downloaded when a page uses its family, so
listing every registered font costs nothing.
"""

import hashlib

from .fonts import generate_font_face_css, get_default_font_family
from .themes import generate_theme_preview_css


def page_stylesheet_css():
    fallback = get_default_font_family()
    parts = [
        generate_font_face_css(),
        generate_theme_preview_css(),
        ":root{--dlux-font-fallback:'%s',sans-serif;--dlux-main-font:'%s',sans-serif}" % (fallback, fallback),
    ]
    return '\n'.join(part for part in parts if part) + '\n'


def page_stylesheet_version(css=None):
    if css is None:
        css = page_stylesheet_css()
    return hashlib.sha256(css.encode('utf-8')).hexdigest()[:16]
