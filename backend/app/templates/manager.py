import os
import io
import re
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docxtpl import DocxTemplate, RichText
import structlog

logger = structlog.get_logger()

TEMPLATES_DIR = Path(__file__).parent / "files"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATE_CATALOG = [
    {
        "id": "default",
        "name": "Default Clean ATS",
        "tagline": "Custom layout matching your Google Doc with dual-side header & section dividers",
        "badge": "Default",
        "badge_color": "emerald",
        "ats_score": 99,
        "style": "Clean Dual-Header",
        "primary_color": "#1e293b",
        "secondary_color": "#0f172a",
        "font_family": "Calibri / Arial",
        "layout": "Dual-Side Header + Dividers",
        "ideal_for": "Full Stack & Software Engineering Roles",
        "features": [
            "Google Doc Exact Match",
            "Inline Contact Bar & Links",
            "Compact Skills Grid",
            "High ATS Readability (99%)"
        ],
    },
    {
        "id": "classic_ats",
        "name": "Classic Ivy ATS",
        "tagline": "Harvard-standard monochrome layout with 100% ATS guarantee",
        "badge": "100% ATS",
        "badge_color": "slate",
        "ats_score": 100,
        "style": "Traditional Monochrome",
        "primary_color": "#000000",
        "secondary_color": "#334155",
        "font_family": "Times New Roman",
        "layout": "Universal Standard",
        "ideal_for": "Enterprise, Corporate & Fortune 500 Applications",
        "features": [
            "100% ATS Parse Rate",
            "Zero Styling Clutter",
            "Strict Chronological Order",
            "Accepted Worldwide"
        ],
    },
]


def _add_bottom_border(paragraph, color_hex="CCCCCC", sz="4"):
    """Add a subtle bottom border underline to a section heading paragraph."""
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), sz)
    bottom.set(qn('w:space'), '4')
    bottom.set(qn('w:color'), color_hex.replace("#", ""))
    pBdr.append(bottom)
    pPr.append(pBdr)


def create_classic_ats_template(output_path: Path):
    """Creates Classic Ivy ATS .docx template in 100% black-and-white standard."""
    doc = Document()
    for s in doc.sections:
        s.top_margin = Inches(0.5)
        s.bottom_margin = Inches(0.5)
        s.left_margin = Inches(0.5)
        s.right_margin = Inches(0.5)

    p_name = doc.add_paragraph()
    p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_name = p_name.add_run("{{ personal.fullName }}")
    r_name.font.name = "Times New Roman"
    r_name.font.size = Pt(18)
    r_name.font.bold = True
    r_name.font.color.rgb = RGBColor(0, 0, 0)

    p_contact = doc.add_paragraph()
    p_contact.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_contact.paragraph_format.space_after = Pt(8)
    r_contact = p_contact.add_run("{{ personal.contact_line }}")
    r_contact.font.name = "Times New Roman"
    r_contact.font.size = Pt(9.5)
    r_contact.font.color.rgb = RGBColor(0, 0, 0)

    for section_title, content_code in [
        ("SUMMARY", "{{ summary }}"),
        ("TECHNICAL SKILLS", "{% for cat in skills_categories %}{{ cat.name }}: {{ cat.items_str }}\n{% endfor %}"),
        ("PROFESSIONAL EXPERIENCE", "{% for exp in experience %}{{ exp.company }} — {{ exp.title }} ({{ exp.dates }})\n{% for resp in exp.responsibilities %}• {{ resp }}\n{% endfor %}\n{% endfor %}"),
        ("PROJECTS", "{% for proj in projects %}{{ proj.name }} | {{ proj.tech_str }}: {{ proj.description }}\n{% endfor %}"),
        ("EDUCATION", "{% for edu in education %}{{ edu.institution }} — {{ edu.degree }} ({{ edu.year }})\n{% endfor %}"),
    ]:
        p_head = doc.add_paragraph()
        p_head.paragraph_format.space_before = Pt(6)
        p_head.paragraph_format.space_after = Pt(2)
        r_head = p_head.add_run(section_title)
        r_head.font.name = "Times New Roman"
        r_head.font.size = Pt(10)
        r_head.font.bold = True
        r_head.font.color.rgb = RGBColor(0, 0, 0)
        _add_bottom_border(p_head, "000000", "4")

        p_body = doc.add_paragraph()
        p_body.paragraph_format.space_after = Pt(4)
        r_body = p_body.add_run(content_code)
        r_body.font.name = "Times New Roman"
        r_body.font.size = Pt(9.5)
        r_body.font.color.rgb = RGBColor(0, 0, 0)

    doc.save(str(output_path))


def ensure_templates_exist():
    """Ensure all template .docx files exist on disk."""
    creators = {
        "classic_ats": create_classic_ats_template,
    }
    for t_id, creator in creators.items():
        path = TEMPLATES_DIR / f"{t_id}.docx"
        if not path.exists():
            creator(path)

    path_default = TEMPLATES_DIR / "default.docx"
    if not path_default.exists() and (TEMPLATES_DIR / "default_backup.docx").exists():
        import shutil
        shutil.copyfile(TEMPLATES_DIR / "default_backup.docx", path_default)


def markdown_to_richtext(text: str) -> RichText:
    """Convert string with markdown **bold** tokens into a docxtpl RichText object."""
    if not text:
        return RichText()
    rt = RichText()
    parts = re.split(r'(\*\*[^*]+\*\*)', str(text))
    for part in parts:
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            rt.add(part[2:-2], bold=True)
        else:
            rt.add(part)
    return rt


def format_skills_rich(items: list[str], matching_skills: list[str]) -> RichText:
    """Format skills list into a RichText object with matching skills in bold."""
    rt = RichText()
    for idx, item in enumerate(items):
        clean_item = str(item).replace("**", "").strip()
        is_match = (
            clean_item.lower() in matching_skills
            or any(m in clean_item.lower() for m in matching_skills if len(m) > 3)
            or str(item).startswith("**")
        )
        if idx > 0:
            rt.add(", ")
        rt.add(clean_item, bold=is_match)
    return rt


def format_profile_for_rendering(profile: dict) -> dict:
    """Transform candidate profile dictionary into standard template rendering context."""
    personal = profile.get("personal", {})
    name = personal.get("fullName") or personal.get("full_name") or "Candidate Name"
    email = personal.get("email", "")
    phone = personal.get("phone", "")

    # Location string
    loc = personal.get("location")
    loc_str = ""
    if isinstance(loc, dict):
        loc_parts = [loc.get(k) for k in ["city", "country"] if loc.get(k)]
        loc_str = ", ".join(loc_parts)
    elif isinstance(loc, str):
        loc_str = loc

    # Contact line parts
    contact_parts = []
    if email: contact_parts.append(email)
    if phone: contact_parts.append(phone)
    if loc_str: contact_parts.append(loc_str)
    for k in ["linkedin", "github", "portfolio"]:
        val = personal.get(k)
        if val:
            clean = str(val).replace("https://", "").replace("http://", "")
            contact_parts.append(clean)

    contact_line = " • ".join(contact_parts)

    # Skills categories and lines with bold matching skills
    skills_raw = profile.get("skills", {})
    matching_skills = [str(m).lower().strip() for m in profile.get("matching_skills", []) if m]
    skills_categories = []
    skills_lines = []

    if isinstance(skills_raw, dict):
        for cat, items in skills_raw.items():
            if items:
                items_rich = format_skills_rich(items, matching_skills)
                skills_categories.append({
                    "name": cat.capitalize(),
                    "items": items,
                    "items_str": items_rich,
                })
                for i in range(0, len(items), 3):
                    chunk = items[i:i + 3]
                    skills_lines.append(format_skills_rich(chunk, matching_skills))
    elif isinstance(skills_raw, list):
        items_rich = format_skills_rich(skills_raw, matching_skills)
        skills_categories.append({
            "name": "Technical Skills",
            "items": skills_raw,
            "items_str": items_rich,
        })
        for i in range(0, len(skills_raw), 3):
            chunk = skills_raw[i:i + 3]
            skills_lines.append(format_skills_rich(chunk, matching_skills))

    # Experience with bold keywords in responsibilities
    raw_exp = profile.get("experience", [])
    experience = []
    for exp in raw_exp:
        title = exp.get("jobTitle") or exp.get("title", "")
        company = exp.get("company", "")
        start = exp.get("startDate") or exp.get("start_date", "")
        is_curr = exp.get("current") or exp.get("is_current", False)
        end = "Present" if is_curr else (exp.get("endDate") or exp.get("end_date", ""))
        dates = f"{start} – {end}".strip(" –")

        resps = exp.get("responsibilities") or exp.get("highlights") or []
        resps_rich = [markdown_to_richtext(r) for r in resps]
        achs = exp.get("achievements", [])

        # Sub-projects achievements and formatted project items
        projects_formatted = []
        for sub in exp.get("projects", []):
            for ach in sub.get("achievements", []):
                achs.append(f"[{sub.get('name', 'Project')}] {ach}")
            p_desc = sub.get("description", "")
            if not p_desc and sub.get("achievements"):
                p_desc = " ".join(sub.get("achievements"))
            projects_formatted.append({
                "title": sub.get("name", "Project"),
                "description": markdown_to_richtext(p_desc),
            })

        experience.append({
            "title": title,
            "company": company,
            "dates": dates,
            "description": markdown_to_richtext(exp.get("description", "")),
            "responsibilities": resps_rich,
            "achievements": achs,
            "projects_formatted": projects_formatted,
        })

    # Projects
    raw_proj = profile.get("projects", [])
    projects = []
    for p in raw_proj:
        tech = p.get("technologies") or p.get("tech_stack") or []
        projects.append({
            "name": p.get("name") or p.get("title", ""),
            "description": markdown_to_richtext(p.get("description", "")),
            "tech": tech,
            "tech_str": ", ".join(tech),
        })

    # Education
    raw_edu = profile.get("education", [])
    education = []
    for ed in raw_edu:
        education.append({
            "degree": ed.get("degree", ""),
            "institution": ed.get("institution", ""),
            "year": ed.get("year") or ed.get("graduation_year", ""),
        })

    has_linkedin = bool(personal.get("linkedin"))
    has_github = bool(personal.get("github"))
    has_portfolio = bool(personal.get("portfolio"))

    return {
        "personal": {
            "fullName": name,
            "email": email,
            "phone": phone,
            "location_str": loc_str,
            "contact_line": contact_line,
            "linkedin": personal.get("linkedin", ""),
            "linkedin_label": "LinkedIn®" if has_linkedin else "",
            "github": personal.get("github", ""),
            "github_label": "GitHub" if has_github else "",
            "portfolio": personal.get("portfolio", ""),
            "portfolio_label": personal.get("portfolio", "") or "portfolio",
        },
        "summary": markdown_to_richtext(profile.get("summary", "")),
        "skills_categories": skills_categories,
        "skills_lines": skills_lines,
        "experience": experience,
        "projects": projects,
        "education": education,
        "achievements": profile.get("achievements", []),
    }


def render_docx_for_profile(template_id: str, profile: dict) -> io.BytesIO:
    """Render a .docx resume using docxtpl and the chosen template."""
    ensure_templates_exist()
    template_path = TEMPLATES_DIR / f"{template_id}.docx"
    if not template_path.exists():
        template_path = TEMPLATES_DIR / "default.docx"
    if not template_path.exists():
        template_path = TEMPLATES_DIR / "classic_ats.docx"

    context = format_profile_for_rendering(profile)
    doc = DocxTemplate(template_path)
    doc.render(context)

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream
