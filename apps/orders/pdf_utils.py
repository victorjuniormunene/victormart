from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generate_order_receipt_pdf_customer(order):
    """Generate a PDF order receipt for the customer."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#ff7f31'),
        spaceAfter=12,
        alignment=1,
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#333333'),
        spaceAfter=8,
        spaceBefore=12,
    )
    story = [
        Paragraph("ORDER RECEIPT - CUSTOMER COPY", title_style),
        Spacer(1, 0.2 * inch),
    ]

    order_data = [
        ['Order Number:', order.order_number],
        ['Order Date:', order.created_at.strftime('%Y-%m-%d %H:%M:%S')],
        ['Status:', order.get_status_display()],
    ]
    order_table = Table(order_data, colWidths=[2 * inch, 4.5 * inch])
    order_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#666666')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#333333')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.extend([order_table, Spacer(1, 0.2 * inch)])

    supplier = order.product.supplier
    sections = [
        ("SUPPLIER INFORMATION", [
            ['Supplier Name:', supplier.company_name],
            ['Phone Number:', getattr(supplier.user, 'phone', 'N/A')],
            ['Email:', supplier.user.email],
        ]),
        ("PRODUCT INFORMATION", [
            ['Product Name:', order.product.name],
            ['Quantity:', str(order.quantity)],
            ['Unit Cost:', f"${order.product.cost:.2f}"],
            ['Total Cost:', f"${order.total_cost:.2f}"],
        ]),
    ]
    for heading, data in sections:
        story.append(Paragraph(heading, heading_style))
        table = Table(data, colWidths=[2 * inch, 4.5 * inch])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#666666')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#333333')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e0e0e0')),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        story.extend([table, Spacer(1, 0.2 * inch)])

    story.extend([
        Spacer(1, 0.1 * inch),
        Paragraph(
            f"Generated on: {datetime.now().strftime('%B %d, %Y at %H:%M:%S')}",
            ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontSize=9,
                textColor=colors.HexColor('#999999'),
                alignment=1,
            ),
        ),
    ])
    document.build(story)
    buffer.seek(0)
    return buffer
