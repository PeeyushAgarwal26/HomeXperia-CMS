"""Order invoice PDF — a fresh, standard commercial-invoice layout (no prior
invoice PDF exists anywhere to port; homexperia-client-backend has no order
code at all). Deliberately uses only FPDF's built-in "helvetica" font, unlike
the visualizer's design-report generator (imaging/pdf_generator.py), which
depends on custom font files that may or may not exist in a given
environment — an invoice has no reason to take on that risk.

Synchronous by design, same convention as the visualizer's PDF generator —
the async service layer runs this via anyio.to_thread.run_sync."""

from __future__ import annotations

from fpdf import FPDF

from app.modules.customers.models import Customer
from app.modules.orders.models import Order, OrderItem

_COLUMN_WIDTHS = {
    "item": 48,
    "category": 26,
    "design_no": 22,
    "size": 18,
    "uom": 16,
    "rate": 22,
    "qty": 14,
    "amount": 24,
}


class InvoicePDF(FPDF):
    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, "Thank you for your business.", align="C")


def _table_header(pdf: InvoicePDF) -> None:
    pdf.set_font("helvetica", "B", 9)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(_COLUMN_WIDTHS["item"], 8, "Item", border=1, fill=True)
    pdf.cell(_COLUMN_WIDTHS["category"], 8, "Category", border=1, fill=True, align="C")
    pdf.cell(_COLUMN_WIDTHS["design_no"], 8, "Design No", border=1, fill=True, align="C")
    pdf.cell(_COLUMN_WIDTHS["size"], 8, "Size", border=1, fill=True, align="C")
    pdf.cell(_COLUMN_WIDTHS["uom"], 8, "UOM", border=1, fill=True, align="C")
    pdf.cell(_COLUMN_WIDTHS["rate"], 8, "Rate", border=1, fill=True, align="R")
    pdf.cell(_COLUMN_WIDTHS["qty"], 8, "Qty", border=1, fill=True, align="R")
    pdf.cell(_COLUMN_WIDTHS["amount"], 8, "Amount", border=1, fill=True, align="R")
    pdf.ln()


def generate_invoice_pdf(order: Order, customer: Customer, items: list[OrderItem]) -> bytes:
    pdf = InvoicePDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(True, margin=20)
    pdf.add_page()

    pdf.set_font("helvetica", "B", 20)
    pdf.cell(0, 10, "HomeXperia", align="L")
    pdf.set_font("helvetica", "", 10)
    pdf.set_xy(-70, 10)
    pdf.cell(60, 6, f"Invoice #: {order.invoice_number}", align="R")
    pdf.set_xy(-70, 16)
    pdf.cell(60, 6, f"Date: {order.created_at:%d %b %Y}", align="R")
    pdf.ln(16)

    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    col_x = [10, 105]
    col_y = pdf.get_y()
    pdf.set_xy(col_x[0], col_y)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(90, 6, "Bill To")
    pdf.set_xy(col_x[1], col_y)
    pdf.cell(90, 6, "Retailer Account")
    pdf.ln(6)

    pdf.set_font("helvetica", "", 10)
    pdf.set_xy(col_x[0], pdf.get_y())
    pdf.multi_cell(90, 6, f"{order.client_name}\n{order.client_email}\n{order.client_whatsapp_no}")
    bill_to_bottom = pdf.get_y()

    pdf.set_xy(col_x[1], col_y + 6)
    pdf.multi_cell(90, 6, f"{customer.name} ({customer.customer_code})\n{order.owner_email}\n{order.owner_whatsapp_no}")

    pdf.set_y(max(bill_to_bottom, pdf.get_y()) + 6)

    _table_header(pdf)
    pdf.set_font("helvetica", "", 9)
    for item in items:
        if pdf.get_y() > 260:
            pdf.add_page()
            _table_header(pdf)
            pdf.set_font("helvetica", "", 9)
        size_label = f'{item.width:g}"' if item.width is not None else "-"
        pdf.cell(_COLUMN_WIDTHS["item"], 8, item.catalog_name[:28], border=1)
        pdf.cell(_COLUMN_WIDTHS["category"], 8, (item.category_name or "-")[:16], border=1, align="C")
        pdf.cell(_COLUMN_WIDTHS["design_no"], 8, item.design_no or "-", border=1, align="C")
        pdf.cell(_COLUMN_WIDTHS["size"], 8, size_label, border=1, align="C")
        pdf.cell(_COLUMN_WIDTHS["uom"], 8, item.uom, border=1, align="C")
        pdf.cell(_COLUMN_WIDTHS["rate"], 8, f"{item.rate:.2f}", border=1, align="R")
        pdf.cell(_COLUMN_WIDTHS["qty"], 8, str(item.quantity), border=1, align="R")
        pdf.cell(_COLUMN_WIDTHS["amount"], 8, f"{item.amount:.2f}", border=1, align="R")
        pdf.ln()

    total_label_width = sum(
        _COLUMN_WIDTHS[k] for k in ("item", "category", "design_no", "size", "uom", "rate", "qty")
    )
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(total_label_width, 9, "Total", border=1, align="R")
    pdf.cell(_COLUMN_WIDTHS["amount"], 9, f"{order.total_amount:.2f}", border=1, align="R")
    pdf.ln(12)

    if order.notes:
        pdf.set_font("helvetica", "I", 9)
        pdf.multi_cell(0, 6, f"Notes: {order.notes}")

    return bytes(pdf.output())
