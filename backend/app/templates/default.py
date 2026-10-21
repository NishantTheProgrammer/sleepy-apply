import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from .base import BaseResumeTemplate


class DefaultATSResumeTemplate(BaseResumeTemplate):
    name: str = "default_ats"

    def render_pdf(self, content: dict, output_path: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()

        # Custom Typography
        title_style = ParagraphStyle(
            "ResumeTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0f172a"),
            alignment=1,  # Center
        )

        contact_style = ParagraphStyle(
            "ResumeContact",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#475569"),
            alignment=1,  # Center
        )

        section_heading = ParagraphStyle(
            "ResumeSectionHeading",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=8,
            spaceAfter=3,
        )

        body_style = ParagraphStyle(
            "ResumeBody",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#334155"),
        )

        item_title_style = ParagraphStyle(
            "ResumeItemTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#0f172a"),
        )

        bullet_style = ParagraphStyle(
            "ResumeBullet",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12.5,
            textColor=colors.HexColor("#334155"),
            leftIndent=12,
            firstLineIndent=-8,
        )

        story = []

        # 1. Header (Personal Details)
        personal = content.get("personal", {})
        name = personal.get("fullName") or personal.get("full_name") or "Candidate"
        story.append(Paragraph(name, title_style))
        story.append(Spacer(1, 4))

        contact_parts = []
        for key in ["email", "phone"]:
            val = personal.get(key)
            if val:
                contact_parts.append(str(val))

        # Location
        loc = personal.get("location")
        if isinstance(loc, dict):
            loc_parts = [loc.get(k) for k in ["city", "country"] if loc.get(k)]
            if loc_parts:
                contact_parts.append(", ".join(loc_parts))
        elif isinstance(loc, str) and loc:
            contact_parts.append(loc)

        for key in ["portfolio", "linkedin", "github"]:
            val = personal.get(key)
            if val:
                contact_parts.append(str(val).replace("https://", ""))

        if contact_parts:
            story.append(Paragraph(" • ".join(contact_parts), contact_style))
            story.append(Spacer(1, 6))

        # 2. Summary
        summary = content.get("summary")
        if summary:
            story.append(Paragraph("PROFESSIONAL SUMMARY", section_heading))
            story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#cbd5e1"), spaceAfter=5))
            story.append(Paragraph(summary, body_style))
            story.append(Spacer(1, 4))

        # 3. Skills (supports both categorized dict and flat list)
        skills_raw = content.get("skills")
        if skills_raw:
            story.append(Paragraph("TECHNICAL & PROFESSIONAL SKILLS", section_heading))
            story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#cbd5e1"), spaceAfter=5))

            if isinstance(skills_raw, dict):
                for cat, items in skills_raw.items():
                    if items:
                        cat_label = cat.capitalize()
                        story.append(Paragraph(f"<b>{cat_label}:</b> {', '.join(items)}", body_style))
            elif isinstance(skills_raw, list):
                story.append(Paragraph(" • ".join(skills_raw), body_style))
            story.append(Spacer(1, 4))

        # 4. Experience
        experience = content.get("experience", [])
        if experience:
            story.append(Paragraph("WORK EXPERIENCE", section_heading))
            story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#cbd5e1"), spaceAfter=5))
            for exp in experience:
                title = exp.get("jobTitle") or exp.get("title", "")
                company = exp.get("company", "")
                start = exp.get("startDate") or exp.get("start_date", "")
                is_curr = exp.get("current") or exp.get("is_current", False)
                end = "Present" if is_curr else (exp.get("endDate") or exp.get("end_date", ""))
                dates = f"{start} – {end}".strip(" –")

                header_text = f"<b>{title}</b> — {company}"
                if dates:
                    header_text += f" <font color='#64748b'>({dates})</font>"
                story.append(Paragraph(header_text, item_title_style))

                desc = exp.get("description")
                if desc:
                    story.append(Paragraph(desc, body_style))

                # Responsibilities
                for resp in exp.get("responsibilities", []):
                    story.append(Paragraph(f"• {resp}", bullet_style))

                # Sub-projects
                for sub in exp.get("projects", []):
                    sub_name = sub.get("name", "")
                    sub_tech = ", ".join(sub.get("technologies", []))
                    if sub_name:
                        line = f"<b>Project: {sub_name}</b>"
                        if sub_tech:
                            line += f" <i>({sub_tech})</i>"
                        story.append(Paragraph(line, item_title_style))
                    for ach in sub.get("achievements", []):
                        story.append(Paragraph(f"• {ach}", bullet_style))

                # Flat achievements
                for ach in exp.get("achievements", []):
                    story.append(Paragraph(f"• {ach}", bullet_style))

                story.append(Spacer(1, 4))

        # 5. Independent Projects
        projects = content.get("projects", [])
        if projects:
            story.append(Paragraph("PROJECTS", section_heading))
            story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#cbd5e1"), spaceAfter=5))
            for proj in projects:
                p_name = proj.get("name", "")
                tech = ", ".join(proj.get("technologies", []))
                p_desc = proj.get("description", "")
                proj_line = f"<b>{p_name}</b>"
                if tech:
                    proj_line += f" <font color='#64748b'>({tech})</font>"
                story.append(Paragraph(proj_line, item_title_style))
                if p_desc:
                    story.append(Paragraph(f"• {p_desc}", bullet_style))
                story.append(Spacer(1, 3))

        # 6. Education
        education = content.get("education", [])
        if education:
            story.append(Paragraph("EDUCATION", section_heading))
            story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#cbd5e1"), spaceAfter=5))
            for edu in education:
                inst = edu.get("institution", "")
                deg = edu.get("degree", "")
                yr = edu.get("year") or edu.get("graduation_year", "")
                line = f"<b>{deg}</b> — {inst}"
                if yr:
                    line += f" <font color='#64748b'>({yr})</font>"
                story.append(Paragraph(line, body_style))
                story.append(Spacer(1, 3))

        # 7. Achievements & Badges
        achievements = content.get("achievements", [])
        if achievements:
            story.append(Paragraph("ACHIEVEMENTS", section_heading))
            story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#cbd5e1"), spaceAfter=5))
            for ach in achievements:
                t = ach.get("title") if isinstance(ach, dict) else str(ach)
                if t:
                    story.append(Paragraph(f"• {t}", bullet_style))
            story.append(Spacer(1, 3))

        doc.build(story)
        return output_path
