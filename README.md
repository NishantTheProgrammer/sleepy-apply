# Sleepy Apply 🌙🤖

> **Agentic AI system that discovers jobs, matches your profile, generates tailored, evidence-grounded resumes, and applies — while you sleep.**

Sleepy Apply is an autonomous job application platform designed to run locally or in the cloud. It pairs an agentic discovery and application workflow with an ultra-strict, evidence-grounded resume tailoring engine that eliminates hallucinations, metric drift, and employer misattributions.

---

## 🌟 Key Features

- **Autonomous Job Discovery**: Crawls job boards and company career pages via Playwright and API integrations.
- **Evidence-Grounded Resume Tailoring (v8.1)**:
  - **Zero-Hallucination Guard**: Two-tier verification (deterministic Python validation + semantic LLM guard) ensuring 100% of claims originate from authentic source profile data.
  - **Tenure & Duration Classification**: Strictly separates overall career experience, professional technology tenure, and personal/academic project exposure (e.g. 5 years overall experience + 1 Spring Boot project is never misrepresented as 5 years of Spring experience).
  - **Strict Entity & Company Isolation**: Uses persistent IDs and entity isolation to guarantee bullets, metrics, and achievements never bleed across employers.
  - **Dynamic JD Analysis**: Analyzes job requirements, categorizing mandatory vs. desirable competencies based on section semantics and canonical technology taxonomies.
  - **Precise Education Matching**: Distinguishes exact qualification matches (B.Tech/BE), related technical disciplines (MCA/BCA), and unmatched credentials while preserving authentic degree titles.
  - **Structured Achievement & URL Preservation**: Cleans line fragments and associates verified profile links (LeetCode, HackerRank, GitHub, Kaggle) into structured records without standalone URL artifacts.
  - **Canonical Schema**: Clean, unified data contracts (`full_name`, `title`, `start_date`, `end_date`, `is_current`, `responsibilities`, `technologies`) with zero duplicate keys and transparent backward-compatible aliases.
- **ATS-Optimized Export**: Generates production-ready, ATS-compliant PDF (via ReportLab) and DOCX (via python-docx / docxtpl) documents.
- **Local-First & Hardware-Efficient**: Optimized for local inference with Ollama (`llama3.2:1b`) on Apple Silicon (M1/M2/M3 Pro, 16GB RAM) completing generation and verification passes in under 1 second deterministically.
- **Native macOS Scheduler**: Run continuous background job crawls and applications via native `launchd` agents, even with your laptop lid closed.

---

## 🏗️ Repository Architecture

```
sleepy-apply/
├── frontend/             # Next.js 16 (App Router), React 19, Tailwind CSS v4, Framer Motion
├── backend/              # FastAPI, LangGraph, Motor (MongoDB), Playwright, ReportLab
│   ├── app/
│   │   ├── agents/       # Agentic pipeline (profile_creator, evidence_mapper, resume_builder, hallucination_guard)
│   │   ├── api/          # REST API endpoints (auth, profile, jobs, applications, settings)
│   │   ├── models/       # Pydantic & Mongo models with CanonicalDict schema support
│   │   ├── templates/    # ATS resume generators (PDF via ReportLab, DOCX via python-docx)
│   │   └── crawler/      # Playwright job scrapers and aggregators
│   └── tests/            # Test suite (evidence tailoring, regression suite, security, API)
└── macos-scheduler/      # Native macOS launchd scheduler for scheduled execution
```

---

## 🚀 Quickstart with Docker (Recommended)

Run Frontend, Backend, and local MongoDB with hot-reloading:

```bash
docker compose up --build
```

- **Frontend**: [http://localhost:3000](http://localhost:3000)
- **Backend API**: [http://localhost:8000](http://localhost:8000)
- **Interactive API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Local MongoDB**: `localhost:27017`

---

## 💻 Local Development Setup

### 1. Prerequisites
- **Python**: 3.11+ (Python 3.12 or 3.14 tested)
- **Node.js**: 20+
- **MongoDB**: Local instance running on port 27017 or a [MongoDB Atlas](https://www.mongodb.com/atlas) cluster URL
- **Ollama** (optional for local LLM inference): `ollama run llama3.2:1b`

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for crawler)
playwright install chromium

# Configure environment variables
cp .env.example .env
```

Generate an encryption key for sensitive credentials:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Paste this value into `CREDENTIAL_ENCRYPTION_KEY` in `backend/.env`.

Run the backend server:
```bash
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd frontend

# Install packages
npm install

# Configure environment
cp .env.local.example .env.local

# Run Next.js development server
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000) to view the application.

---

## 🧪 Running the Test Suite

The backend contains a comprehensive unit and regression suite verifying company isolation, evidence mapping, metric preservation, and hallucination guardrails:

```bash
# From repository root
PYTHONPATH=backend ./backend/.venv/bin/pytest backend/tests
```

Run specific test modules:
```bash
# Evidence mapping and targeted Version 8.1 corrections
PYTHONPATH=backend ./backend/.venv/bin/pytest backend/tests/test_evidence_tailoring.py -v

# Multi-persona generic regression suite (Frontend, ML, DevOps, Junior, Adversarial)
PYTHONPATH=backend ./backend/.venv/bin/pytest backend/tests/test_generic_regression_suite.py -v
```

---

## 🔒 Security & AI Provider Configuration

Each user configures their chosen AI provider in **Settings** via the web UI:

| Provider | Requirement | Notes |
|---|---|---|
| **Ollama** (Default / Local) | `ollama serve` (`llama3.2:1b` recommended) | Fully local, free, zero data egress |
| **OpenAI** | API Key from [platform.openai.com](https://platform.openai.com) | GPT-4o / GPT-4o-mini |
| **Google Gemini** | API Key from [aistudio.google.com](https://aistudio.google.com) | Gemini 1.5 Pro / Flash |
| **Anthropic** | API Key from [console.anthropic.com](https://console.anthropic.com) | Claude 3.5 Sonnet |

> [!IMPORTANT]
> All credentials and API keys are **Fernet-encrypted** at rest before being written to MongoDB. Keys are never logged, decrypted in memory only when needed, and never exposed in client API responses.

---

## ⏰ macOS Scheduler (Autonomous Overnight Runs)

Trigger job crawlers and applications on a recurring schedule without leaving your terminal open:

```bash
# 1. Configure preferences (interval, target queries, notifications)
nano macos-scheduler/config.sh

# 2. Register as a user launchd agent (runs every 6 hours, wakes on lid-close if power connected)
./macos-scheduler/manage.sh setup

# 3. Check scheduler daemon status
./macos-scheduler/manage.sh status

# 4. Trigger manual pipeline run immediately
./macos-scheduler/manage.sh run-now
```

---

## 🚢 Deployment

| Component | Target Platform | Instructions |
|---|---|---|
| **Frontend** | [Vercel](https://vercel.com) | Set Root Directory to `frontend`, add `NEXT_PUBLIC_API_URL` |
| **Backend** | [Render.com](https://render.com) or [Railway](https://railway.app) | Set Root Directory to `backend`, start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Database** | [MongoDB Atlas](https://www.mongodb.com/atlas) | Free M0 tier (512MB), add connection string to `MONGODB_URI` |

---

## 📄 License

MIT © [Sleepy Apply Contributors](LICENSE)
