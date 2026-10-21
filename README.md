# Sleepy Apply

> Agentic AI system that discovers jobs, matches your profile, generates tailored resumes, and applies — while you sleep.

## Repository Structure

```
sleepy-apply/
├── frontend/          # Next.js 16 + Tailwind v4 (deploy to Vercel)
├── backend/           # FastAPI + LangGraph + Python (deploy to Render.com)
└── macos-scheduler/   # Native macOS launchd scheduler (run on your machine)
```

## Running with Docker (Recommended)

Run everything (Frontend, Backend, and local MongoDB) with hot-reloading enabled, exactly like `winter-arc`:

```bash
docker compose up --build
```

- **Frontend**: [http://localhost:3000](http://localhost:3000)
- **Backend API**: [http://localhost:8000](http://localhost:8000)
- **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **MongoDB**: `localhost:27017` (or set `MONGODB_URI` in `.env` to connect to MongoDB Atlas)

---

## Running Locally Without Docker

### 1. Backend

```bash
cd backend
cp .env.example .env
# Fill in: MONGODB_URI, DISCORD_CLIENT_ID/SECRET, JWT_SECRET, CREDENTIAL_ENCRYPTION_KEY

# Generate Fernet key:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 2. Frontend

```bash
cd frontend
cp .env.local.example .env.local
# Fill in: NEXT_PUBLIC_API_URL, NEXT_PUBLIC_DISCORD_CLIENT_ID

npm install
npm run dev
```

### 3. macOS Scheduler (optional — triggers your pipeline on a schedule)

```bash
# Edit config
nano macos-scheduler/config.sh

# Install as launchd agent (runs every 6h, works with lid closed)
./macos-scheduler/manage.sh setup

# Check status
./macos-scheduler/manage.sh status

# Run immediately (test)
./macos-scheduler/manage.sh run-now
```

## Discord App Setup

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create a new application
3. OAuth2 → Add redirect: `http://localhost:3000/auth/callback` (dev) + your Vercel URL (prod)
4. Copy Client ID + Secret to `.env`
5. Create a Bot token for notifications → add to `DISCORD_BOT_TOKEN`

## AI Provider Setup

Each user configures their own AI provider in **Settings**:

| Provider | What you need |
|---|---|
| **Ollama** (local) | Run `ollama serve`, enter your machine's URL |
| **OpenAI** | API key from [platform.openai.com](https://platform.openai.com) |
| **Gemini** | API key from [aistudio.google.com](https://aistudio.google.com) |
| **Anthropic** | API key from [console.anthropic.com](https://console.anthropic.com) |

All API keys are **Fernet-encrypted** before being stored in MongoDB. They are never logged or returned in API responses.

## Deployment

| Service | Platform | Notes |
|---|---|---|
| Frontend | [Vercel](https://vercel.com) | Connect GitHub repo, auto-deploy |
| Backend | [Render.com](https://render.com) | Free tier, 750hrs/month |
| Database | [MongoDB Atlas](https://www.mongodb.com/atlas) | Free 512MB cluster |
