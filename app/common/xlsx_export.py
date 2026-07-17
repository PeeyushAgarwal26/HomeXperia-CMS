from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from starlette.responses import StreamingResponse


def build_xlsx_response(filename: str, headers: list[str], rows: list[list[Any]]) -> StreamingResponse:
    """Builds a single-sheet .xlsx in memory and wraps it as a downloadable
    response. Used by every module's `/export` endpoint — same shape as the
    list endpoint's columns, just unpaginated and rendered to a file instead
    of JSON."""
    workbook = Workbook()
    sheet = workbook.active

    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for row in rows:
        sheet.append(row)

    for column_cells in sheet.columns:
        max_length = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells)
        sheet.column_dimensions[column_cells[0].column_letter].width = min(max_length + 2, 50)

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
