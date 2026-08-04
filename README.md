# jobctl

`jobctl` is a local-first job discovery, ranking, and application-assistance system. It aggregates openings from public ATS boards and job boards, scores them against your resume, generates tailored resumes and grounded application content, and gives you a review-first dashboard for everything that is worth acting on.

It is designed to run on your own machine. Job data, resume data, generated PDFs, and browser session state stay local.

```
ATS APIs (Greenhouse / Lever / Ashby / Workday)
    ─┐
Public boards (Remotive / RemoteOK / Arbeitnow / The Muse / Jobicy / Adzuna)
    ├──▶ jobs in SQLite ───▶ LLM fit scoring ───▶ Recommended jobs
LinkedIn / Indeed discovery (logged-in browser session)
    ─┘

Recommended jobs ─▶ tailored resume PDF ─▶ applied tracking ─▶ outreach drafts ─▶ human review
```

## What changed recently

The codebase is no longer just a scraper + scorer. It now includes an agentic layer that can:

- research companies,
- evaluate job fit with structured reasoning,
- tailor resume content in agent passes,
- draft outreach messages,
- generate discovery suggestions,
- and record reflection / strategy proposals for human review.

The scheduler still handles the main discover-and-score pipeline. The new agent layer is a separate, reviewable workflow exposed through the API and dashboard.

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [LLM setup: Gemini vs Ollama](#llm-setup-gemini-vs-ollama)
- [Running the app](#running-the-app)
- [Dashboard tour](#dashboard-tour)
- [API surface](#api-surface)
- [Agentic AI layer](#agentic-ai-layer)
- [How the pipeline works](#how-the-pipeline-works)
- [Data model](#data-model)
- [Responsible use](#responsible-use)
- [Troubleshooting](#troubleshooting)
- [Project structure](#project-structure)

## Features

- **Multi-source discovery** — scrapes ATS boards and public boards, then optionally discovers LinkedIn and Indeed postings through your own persistent browser session.
- **LLM scoring** — ranks jobs with a fit score, reasoning, matched skills, and gaps so you can focus on the strongest matches first.
- **Review-first recommendations** — the dashboard shows the best-fit jobs at the top and keeps the actual application action in your hands.
- **Tailored resumes** — generates a job-specific LaTeX resume and compiles it to PDF when a LaTeX engine is available.
- **Base-resume fallback** — if tailoring or compilation fails, the system can still attach your base resume so you are not blocked.
- **Grounded answers** — generates short, resume-backed responses for common application questions.
- **Applied tracking** — lets you mark jobs as applied, undo that action, and keep an application history.
- **Outreach drafting** — drafts LinkedIn and email outreach messages for jobs that deserve follow-up, but never sends anything automatically.
- **Agent activity traceability** — records autonomous agent runs, steps, tool calls, and reviewable suggestions.
- **Provider flexibility** — supports Gemini and local Ollama, with fallback logic in auto mode.
- **Scheduled pipeline** — continuously discovers and scores jobs on a configurable interval.

## Architecture

The app is split into four layers:

1. **Discovery** — ATS/public board scrapers and optional browser-based LinkedIn/Indeed discovery add jobs to SQLite.
2. **Ranking** — the scorer adds fit scores, reasoning, matched skills, and gaps.
3. **Action support** — the resume tailor, answer generator, and outreach drafter prepare materials for you.
4. **Human review** — the dashboard and agent review queues keep the final decisions with you.

The backend exposes a FastAPI app, the dashboard is a multi-page Streamlit UI, and the scheduler is an APScheduler loop that runs discovery and scoring on cadence.

## Tech stack

Python 3.11+ · FastAPI · SQLAlchemy + SQLite · Streamlit · Playwright · APScheduler · Gemini / Ollama · LaTeX via tectonic or pdflatex.

## Quick start

```bash
# 1. Clone and enter the repo
git clone https://github.com/chiragdhunna/jobctl.git
cd jobctl

# 2. Create a virtual environment and install dependencies
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. Install Playwright Chromium if you plan to use LinkedIn / Indeed discovery
python -m playwright install chromium

# 4. Configure local secrets and search preferences
copy .env.example .env
# edit .env, config/keywords.yaml, and config/base_resume_data.json

# 5. Install a LaTeX engine for PDF generation
# Windows: install MiKTeX
# macOS: brew install tectonic
# Linux: install tectonic or pdflatex through your package manager

# 6. Start the app
./run.sh

# 7. In another terminal, run one discovery + scoring cycle
./discover.sh
```

Then open the dashboard at http://localhost:8501 and the API docs at http://localhost:8000/docs.

If you use LinkedIn or Indeed discovery, log into the persistent browser profile once before relying on automated discovery.

## Configuration

### `.env`

These values are read from the environment at startup:

| Variable                               | Purpose                                                      |
| -------------------------------------- | ------------------------------------------------------------ |
| `GEMINI_API_KEY`                       | Gemini key; leave blank to use Ollama.                       |
| `LLM_PROVIDER`                         | `auto`, `gemini`, or `ollama`.                               |
| `GEMINI_MODEL`                         | Gemini model name, default `gemini-2.0-flash`.               |
| `OLLAMA_HOST`                          | Ollama HTTP endpoint, default `http://localhost:11434`.      |
| `OLLAMA_MODEL`                         | Local Ollama model name, default `llama3.1:8b`.              |
| `OLLAMA_TIMEOUT`                       | Timeout for long LLM generations.                            |
| `OLLAMA_NUM_CTX`                       | Context window for long prompts.                             |
| `RESUME_MODE`                          | `auto` or `base_only`.                                       |
| `RESUME_TAILOR_STRATEGY`               | `auto`, `patch`, or `full`.                                  |
| `RESUME_REPAIR_ATTEMPTS`               | Number of repair passes for bad LaTeX output.                |
| `LATEX_COMPILE_TIMEOUT`                | Timeout per LaTeX compile attempt.                           |
| `LINKEDIN_EMAIL` / `LINKEDIN_PASSWORD` | Reference only; login is manual.                             |
| `INDEED_EMAIL` / `INDEED_PASSWORD`     | Reference only; login is manual.                             |
| `INDEED_DOMAIN`                        | Regional Indeed domain, for example `https://uk.indeed.com`. |
| `DB_PATH`                              | SQLite path, default `./data/jobs.db`.                       |
| `BROWSER_PROFILE_DIR`                  | Persistent browser profile for LinkedIn / Indeed discovery.  |
| `MAX_APPLICATIONS_PER_RUN`             | Per-run cap for application automation.                      |
| `AUTOMATION_DRY_RUN`                   | Fill forms without clicking the final submit button.         |

### `config/keywords.yaml`

This file defines your job-search defaults:

- target roles,
- target locations,
- excluded companies,
- salary floor,
- score threshold,
- platform toggles,
- source toggles,
- run interval,
- ATS company slugs to scrape.

Example:

```yaml
ats_companies:
  greenhouse: ["stripe", "gitlab", "databricks"]
  lever: ["leverdemo", "plaid"]
  ashby: ["ramp", "notion", "openai"]
  workday: []
```

Workday is tenant-specific. To add a Workday board, use objects shaped like this:

```yaml
workday:
  - name: "Some Company"
    cxs_url: "https://company.wd1.myworkdayjobs.com/wday/cxs/company/External/jobs"
    site_url: "https://company.wd1.myworkdayjobs.com/en-US/External"
```

### Runtime overrides

The dashboard Settings page writes runtime overrides into the `settings` table. Those values win over `keywords.yaml` for:

- `score_threshold`
- `platform_toggles`
- `source_toggles`
- `run_interval_minutes`

## LLM setup: Gemini vs Ollama

Every LLM call goes through `backend/llm/client.py`. The provider behavior is:

| `LLM_PROVIDER` | Behavior                                                                                                                 |
| -------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `auto`         | Gemini if `GEMINI_API_KEY` is present; otherwise Ollama. If Gemini fails at runtime, the client can fall back to Ollama. |
| `gemini`       | Force Gemini only.                                                                                                       |
| `ollama`       | Force local Ollama only.                                                                                                 |

### Gemini

Gemini is the best choice for quality and speed if you want remote inference. Create a key at https://aistudio.google.com/app/apikey and set `GEMINI_API_KEY`.

### Ollama

Ollama keeps everything local. Install it from https://ollama.com, then pull a model before the first run:

```bash
ollama pull llama3.1:8b
```

Suggested models by hardware:

| Hardware        | Suggested model                 | Notes                                       |
| --------------- | ------------------------------- | ------------------------------------------- |
| Low-VRAM laptop | `llama3.1:8b`                   | Balanced default.                           |
| 12 GB+ VRAM     | `qwen2.5:14b` or `mistral-nemo` | Stronger at strict JSON and longer outputs. |

The app checks both provider status and Ollama reachability on the dashboard Settings page and through `GET /settings/llm-status`.

## Running the app

The repository intentionally separates the long-running UI/backend process from the batch discovery pipeline.

```bash
./run.sh
./discover.sh
./discover.sh --loop
```

- `./run.sh` starts the backend API and the dashboard.
- `./discover.sh` runs one discovery + scoring cycle and exits.
- `./discover.sh --loop` keeps that pipeline running on the configured interval.

Useful direct commands:

```bash
uvicorn backend.main:app --reload --port 8000
python -m scheduler.runner --once
streamlit run dashboard/app.py
```

### Browser login flow

LinkedIn and Indeed discovery use your own logged-in persistent browser profile. The login itself is not automated.

```bash
python -m automation.linkedin_apply --login
python -m automation.indeed_apply --login
```

Open the browser, sign in manually, then save the session by closing the browser or following the terminal prompt.

### Windows notes

- `./run.sh` auto-detects the Windows virtualenv layout.
- If the login command is running in Git Bash, use `winpty` if stdin handling is awkward.
- For PDF generation on Windows, install MiKTeX and compile `config/base_resume.tex` once to preload missing packages.

### Docker

```bash
docker compose up --build
```

The container setup covers the API and dashboard. Browser-based discovery and the scheduler still need a host browser/session, so keep LinkedIn/Indeed toggles off for container-only runs unless you know what you are doing.

## Dashboard tour

The dashboard is the main operating surface.

- **Home** — pipeline status, active LLM provider, and one-click discovery / scoring.
- **Recommended** — best-fit jobs first, with score, reasoning, posting link, tailored resume, quick base resume, applied tracking, and skip controls.
- **Applied** — jobs you marked as applied, with filters for platform, status, and date.
- **Settings** — score threshold, platform/source toggles, run interval, and live LLM/Ollama status.
- **Resume Versions** — every generated resume per job, with PDF download and LaTeX view.
- **Outreach** — review-only outreach drafts for recruiter / hiring-manager contact.
- **Agent Activity** — agent runs, trace steps, and tool-call history.
- **Suggestions** — human review queue for agent proposals.

The dashboard talks to the backend over HTTP, so it operates on the same data and settings as the scheduler.

## API surface

The main FastAPI app lives in `backend/main.py` and mounts these routers:

- `GET /health` — liveness check.
- `GET /settings` / `PUT /settings` — read and edit runtime settings.
- `GET /settings/llm-status` — live provider and Ollama reachability status.
- `POST /settings/clear-data` — destructive data reset with confirmation.
- `GET /jobs` — list jobs.
- `POST /jobs/scrape` — run discovery now.
- `GET /jobs/recommended` — ranked jobs, highest fit first.
- `POST /jobs/{id}/score` and `POST /jobs/score` — score a single job or all new jobs.
- `POST /jobs/{id}/resume` — generate a resume for a job.
- `POST /jobs/{id}/answers` — generate grounded answers for application questions.
- `GET /jobs/{id}/resumes` and `GET /jobs/resume-version/{rv_id}` — inspect generated resume versions.
- `POST /jobs/{id}/mark-applied` / `POST /jobs/{id}/unmark-applied` — applied tracking.
- `GET /outreach` — jobs with outreach state.
- `POST /outreach/{job_id}/regenerate` — rebuild contact and drafts.
- `PUT /outreach/{job_id}/contact` — manually set a contact.
- `PUT /outreach/{job_id}/draft/{draft_id}` — edit a draft.
- `PUT /outreach/{job_id}/draft/{draft_id}/mark-sent` — record that you sent it yourself.
- `GET /agents/runs` / `GET /agents/runs/{run_id}/steps` — agent traces.
- `POST /agents/run` — trigger an autonomous agent cycle.
- `GET /agents/suggestions` / `POST /agents/suggestions/{id}/review` — review the agent proposal queue.
- `GET /agents/research/{company_name}` — company research lookup.
- `GET /debug/llm-check` — simple provider smoke test.

## Agentic AI layer

The agentic layer is separate from the main discovery scheduler. It is designed for controlled, inspectable automation rather than hidden background behavior.

### Orchestrated agent cycle

`POST /agents/run` triggers `AgentOrchestrator.run_pipeline_cycle()`.

That cycle currently does the following:

1. Generates discovery suggestions.
2. Evaluates unscored jobs with fit reasoning.
3. Moves strong matches into a queued state.
4. Drafts outreach when the fit is high enough.
5. Records agent runs and steps for later inspection.

### Research agent

The research agent builds a lightweight company profile using cached data first, then the database, then the LLM if needed. The output is cached so the same company does not need to be researched repeatedly.

### Fit agent

The fit agent evaluates a job against your resume and produces the structured data that powers fit scores, recommendations, and the reasoning shown in the dashboard.

### Tailoring agent

The tailoring agent produces resume-tailoring content in JSON form, then the LaTeX engine turns that into an updated resume document.

### Outreach agent

The outreach agent drafts a short LinkedIn message or email based on the role and company context. It never sends anything automatically.

### Reflection agent

The reflection agent summarizes outcomes and proposes strategy changes, such as threshold tweaks or keyword additions. Those proposals land in the suggestions queue for human review.

## How the pipeline works

The scheduler loop in `scheduler/runner.py` handles the main recurring pipeline. On each interval it:

1. Scrapes ATS boards.
2. Scrapes public job boards.
3. Optionally discovers LinkedIn and Indeed postings through your logged-in browser profile.
4. Scores all new jobs.
5. Optionally generates outreach drafts for jobs that should be followed up.

Jobs at or above your score threshold appear on the Recommended page. From there you can:

- open the posting,
- generate a tailored resume,
- compile your base resume quickly,
- mark the job as applied,
- undo a mistaken applied mark,
- or skip the job.

The scheduler logs a condensed summary to the console and `logs/scheduler.log`.

### Status flow

The main job statuses are:

- `new`
- `scored`
- `queued`
- `applied`
- `skipped`
- `failed`
- `needs_review`

## Data model

SQLite is accessed through SQLAlchemy models. The key tables are:

- `jobs` — discovered postings and score data.
- `applications` — application history and submission notes.
- `resume_versions` — generated LaTeX and PDF paths for a job.
- `settings` — runtime overrides stored as JSON.
- `agent_runs` — top-level agent cycle records.
- `agent_steps` — trace entries for each agent node.
- `suggestions` — human-review proposals from the agent layer.
- `company_research` — cached company summaries.
- outreach contact and draft tables for review-only message drafting.

## Responsible use

This project is intended to help you manage your own job search.

- Public ATS and job-board discovery is mostly ordinary read-only API usage.
- LinkedIn and Indeed discovery uses your own logged-in browser session and should be enabled only if you are comfortable with the relevant site terms.
- Outreach is draft-only. There is no send endpoint, no background auto-send, and no hidden submission path.
- Keep `.env`, `data/`, `logs/`, and the browser profile out of version control.

### Legacy automation modules

The older ATS apply automation still exists under `automation/`, but it is not the primary path used by the scheduler. The main app flow is discovery, scoring, tailoring, manual review, and explicit user action.

## Troubleshooting

- **Ollama not reachable** — start it with `ollama serve` and pull a model, or set `GEMINI_API_KEY`.
- **Ollama times out on resume generation** — increase `OLLAMA_TIMEOUT`, use a smaller model, increase `OLLAMA_NUM_CTX`, or switch to Gemini.
- **Generated LaTeX does not compile** — install `tectonic` or `pdflatex`. The app stores the LaTeX even if the PDF compilation fails.
- **Resume generation falls back to base resume** — that is expected when tailoring fails or the LLM is unavailable.
- **LinkedIn / Indeed discovery says not logged in** — run the manual login flow for that platform once.
- **Scores look wrong** — improve `config/base_resume_data.json`, tune your target roles and keywords, or use a stronger model.
- **Agent suggestions look off** — review them in the Suggestions page before accepting anything.

## Project structure

```text
backend/        FastAPI app, config, DB models, LLM client, scrapers, scoring,
               resume tailoring, answer generation, outreach, agent graph, routers
automation/     Playwright browser automation and legacy ATS apply helpers
dashboard/      Streamlit multi-page dashboard and API client
scheduler/      APScheduler discovery + scoring loop
config/         keywords.yaml and base_resume_data.json
tests/          test coverage for agent and app behavior
run.sh          local launcher for backend + dashboard
discover.sh     one discovery/scoring pipeline run or loop
docker-compose.yml / Dockerfile   optional API + dashboard container setup
```

## Closing note

The project is intentionally opinionated: the system automates the boring parts, but it keeps the final application and outreach decisions in your control.
