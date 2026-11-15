"""dlux.utils.spreadsheets — rows written to XLSX exports.

openpyxl stores any string that starts with ``=`` as a formula, and a spreadsheet
evaluates it when the file opens. Exported values come from records, activity
logs and request headers, so every string is written as a text cell.
"""


def append_text_safe_row(worksheet, values):
    """Append ``values`` as the next row, keeping every string a text cell."""
    worksheet.append(values)
    for cell in worksheet[worksheet.max_row]:
        if cell.data_type == 'f':
            cell.data_type = 's'
