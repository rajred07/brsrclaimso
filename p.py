"""
Script to generate a 12-slide PowerPoint (.pptx) presentation on
'ACCOUNT HEADS OF THE INDIAN ARMY' following the military template specs.

Prerequisite:
    pip install python-pptx
"""

import sys
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

def create_army_account_heads_presentation(output_filename="Indian_Army_Account_Heads.pptx"):
    # Initialize 16:9 Widescreen Presentation
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # Theme Colors matching the demo slides template
    COLOR_MAROON = RGBColor(128, 0, 0)
    COLOR_YELLOW = RGBColor(255, 255, 0)
    COLOR_BLACK  = RGBColor(0, 0, 0)
    COLOR_RED    = RGBColor(255, 0, 0)
    COLOR_BLUE   = RGBColor(0, 0, 255)
    COLOR_GREEN  = RGBColor(0, 128, 0)

    # Bullet colors in strict sequence: Red -> Blue -> Green -> Black
    COLOR_SEQUENCE = [COLOR_RED, COLOR_BLUE, COLOR_GREEN, COLOR_BLACK]

    def add_base_template(slide, header_title):
        """Adds the standard maroon header bar and inner black frame border."""
        # 1. Maroon Header Bar (Top)
        header_shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(1.1)
        )
        header_shape.fill.solid()
        header_shape.fill.fore_color.rgb = COLOR_MAROON
        header_shape.line.fill.background()

        header_tf = header_shape.text_frame
        header_tf.word_wrap = True
        p_head = header_tf.paragraphs[0]
        p_head.text = header_title.upper()
        p_head.font.size = Pt(30)
        p_head.font.bold = True
        p_head.font.underline = True
        p_head.font.color.rgb = COLOR_YELLOW
        p_head.alignment = PP_ALIGN.CENTER

        # 2. Black Inner Frame Line
        frame_shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(1.4), Inches(12.333), Inches(5.6)
        )
        frame_shape.fill.background()  # Transparent background
        frame_shape.line.color.rgb = COLOR_BLACK
        frame_shape.line.width = Pt(2.25)

    def add_standard_slide(header_title, subhead_title, bullet_items):
        """Creates a slide with subhead and sequential color bullet points."""
        slide = prs.slides.add_slide(blank_layout)
        add_base_template(slide, header_title)

        # 1. Red Sub-Header
        subhead_box = slide.shapes.add_textbox(Inches(0.8), Inches(1.6), Inches(11.733), Inches(0.8))
        tf_sub = subhead_box.text_frame
        tf_sub.word_wrap = True
        p_sub = tf_sub.paragraphs[0]
        p_sub.text = subhead_title.upper()
        p_sub.font.size = Pt(24)
        p_sub.font.bold = True
        p_sub.font.underline = True
        p_sub.font.color.rgb = COLOR_RED
        p_sub.alignment = PP_ALIGN.CENTER

        # 2. Bullet Points List
        content_box = slide.shapes.add_textbox(Inches(1.2), Inches(2.5), Inches(10.933), Inches(4.2))
        tf_content = content_box.text_frame
        tf_content.word_wrap = True

        for idx, text in enumerate(bullet_items):
            p = tf_content.add_paragraph() if idx > 0 else tf_content.paragraphs[0]
            p.text = f">  {text}"
            p.font.size = Pt(21)
            p.font.bold = True
            p.space_after = Pt(16)
            
            # Sequence bullet colors: Red -> Blue -> Green -> Black
            color_choice = COLOR_SEQUENCE[idx % len(COLOR_SEQUENCE)]
            p.font.color.rgb = color_choice

        return slide

    # ==========================================
    # SLIDE 1: TITLE SLIDE
    # ==========================================
    slide1 = prs.slides.add_slide(blank_layout)
    add_base_template(slide1, "ACCOUNT HEADS OF THE INDIAN ARMY")
    
    t_box = slide1.shapes.add_textbox(Inches(1.0), Inches(2.2), Inches(11.333), Inches(4.0))
    tf1 = t_box.text_frame
    tf1.word_wrap = True
    
    p1 = tf1.paragraphs[0]
    p1.text = "DIRECTED BY DGFP INDIA"
    p1.font.size = Pt(26)
    p1.font.bold = True
    p1.font.underline = True
    p1.font.color.rgb = COLOR_RED
    p1.alignment = PP_ALIGN.CENTER
    p1.space_after = Pt(24)

    p2 = tf1.add_paragraph()
    p2.text = "Financial Planning & Budgetary Accounting Structure"
    p2.font.size = Pt(28)
    p2.font.bold = True
    p2.font.color.rgb = COLOR_BLACK
    p2.alignment = PP_ALIGN.CENTER
    p2.space_after = Pt(18)

    p3 = tf1.add_paragraph()
    p3.text = "Detailed Analysis of Major & Minor Account Heads"
    p3.font.size = Pt(22)
    p3.font.bold = True
    p3.font.color.rgb = COLOR_BLUE
    p3.alignment = PP_ALIGN.CENTER

    # ==========================================
    # SLIDE 2: DIRECTED BY DGFP INDIA
    # ==========================================
    add_standard_slide(
        header_title="DGFP: STRATEGIC DIRECTION",
        subhead_title="DIRECTED BY DGFP INDIA",
        bullet_items=[
            "Directorate General of Financial Planning (DGFP) governs Army budget",
            "Formulates long-term and annual financial plans for defence readiness",
            "Monitors expenditure allocations across all commands & formations",
            "Ensures optimal resource utilization and financial discipline"
        ]
    )

    # ==========================================
    # SLIDE 3: CONCEPT OF ACCOUNT HEADS
    # ==========================================
    add_standard_slide(
        header_title="CONCEPT OF ACCOUNT HEADS",
        subhead_title="TYPES & SIGNIFICANCE",
        bullet_items=[
            "Standardized accounting codes used to classify government expenditure",
            "Major Heads: Define broad functions of the Indian Army",
            "Minor Heads: Identify specific programs and activities",
            "Ensures parliamentary control and financial transparency",
            "Facilitates auditing by CGDA, CDAO, and CAG India"
        ]
    )

    # ==========================================
    # SLIDE 4: CLASSIFICATION HIERARCHY
    # ==========================================
    add_standard_slide(
        header_title="CLASSIFICATION HIERARCHY",
        subhead_title="6-TIER ACCOUNTING STRUCTURE",
        bullet_items=[
            "MAJOR HEAD (4-Digit): Defines the Function (e.g., Army Revenue)",
            "MINOR HEAD (3-Digit): Defines Program / Purpose (e.g., Stores, Pay)",
            "SUB HEAD (2-Digit): Defines Sub-Scheme / Activity",
            "DETAILED HEAD (2-Digit): Defines Sub-activity details",
            "OBJECT HEAD (2-Digit): Defines exact object of spend (e.g., Rations)"
        ]
    )

    # ==========================================
    # SLIDE 5: WHAT THEY GOVERN
    # ==========================================
    add_standard_slide(
        header_title="WHAT THEY GOVERN",
        subhead_title="PRIMARY FUNCTIONAL HEADS",
        bullet_items=[
            "MH 2076 (Revenue): Governs recurring operational expenditure",
            "Deals with pay & allowances, rations, stores, and transport maintenance",
            "MH 4076 (Capital): Governs non-recurring capital investments",
            "Deals with land acquisition, weapon systems, tanks, & infrastructure"
        ]
    )

    # ==========================================
    # SLIDE 6: BREAKDOWN OF MAJOR HEADS
    # ==========================================
    add_standard_slide(
        header_title="MAJOR HEADS BREAKDOWN",
        subhead_title="REVENUE VS CAPITAL HEADS",
        bullet_items=[
            "Revenue Heads: MH 2076 (Army), MH 2077 (Navy), MH 2078 (Air Force)",
            "Capital Outlay: MH 4076 encompasses capital for all 3 services",
            "MH 2076 consists of Minor Heads 101 through 800",
            "MH 4076 contains Sub-Major Head 01 dedicated to Army Capital"
        ]
    )

    # ==========================================
    # SLIDE 7: MINOR HEADS DETAILS
    # ==========================================
    add_standard_slide(
        header_title="MINOR HEADS (3-DIGIT)",
        subhead_title="PROGRAM LEVEL IDENTIFICATION",
        bullet_items=[
            "Minor Head 101: Pay & Allowances for Officers & Personnel (PBOR)",
            "Minor Head 110: Stores (Rations, Ordnance spares, Arms, Ammunition)",
            "Minor Head 105: Transportation (Move of troops, rail/air freight, POL)",
            "Minor Head 111: Works (Maintenance of cantonments & barracks)"
        ]
    )

    # ==========================================
    # SLIDE 8: REVENUE EXPENDITURE (MH 2076)
    # ==========================================
    add_standard_slide(
        header_title="REVENUE EXPENDITURE",
        subhead_title="MH 2076: DAILY OPERATIONS",
        bullet_items=[
            "Sustenance and operational maintenance of the standing army",
            "Operation & Maintenance (O&M) recurring costs",
            "Routine logistics support, training exercises, and repairs",
            "Focuses on immediate combat readiness without asset creation"
        ]
    )

    # ==========================================
    # SLIDE 9: CAPITAL EXPENDITURE (MH 4076)
    # ==========================================
    add_standard_slide(
        header_title="CAPITAL EXPENDITURE",
        subhead_title="MH 4076: MODERNIZATION",
        bullet_items=[
            "Non-recurring large-scale capital investments",
            "Minor Head 050: Land acquisition for firing ranges & bases",
            "Minor Head 102: Heavy Vehicles (Tanks, BMPs, Armoured Fighting Vehicles)",
            "Minor Head 103: Other Equipment (Artillery, Radars, Missiles)"
        ]
    )

    # ==========================================
    # SLIDE 10: SUB & DETAILED HEADS
    # ==========================================
    add_standard_slide(
        header_title="SPECIFIC SPEND LEVELS",
        subhead_title="SUB HEAD & DETAILED HEAD",
        bullet_items=[
            "Sub Head (2-Digit): Identifies specific unit type or scheme",
            "Example: ASC Supplies / Ordnance Depots / Infantry Formations",
            "Detailed Head: Identifies exact sub-item of expenditure",
            "Object Head: Exact bill item code (e.g., Provisions / Dry Rations)"
        ]
    )

    # ==========================================
    # SLIDE 11: BUDGET ALLOCATION FLOW
    # ==========================================
    add_standard_slide(
        header_title="BUDGET ALLOCATION FLOW",
        subhead_title="THE FINANCIAL CHAIN",
        bullet_items=[
            "Step 1: Ministry of Finance & Parliament pass Demand No. 20",
            "Step 2: Ministry of Defence (MoD) allocates budget to DGFP",
            "Step 3: DGFP / Army HQ distributes across Major & Minor Heads",
            "Step 4: Command HQs allocate funds down to Unit Level for spending"
        ]
    )

    # ==========================================
    # SLIDE 12: DISCUSSION & CONCLUSION
    # ==========================================
    add_standard_slide(
        header_title="DISCUSSION / Q&A",
        subhead_title="SUMMARY & CONCLUSION",
        bullet_items=[
            "Strategic alignment of financial resources with national defence requirements",
            "Precision accounting ensured through 4-digit Major and 3-digit Minor heads",
            "Rigorous audit oversight by CGDA, CDAO, and CAG India",
            "Open for Questions & Discussion"
        ]
    )

    # Save presentation
    prs.save(output_filename)
    print(f"Presentation successfully created and saved as '{output_filename}'")

if __name__ == "__main__":
    create_army_account_heads_presentation()