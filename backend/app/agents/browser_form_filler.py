import os
import re
import json
import base64
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Literal
import structlog
from bson import ObjectId

from app.db.client import get_db
from app.core.system_logger import log_system_event

logger = structlog.get_logger()


class FormFillResult:
    def __init__(
        self,
        success: bool,
        status: str,
        message: str,
        target_url: str,
        fields_filled: list[dict[str, Any]],
        submit_button_found: bool = False,
        screenshot_path: str | None = None,
        screenshot_base64: str | None = None,
        questions_answered: list[dict[str, str]] | None = None,
    ):
        self.success = success
        self.status = status
        self.message = message
        self.target_url = target_url
        self.fields_filled = fields_filled
        self.submit_button_found = submit_button_found
        self.screenshot_path = screenshot_path
        self.screenshot_base64 = screenshot_base64
        self.questions_answered = questions_answered or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "message": self.message,
            "target_url": self.target_url,
            "fields_filled": self.fields_filled,
            "submit_button_found": self.submit_button_found,
            "screenshot_path": self.screenshot_path,
            "screenshot_base64": self.screenshot_base64,
            "questions_answered": self.questions_answered,
        }


class BrowserFormFillerAgent:
    """
    Autonomous AI Browser Agent for Job Applications.
    Fills candidate personal information, contact info, professional links,
    screening questions, and attaches tailored resumes.
    
    SAFETY FIRST:
    When dry_run=True (default), it stops strictly before pressing the final
    Submit / Apply button, injects a review banner, and takes a full preview screenshot.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless

    async def fill_application_form(
        self,
        job: dict[str, Any],
        user: dict[str, Any],
        profile: dict[str, Any],
        resume: dict[str, Any] | None = None,
        dry_run: bool = True,
        app_id: str | None = None,
    ) -> FormFillResult:
        from playwright.async_api import async_playwright, Page

        target_url = (
            job.get("application_url")
            or job.get("source_url")
            or job.get("apply_url")
            or job.get("url")
            or job.get("job_url")
            or job.get("link")
        )
        if not target_url or target_url.startswith("#"):
            return FormFillResult(
                success=False,
                status="FAILED",
                message="No valid application URL found for this job posting.",
                target_url="",
                fields_filled=[],
            )

        company = job.get("company", "Company")
        title = job.get("title", "Position")

        # ── 1. Extract Candidate Profile Details ──
        personal = profile.get("personal", {}) or {}
        full_name = personal.get("full_name") or personal.get("fullName") or user.get("discord_username") or "Nishant"
        name_parts = full_name.strip().split()
        first_name = name_parts[0] if name_parts else "Nishant"
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else first_name

        email = personal.get("email") or user.get("email") or "applicant@example.com"
        phone = personal.get("phone") or "+91 9971766194"
        location = personal.get("location", {})
        city = location.get("city") if isinstance(location, dict) else str(location or "Delhi NCR, India")

        linkedin = personal.get("linkedin") or "https://linkedin.com/in/applicant"
        if linkedin and not linkedin.startswith("http"):
            linkedin = f"https://{linkedin}"

        github = personal.get("github") or "https://github.com/applicant"
        if github and not github.startswith("http"):
            github = f"https://{github}"

        portfolio = personal.get("portfolio") or github or linkedin

        # Experience & Education
        experiences = profile.get("experience", []) or []
        latest_exp = experiences[0] if experiences else {}
        current_company = latest_exp.get("company", "Tech Solutions")
        current_title = latest_exp.get("title", title or "Senior Software Engineer")

        # Screening Q&A lookup map
        qa_map: dict[str, str] = {}
        for item in profile.get("qa_history", []) or []:
            if item.get("question") and item.get("answer"):
                qa_map[item["question"].lower()] = str(item["answer"])
        for item in profile.get("screening_questions", []) or []:
            if item.get("question") and item.get("answer"):
                qa_map[item["question"].lower()] = str(item["answer"])

        # Locate Resume File
        resume_path = None
        if resume and resume.get("pdf_path") and os.path.exists(resume.get("pdf_path", "")):
            resume_path = resume["pdf_path"]
        elif profile.get("resume_filename"):
            # Check candidate uploaded resumes
            possible_path = os.path.join("/tmp", profile["resume_filename"])
            if os.path.exists(possible_path):
                resume_path = possible_path

        if not resume_path:
            # Fallback to any tailored resume in storage or workspace
            storage_dir = "/app/storage/resumes"
            if not os.path.exists(storage_dir):
                storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage", "resumes")
            if os.path.exists(storage_dir):
                for root, _, files in os.walk(storage_dir):
                    for f in files:
                        if f.endswith(".pdf"):
                            resume_path = os.path.join(root, f)
                            break
                    if resume_path:
                        break

        fields_filled: list[dict[str, Any]] = []
        questions_answered: list[dict[str, str]] = []
        submit_btn_detected = False
        screenshot_path = None
        screenshot_base64 = None

        logger.info(
            "Starting autonomous form autofill",
            company=company,
            title=title,
            url=target_url,
            dry_run=dry_run,
        )

        is_in_docker = os.path.exists("/.dockerenv") or not os.environ.get("DISPLAY")
        actual_headless = True if is_in_docker else self.headless

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=actual_headless,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
            context = None
            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 900},
                )
                page = await context.new_page()

                # Navigate
                print(f"🌐 [Auto-Apply] Navigating to: {target_url}")
                try:
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
                    await page.wait_for_timeout(2000)
                except Exception as e:
                    logger.warning("Initial navigation issue, proceeding", error=str(e))

                # If on a JD landing page, find and click "Apply" button to reveal form
                await self._navigate_to_form(page)

                # ── 2. Fill Common Personal Information Fields ──
                # Name
                if await self._try_fill(page, ['input[name*="first" i]', 'input[id*="first" i]', 'input[placeholder*="first name" i]'], first_name):
                    fields_filled.append({"field": "First Name", "value": first_name, "type": "text"})
                    if await self._try_fill(page, ['input[name*="last" i]', 'input[id*="last" i]', 'input[placeholder*="last name" i]'], last_name):
                        fields_filled.append({"field": "Last Name", "value": last_name, "type": "text"})
                else:
                    # Try single full name input
                    if await self._try_fill(
                        page,
                        ['input[name="name"]', 'input[name*="full_name" i]', 'input[id*="name" i]', 'input[placeholder*="full name" i]', 'input[name="applicant_name"]'],
                        full_name,
                    ):
                        fields_filled.append({"field": "Full Name", "value": full_name, "type": "text"})

                # Email
                if await self._try_fill(page, ['input[type="email"]', 'input[name*="email" i]', 'input[id*="email" i]', 'input[placeholder*="email" i]'], email):
                    fields_filled.append({"field": "Email Address", "value": email, "type": "email"})

                # Phone
                if await self._try_fill(page, ['input[type="tel"]', 'input[name*="phone" i]', 'input[id*="phone" i]', 'input[placeholder*="phone" i]', 'input[name*="mobile" i]'], phone):
                    fields_filled.append({"field": "Phone Number", "value": phone, "type": "tel"})

                # City / Location
                if await self._try_fill(page, ['input[name*="location" i]', 'input[id*="location" i]', 'input[name*="city" i]', 'input[placeholder*="city" i]', 'input[placeholder*="location" i]'], city):
                    fields_filled.append({"field": "City / Location", "value": city, "type": "text"})

                # Professional Links
                if await self._try_fill(page, ['input[name*="linkedin" i]', 'input[id*="linkedin" i]', 'input[placeholder*="linkedin" i]', 'input[name="urls[LinkedIn]"]'], linkedin):
                    fields_filled.append({"field": "LinkedIn Profile", "value": linkedin, "type": "url"})

                if await self._try_fill(page, ['input[name*="github" i]', 'input[id*="github" i]', 'input[placeholder*="github" i]', 'input[name="urls[GitHub]"]'], github):
                    fields_filled.append({"field": "GitHub Profile", "value": github, "type": "url"})

                if await self._try_fill(page, ['input[name*="portfolio" i]', 'input[name*="website" i]', 'input[name="urls[Other]"]', 'input[placeholder*="website" i]'], portfolio):
                    fields_filled.append({"field": "Portfolio / Website", "value": portfolio, "type": "url"})

                # Current Employment
                if await self._try_fill(page, ['input[name="org"]', 'input[name*="company" i]', 'input[id*="company" i]', 'input[placeholder*="current company" i]'], current_company):
                    fields_filled.append({"field": "Current Employer", "value": current_company, "type": "text"})

                if await self._try_fill(page, ['input[name*="current_title" i]', 'input[name*="title" i]', 'input[id*="title" i]', 'input[placeholder*="current title" i]'], current_title):
                    fields_filled.append({"field": "Current Job Title", "value": current_title, "type": "text"})

                # CTC / Compensation
                ctc_val = profile.get("preferences", {}).get("min_salary") or "24 LPA"
                if isinstance(ctc_val, (int, float)):
                    ctc_val = f"₹{int(ctc_val):,} / year"
                if await self._try_fill(page, ['input[name*="ctc" i]', 'input[id*="ctc" i]', 'input[placeholder*="ctc" i]', 'input[name*="salary" i]'], str(ctc_val)):
                    fields_filled.append({"field": "Current / Expected CTC", "value": str(ctc_val), "type": "text"})

                # ── 3. Resume File Attachment ──
                if resume_path and os.path.exists(resume_path):
                    try:
                        file_input = page.locator('input[type="file"]').first
                        if await file_input.count() > 0:
                            await file_input.set_input_files(resume_path)
                            fields_filled.append({"field": "Resume PDF", "value": os.path.basename(resume_path), "type": "file"})
                    except Exception as fe:
                        logger.debug("Resume file upload skipped or not visible", error=str(fe))

                # ── 4. Standard Radio / Dropdown Options ──
                await self._handle_standard_questions(page, qa_map, questions_answered)
                for q in questions_answered:
                    fields_filled.append({"field": q["field"], "value": q["answer"], "type": "qa"})

                # ── 5. Terms & Policy Consent Checkbox ──
                try:
                    consent_boxes = page.locator('input[type="checkbox"]')
                    cnt = await consent_boxes.count()
                    for i in range(cnt):
                        box = consent_boxes.nth(i)
                        is_checked = await box.is_checked()
                        if not is_checked:
                            await box.check(timeout=2000)
                            fields_filled.append({"field": "Consent & Policy Agreement", "value": "Checked", "type": "checkbox"})
                except Exception:
                    pass

                # ── 6. DETECT SUBMIT BUTTON & STRICTLY DO NOT PRESS ──
                submit_selectors = [
                    'button[type="submit"]',
                    'input[type="submit"]',
                    '#btn-submit',
                    '#submit-app',
                    'button:has-text("Submit Application")',
                    'button:has-text("Submit")',
                    'button:has-text("Apply for this job")',
                    'button:has-text("Complete Application")',
                    'button:has-text("Submit application")',
                ]

                submit_btn = None
                for sel in submit_selectors:
                    loc = page.locator(sel).first
                    try:
                        if await loc.count() > 0 and await loc.is_visible():
                            submit_btn = loc
                            submit_btn_detected = True
                            break
                    except Exception:
                        continue

                # Inject Sleepy Apply Form Review Banner right above submit button
                try:
                    await page.evaluate("""
                        () => {
                            const submitBtns = Array.from(document.querySelectorAll('button[type="submit"], input[type="submit"], #btn-submit, #submit-app, button'));
                            const submitBtn = submitBtns.find(b => {
                                const t = (b.innerText || b.value || '').toLowerCase();
                                return t.includes('submit') || t.includes('apply');
                            });

                            const banner = document.createElement("div");
                            banner.id = "sleepy-apply-review-banner";
                            banner.style.cssText = "margin: 24px 0; padding: 18px; border-radius: 14px; background: rgba(16, 185, 129, 0.12); border: 2px dashed #10b981; color: #10b981; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; line-height: 1.5; box-shadow: 0 4px 20px rgba(16, 185, 129, 0.2);";
                            banner.innerHTML = `
                                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
                                    <span style="font-size: 18px;">⚡</span>
                                    <strong style="font-size: 15px; color: #34d399;">Sleepy Apply AI: Application Form Autofilled</strong>
                                    <span style="margin-left: auto; background: #064e3b; color: #6ee7b7; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: bold;">Review Mode</span>
                                </div>
                                <div style="color: #cbd5e1; font-size: 12px;">
                                    All candidate contact details, links, and profile questions have been filled.
                                    <strong style="color: #fbbf24;">The final submit button was intentionally NOT pressed</strong> so you can inspect and verify before final submission.
                                </div>
                            `;

                            if (submitBtn && submitBtn.parentNode) {
                                submitBtn.parentNode.insertBefore(banner, submitBtn);
                                submitBtn.style.outline = "3px solid #f59e0b";
                                submitBtn.style.outlineOffset = "4px";
                                submitBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            } else {
                                document.body.appendChild(banner);
                            }
                        }
                    """)
                    await page.wait_for_timeout(1000)
                except Exception as ie:
                    logger.debug("Banner injection skipped", error=str(ie))

                # ── 7. Capture Full Page Screenshot Preview ──
                unique_name = app_id or f"{job.get('_id', 'preview')}_{int(datetime.now().timestamp())}"
                static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "form_previews")
                os.makedirs(static_dir, exist_ok=True)
                screenshot_filename = f"form_fill_{unique_name}.png"
                full_screenshot_path = os.path.join(static_dir, screenshot_filename)

                screenshot_bytes = await page.screenshot(full_page=False)
                with open(full_screenshot_path, "wb") as f:
                    f.write(screenshot_bytes)

                screenshot_path = f"/static/form_previews/{screenshot_filename}"
                screenshot_base64 = f"data:image/png;base64,{base64.b64encode(screenshot_bytes).decode('utf-8')}"

                msg = (
                    f"✅ Form successfully autofilled with {len(fields_filled)} fields for {company} ({title}). "
                    f"Final submission button was intentionally withheld for human review."
                )

                await log_system_event(
                    level="INFO",
                    category="auto_apply",
                    message=msg,
                    details={
                        "company": company,
                        "title": title,
                        "fields_count": len(fields_filled),
                        "dry_run": dry_run,
                        "submit_button_detected": submit_btn_detected,
                    },
                )

                return FormFillResult(
                    success=True,
                    status="FORM_FILLED_READY",
                    message=msg,
                    target_url=page.url,
                    fields_filled=fields_filled,
                    submit_button_found=submit_btn_detected,
                    screenshot_path=screenshot_path,
                    screenshot_base64=screenshot_base64,
                    questions_answered=questions_answered,
                )

            finally:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass
                try:
                    await browser.close()
                except Exception:
                    pass

    async def _navigate_to_form(self, page: Any) -> None:
        """Finds and clicks 'Apply' or 'Apply for this job' button if landing on a JD view."""
        apply_triggers = [
            'a[href*="#apply"]',
            'a:has-text("Apply for this job")',
            'a:has-text("Apply Now")',
            'a:has-text("Apply")',
            'button:has-text("Apply for this job")',
            'button:has-text("Apply Now")',
            'button:has-text("Apply")',
            '[data-qa="btn-apply"]',
            '.postings-btn',
        ]
        for sel in apply_triggers:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    print(f"🔗 Clicking '{sel}' to reveal application form...")
                    await loc.click(timeout=5000)
                    await page.wait_for_timeout(1500)
                    break
            except Exception:
                continue

    async def _try_fill(self, page: Any, selectors: list[str], value: str) -> bool:
        if not value:
            return False
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    try:
                        cur_val = await loc.input_value(timeout=1000)
                    except Exception:
                        cur_val = ""
                    if not cur_val:
                        await loc.fill(value, timeout=2000)
                        return True
            except Exception:
                continue
        return False

    async def _handle_standard_questions(
        self,
        page: Any,
        qa_map: dict[str, str],
        questions_answered: list[dict[str, str]],
    ) -> None:
        """Intelligently handles dropdowns, authorization questions, and textareas."""
        # 1. Textareas (Cover letter or open ended questions)
        try:
            textareas = page.locator("textarea")
            t_count = await textareas.count()
            for i in range(min(t_count, 3)):
                ta = textareas.nth(i)
                if await ta.is_visible():
                    cur_text = await ta.input_value()
                    if not cur_text:
                        note = (
                            "I am strongly interested in this role. My background in software engineering, "
                            "system architecture, and modern scalable platforms directly matches your requirements."
                        )
                        await ta.fill(note, timeout=2000)
                        questions_answered.append({"field": "Additional Notes / Cover Summary", "answer": note})
        except Exception:
            pass

        # 2. Selects (Country, Work Authorization, etc.)
        try:
            selects = page.locator("select")
            s_count = await selects.count()
            for i in range(min(s_count, 5)):
                sel = selects.nth(i)
                if await sel.is_visible():
                    html = await sel.inner_html()
                    html_lower = html.lower()
                    try:
                        if "india" in html_lower:
                            await sel.select_option(label="India")
                        elif "yes" in html_lower:
                            await sel.select_option(label="Yes")
                    except Exception:
                        pass
        except Exception:
            pass

        # 3. Radio Buttons (e.g. Relocation, Notice Period, Authorization)
        try:
            radios = page.locator('input[type="radio"]')
            r_count = await radios.count()
            handled_groups = set()
            for i in range(r_count):
                radio = radios.nth(i)
                group_name = await radio.get_attribute("name") or ""
                if not group_name or group_name in handled_groups:
                    continue
                # If there is a "Yes" option in this radio group, check it
                try:
                    yes_radio = page.locator(f'input[type="radio"][name="{group_name}"][value="Yes"], input[type="radio"][name="{group_name}"][value="yes"]').first
                    if await yes_radio.count() > 0:
                        await yes_radio.check(timeout=1000)
                        handled_groups.add(group_name)
                        label = group_name.replace("_", " ").title()
                        questions_answered.append({"field": label, "answer": "Yes"})
                except Exception:
                    pass
        except Exception:
            pass


form_filler = BrowserFormFillerAgent()

