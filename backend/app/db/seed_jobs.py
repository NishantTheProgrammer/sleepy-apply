import asyncio
import hashlib
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
import structlog
from app.db.client import connect_db, get_db

logger = structlog.get_logger()

SAMPLE_TECH_JOBS = [
    # ── Stripe (Tier-1) ───────────────────────────────────────────────────────
    {
        "title": "Staff Software Engineer, Global Payment Infrastructure",
        "company": "Stripe",
        "location": "San Francisco, CA / Remote",
        "is_remote": True,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://stripe.com/jobs",
        "application_url": "https://stripe.com/jobs/search?q=payment+infrastructure",
        "company_info": {"website": "https://stripe.com", "industry": "Fintech & Developer Tools"},
        "salary_range": {"min": 210000, "max": 290000, "currency": "USD"},
        "requirements": [
            "8+ years of professional backend software engineering experience",
            "Expertise in distributed systems, high throughput low-latency architectures",
            "Proficiency in Go, Java, or Ruby",
            "Experience operating systems with 99.999% availability SLAs",
        ],
        "responsibilities": [
            "Architect and lead implementation of payment routing and authorization systems",
            "Optimize database transactions across global multi-region deployments",
            "Mentor senior engineers across the payments organization",
        ],
        "required_skills": ["Go", "Distributed Systems", "PostgreSQL", "AWS", "Kafka", "Microservices"],
        "description": "Stripe is looking for a Staff Software Engineer to lead the architecture of our core global payment rails. You will design systems processing billions of dollars daily with extreme reliability.",
    },
    {
        "title": "Full Stack Engineer, Billing & Invoicing Engine",
        "company": "Stripe",
        "location": "Remote (US/Canada)",
        "is_remote": True,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://stripe.com/jobs",
        "application_url": "https://stripe.com/jobs/search?q=billing",
        "company_info": {"website": "https://stripe.com", "industry": "Fintech & Developer Tools"},
        "salary_range": {"min": 170000, "max": 235000, "currency": "USD"},
        "requirements": [
            "4+ years building production full stack applications",
            "Strong command of TypeScript, React, and backend services (Node.js/Go/Ruby)",
            "Deep understanding of relational database modeling and transactional safety",
        ],
        "responsibilities": [
            "Build self-serve merchant workflows for custom billing schedules and invoice generation",
            "Develop high-performance frontends and robust API endpoints",
        ],
        "required_skills": ["TypeScript", "React", "Node.js", "SQL", "REST APIs", "GraphQL"],
        "description": "Join Stripe's Billing team to empower millions of digital businesses with recurring revenue billing engines and intuitive customer portals.",
    },

    # ── OpenAI (Tier-1) ───────────────────────────────────────────────────────
    {
        "title": "Software Engineer, Model Inference & Serving",
        "company": "OpenAI",
        "location": "San Francisco, CA",
        "is_remote": False,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://openai.com/careers",
        "application_url": "https://openai.com/careers/software-engineer-inference",
        "company_info": {"website": "https://openai.com", "industry": "Artificial Intelligence"},
        "salary_range": {"min": 240000, "max": 330000, "currency": "USD"},
        "requirements": [
            "5+ years building and operating large scale high-performance GPU serving systems",
            "Strong systems programming background in Python, C++, and CUDA",
            "Knowledge of distributed key-value caches and batching algorithms",
        ],
        "responsibilities": [
            "Scale the ChatGPT and OpenAI API inference clusters for hundred of millions of daily users",
            "Optimize latency, throughput, and GPU utilization across thousands of nodes",
        ],
        "required_skills": ["Python", "C++", "CUDA", "PyTorch", "Kubernetes", "Linux Kernel", "Distributed Systems"],
        "description": "OpenAI's mission is to ensure that artificial general intelligence benefits all of humanity. In this role, you will scale model inference engines serving billions of tokens every second.",
    },
    {
        "title": "Full Stack Platform Engineer, Developer Experience",
        "company": "OpenAI",
        "location": "San Francisco, CA / Remote",
        "is_remote": True,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://openai.com/careers",
        "application_url": "https://openai.com/careers/full-stack-platform",
        "company_info": {"website": "https://openai.com", "industry": "Artificial Intelligence"},
        "salary_range": {"min": 200000, "max": 280000, "currency": "USD"},
        "requirements": [
            "4+ years building full stack web platforms with Next.js/React and Python/FastAPI",
            "Experience building API developer portals, playground consoles, and telemetry dashboards",
        ],
        "responsibilities": [
            "Develop the developer dashboard, API key management, and evaluation tooling for OpenAI platform customers",
            "Implement reactive web interfaces with real-time streaming LLM responses",
        ],
        "required_skills": ["Next.js", "React", "TypeScript", "Python", "FastAPI", "WebSockets", "TailwindCSS"],
        "description": "Design and build developer interfaces that allow world-class software teams to integrate cutting-edge frontier models into their applications.",
    },

    # ── Datadog (Tier-1) ──────────────────────────────────────────────────────
    {
        "title": "Senior Backend Engineer, Cloud Observability Pipelines",
        "company": "Datadog",
        "location": "New York, NY / Remote",
        "is_remote": True,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://www.datadoghq.com/careers/",
        "application_url": "https://www.datadoghq.com/careers/detail/?gh_jid=datadog-backend",
        "company_info": {"website": "https://www.datadoghq.com", "industry": "Cloud & Observability"},
        "salary_range": {"min": 175000, "max": 240000, "currency": "USD"},
        "requirements": [
            "5+ years software engineering experience in Go, Java, or C++",
            "Experience with streaming platforms (Kafka, Flink) and time-series databases",
            "Hands-on experience with cloud infrastructure on AWS or GCP",
        ],
        "responsibilities": [
            "Process trillions of data points per day in real-time telemetry pipelines",
            "Build scalable storage backends and write high-efficiency distributed aggregators",
        ],
        "required_skills": ["Go", "Kafka", "Distributed Systems", "Kubernetes", "PostgreSQL", "Linux"],
        "description": "Datadog is the monitoring and security platform for cloud applications. You will join our telemetry ingest teams processing massive real-time streams of metrics and traces.",
    },

    # ── Figma (Tier-1) ────────────────────────────────────────────────────────
    {
        "title": "Senior Frontend Engineer, Multiplayer Collaboration Engine",
        "company": "Figma",
        "location": "San Francisco, CA / Remote",
        "is_remote": True,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://www.figma.com/careers/",
        "application_url": "https://www.figma.com/careers/frontend-engineer",
        "company_info": {"website": "https://www.figma.com", "industry": "Design & Collaboration"},
        "salary_range": {"min": 185000, "max": 255000, "currency": "USD"},
        "requirements": [
            "5+ years developing complex client-side applications in TypeScript and WebAssembly/Rust",
            "Deep understanding of browser rendering engines, canvas/WebGL, and memory management",
            "Experience with Operational Transformation (OT) or CRDT algorithms",
        ],
        "responsibilities": [
            "Engineer real-time multiplayer editing capabilities with sub-50ms synchronization latency",
            "Create responsive UI components and canvas interaction layers",
        ],
        "required_skills": ["TypeScript", "React", "WebAssembly", "Rust", "Canvas", "WebGL", "Performance Optimization"],
        "description": "Figma makes design accessible to all teams. As a Senior Frontend Engineer on Multiplayer, you will push the boundaries of browser capabilities to deliver instant multiplayer canvas interactions.",
    },

    # ── Anthropic (Tier-1) ────────────────────────────────────────────────────
    {
        "title": "Backend Platform Engineer, Claude Infrastructure",
        "company": "Anthropic",
        "location": "San Francisco, CA / Remote",
        "is_remote": True,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://www.anthropic.com/careers",
        "application_url": "https://www.anthropic.com/careers/backend-platform",
        "company_info": {"website": "https://www.anthropic.com", "industry": "AI & Safety Research"},
        "salary_range": {"min": 220000, "max": 310000, "currency": "USD"},
        "requirements": [
            "4+ years building distributed backend services in Python, Go, or Rust",
            "Experience with asynchronous web servers, connection pooling, and rate-limiting at scale",
            "Familiarity with Kubernetes, Docker, and AWS cloud primitives",
        ],
        "responsibilities": [
            "Build the core API services that power Claude 3.5 Sonnet and Enterprise deployments",
            "Implement high-performance streaming token pipelines and enterprise compliance filters",
        ],
        "required_skills": ["Python", "FastAPI", "Go", "AWS", "Kubernetes", "Redis", "PostgreSQL"],
        "description": "Anthropic is an AI safety and research company. We build reliable, interpretable, and steerable AI systems. Help us build the platform infrastructure delivering Claude to millions worldwide.",
    },

    # ── Razorpay (Tier-2) ─────────────────────────────────────────────────────
    {
        "title": "Lead Backend Engineer, Payments Gateway & Core Banking",
        "company": "Razorpay",
        "location": "Bengaluru, India",
        "is_remote": False,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://razorpay.com/jobs/",
        "application_url": "https://razorpay.com/jobs/lead-backend-engineer",
        "company_info": {"website": "https://razorpay.com", "industry": "Fintech & Payments"},
        "salary_range": {"min": 3500000, "max": 5500000, "currency": "INR"},
        "requirements": [
            "6+ years experience in backend architecture using Golang or Java / Spring Boot",
            "Deep understanding of distributed transactions, idempotency, and reconciliation systems",
            "Experience designing microservices with high concurrent traffic",
        ],
        "responsibilities": [
            "Own end-to-end architecture for payment routing across 50+ banking partners",
            "Drive 99.99% gateway uptime and optimize transaction processing latency",
        ],
        "required_skills": ["Golang", "Java", "Spring Boot", "MySQL", "Kafka", "Redis", "Distributed Systems"],
        "description": "Razorpay powers payments for India's largest businesses. You will lead core engineering teams building mission-critical financial software handling billions of transactions.",
    },
    {
        "title": "Senior Frontend Developer, RazorpayX Neo-Banking",
        "company": "Razorpay",
        "location": "Bengaluru, India / Hybrid",
        "is_remote": True,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://razorpay.com/jobs/",
        "application_url": "https://razorpay.com/jobs/senior-frontend-developer",
        "company_info": {"website": "https://razorpay.com", "industry": "Fintech & Payments"},
        "salary_range": {"min": 2500000, "max": 4000000, "currency": "INR"},
        "requirements": [
            "4+ years building responsive enterprise applications in React, Next.js, and TypeScript",
            "Expertise in modern state management, frontend security, and performance profiling",
        ],
        "responsibilities": [
            "Build seamless, lightning-fast banking workflows for corporate treasury and payouts",
            "Collaborate with design and product teams to uphold world-class UI standards",
        ],
        "required_skills": ["React", "TypeScript", "Next.js", "Redux Toolkit", "TailwindCSS", "Jest"],
        "description": "Help craft modern corporate banking interfaces on RazorpayX, transforming how Indian startups manage payroll, vendor payouts, and capital.",
    },

    # ── Supabase (Tier-2) ─────────────────────────────────────────────────────
    {
        "title": "Full Stack Engineer, Developer Dashboard & Studio",
        "company": "Supabase",
        "location": "All-Remote",
        "is_remote": True,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://supabase.com/careers",
        "application_url": "https://supabase.com/careers/full-stack-studio",
        "company_info": {"website": "https://supabase.com", "industry": "Open Source Backend"},
        "salary_range": {"min": 140000, "max": 190000, "currency": "USD"},
        "requirements": [
            "3+ years building full stack web applications with Next.js, React, and TypeScript",
            "Comfortable writing SQL queries, Postgres schemas, and database triggers",
            "Passionate about open-source developer tooling and developer experience",
        ],
        "responsibilities": [
            "Design and build features for Supabase Studio, our open source database GUI",
            "Implement interactive SQL editors, table schema visualizers, and auth management",
        ],
        "required_skills": ["Next.js", "React", "TypeScript", "PostgreSQL", "SQL", "TailwindCSS"],
        "description": "Supabase is an open source Firebase alternative. Build the open source developer console loved by over 1 million developers.",
    },

    # ── Meesho (Tier-2) ───────────────────────────────────────────────────────
    {
        "title": "Software Development Engineer III (Backend)",
        "company": "Meesho",
        "location": "Bengaluru, India",
        "is_remote": False,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://www.meesho.io/careers",
        "application_url": "https://www.meesho.io/careers/sde-3-backend",
        "company_info": {"website": "https://www.meesho.io", "industry": "E-Commerce & Marketplace"},
        "salary_range": {"min": 4000000, "max": 6000000, "currency": "INR"},
        "requirements": [
            "5+ years backend software development in Java, Spring Boot, or Golang",
            "Experience scaling e-commerce catalog, search, and checkout systems for millions of DAUs",
        ],
        "responsibilities": [
            "Architect high-throughput order management and inventory services",
            "Ensure low-latency discovery and recommendations across 100M+ listings",
        ],
        "required_skills": ["Java", "Spring Boot", "MySQL", "Kafka", "Elasticsearch", "AWS", "Microservices"],
        "description": "Meesho is democratizing internet commerce for everyone in India. You will engineer platforms that handle festive sale spikes of hundreds of thousands of orders per minute.",
    },

    # ── CRED (Tier-2) ─────────────────────────────────────────────────────────
    {
        "title": "Backend Architect, High-Trust Financial Workflows",
        "company": "CRED",
        "location": "Bengaluru, India",
        "is_remote": False,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://careers.cred.club/",
        "application_url": "https://careers.cred.club/backend-architect",
        "company_info": {"website": "https://cred.club", "industry": "Fintech & Rewards"},
        "salary_range": {"min": 5000000, "max": 7500000, "currency": "INR"},
        "requirements": [
            "7+ years experience designing ultra-scalable backend systems in Golang or Java",
            "Expertise in event-driven architectures, distributed tracing, and zero-loss message processing",
        ],
        "responsibilities": [
            "Design backend foundations for instant credit card bill payments, lending, and rewards",
            "Establish engineering standards for resilient and fault-tolerant service communication",
        ],
        "required_skills": ["Golang", "Java", "Kafka", "DynamoDB", "PostgreSQL", "System Design"],
        "description": "CRED is an exclusive community of creditworthy individuals. Build world-class financial software with unparalleled craftsmanship and reliability.",
    },

    # ── Linear (Tier-2) ───────────────────────────────────────────────────────
    {
        "title": "Product Engineer, Full Stack Web & Sync Engine",
        "company": "Linear",
        "location": "San Francisco, CA / Remote",
        "is_remote": True,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://linear.app/careers",
        "application_url": "https://linear.app/careers/product-engineer",
        "company_info": {"website": "https://linear.app", "industry": "Productivity & Issue Tracking"},
        "salary_range": {"min": 170000, "max": 230000, "currency": "USD"},
        "requirements": [
            "4+ years building fluid, high-performance web applications in TypeScript and Node.js",
            "Obsession with micro-interactions, keyboard shortcuts, and sub-100ms response times",
        ],
        "responsibilities": [
            "Build new features for Linear's issue tracking, project updates, and roadmap views",
            "Optimize local-first client database sync with IndexedDB and WebSocket real-time updates",
        ],
        "required_skills": ["TypeScript", "React", "Node.js", "GraphQL", "WebSockets", "IndexedDB"],
        "description": "Linear builds tools for high-performing software teams. Help create the standard of modern software engineering productivity.",
    },

    # ── Cloudflare (Tier-1) ───────────────────────────────────────────────────
    {
        "title": "Systems Engineer, Edge Workers & Serverless Runtime",
        "company": "Cloudflare",
        "location": "Austin, TX / San Francisco, CA / Remote",
        "is_remote": True,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://www.cloudflare.com/careers/",
        "application_url": "https://www.cloudflare.com/careers/jobs/edge-workers",
        "company_info": {"website": "https://www.cloudflare.com", "industry": "Cloud Infrastructure"},
        "salary_range": {"min": 170000, "max": 240000, "currency": "USD"},
        "requirements": [
            "5+ years systems programming in Rust, C++, or Go",
            "Deep understanding of V8 isolates, POSIX systems, and HTTP/3 protocols",
        ],
        "responsibilities": [
            "Engineer the global serverless edge execution runtime running in 300+ cities",
            "Optimize startup times and security sandboxing for millions of customer functions",
        ],
        "required_skills": ["Rust", "C++", "Go", "V8", "Networking", "Distributed Systems", "Linux"],
        "description": "Cloudflare protects and accelerates Internet applications globally. Help power the future of edge computing on Cloudflare Workers.",
    },

    # ── Freshworks (Tier-3) ───────────────────────────────────────────────────
    {
        "title": "Lead Software Engineer, Customer Success Cloud",
        "company": "Freshworks",
        "location": "Chennai, India",
        "is_remote": False,
        "employment_type": "full-time",
        "source": "company_ats",
        "source_url": "https://www.freshworks.com/company/careers/",
        "application_url": "https://www.freshworks.com/company/careers/lead-engineer",
        "company_info": {"website": "https://www.freshworks.com", "industry": "Enterprise SaaS"},
        "salary_range": {"min": 2800000, "max": 4200000, "currency": "INR"},
        "requirements": [
            "6+ years experience in Ruby on Rails, Java, or Node.js backend development",
            "Experience building multi-tenant SaaS architectures serving enterprise clients",
        ],
        "responsibilities": [
            "Develop multi-channel customer ticketing, live chat, and CRM integrations",
            "Optimize relational database performance and query indexing for large tenant data",
        ],
        "required_skills": ["Ruby on Rails", "Java", "PostgreSQL", "AWS", "Redis", "Microservices"],
        "description": "Freshworks makes intuitive software that businesses love. Build SaaS applications trusted by over 60,000 businesses worldwide.",
    },
]


def generate_content_hash(title: str, company: str, location: str) -> str:
    raw = f"{title.strip().lower()}|{company.strip().lower()}|{location.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def seed_jobs_collection(db: AsyncIOMotorDatabase, force_overwrite: bool = False) -> int:
    """Seeds the jobs collection with verified high-caliber job postings from target companies.

    Deduplicates using SHA-256 content_hash.
    """
    now = datetime.now(timezone.utc)
    count = 0

    for job_data in SAMPLE_TECH_JOBS:
        content_hash = generate_content_hash(
            job_data["title"],
            job_data["company"],
            job_data["location"],
        )

        job_doc = {
            "source": job_data.get("source", "company_ats"),
            "source_url": job_data["source_url"],
            "external_id": None,
            "title": job_data["title"],
            "company": job_data["company"],
            "company_info": job_data.get("company_info", {}),
            "description": job_data["description"],
            "requirements": job_data.get("requirements", []),
            "responsibilities": job_data.get("responsibilities", []),
            "location": job_data["location"],
            "is_remote": job_data.get("is_remote", False),
            "employment_type": job_data.get("employment_type", "full-time"),
            "salary_range": job_data.get("salary_range", {}),
            "application_url": job_data["application_url"],
            "hr_contact": {},
            "required_skills": job_data.get("required_skills", []),
            "is_active": True,
            "enriched": True,
            "discovered_at": now,
            "content_hash": content_hash,
        }

        if force_overwrite:
            await db.jobs.update_one(
                {"content_hash": content_hash},
                {"$set": job_doc},
                upsert=True,
            )
            count += 1
        else:
            exists = await db.jobs.find_one({"content_hash": content_hash})
            if not exists:
                await db.jobs.insert_one(job_doc)
                count += 1

    logger.info("Jobs collection seeded", count=count)
    return count


async def main():
    await connect_db()
    db = get_db()
    count = await seed_jobs_collection(db)
    total = await db.jobs.count_documents({})
    print(f"✅ Seeding complete. Total jobs in db.jobs: {total} (New inserted: {count})")


if __name__ == "__main__":
    asyncio.run(main())
