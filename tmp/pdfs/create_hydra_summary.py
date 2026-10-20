from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "pdf" / "hydra-project-summary.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

PAGE_W, PAGE_H = A4
NAVY = colors.HexColor("#071A17")
PANEL = colors.HexColor("#102C27")
MINT = colors.HexColor("#63E6B4")
TEAL = colors.HexColor("#1AAE86")
INK = colors.HexColor("#15231F")
MUTED = colors.HexColor("#5A6D67")
LIGHT = colors.HexColor("#EFF8F4")
WHITE = colors.white


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="Hero", fontName="Helvetica-Bold", fontSize=30, leading=32,
                          textColor=WHITE, spaceAfter=7))
styles.add(ParagraphStyle(name="HeroSub", fontName="Helvetica", fontSize=12.5, leading=18,
                          textColor=colors.HexColor("#CFECE2")))
styles.add(ParagraphStyle(name="Section", fontName="Helvetica-Bold", fontSize=15.5, leading=19,
                          textColor=NAVY, spaceBefore=5, spaceAfter=7))
styles.add(ParagraphStyle(name="BodyX", fontName="Helvetica", fontSize=9.4, leading=14,
                          textColor=INK, spaceAfter=5))
styles.add(ParagraphStyle(name="Small", fontName="Helvetica", fontSize=8.2, leading=12,
                          textColor=MUTED))
styles.add(ParagraphStyle(name="CardTitle", fontName="Helvetica-Bold", fontSize=10.2, leading=13,
                          textColor=NAVY, spaceAfter=3))
styles.add(ParagraphStyle(name="CardBody", fontName="Helvetica", fontSize=8.4, leading=12,
                          textColor=INK))
styles.add(ParagraphStyle(name="Quote", fontName="Helvetica-Bold", fontSize=14, leading=20,
                          textColor=NAVY, alignment=TA_CENTER))


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - 18 * mm, PAGE_W, 18 * mm, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(MINT)
    canvas.drawString(16 * mm, PAGE_H - 11.5 * mm, "HYDRA")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#BBD8CF"))
    canvas.drawRightString(PAGE_W - 16 * mm, PAGE_H - 11.5 * mm, "Hackathon Project Brief")
    canvas.setStrokeColor(colors.HexColor("#D7E8E1"))
    canvas.line(16 * mm, 14 * mm, PAGE_W - 16 * mm, 14 * mm)
    canvas.setFillColor(MUTED)
    canvas.drawString(16 * mm, 8.5 * mm, "AI browser workflows as reusable APIs")
    canvas.drawRightString(PAGE_W - 16 * mm, 8.5 * mm, f"{doc.page}")
    canvas.restoreState()


def bullet(text):
    return Paragraph(f"<font color='#1AAE86'>&#8226;</font>&nbsp;&nbsp;{text}", styles["BodyX"])


def card(title, body):
    return Table([[Paragraph(title, styles["CardTitle"]), Paragraph(body, styles["CardBody"])]],
                 colWidths=[39 * mm, 48 * mm], style=TableStyle([
                     ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                     ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBE6DC")),
                     ("VALIGN", (0, 0), (-1, -1), "TOP"),
                     ("LEFTPADDING", (0, 0), (-1, -1), 9),
                     ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                     ("TOPPADDING", (0, 0), (-1, -1), 8),
                     ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                 ]))


doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                      topMargin=25 * mm, bottomMargin=20 * mm,
                      title="Hydra Project Summary", author="Hydra Hackathon Team")
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
doc.addPageTemplates(PageTemplate(id="summary", frames=[frame], onPage=header_footer))

story = []

hero = Table([[Paragraph("HYDRA", styles["Hero"]),
               Paragraph("Turn website tasks into reusable JSON APIs", styles["HeroSub"])]],
             colWidths=[55 * mm, 113 * mm], rowHeights=[37 * mm],
             style=TableStyle([
                 ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("LEFTPADDING", (0, 0), (0, 0), 14),
                 ("LEFTPADDING", (1, 0), (1, 0), 8),
                 ("RIGHTPADDING", (1, 0), (1, 0), 14),
             ]))
story.extend([hero, Spacer(1, 6 * mm)])

story.append(Paragraph("The idea", styles["Section"]))
story.append(Paragraph(
    "Hydra is an AI-powered platform that converts a natural-language browser task into a reusable API. "
    "A user provides a website URL, describes the information they need, and confirms they are authorized "
    "to access it. Hydra navigates the website, extracts the requested data, converts it into clean JSON, "
    "and publishes an endpoint that other applications can call.", styles["BodyX"]))

story.append(Spacer(1, 2 * mm))
story.append(Paragraph("Why it matters", styles["Section"]))
story.append(Paragraph(
    "Many useful websites have no public API. Teams must browse them manually or maintain a separate scraper "
    "for every source. Those scripts often fail on JavaScript-heavy pages, complex navigation, or layout changes. "
    "Hydra lets users describe the outcome they want instead of writing scraping logic.", styles["BodyX"]))

story.append(Spacer(1, 3 * mm))
story.append(Paragraph("How it works", styles["Section"]))
steps = [
    ("1. Describe", "Enter an authorized website URL and a plain-English command."),
    ("2. Explore", "TinyFish opens a browser and navigates the live website."),
    ("3. Structure", "Groq converts the browser result into clean JSON data."),
    ("4. Publish", "Hydra saves the workflow and creates a reusable GET or POST endpoint."),
]
step_table = Table([[Paragraph(t, styles["CardTitle"]), Paragraph(b, styles["CardBody"])] for t, b in steps],
                   colWidths=[35 * mm, 133 * mm],
                   style=TableStyle([
                       ("BACKGROUND", (0, 0), (0, -1), MINT),
                       ("BACKGROUND", (1, 0), (1, -1), LIGHT),
                       ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#C9E4DA")),
                       ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                       ("LEFTPADDING", (0, 0), (-1, -1), 9),
                       ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                       ("TOPPADDING", (0, 0), (-1, -1), 7),
                       ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                   ]))
story.append(step_table)

story.append(Spacer(1, 5 * mm))
story.append(KeepTogether([
    Paragraph("One-line pitch", styles["Section"]),
    Table([[Paragraph("Hydra turns a natural-language website instruction into a reusable JSON API - without requiring the user to write a scraper.", styles["Quote"])]],
          colWidths=[168 * mm], style=TableStyle([
              ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#DDF8ED")),
              ("BOX", (0, 0), (-1, -1), 1, TEAL),
              ("LEFTPADDING", (0, 0), (-1, -1), 14),
              ("RIGHTPADDING", (0, 0), (-1, -1), 14),
              ("TOPPADDING", (0, 0), (-1, -1), 12),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
          ]))
]))

story.append(PageBreak())
story.append(Paragraph("Core capabilities", styles["Section"]))
cards = [
    ("Natural-language commands", "Users describe the browser task instead of writing selectors or automation code."),
    ("Live browser navigation", "TinyFish handles dynamic pages, navigation, and JavaScript-rendered content."),
    ("Structured responses", "Groq normalizes browser results into predictable JSON for downstream applications."),
    ("Reusable APIs", "Every successful workflow receives a GET or POST endpoint that can be called again."),
    ("Workflow dashboard", "Users can create, run, inspect, version, and remove workflows from one interface."),
    ("Read-only safety", "Hydra requires authorization and is designed for public or permitted data access."),
]
card_rows = []
for i in range(0, len(cards), 2):
    card_rows.append([card(*cards[i]), card(*cards[i + 1])])
story.append(Table(card_rows, colWidths=[84 * mm, 84 * mm], hAlign="LEFT",
                   style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                                     ("TOPPADDING", (0, 0), (-1, -1), 3),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 3)])))

story.append(Spacer(1, 5 * mm))
story.append(Paragraph("Technology stack", styles["Section"]))
stack_data = [
    ["Frontend", "React, TypeScript, Vite"],
    ["Backend", "Python, FastAPI, REST endpoints"],
    ["Database", "SQLite workflow, version, run, and event storage"],
    ["Automation", "TinyFish Agent and browser/CDP integration"],
    ["LLM", "Groq for result interpretation and JSON normalization"],
]
story.append(Table(stack_data, colWidths=[34 * mm, 134 * mm], style=TableStyle([
    ("BACKGROUND", (0, 0), (0, -1), PANEL),
    ("TEXTCOLOR", (0, 0), (0, -1), MINT),
    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
    ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#F5FAF8")),
    ("TEXTCOLOR", (1, 0), (1, -1), INK),
    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
    ("FONTSIZE", (0, 0), (-1, -1), 8.8),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBDDD7")),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
])))

story.append(Spacer(1, 5 * mm))
story.append(Paragraph("Working demonstrations", styles["Section"]))
demo_data = [
    ["Books to Scrape", "Returned five Travel books with title, price, availability, and rating."],
    ["ICAI", "Navigated the public site and returned five notification titles with PDF links."],
]
story.append(Table([[Paragraph(a, styles["CardTitle"]), Paragraph(b, styles["CardBody"])] for a, b in demo_data],
                   colWidths=[40 * mm, 128 * mm], style=TableStyle([
                       ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                       ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#C9E4DA")),
                       ("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("LEFTPADDING", (0, 0), (-1, -1), 8),
                       ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                       ("TOPPADDING", (0, 0), (-1, -1), 7),
                       ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                   ])))

story.append(Spacer(1, 5 * mm))
story.append(Paragraph("Responsible use", styles["Section"]))
for item in [
    "Use Hydra only for public information or websites where the user has permission.",
    "Respect website terms, robots.txt rules, authentication boundaries, and rate limits.",
    "Stop on CAPTCHA, access-denied responses, or technical restrictions instead of bypassing them.",
    "Use official APIs when a platform provides an approved integration path.",
]:
    story.append(bullet(item))

story.append(Spacer(1, 3 * mm))
story.append(Paragraph("Next steps", styles["Section"]))
next_items = [
    "Automatic workflow repair when page layouts change",
    "Scheduled runs, alerts, and monitoring",
    "Authentication, API tokens, and team workspaces",
]
story.append(Table([[bullet(x) for x in next_items]],
                   colWidths=[56 * mm] * 3, style=TableStyle([
                       ("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("LEFTPADDING", (0, 0), (-1, -1), 0),
                       ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                   ])))

doc.build(story)
print(OUT)
