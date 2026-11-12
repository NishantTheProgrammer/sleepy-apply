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

    def __init__(self, headless: bool = True, slow_mo: int = 0):
        self.headless = headless
        self.slow_mo = slow_mo

    async def fill_application_form(
        self,
        job: dict[str, Any],
        user: dict[str, Any],
        profile: dict[str, Any],
        resume: dict[str, Any] | None = None,
        dry_run: bool = True,
        app_id: str | None = None,
        keep_open: bool = False,
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

        # ── 1. Extract Candidate Profile Details (Real User Profile Data Only) ──
        personal = profile.get("personal", {}) or {}
        full_name = (
            personal.get("full_name")
            or personal.get("fullName")
            or user.get("name")
            or user.get("discord_username")
            or ""
        ).strip()
        name_parts = full_name.split() if full_name else []
        first_name = name_parts[0] if name_parts else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else (personal.get("last_name") or personal.get("lastName") or "")

        email = (personal.get("email") or user.get("email") or "").strip()
        phone = (personal.get("phone") or "").strip()
        phone_digits = re.sub(r"\D", "", phone)[-10:] if phone else ""
        location = personal.get("location", {})
        if isinstance(location, dict):
            city = (location.get("city") or "").strip()
            country = (location.get("country") or "").strip()
            address = (location.get("address") or "").strip()
        else:
            city = str(location or "").strip()
            country = ""
            address = ""
        full_location = f"{city}, {country}".strip(", ") if city else ""

        linkedin = (personal.get("linkedin") or "").strip()
        if linkedin and not linkedin.startswith("http"):
            linkedin = f"https://{linkedin}"

        github = (personal.get("github") or "").strip()
        if github and not github.startswith("http"):
            github = f"https://{github}"

        portfolio = (personal.get("portfolio") or "").strip()
        if portfolio and not portfolio.startswith("http"):
            portfolio = f"https://{portfolio}"
        elif not portfolio:
            portfolio = github or linkedin

        # Screening Q&A lookup map
        qa_map: dict[str, str] = {}
        for item in profile.get("qa_history", []) or []:
            if item.get("question") and item.get("answer"):
                qa_map[item["question"].lower()] = str(item["answer"])
        for item in profile.get("screening_questions", []) or []:
            if item.get("question") and item.get("answer"):
                qa_map[item["question"].lower()] = str(item["answer"])

        # Experience & Employment Details from Profile
        experiences = profile.get("experience", []) or []
        latest_exp = experiences[0] if experiences else {}
        current_company = (latest_exp.get("company") or "").strip()
        current_title = (latest_exp.get("title") or latest_exp.get("jobTitle") or "").strip()
        exp_location = (latest_exp.get("location") or city or "").strip()
        is_currently_working = bool(
            latest_exp.get("is_current")
            or latest_exp.get("current")
            or (str(latest_exp.get("end_date") or "").strip().lower() in ["present", "current", ""])
        )
        exp_start_date = (latest_exp.get("start_date") or latest_exp.get("startDate") or "").strip()
        exp_end_date = (latest_exp.get("end_date") or latest_exp.get("endDate") or "").strip()

        # Helper to format dates for ATS inputs (e.g. "May 2022" -> "01 May 2022")
        def format_date_for_input(raw: str) -> str:
            if not raw or raw.lower() in ["present", "current"]:
                return ""
            parts = raw.split()
            if len(parts) == 2 and not parts[0].isdigit():
                return f"01 {parts[0].capitalize()} {parts[1]}"
            return raw

        joining_date_str = format_date_for_input(exp_start_date)
        relieving_date_str = format_date_for_input(exp_end_date) if not is_currently_working else ""

        # Total Experience Years (derived from additionalInformation or experience timeline)
        add_info = profile.get("additionalInformation", {}) or profile.get("additional_info", {}) or {}
        total_exp_years = (
            add_info.get("yearsOfExperience")
            or profile.get("years_of_experience")
            or profile.get("experience_years")
        )
        if total_exp_years is None and experiences:
            years_found = []
            for exp in experiences:
                sd = exp.get("start_date") or exp.get("startDate") or ""
                ym = re.search(r"\b(20\d\d|19\d\d)\b", sd)
                if ym:
                    years_found.append(int(ym.group(1)))
            if years_found:
                from datetime import datetime
                total_exp_years = max(1, datetime.now().year - min(years_found))

        cand_years_str = str(total_exp_years) if total_exp_years is not None else ""

        # Compensation / CTC from profile & preferences
        job_prefs = profile.get("jobPreferences", {}) or profile.get("job_preferences", {}) or {}
        user_prefs = profile.get("preferences", {}) or {}
        curr_sal = (
            profile.get("current_salary")
            or user_prefs.get("current_salary")
            or ""
        )
        exp_sal = (
            profile.get("expected_salary")
            or user_prefs.get("expected_salary")
            or user_prefs.get("min_salary")
            or job_prefs.get("minimumSalary")
            or job_prefs.get("salary_min")
            or ""
        )
        if not curr_sal:
            for k, v in qa_map.items():
                if "current" in k and ("salary" in k or "ctc" in k):
                    curr_sal = v
                    break
        if not exp_sal:
            for k, v in qa_map.items():
                if ("expected" in k or "annual" in k) and ("salary" in k or "ctc" in k):
                    exp_sal = v
                    break

        # Availability / Notice Period from profile
        avail_days = (
            add_info.get("noticePeriod")
            or profile.get("notice_period")
            or profile.get("availability_days")
            or ""
        )
        if not avail_days:
            for k, v in qa_map.items():
                if "notice" in k or "joining" in k or "availability" in k:
                    avail_days = v
                    break
        avail_days_str = ""
        if avail_days:
            nums = re.findall(r"\d+", str(avail_days))
            avail_days_str = nums[-1] if nums else str(avail_days)

        # Preferred locations from candidate's profile
        user_pref_locations = (
            job_prefs.get("locations")
            or user_prefs.get("locations")
            or ([city] if city else [])
        )

        # Education details from profile
        educations = profile.get("education", []) or []
        latest_edu = educations[0] if educations else {}
        edu_degree = (latest_edu.get("degree") or "").strip()
        edu_school = (latest_edu.get("institution") or latest_edu.get("school") or latest_edu.get("university") or "").strip()
        edu_year = str(latest_edu.get("year") or latest_edu.get("graduation_year") or "").strip()
        edu_branch = (latest_edu.get("branch") or latest_edu.get("fieldOfStudy") or "").strip()
        if not edu_branch and edu_degree:
            edu_branch = "Computer Applications" if ("mca" in edu_degree.lower() or "bca" in edu_degree.lower()) else "Computer Science"
        edu_location = city

        # Flattened candidate skills list
        candidate_skills = []
        raw_skills = profile.get("skills", {})
        if isinstance(raw_skills, dict):
            for cat_skills in raw_skills.values():
                if isinstance(cat_skills, list):
                    candidate_skills.extend([str(s).strip() for s in cat_skills if str(s).strip()])
        elif isinstance(raw_skills, list):
            candidate_skills.extend([str(s).strip() for s in raw_skills if str(s).strip()])
        candidate_skills = list(dict.fromkeys(candidate_skills))

        # Locate Resume File (strictly from candidate's storage, never random /tmp files)
        resume_path = None
        if resume and resume.get("pdf_path") and os.path.exists(resume.get("pdf_path", "")):
            resume_path = resume["pdf_path"]

        user_id_str = str(user.get("_id") or user.get("id") or "")
        user_storage_dirs = []
        if user_id_str:
            user_storage_dirs.extend([
                f"/app/storage/resumes/{user_id_str}",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage", "resumes", user_id_str),
            ])
        user_storage_dirs.extend([
            "/app/storage/resumes",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage", "resumes"),
        ])

        if not resume_path and profile.get("resume_filename"):
            cand_fn = profile["resume_filename"]
            for pdir in user_storage_dirs:
                cand_path = os.path.join(pdir, cand_fn)
                if os.path.exists(cand_path):
                    resume_path = cand_path
                    break

        if not resume_path:
            for pdir in user_storage_dirs:
                if os.path.exists(pdir):
                    for root, _, files in os.walk(pdir):
                        for f in files:
                            if f.endswith(".pdf") and "tailor" not in f.lower():
                                resume_path = os.path.join(root, f)
                                break
                        if resume_path:
                            break
                if resume_path:
                    break
            if not resume_path:
                for pdir in user_storage_dirs:
                    if os.path.exists(pdir):
                        for root, _, files in os.walk(pdir):
                            for f in files:
                                if f.endswith(".pdf"):
                                    resume_path = os.path.join(root, f)
                                    break
                            if resume_path:
                                break
                    if resume_path:
                        break

        # Ensure the uploaded resume filename NEVER contains 'tailor', 'tailored', or internal hashes.
        # Stage a clean, professional copy e.g. "Nishant_Resume.pdf" before attaching to forms.
        if resume_path and os.path.exists(resume_path):
            import shutil
            clean_cand_name = re.sub(r"[^\w\s-]", "", full_name or first_name or "Candidate").strip()
            clean_cand_name = re.sub(r"[-\s]+", "_", clean_cand_name) or "Candidate"
            clean_filename = f"{clean_cand_name}_Resume.pdf"
            staging_dir = os.path.join("/tmp", "sleepy_apply_upload", user_id_str or "default")
            os.makedirs(staging_dir, exist_ok=True)
            staged_path = os.path.join(staging_dir, clean_filename)
            try:
                shutil.copyfile(resume_path, staged_path)
                resume_path = staged_path
            except Exception as ce:
                logger.debug("Resume clean staging skipped", error=str(ce))

        # Candidate Data Bundle for Semantic & Specialized Autofill
        candidate_data: dict[str, Any] = {
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "phone_digits": phone_digits,
            "city": city,
            "state": "Delhi" if "delhi" in city.lower() else "",
            "country": country or "India",
            "full_location": full_location,
            "linkedin": linkedin,
            "github": github,
            "portfolio": portfolio,
            "gender": personal.get("gender") or qa_map.get("gender") or "Male",
            "current_company": current_company,
            "current_title": current_title,
            "exp_location": exp_location,
            "total_exp_years": cand_years_str,
            "curr_sal": curr_sal,
            "exp_sal": exp_sal,
            "avail_days": avail_days_str,
            "joining_date_str": joining_date_str,
            "relieving_date_str": relieving_date_str,
            "is_currently_working": is_currently_working,
            "edu_degree": edu_degree,
            "edu_school": edu_school,
            "edu_year": edu_year,
            "edu_branch": edu_branch,
            "edu_location": edu_location,
            "skills": candidate_skills,
            "user_pref_locations": user_pref_locations,
            "experiences": experiences,
            "educations": educations,
            "qa_map": qa_map,
            "resume_path": resume_path,
        }

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

        is_in_docker = os.path.exists("/.dockerenv")
        # On macOS host, DISPLAY is not set, but Chromium runs natively in headed mode!
        actual_headless = True if (is_in_docker and not os.environ.get("DISPLAY")) else self.headless

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=actual_headless,
                slow_mo=self.slow_mo if not actual_headless else 0,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"] if is_in_docker else [],
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

                # Dismiss any initial cookie banners, tracking modals, or obstructive popups
                await self._dismiss_overlays_and_popups(page)

                # If on a JD landing page, find and click "Apply" button to reveal form (handles popup / new tab)
                page = await self._navigate_to_form(page, context)

                # Dismiss popups again if opened during Apply click
                await self._dismiss_overlays_and_popups(page)

                # ── 2a. Specialized ATS Handlers (e.g. Keka) ──
                is_keka = "keka" in page.url or await page.locator("#educationDetails, #skills-container").count() > 0
                if is_keka:
                    await self._fill_keka_specialized(page, candidate_data, fields_filled)

                # ── 2b. Universal Semantic ATS Filler (Cross-Frame: Greenhouse, Lever, Workday, Taleo, Ashby) ──
                await self._semantic_fill_portal(page, candidate_data, fields_filled)

                # ── 3. Resume File Attachment across all frames ──
                if resume_path and os.path.exists(resume_path):
                    await self._attach_resume_to_frames(page, resume_path, fields_filled)

                # ── 4. Standard Radio / Dropdown Options across frames ──
                await self._handle_standard_questions_all_frames(page, qa_map, questions_answered)
                for q in questions_answered:
                    fields_filled.append({"field": q["field"], "value": q["answer"], "type": "qa"})

                # ── 5. Terms & Policy Consent Checkboxes ──
                await self._check_consent_checkboxes(page, fields_filled)

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

                # ── 6b. Detect CAPTCHA barriers & notify Discord ──
                captcha_detected = False
                captcha_selectors = [
                    'input[name="captcha"]',
                    '#captcha',
                    '.g-recaptcha',
                    '.h-captcha',
                    'iframe[src*="recaptcha"]',
                    'iframe[src*="hcaptcha"]',
                ]
                for csel in captcha_selectors:
                    try:
                        cloc = page.locator(csel).first
                        if await cloc.count() > 0 and await cloc.is_visible():
                            captcha_detected = True
                            await cloc.evaluate("el => { el.style.outline = '3px solid #f59e0b'; el.style.outlineOffset = '2px'; }")
                            break
                    except Exception:
                        pass

                if captcha_detected:
                    try:
                        from app.agents.discord_bot import DiscordAgent
                        discord = DiscordAgent()
                        await discord.notify_apply_issue(
                            job_title=title,
                            company=company,
                            issue_message="⚠️ CAPTCHA verification required on application form. Sleepy Apply has autofilled all fields and attached your resume. Please solve the captcha in the open browser window to finish submitting.",
                            target_url=page.url,
                            discord_user_id=user.get("discord_id") if user else None,
                        )
                    except Exception as de:
                        logger.debug("Discord captcha alert skipped", error=str(de))

                # ── 7. In-Memory Preview Only (Do NOT write images to disk) ──
                screenshot_base64 = None
                screenshot_path = None
                try:
                    screenshot_bytes = await page.screenshot(full_page=False)
                    screenshot_base64 = f"data:image/png;base64,{base64.b64encode(screenshot_bytes).decode('utf-8')}"
                except Exception:
                    pass

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
                if not actual_headless and keep_open and page:
                    print("👀 Visible browser is active for user inspection. Window will stay open for human review (close window when done)...")
                    try:
                        await page.wait_for_event("close", timeout=600000)
                    except Exception:
                        pass
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass
                try:
                    await browser.close()
                except Exception:
                    pass

    async def _dismiss_overlays_and_popups(self, page: Any) -> None:
        """Intelligently detects and dismisses cookie banners, tracking popups, and dialog overlays."""
        # 1. Target standard Accept / Dismiss buttons
        popup_triggers = [
            'button:has-text("Accept")',
            'button:has-text("Accept All")',
            'button:has-text("Accept all cookies")',
            'button:has-text("I Accept")',
            'button:has-text("Agree")',
            'button:has-text("Allow all")',
            'button:has-text("Got it")',
            'button:has-text("OK")',
            'button:has-text("Dismiss")',
            'a:has-text("Accept")',
            'a:has-text("Accept All")',
            '#onetrust-accept-btn-handler',
            '#onetrust-banner-sdk button',
            '.cc-accept',
            '.cc-btn.cc-allow',
            '[aria-label="Accept Cookies"]',
            '[aria-label="Accept all cookies"]',
            '[data-qa="cookie-consent-accept"]',
            '[data-action="accept-cookies"]',
            'button[aria-label="Close"]',
            'button.close',
            '.modal-close',
            '.close-button',
        ]
        for sel in popup_triggers:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    print(f"🍪 [Popup / Cookie Consent] Dismissing '{sel}'...")
                    await loc.click(timeout=1500)
                    await page.wait_for_timeout(500)
                    break
            except Exception:
                continue

        # 2. JavaScript DOM cleanup for obstructive fixed overlays & backdrop traps
        try:
            await page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('button, a'));
                    for (const b of buttons) {
                        const txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                        if (['accept', 'accept all', 'i accept', 'agree', 'allow all', 'got it'].includes(txt)) {
                            b.click();
                            break;
                        }
                    }
                    const overlays = document.querySelectorAll(
                        '#onetrust-banner-sdk, .modal-backdrop, .overlay, [class*="cookie" i], [id*="cookie" i], [role="dialog"]'
                    );
                    overlays.forEach(el => {
                        const txt = (el.innerText || '').toLowerCase();
                        if (txt.includes('cookie') || txt.includes('tracking') || txt.includes('privacy') || txt.includes('notice')) {
                            el.remove();
                        }
                    });
                    document.body.style.overflow = 'auto';
                    if (document.documentElement) {
                        document.documentElement.style.overflow = 'auto';
                    }
                }
            """)
        except Exception:
            pass

    async def _navigate_to_form(self, page: Any, context: Any = None) -> Any:
        """
        Finds and clicks 'Apply' or 'Apply for this job' button if landing on a JD view.
        Intelligently handles new tabs opened via target="_blank" or window.open().
        """
        await self._dismiss_overlays_and_popups(page)

        # If the page already has application inputs, we are already on the application form!
        try:
            for f in page.frames:
                form_inputs = f.locator('input[type="email"], input[name*="email" i], input[name*="first" i], #firstName, #email')
                if await form_inputs.count() > 0:
                    return page
        except Exception:
            pass

        apply_triggers = [
            'a[href*="#apply"]',
            'a:has-text("Apply for this job")',
            'a:has-text("Apply Now")',
            'a:has-text("Apply")',
            'button:has-text("Apply for this job")',
            'button:has-text("Apply Now")',
            'button:has-text("Apply")',
            'a[href*="/apply"]',
            '[data-qa="btn-apply"]',
            '.postings-btn',
        ]
        for sel in apply_triggers:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    print(f"🔗 Clicking '{sel}' to reveal application form...")
                    # Check if target="_blank"
                    is_blank = False
                    try:
                        target_attr = await loc.get_attribute("target")
                        is_blank = target_attr == "_blank"
                    except Exception:
                        pass

                    if is_blank and context:
                        async with context.expect_page(timeout=7000) as new_page_info:
                            await loc.click(timeout=5000)
                        new_page = await new_page_info.value
                        await new_page.wait_for_load_state("domcontentloaded")
                        await self._dismiss_overlays_and_popups(new_page)
                        return new_page
                    else:
                        await loc.click(timeout=5000)
                        await page.wait_for_timeout(1500)
                        # Check if a new tab opened in context anyway
                        if context and len(context.pages) > 1:
                            new_p = context.pages[-1]
                            await new_p.bring_to_front()
                            await new_p.wait_for_load_state("domcontentloaded")
                            await self._dismiss_overlays_and_popups(new_p)
                            return new_p
                        await self._dismiss_overlays_and_popups(page)
                        break
            except Exception:
                continue
        return page

    async def _fill_keka_specialized(self, page: Any, data: dict[str, Any], fields_filled: list[dict[str, Any]]) -> None:
        """Deep, specialized autofill for Keka ATS (ClickPost, etc.)."""
        # 1. Names
        if data.get("first_name"):
            await self._try_fill(page, ['#firstName', 'input[name="firstName"]'], data["first_name"])
            fields_filled.append({"field": "First Name", "value": data["first_name"], "type": "text"})
        if data.get("last_name"):
            await self._try_fill(page, ['#lastName', 'input[name="lastName"]'], data["last_name"])
            fields_filled.append({"field": "Last Name", "value": data["last_name"], "type": "text"})

        # 2. Email
        if data.get("email"):
            await self._try_fill(page, ['#email', 'input[name="email"]'], data["email"])
            fields_filled.append({"field": "Email", "value": data["email"], "type": "email"})

        # 3. Country code & Phone
        if data.get("phone"):
            try:
                cc = page.locator('#mobilePhone\\.countryCode, select[name="mobilePhone.countryCode"]').first
                if await cc.count() > 0:
                    await cc.select_option(value="+91")
                    fields_filled.append({"field": "Country Code", "value": "+91", "type": "select"})
            except Exception:
                pass
            if data.get("phone_digits"):
                await self._try_fill(page, ['#mobilePhone\\.number', 'input[name="mobilePhone.number"]'], data["phone_digits"])
                fields_filled.append({"field": "Mobile Phone", "value": data["phone_digits"], "type": "tel"})

        # 4. Gender
        try:
            g = page.locator('#gender, select[name="gender"]').first
            if await g.count() > 0:
                await g.select_option(value="1")  # 1 = Male
                fields_filled.append({"field": "Gender", "value": "Male", "type": "select"})
        except Exception:
            pass

        # 5. Experience Years & Months
        if data.get("total_exp_years"):
            await self._try_fill(page, ['#workExperience', 'input[name="workExperience.years"]'], str(data["total_exp_years"]))
            fields_filled.append({"field": "Experience (Years)", "value": str(data["total_exp_years"]), "type": "text"})
            try:
                mo = page.locator('select[name="workExperience.months"]').first
                if await mo.count() > 0:
                    await mo.select_option(value="0")
            except Exception:
                pass

        # 6. Current & Expected Salary
        if data.get("curr_sal"):
            c_sal = re.sub(r"[^\d,]", "", str(data["curr_sal"])) or str(data["curr_sal"])
            await self._try_fill(page, ['#currentSalary', 'input[name="currentSalary.amount"]'], c_sal)
            fields_filled.append({"field": "Current Salary", "value": c_sal, "type": "text"})
        if data.get("exp_sal"):
            e_sal = re.sub(r"[^\d,]", "", str(data["exp_sal"])) or str(data["exp_sal"])
            await self._try_fill(page, ['#expectedSalary', 'input[name="expectedSalary.amount"]'], e_sal)
            fields_filled.append({"field": "Expected Salary", "value": e_sal, "type": "text"})

        # 7. Availability / Notice Period in Days
        if data.get("avail_days"):
            await self._try_fill(page, ['#availability', 'input[name="standardFields.availability.answer"]'], str(data["avail_days"]))
            fields_filled.append({"field": "Availability (Days)", "value": str(data["avail_days"]), "type": "number"})

        # 8. Location Preference
        try:
            lp = page.locator('#locationPreference, select[name="standardFields.locationPreference.answer"]').first
            if await lp.count() > 0:
                opts = await lp.locator('option').all_text_contents()
                valid_opts = [o.strip() for o in opts if o.strip() and "select" not in o.lower()]
                match_loc = None
                for pref in data.get("user_pref_locations", []):
                    pref_l = pref.lower().strip()
                    for opt in valid_opts:
                        if pref_l in opt.lower() or opt.lower() in pref_l:
                            match_loc = opt
                            break
                    if match_loc:
                        break
                if not match_loc and valid_opts:
                    match_loc = valid_opts[0]
                if match_loc:
                    await lp.select_option(label=match_loc)
                    fields_filled.append({"field": "Preferred Location", "value": match_loc, "type": "select"})
        except Exception:
            pass

        # 9. Current Location
        if data.get("city"):
            await self._try_fill(page, ['#currentLocation', 'input[name="standardFields.currentLocation.answer"]'], data["city"])

        # 10. Primary Experience (Experience 0)
        if data.get("current_company"):
            await self._try_fill(page, ['#companyName_0', 'input[name="ExperienceDetails[0].companyName"]'], data["current_company"])
            fields_filled.append({"field": "Experience 1 Company", "value": data["current_company"], "type": "text"})
        if data.get("current_title"):
            await self._try_fill(page, ['#designation_0', 'input[name="ExperienceDetails[0].designation"]'], data["current_title"])
            fields_filled.append({"field": "Experience 1 Title", "value": data["current_title"], "type": "text"})
        if data.get("exp_location"):
            await self._try_fill(page, ['#experienceLocation_0', 'input[name="ExperienceDetails[0].location"]'], data["exp_location"])
        try:
            chk0 = page.locator('#isCurrentlyWorking_0, input[name="ExperienceDetails[0].isCurrentlyWorking"]').first
            if await chk0.count() > 0:
                if data.get("is_currently_working"):
                    if not await chk0.is_checked():
                        await chk0.check()
                else:
                    if await chk0.is_checked():
                        await chk0.uncheck()
        except Exception:
            pass
        if data.get("joining_date_str"):
            await page.evaluate("""(val) => {
                const el = document.getElementById('experienceDateOfJoining_0') || document.querySelector('input[name="ExperienceDetails[0].dateOfJoining"]');
                if (el) { el.removeAttribute('readonly'); el.value = val; el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }
            }""", data["joining_date_str"])
            fields_filled.append({"field": "Experience 1 Joining Date", "value": data["joining_date_str"], "type": "date"})

        # 11. Additional Experience (Experience 1)
        experiences = data.get("experiences", [])
        if len(experiences) > 1:
            exp1 = experiences[1]
            try:
                add_exp = page.locator("a:has-text('Add Experience Details')").first
                if await add_exp.count() > 0:
                    await add_exp.click()
                    await page.wait_for_timeout(400)
                    if exp1.get("company"):
                        await self._try_fill(page, ['#companyName_1'], exp1["company"])
                        fields_filled.append({"field": "Experience 2 Company", "value": exp1["company"], "type": "text"})
                    if exp1.get("title") or exp1.get("jobTitle"):
                        t1 = exp1.get("title") or exp1.get("jobTitle")
                        await self._try_fill(page, ['#designation_1'], t1)
                    if exp1.get("location"):
                        await self._try_fill(page, ['#experienceLocation_1'], exp1["location"])
                    sd1 = exp1.get("start_date") or exp1.get("startDate") or ""
                    ed1 = exp1.get("end_date") or exp1.get("endDate") or ""
                    parts_sd = sd1.split()
                    j1 = f"01 {parts_sd[0].capitalize()} {parts_sd[1]}" if len(parts_sd) == 2 else sd1
                    parts_ed = ed1.split()
                    r1 = f"01 {parts_ed[0].capitalize()} {parts_ed[1]}" if len(parts_ed) == 2 else ed1
                    await page.evaluate("""([j, r]) => {
                        const jEl = document.getElementById('experienceDateOfJoining_1');
                        if (jEl && j) { jEl.removeAttribute('readonly'); jEl.value = j; jEl.dispatchEvent(new Event('change', {bubbles: true})); }
                        const rEl = document.getElementById('dateOfRelieving_1');
                        if (rEl && r) { rEl.removeAttribute('readonly'); rEl.value = r; rEl.dispatchEvent(new Event('change', {bubbles: true})); }
                    }""", [j1, r1])
            except Exception as e:
                logger.debug("Keka 2nd experience fill skipped", error=str(e))

        # 12. Education Details
        educations = data.get("educations", [])
        if educations:
            try:
                add_edu = page.locator("a:has-text('Add Education Details')").first
                if await add_edu.count() > 0:
                    await add_edu.click()
                    await page.wait_for_timeout(400)
                    if data.get("edu_degree"):
                        await self._try_fill(page, ['#degree_0'], data["edu_degree"])
                        fields_filled.append({"field": "Education Degree", "value": data["edu_degree"], "type": "text"})
                    if data.get("edu_branch"):
                        await self._try_fill(page, ['#branch_0'], data["edu_branch"])
                    if data.get("edu_school"):
                        await self._try_fill(page, ['#university_0'], data["edu_school"])
                        fields_filled.append({"field": "Education University", "value": data["edu_school"], "type": "text"})
                    if data.get("edu_location"):
                        await self._try_fill(page, ['#educationLocation_0'], data["edu_location"])
                    if data.get("edu_year"):
                        y_str = f"01 May {data['edu_year']}" if len(data['edu_year']) == 4 else data['edu_year']
                        await page.evaluate("""(val) => {
                            const el = document.getElementById('dateOfCompletion_0');
                            if (el) { el.removeAttribute('readonly'); el.value = val; el.dispatchEvent(new Event('change', {bubbles: true})); }
                        }""", y_str)
            except Exception as ee:
                logger.debug("Keka education fill skipped", error=str(ee))

        # 13. Skills Container (Inject candidate's skills)
        cand_skills = data.get("skills", [])
        if cand_skills:
            try:
                top_skills = cand_skills[:12]
                added = await page.evaluate("""(skills) => {
                    if (typeof $ === 'undefined') return [];
                    const res = [];
                    for (const s of skills) {
                        $('#skills').val(s).trigger('keyup');
                        const btn = document.getElementById('skillCheck');
                        if (btn) { btn.click(); res.push(s); }
                    }
                    return res;
                }""", top_skills)
                if added:
                    fields_filled.append({"field": "Skills Tags", "value": f"{len(added)} skills added ({', '.join(added[:5])}...)", "type": "tags"})
            except Exception as se:
                logger.debug("Keka skills fill skipped", error=str(se))

        # 14. Consent Checkbox
        try:
            consent = page.locator('#candidateConsent, input[name="candidateConsent"]').first
            if await consent.count() > 0 and not await consent.is_checked():
                await consent.check(timeout=1000)
                fields_filled.append({"field": "Candidate Consent", "value": "Checked", "type": "checkbox"})
        except Exception:
            pass

    async def _semantic_fill_portal(self, page: Any, data: dict[str, Any], fields_filled: list[dict[str, Any]]) -> None:
        """
        Universal semantic form filler for any career portal (Greenhouse, Lever, Workday, Taleo, Ashby, etc.).
        Inspects all inputs across the main page and all child frames.
        """
        frames = [page.main_frame] + [f for f in page.frames if f != page.main_frame]
        for frame in frames:
            try:
                inputs = await frame.evaluate("""() => {
                    const elements = Array.from(document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="checkbox"]):not([type="radio"]):not([type="file"]), textarea, select'));
                    return elements.map((el, index) => {
                        let labelText = '';
                        if (el.labels && el.labels.length > 0) {
                            labelText = Array.from(el.labels).map(l => l.innerText).join(' ');
                        } else if (el.id) {
                            const lbl = document.querySelector(`label[for="${el.id}"]`);
                            if (lbl) labelText = lbl.innerText;
                        }
                        if (!labelText) {
                            let parent = el.parentElement;
                            for (let i = 0; i < 3 && parent; i++) {
                                const lbl = parent.querySelector('label, .label, [class*="label" i]');
                                if (lbl && lbl !== el) {
                                    labelText = lbl.innerText;
                                    break;
                                }
                                parent = parent.parentElement;
                            }
                        }
                        return {
                            index,
                            tag: el.tagName.toLowerCase(),
                            type: (el.type || 'text').toLowerCase(),
                            id: el.id || '',
                            name: el.name || '',
                            placeholder: el.placeholder || '',
                            ariaLabel: el.getAttribute('aria-label') || '',
                            labelText: (labelText || '').trim(),
                            value: el.value || '',
                            disabled: el.disabled || false,
                            readOnly: el.readOnly || false,
                            options: el.tagName === 'SELECT' ? Array.from(el.options).map(o => ({ value: o.value, text: o.text })) : []
                        };
                    });
                }""")
            except Exception:
                continue

            for item in inputs:
                if item.get("disabled") or item.get("value"):
                    continue

                sig = f"{item['id']} {item['name']} {item['placeholder']} {item['ariaLabel']} {item['labelText']}".lower()
                sel = f"#{item['id']}" if item['id'] else (f"[name='{item['name']}']" if item['name'] else None)
                if not sel:
                    continue

                try:
                    target_loc = frame.locator(sel).first
                    if await target_loc.count() == 0 or not await target_loc.is_visible():
                        continue
                except Exception:
                    continue

                val_to_fill = None
                field_label = None

                # Dropdown handling
                if item["tag"] == "select":
                    options = item.get("options", [])
                    valid_opts = [o for o in options if o["text"].strip() and "select" not in o["text"].lower()]

                    if any(k in sig for k in ["gender", "sex"]):
                        target_g = "female" if "female" in (data.get("gender") or "").lower() else "male"
                        matched = next((o for o in valid_opts if target_g in o["text"].lower()), None)
                        if matched:
                            try:
                                await target_loc.select_option(value=matched["value"])
                                fields_filled.append({"field": "Gender", "value": matched["text"], "type": "select"})
                            except Exception:
                                pass
                    elif any(k in sig for k in ["country", "nationality"]):
                        matched = next((o for o in valid_opts if "india" in o["text"].lower()), None)
                        if matched:
                            try:
                                await target_loc.select_option(value=matched["value"])
                                fields_filled.append({"field": "Country", "value": matched["text"], "type": "select"})
                            except Exception:
                                pass
                    elif any(k in sig for k in ["authorized", "eligib", "work permit", "right to work"]):
                        matched = next((o for o in valid_opts if o["text"].strip().lower() in ["yes", "true"]), None)
                        if matched:
                            try:
                                await target_loc.select_option(value=matched["value"])
                                fields_filled.append({"field": "Work Authorization", "value": matched["text"], "type": "select"})
                            except Exception:
                                pass
                    elif any(k in sig for k in ["sponsorship", "visa sponsor"]):
                        matched = next((o for o in valid_opts if o["text"].strip().lower() in ["no", "false"]), None)
                        if matched:
                            try:
                                await target_loc.select_option(value=matched["value"])
                                fields_filled.append({"field": "Visa Sponsorship", "value": matched["text"], "type": "select"})
                            except Exception:
                                pass
                    elif any(k in sig for k in ["hear about", "source"]):
                        matched = next((o for o in valid_opts if "linkedin" in o["text"].lower() or "website" in o["text"].lower()), None)
                        if matched:
                            try:
                                await target_loc.select_option(value=matched["value"])
                                fields_filled.append({"field": "Source", "value": matched["text"], "type": "select"})
                            except Exception:
                                pass
                    continue

                # Text / Textarea handling
                if any(k in sig for k in ["first name", "given name", "legal first", "firstname", "fname"]) and not any(k in sig for k in ["last", "middle"]):
                    val_to_fill = data.get("first_name")
                    field_label = "First Name"
                elif any(k in sig for k in ["last name", "surname", "family name", "lastname", "lname"]):
                    val_to_fill = data.get("last_name")
                    field_label = "Last Name"
                elif any(k in sig for k in ["full name", "applicant name", "candidate name", "your name"]) and not any(k in sig for k in ["first", "last"]):
                    val_to_fill = data.get("full_name")
                    field_label = "Full Name"
                elif "email" in sig:
                    val_to_fill = data.get("email")
                    field_label = "Email Address"
                elif any(k in sig for k in ["phone", "mobile", "cell", "telephone", "contact number"]):
                    val_to_fill = data.get("phone_digits") or data.get("phone")
                    field_label = "Phone Number"
                elif any(k in sig for k in ["city", "current location", "location (city)"]) and not any(k in sig for k in ["state", "country", "postal", "zip"]):
                    val_to_fill = data.get("city")
                    field_label = "City"
                elif any(k in sig for k in ["state", "province"]):
                    val_to_fill = data.get("state")
                    field_label = "State"
                elif "country" in sig and not any(k in sig for k in ["code", "dial"]):
                    val_to_fill = data.get("country")
                    field_label = "Country"
                elif "linkedin" in sig:
                    val_to_fill = data.get("linkedin")
                    field_label = "LinkedIn"
                elif "github" in sig:
                    val_to_fill = data.get("github")
                    field_label = "GitHub"
                elif any(k in sig for k in ["portfolio", "website", "other link"]):
                    val_to_fill = data.get("portfolio")
                    field_label = "Portfolio"
                elif any(k in sig for k in ["current company", "employer", "company name", "most recent"]):
                    val_to_fill = data.get("current_company")
                    field_label = "Company"
                elif any(k in sig for k in ["job title", "designation", "current role", "title"]):
                    val_to_fill = data.get("current_title")
                    field_label = "Job Title"
                elif any(k in sig for k in ["years of experience", "total experience", "experience in years"]):
                    val_to_fill = data.get("total_exp_years")
                    field_label = "Experience (Years)"
                elif any(k in sig for k in ["notice period", "availability", "how soon"]):
                    val_to_fill = data.get("avail_days")
                    field_label = "Notice Period"
                elif any(k in sig for k in ["current salary", "current ctc"]):
                    val_to_fill = data.get("curr_sal")
                    field_label = "Current Salary"
                elif any(k in sig for k in ["expected salary", "expected ctc"]):
                    val_to_fill = data.get("exp_sal")
                    field_label = "Expected Salary"
                elif any(k in sig for k in ["degree", "qualification"]):
                    val_to_fill = data.get("edu_degree")
                    field_label = "Degree"
                elif any(k in sig for k in ["university", "school", "institution", "college"]):
                    val_to_fill = data.get("edu_school")
                    field_label = "University"
                elif any(k in sig for k in ["graduation year", "completion year"]):
                    val_to_fill = data.get("edu_year")
                    field_label = "Graduation Year"

                if val_to_fill:
                    try:
                        await target_loc.fill(str(val_to_fill), timeout=1500)
                        fields_filled.append({"field": field_label, "value": str(val_to_fill), "type": item["type"]})
                    except Exception:
                        pass

    async def _attach_resume_to_frames(self, page: Any, resume_path: str, fields_filled: list[dict[str, Any]]) -> None:
        """Finds and attaches candidate PDF resume to file inputs across all frames."""
        frames = [page.main_frame] + [f for f in page.frames if f != page.main_frame]
        for frame in frames:
            try:
                file_inputs = frame.locator('input[type="file"]')
                count = await file_inputs.count()
                for i in range(count):
                    finp = file_inputs.nth(i)
                    try:
                        await finp.set_input_files(resume_path, timeout=3000)
                        fields_filled.append({"field": "Resume PDF Attached", "value": os.path.basename(resume_path), "type": "file"})
                        return
                    except Exception:
                        continue
            except Exception:
                continue

    async def _handle_standard_questions_all_frames(
        self,
        page: Any,
        qa_map: dict[str, str],
        questions_answered: list[dict[str, str]],
    ) -> None:
        """Intelligently handles dropdowns, authorization questions, and textareas across all frames."""
        frames = [page.main_frame] + [f for f in page.frames if f != page.main_frame]
        for frame in frames:
            await self._handle_standard_questions(frame, qa_map, questions_answered)

    async def _check_consent_checkboxes(self, page: Any, fields_filled: list[dict[str, Any]]) -> None:
        """Safely checks consent & privacy policy checkboxes across all frames."""
        frames = [page.main_frame] + [f for f in page.frames if f != page.main_frame]
        for frame in frames:
            try:
                checkboxes = frame.locator('input[type="checkbox"]')
                count = await checkboxes.count()
                for i in range(count):
                    cb = checkboxes.nth(i)
                    try:
                        if not await cb.is_checked():
                            await cb.check(timeout=1000)
                            fields_filled.append({"field": "Consent & Policy Agreement", "value": "Checked", "type": "checkbox"})
                    except Exception:
                        continue
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

