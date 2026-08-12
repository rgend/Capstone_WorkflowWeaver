# WorkflowWeaver

Describe a business workflow in plain English. An AI agent — built on LangGraph and Claude —
plans it into concrete steps and executes them autonomously across Notion, Google Drive, and
Microsoft Teams, with live streamed progress, retries, and rollback on failure.

> Turn "*Take today's meeting notes and create a Notion project page, generate action items, and
> post a summary to Microsoft Teams*" into a Notion page, an action-item list, and a Teams
> notification — with zero manual copy-pasting between tools.

---

## 1. Project Overview

WorkflowWeaver is an agentic workflow-automation platform for cross-tool business processes.
Instead of a human manually creating a Notion page, then a Google Drive doc, then a Teams
message, the user writes one sentence and an AI agent plans and executes the whole sequence.

**Core pieces:**

- **Natural-language workflow input** — free text, optionally with pasted meeting
  notes/requirements, or a pre-built template.
- **LLM planning** — Claude (via tool-use) decomposes the description into an ordered,
  tool-routed execution plan (`notion` / `google_drive` / `teams` steps).
- **Autonomous multi-tool execution** — a LangGraph state machine executes each step, retrying
  failed steps with exponential backoff, and rolling back previously-created resources
  (archiving Notion pages, deleting Drive files) if a step fails unrecoverably.
- **Real-time observability for the user** — every planning decision and tool call streams to
  the browser over Server-Sent Events as it happens.
- **Real observability for the developer** — every LLM call and tool invocation is traced to
  Langfuse (generations, spans, latency, token usage).
- **Runs with zero external accounts** — a built-in dry-run (`MOCK_MODE`) simulates every tool
  call realistically, so the full agent loop is demonstrable without any API keys. Supplying real
  credentials switches each integration to live calls automatically, one at a time.

## 2. Architecture Description

See [`docs/architecture.png`](docs/architecture.png) (source: `docs/architecture.mmd`) for the
full diagram. Summary of the five layers:

| Layer | Technology | Responsibility |
|---|---|---|
| 1. UI | React 18 + Vite + Tailwind CSS v3 | Workflow composer, template library, live SSE log viewer, execution reports, run history |
| 2. Backend API | FastAPI + Uvicorn | REST endpoints, SSE streaming, workflow history persistence, background task orchestration |
| 3. AI Orchestration | LangGraph + Claude (Anthropic) | `parse_intent → plan_actions → execute_step (loop, retry+backoff) → [rollback] → report` state graph |
| 4. Tool Layer | MCP (stdio) + webhook | Notion MCP server, Google Drive MCP server (both launched as local subprocesses over the standard MCP stdio transport), Microsoft Teams Incoming Webhook |
| 5. Observability | Langfuse | One trace per workflow run; one generation per LLM planning call; one span per tool-call attempt and per rollback action |

**Why MCP over stdio instead of Docker containers?** The MCP standard's most common transport is
a local subprocess over stdio — it's exactly how Claude Desktop/Code itself launches MCP
servers. This backend launches `npx @notionhq/notion-mcp-server` and a Google Drive MCP server
the same way, via `app/mcp/client.py`. This keeps the "real MCP orchestration" requirement fully
met without requiring Docker Desktop + WSL2 to be installed and running (see Known Limitations).

**LangGraph state machine:**

```
parse_intent -> plan_actions -> execute_step -+-> execute_step (more steps)
                                               +-> rollback -> report
                                               +-> report (all steps done)
```

Each `execute_step` iteration retries the current step up to `MAX_STEP_RETRIES` times with
exponential backoff (`RETRY_BACKOFF_BASE_SECONDS * 2^attempt`) before marking it failed and
routing to `rollback`, which walks previously-created resources in reverse and archives/deletes
them via the same adapters.

## 3. Setup Instructions

### Prerequisites

- Python 3.10+ (developed against 3.12)
- Node.js 18+ and npm (developed against Node 20)
- (Optional, for real Notion/Google Drive integrations) Node's `npx` on `PATH` — used to launch
  the MCP servers as subprocesses
- An Anthropic API key (optional — falls back to a deterministic offline planner without one)

### Clone & install

```bash
git clone <this-repo-url> workflowweaver
cd workflowweaver

# Backend
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env          # then edit backend/.env with your real keys (all optional)

# Frontend
cd ../frontend
npm install
```

## 4. Environment Variables

All variables live in `.env.example` at the repo root — copy it to `backend/.env`. **Every
variable is optional**; WorkflowWeaver runs fully in dry-run mode with none of them set.

| Variable | Purpose | If unset |
|---|---|---|
| `LLM_API_KEY` | Anthropic (or OpenAI) API key used for plan generation | Falls back to a deterministic keyword-based planner |
| `LLM_PROVIDER` | `anthropic` (default) or `openai` | `anthropic` |
| `ANTHROPIC_MODEL` / `OPENAI_MODEL` | Model id to use for planning | sensible defaults |
| `NOTION_TOKEN` | Notion internal integration token | Notion steps run in mock mode |
| `NOTION_PAGE_ID` | Parent page the agent creates project pages under | required once `NOTION_TOKEN` is set |
| `GOOGLE_CREDENTIALS_PATH` | Path to Google OAuth `credentials.json` | Drive steps run in mock mode |
| `GOOGLE_DRIVE_FOLDER_ID` | Target Drive folder | required once credentials are set |
| `TEAMS_WEBHOOK_URL` | Teams Incoming Webhook / Workflow webhook URL | Teams steps run in mock mode |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | Langfuse project credentials | Tracing is skipped (app still runs) |
| `MOCK_MODE` | Force-simulate every tool call regardless of the keys above | `true` |
| `MAX_STEP_RETRIES` | Retry attempts per step before failing/rolling back | `3` |
| `RETRY_BACKOFF_BASE_SECONDS` | Base for exponential backoff between retries | `1.5` |
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API | `http://localhost:5173,http://127.0.0.1:5173` |

## 5. Frontend Run Instructions

```bash
cd frontend
npm install       # first time only
npm run dev
```

Open **http://localhost:5173**. The Vite dev server proxies `/api/*` to `http://127.0.0.1:8000`
(see `frontend/vite.config.js`), so the backend must be running first (step 6).

Other scripts: `npm run build` (production build to `frontend/dist/`), `npm run preview`
(preview the build), `npm run lint` (ESLint).

## 6. Backend Run Instructions

```bash
cd backend
.venv\Scripts\activate    # Windows;  source .venv/bin/activate on macOS/Linux
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API base: **http://127.0.0.1:8000**
- Interactive API docs (Swagger UI): **http://127.0.0.1:8000/docs**
- Health/integration status: **http://127.0.0.1:8000/api/health**

Run the backend test suite: `pytest` (7 tests covering the API surface and the offline planner).
Lint: `ruff check app tests`.

## 7. Sample Workflow Examples

Four ready-to-run templates ship in `backend/app/core/templates.py` and appear in the "Templates"
tab of the UI:

1. **Meeting Notes to Tasks** — *"Take today's meeting notes and create a Notion project page,
   generate action items with owners, and post a summary to Microsoft Teams."*
2. **Sprint Planning Kickoff** — creates a Notion sprint page, saves a sprint goal doc to Drive,
   and announces the kickoff on Teams.
3. **Incident Response Report** — documents an incident in Notion, archives the postmortem to
   Drive, and alerts stakeholders on Teams.
4. **Requirements to Notion Backlog** — converts an unstructured requirements list into a
   structured Notion backlog and notifies the team.

You can also write your own, e.g.:

> *"Save this incident postmortem as a document in our drive and notify the on-call channel on
> Teams that the incident is resolved."*

Paste it into "New Workflow" with no template selected, optionally add source notes in the
"Meeting notes / requirements" box, and click **Run workflow** — the live log and execution
report render as the agent works.

## 8. Known Limitations

- **Docker/WSL2 is not used for MCP servers.** The Notion and Google Drive MCP servers are
  launched over stdio (`npx <package>`) rather than in Docker containers, because Docker
  Desktop's backend requires WSL2, which isn't guaranteed to be installed/enabled on the target
  machine. This is a standard, spec-compliant MCP transport (the same one Claude Desktop/Code
  uses), not a shortcut — but it does mean the MCP server package must be installable via `npx`
  on the host running the backend.
- **Third-party MCP server tool names aren't pinned.** `NotionAdapter`/`GoogleDriveAdapter` try a
  known tool name first and fall back to heuristic keyword matching against the live server's
  `list_tools()` response, since community MCP server packages can rename/version their tools.
  This has been validated in `MOCK_MODE`; live calls should be smoke-tested against your specific
  server version before production use.
- **Single-process, in-memory active runs.** SSE streams are backed by an in-memory
  `asyncio.Queue` per run; restarting the backend mid-run drops that run's live stream (the final
  report, once written, still persists to disk).
- **JSON-file workflow store**, not a database — adequate for a single-instance capstone
  deployment, not for concurrent multi-instance scaling.
- **No authentication/multi-tenancy** — anyone who can reach the API can trigger workflows and
  read run history. Add an auth layer before exposing this beyond local/trusted-network use.
- **Rollback covers Notion/Drive only.** Teams notifications aren't rolled back (deleting a
  delivered chat message isn't a meaningful "undo" for this workflow).
- **`npm audit` reports 1 moderate + 1 high advisory** in Vite's dev-server dependency chain
  (dev-only, not shipped in the production build) — acceptable for local/dev use as scoped here.
- **LLM planning requires network access to Anthropic's API** when `LLM_API_KEY` is set; without
  it, planning uses the deterministic fallback described above.

## Project Structure

```
workflowweaver/
├── README.md
├── .env.example
├── .gitignore
├── docs/
│   ├── architecture.mmd
│   └── architecture.png
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + lifespan wiring
│   │   ├── api/                 # REST + SSE routes
│   │   ├── core/                # config, models, templates, JSON store, errors
│   │   ├── graph/                # LangGraph nodes, build, runner, LLM planning
│   │   ├── mcp/                  # generic MCP stdio client + Notion/Drive adapters
│   │   └── integrations/         # Microsoft Teams webhook client
│   ├── tests/
│   ├── requirements.txt
│   └── requirements-dev.txt
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   ├── api.js                # REST + SSE client
    │   └── components/
    └── package.json
```
