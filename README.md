# WorkflowWeaver

Describe a business workflow in plain English. An AI agent — built on LangGraph and an LLM
(Claude or Gemini) — plans it into concrete steps and executes them autonomously across Notion,
Google Drive, and Slack, with live streamed progress, retries, and rollback on failure.

> Turn "*Take today's meeting notes and create a Notion project page, generate action items, and
> post a summary to Slack*" into a Notion page, an action-item list, and a Slack
> notification — with zero manual copy-pasting between tools.

---

## 1. Project Overview

WorkflowWeaver is an agentic workflow-automation platform for cross-tool business processes.
Instead of a human manually creating a Notion page, then a Google Drive doc, then a Slack
message, the user writes one sentence and an AI agent plans and executes the whole sequence.

**Core pieces:**

- **Natural-language workflow input** — free text, optionally with pasted meeting
  notes/requirements, or a pre-built template.
- **LLM planning** — Claude tool-use or Gemini function-calling decomposes the description into
  the standard pipeline: `notion` → `google_drive` → `slack`, always in that order and always all
  three, unless the description explicitly says to skip one. If the live LLM call fails for any
  reason (quota exhaustion, rate limiting, a transient outage), planning transparently degrades to
  the same deterministic offline planner used when no API key is configured at all — the run
  still completes end-to-end rather than failing outright (see `generate_plan` in `app/graph/llm.py`).
- **Autonomous multi-tool execution** — a LangGraph state machine executes each step, retrying
  failed steps with exponential backoff, and rolling back previously-created resources
  (deleting the Notion report block, deleting Drive files) if a step fails unrecoverably.
- **Professionally formatted, de-duplicated reports** — Notion pages and Drive docs render the
  same structured content (headings, bulleted/numbered/checklist sections) instead of a wall of
  text, with a timestamp in the title (not the body) so the latest report is identifiable at a
  glance. Each Notion report is a single collapsible block embedded directly in your configured
  parent page — not a separate page — inserted newest-first at the top (Notion's public API has
  no block-reorder endpoint, so this is done by always inserting after a fixed anchor heading; see
  `app/mcp/notion_adapter.py`). The Slack notification is a Block Kit card with a summary plus
  auto-injected links to the Notion report and Drive doc created earlier in the same run — the LLM
  never has to (and can't) guess those URLs, since they don't exist until those steps actually run.
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
| 3. AI Orchestration | LangGraph + LLM (Anthropic Claude or Google Gemini) | `parse_intent → plan_actions → execute_step (loop, retry+backoff) → [rollback] → report` state graph |
| 4. Tool Layer | MCP (stdio) + Web API | Notion MCP server, Google Drive MCP server (both launched as local subprocesses over the standard MCP stdio transport), Slack Web API (`chat.postMessage`) |
| 5. Observability | Langfuse | One trace per workflow run; one generation per LLM planning call; one span per tool-call attempt and per rollback action |

**Why MCP over stdio instead of Docker containers for the MCP servers themselves?** The MCP
standard's most common transport is a local subprocess over stdio — it's exactly how Claude
Desktop/Code itself launches MCP servers. This backend launches `npx @notionhq/notion-mcp-server`
and a Google Drive MCP server the same way, via `app/mcp/client.py`. This keeps the "real MCP
orchestration" requirement fully met without requiring every MCP server to ship its own Docker
image. Docker is still available for running the *app itself* (backend + frontend containers) —
see "Running with Docker" in Section 6 — the MCP servers just run as subprocesses inside the
backend container the same way they do on bare metal.

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
- An LLM API key — Anthropic or Google Gemini (optional — falls back to a deterministic offline
  planner without one)

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
| `LLM_API_KEY` | API key used for plan generation | Falls back to a deterministic keyword-based planner |
| `LLM_PROVIDER` | `anthropic` (Claude tool-use, default) or `google-gemini-ai` (Gemini function-calling) | `anthropic` |
| `LLM_MODEL` | Model id, overrides the per-provider default — check your provider's current model catalog, since specific model ids get deprecated over time (e.g. Gemini's `models/gemini-2.5-flash` was retired in favor of `models/gemini-3.6-flash` during this project's development) | provider's default model |
| `LLM_MAX_OUTPUT_TOKENS` | Max output tokens for the planning call | `4096` |
| `ANTHROPIC_MODEL` / `OPENAI_MODEL` | Legacy per-provider model id, used when `LLM_MODEL` is unset | sensible defaults |
| `NOTION_TOKEN` | Notion internal integration token | Notion steps run in mock mode |
| `NOTION_PAGE_ID` | Parent page the agent creates project pages under | required once `NOTION_TOKEN` is set |
| `NOTION_MCP_COMMAND` | Override the `npx` launch command (Windows only, only needed with multiple Node installs on PATH — see Known Limitations) | `npx` |
| `GOOGLE_CREDENTIALS_PATH` | Path to Google OAuth `credentials.json` | Drive steps run in mock mode |
| `GOOGLE_DRIVE_FOLDER_ID` | Target Drive folder | required once credentials are set |
| `SLACK_BOT_TOKEN` | Slack bot token (`chat:write` scope, bot must be in the target channel) | Slack steps run in mock mode |
| `SLACK_CHANNEL_ID` | Default channel ID `chat.postMessage` posts to | required once `SLACK_BOT_TOKEN` is set |
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
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

> **Don't add `--reload` on Windows if you need real Notion/Drive calls.** See Known
> Limitations below — `--reload` silently breaks MCP subprocess spawning on Windows. Restart
> the process manually after editing backend code instead.

- API base: **http://127.0.0.1:8000**
- Interactive API docs (Swagger UI): **http://127.0.0.1:8000/docs**
- Health/integration status: **http://127.0.0.1:8000/api/health**

Run the backend test suite: `pytest` (7 tests covering the API surface and the offline planner).
Lint: `ruff check app tests`.

### Running with Docker (optional)

```bash
docker compose build
docker compose up
```

This builds and runs both containers — backend on **http://127.0.0.1:8000**, frontend on
**http://localhost:5173** — with source directories bind-mounted so both hot-reload on edits,
same as running natively. `docker-compose.yml` reads `backend/.env` directly (`env_file`) and
overrides the handful of values in it that are host-specific (a Windows-only alternate `npx`
path, a host-relative credentials path) so the same `.env` works in both bare-metal and Docker.

- The backend image installs Node.js 20 alongside Python (for the Notion MCP server's `npx`
  subprocess) via NodeSource's apt repo — cherry-picking Node binaries from the official `node`
  image works in some Node versions but not others (internal `require` paths shift), so don't go
  back to that approach if you edit the Dockerfile.
- Google Drive's OAuth consent is an interactive browser flow that doesn't work well inside a
  container. Run it once natively first (`GOOGLE_CREDENTIALS_PATH`/first real Drive call opens a
  browser) so `backend/data/gdrive_token.json` exists — Compose mounts `backend/data/` into the
  container, so the token (and its auto-refresh) just works from there afterward.
- If `docker compose build` fails with `httpReadSeeker` / `503 Service Unavailable` errors pulling
  a base image, Docker Desktop's "Use containerd for pulling and storing images" setting (Settings
  → General) is likely on and hitting a bad lazy-pull path — turn it off, Apply & Restart, and
  rebuild.
- Since this runs on Linux instead of Windows, `--reload` is safe here (see the Known Limitations
  note above about *not* using it natively on Windows) — the Windows-only event-loop workaround
  that breaks MCP subprocess spawning never triggers on Linux.

## 7. Sample Workflow Examples

Four ready-to-run templates ship in `backend/app/core/templates.py` and appear in the "Templates"
tab of the UI:

1. **Meeting Notes to Tasks** — *"Take today's meeting notes and create a Notion project page,
   generate action items with owners, save a summary document to Google Drive, and post a summary
   to Slack."*
2. **Sprint Planning Kickoff** — creates a Notion sprint page, saves a sprint goal doc to Drive,
   and announces the kickoff on Slack.
3. **Incident Response Report** — documents an incident in Notion, archives the postmortem to
   Drive, and alerts stakeholders on Slack.
4. **Requirements to Notion Backlog** — converts an unstructured requirements list into a
   structured Notion backlog, saves a copy to Drive, and notifies the team on Slack.

Every workflow — templated or freeform — runs the same standard pipeline (Notion → Drive →
Slack), regardless of which of the three the description happens to mention explicitly.

You can also write your own, e.g.:

> *"Save this incident postmortem as a document in our drive and notify the on-call channel on
> Slack that the incident is resolved."*

Paste it into "New Workflow" with no template selected, optionally add source notes in the
"Meeting notes / requirements" box, and click **Run workflow** — the live log and execution
report render as the agent works.

## 8. Known Limitations

- **Never run with `--reload` on Windows when Notion/Drive need to make real calls.** Uvicorn's
  `--reload` (and `--workers > 1`) sets `use_subprocess=True`, which makes uvicorn force
  `asyncio.WindowsSelectorEventLoopPolicy` for the worker process
  (`uvicorn/loops/asyncio.py`) — a Windows-specific accommodation for its own reload-supervisor
  subprocess. But `SelectorEventLoop` cannot spawn child processes on Windows at all: any
  `anyio.open_process()` call (which is exactly how `MCPStdioClient` launches the Notion/Drive
  MCP servers) raises a bare `NotImplementedError()`. Every Notion/Drive step then fails
  instantly, before any network call. Run the backend without `--reload` (see Section 6) and
  restart it manually after editing code — that keeps the default `ProactorEventLoopPolicy`,
  which supports subprocesses.
- **The MCP servers themselves don't run in their own Docker containers.** The Notion MCP server
  is launched over stdio via `npx @notionhq/notion-mcp-server`, and the Google Drive MCP server is
  a first-party module (`app/mcp/gdrive_server.py`) launched via the same Python interpreter
  running the backend — both as subprocesses of the backend process, not as separate containers.
  This is a standard, spec-compliant MCP transport (the same one Claude Desktop/Code uses), not a
  shortcut — but it does mean `npx` must be able to install/run `@notionhq/notion-mcp-server`
  wherever the backend runs (bare metal or inside the backend's own Docker container — see
  "Running with Docker" in Section 6).
- **Third-party MCP server tool names aren't pinned.** `NotionAdapter`/`GoogleDriveAdapter` try a
  known tool name first and fall back to heuristic keyword matching against the live server's
  `list_tools()` response, since community MCP server packages can rename/version their tools.
  Live-smoke-tested end-to-end against `@notionhq/notion-mcp-server` and the first-party Drive
  server in this repo; re-verify if you swap in a different Drive MCP server package.
- **Multiple Node.js installs on Windows PATH can break the Notion MCP server.** If an older Node
  (<18) resolves first, `npx` either fails outright or launches a Node too old to run
  `notion-mcp-server`'s ESM bundle. `MCPStdioClient` prepends the resolved command's own directory
  to `PATH` for the child process to make this consistent, but if the *default* `npx` itself
  resolves to the old install, set `NOTION_MCP_COMMAND` to the `npx`/`npx.cmd` of a Node 18+
  install instead.
- **Google Drive documents are created as native Google Docs, not `.txt` files.** Planned step
  content (`sections`) is rendered to HTML and uploaded with Drive's HTML→Google-Doc import
  conversion, so headings/bold/bulleted-and-numbered lists/checklists survive in the created doc
  instead of landing as flat unstructured text.
- **Single-process, in-memory active runs.** SSE streams are backed by an in-memory
  `asyncio.Queue` per run; restarting the backend mid-run drops that run's live stream (the final
  report, once written, still persists to disk).
- **JSON-file workflow store**, not a database — adequate for a single-instance capstone
  deployment, not for concurrent multi-instance scaling.
- **No authentication/multi-tenancy** — anyone who can reach the API can trigger workflows and
  read run history. Add an auth layer before exposing this beyond local/trusted-network use.
- **Rollback covers Notion/Drive only.** Slack notifications aren't rolled back (deleting a
  delivered chat message isn't a meaningful "undo" for this workflow, even though the Slack API
  itself supports `chat.delete`). On a Notion rollback, `NotionAdapter.delete_report` deletes the
  report's toggle block, not a whole page (see the next point for why).
- **Notion reports are one toggle block in your parent page, deliberately not a separate Notion
  page.** Two earlier designs were tried and rejected: a plain child page under the parent (Notion
  auto-renders a native listing for *any* page you create there, so each report showed up twice —
  once as our own newest-first index, once as Notion's own listing), and filing pages under a
  hidden "archive" container page (avoids the duplicate, but if that one container page is ever
  deleted, every report nested under it is silently orphaned along with it — this happened during
  development and lost real report content). A toggle block is owned directly by the parent page,
  so there's no separate object for either problem to come back through.
- **`npm audit` reports 1 moderate + 1 high advisory** in Vite's dev-server dependency chain
  (dev-only, not shipped in the production build) — acceptable for local/dev use as scoped here.
- **LLM planning requires network access to your configured provider's API** (Anthropic or
  Google) when `LLM_API_KEY` is set. If that call fails for any reason — no key configured, a
  quota/rate-limit error, or a transient provider outage — planning degrades to the deterministic
  offline planner automatically; the run still completes, it just won't be LLM-authored. Check the
  step's logged message (`plan_actions`) to see whether a given run used the real LLM or the
  fallback.
- **Langfuse trace URLs require one extra API call.** `Langfuse.get_trace_url()` resolves the
  dashboard project id via the Langfuse API (cached per client instance) to build the correct
  `/project/{id}/traces/{traceId}` URL, rather than guessing the URL shape.

## 9. Security Notes

- **Never commit real credentials.** `.gitignore` at the repo root excludes `backend/.env`,
  `credentials.json`, and `backend/data/` (which holds the JSON workflow store and Google's cached
  OAuth token) — verified clean across this repo's git history, not just the current working
  tree. `.env.example` ships with placeholder values only; copy it to `backend/.env` and fill in
  real ones there.
- **Rotate any credential that was ever pasted into a chat, ticket, screenshot, or log**, even if
  it never touched git. Plaintext secrets shared through those channels should be treated as
  potentially exposed regardless of where the repo itself ends up.
- **Least-privilege scopes are already the default for each integration** — keep it that way when
  reconfiguring: Notion's internal integration should only be shared with the specific parent page
  it needs (Settings → Connections in Notion), not the whole workspace; the Google OAuth scope is
  `drive.file` (access limited to files this app creates, not full Drive read/write); the Slack bot
  token only needs `chat:write` and membership in the target channel.
- **No authentication on the API itself** (see Known Limitations above) — anyone who can reach the
  backend can trigger workflows and read run history, including the content of past
  descriptions/meeting notes. Don't expose this beyond local/trusted-network use without adding an
  auth layer first.
- **Meeting notes and workflow descriptions flow to whichever LLM provider and Langfuse project
  you've configured.** Don't paste anything into those fields that you wouldn't want stored by a
  third-party API/observability provider — Langfuse traces in particular retain full prompt and
  tool-call payloads for later inspection in its dashboard.
- **`MOCK_MODE=true` (the default) never requires or transmits real credentials** — the entire
  agent loop is demonstrable without any live account access; only flip it to `false` once you're
  ready for real writes.

## Project Structure

```
workflowweaver/
├── README.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── docs/
│   ├── architecture.mmd
│   └── architecture.png
├── backend/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── app/
│   │   ├── main.py              # FastAPI app + lifespan wiring
│   │   ├── api/                 # REST + SSE routes
│   │   ├── core/                # config, models, templates, JSON store, errors, rich-text formatting
│   │   ├── graph/                # LangGraph nodes, build, runner, LLM planning
│   │   ├── mcp/                  # generic MCP stdio client + Notion/Drive adapters
│   │   └── integrations/         # Slack Web API client
│   ├── tests/
│   ├── requirements.txt
│   └── requirements-dev.txt
└── frontend/
    ├── Dockerfile
    ├── .dockerignore
    ├── src/
    │   ├── App.jsx
    │   ├── api.js                # REST + SSE client
    │   └── components/
    └── package.json
```
