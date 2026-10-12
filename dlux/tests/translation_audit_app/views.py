"""Scanned as text by dlux_translations; never imported."""


def page(strings, t, kind):
    return [
        t('fx_title'),
        strings.get('fx_missing_everywhere', 'Fallback text'),
        t(f'fx_dyn_{kind}'),
    ]
