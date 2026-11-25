from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generate_plan_receipt_pdf(plan_name, plan_price, customer_name, customer_email):
    """Generate a PDF receipt for an architectural plan purchase."""
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
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#333333'),
        spaceAfter=6,
    )
    story = [
        Paragraph("PLAN PURCHASE RECEIPT", title_style),
        Spacer(1, 0.2 * inch),
    ]

    receipt_data = [
        ['Receipt Number:', f'PLAN-{datetime.now().strftime("%Y%m%d%H%M%S")}'],
        ['Date:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
    ]
    receipt_table = Table(receipt_data, colWidths=[2 * inch, 4.5 * inch])
    receipt_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#666666')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#333333')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.extend([receipt_table, Spacer(1, 0.2 * inch)])

    tables = [
        ("CUSTOMER INFORMATION", [
            ['Customer Name:', customer_name],
            ['Email:', customer_email],
        ]),
        ("PLAN INFORMATION", [
            ['Plan Name:', plan_name],
            ['Price:', f'KSH {plan_price}'],
        ]),
        ("PLANNER INFORMATION", [
            ['Planner Name:', 'Victor Munene'],
            ['Phone Number:', '0724689824'],
            ['Email:', 'victorjunior@gmail.com'],
        ]),
    ]
    for heading, data in tables:
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
        Paragraph("Thank you for your purchase! For any inquiries, please contact the planner.", normal_style),
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
