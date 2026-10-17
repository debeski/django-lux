from django import template

register = template.Library()


@register.inclusion_tag('dlux/pdf/viewer.html', takes_context=True)
def dlux_document_viewer(context, document, field_name='pdf_file'):
    """The PDF viewer of a registered document file, with edit/history/download wired to DjangoLux routes."""
    from dlux.files.views import document_file_context

    values = dict(context.flatten())
    values.update(document_file_context(context['request'], document, field_name))
    return values
