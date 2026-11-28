"""Asset bundles that pages load on demand instead of on every page.

``dlux/base.html`` publishes these as ``#dlux-asset-bundles`` and
``dlux/base/js/lazy.js`` loads a bundle the first time it is needed: when markup
matching its ``selector`` is on the page or arrives in the dynamic modal, or when
code calls ``window.DluxAssets.load(name)``. Stylesheets load before scripts, and
scripts run in the order listed here. A bundle with ``css_before_theme`` puts its
stylesheets at ``<meta name="dlux-lazy-styles">``, ahead of the theme; the others
go at the end of ``<body>``, after it.

A bundle's ``module`` and ``worker`` are ES modules that its own loader imports
instead of ``DluxAssets``: ``dlux/pdf/js/pdfjs.js`` imports PDF.js from them.
"""

SETTINGS_SELECTOR = ', '.join((
    'form.dlux-system-setup-form',
    '.dlux-setup-builder',
    '[data-sidebar-builder]',
    '[data-navbar-builder]',
    '[data-dlux-icon-picker]',
    '[data-language-catalog-editor]',
    '[data-translation-matrix]',
    '[data-setup-font-picker]',
    '#dluxLanguageFontsEditor',
    '[data-ribbon-builder]',
    '[data-table-column-builder]',
    '[data-weather-settings]',
    '[data-ocr-settings]',
    'input[name="ribbon_layout"]',
    '[data-dlux-assets~="settings"]',
))

ASSET_BUNDLES = {
    # The System Settings editors: setup wizard steps, builders, inspector shell,
    # icon picker, and the Extra Features panels for weather and OCR.
    'settings': {
        'selector': SETTINGS_SELECTOR,
        'css_before_theme': True,
        'css': (
            'dlux/setup/css/main.css',
            'dlux/helpers/icon_picker/css/main.css',
            'dlux/helpers/inspector/css/main.css',
        ),
        'js': (
            'dlux/helpers/icon_picker/js/main.js',
            'dlux/helpers/inspector/js/main.js',
            'dlux/setup/js/dom.js',
            'dlux/setup/js/builder_model.js',
            'dlux/setup/js/appearance.js',
            'dlux/setup/js/security.js',
            'dlux/setup/js/email.js',
            'dlux/setup/js/builders.js',
            'dlux/setup/js/state.js',
            'dlux/setup/js/language.js',
            'dlux/setup/js/shell.js',
            'dlux/setup/js/previews.js',
            'dlux/setup/js/main.js',
            'dlux/weather/js/settings.js',
            'dlux/ocr/js/settings.js',
            'dlux/ribbon/js/ribbon_settings.js',
            'dlux/ribbon/js/ribbon_builder.js',
            'dlux/table_columns/js/main.js',
        ),
    },
    # The guided tour, loaded when a tour button is clicked.
    'tutorial': {
        'css': ('dlux/tutorial/css/main.css',),
        'js': ('dlux/tutorial/js/driver.js', 'dlux/tutorial/js/main.js'),
    },
    # PDF.js, imported by DluxPdfJs when the PDF viewer or page editor opens a file.
    'pdf': {
        'module': 'dlux/pdf/vendor/pdf.min.js',
        'worker': 'dlux/pdf/vendor/pdf.worker.min.js',
    },
}


def asset_bundle_urls(static_url):
    """Return ``ASSET_BUNDLES`` with each path resolved through ``static_url``."""
    resolved = {}
    for name, bundle in ASSET_BUNDLES.items():
        entry = {
            'css': [static_url(path) for path in bundle.get('css', ())],
            'js': [static_url(path) for path in bundle.get('js', ())],
        }
        for key in ('module', 'worker'):
            if bundle.get(key):
                entry[key] = static_url(bundle[key])
        if bundle.get('selector'):
            entry['selector'] = bundle['selector']
        if bundle.get('css_before_theme'):
            entry['css_before_theme'] = True
        resolved[name] = entry
    return resolved
