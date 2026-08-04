# jobctl → Agentic AI: Detailed Implementation Plan

## 0. What "agentic" means for this repo specifically

Today jobctl is a **scripted pipeline**: fixed steps (scrape → score → tailor → track) run on a
timer, each step is one LLM call with a fixed prompt, and the only "decision" the LLM makes is a
fit score. That's automation, not agency.

Turning it agentic means introducing components that:

1. **Plan** their own next action instead of following a hardcoded sequence
2. **Use tools** dynamically (search, fetch, query DB, send draft) rather than being called by tools
3. **Maintain memory** across runs (what worked, what got rejected, what you liked/rejected)
4. **Reflect and self-correct** (critique their own output and retry before showing it to you)
5. **Ask for human approval** at the right checkpoints instead of either full-auto or full-manual

The plan below keeps your existing FastAPI/SQLAlchemy/Streamlit/APScheduler stack and _adds_ an
agent layer on top of it — it does not propose a rewrite.

---

## 1. High-level architecture

```
                         ┌─────────────────────────────────────────┐
                         │              backend/agents/              │
                         │                                           │
   scheduler/  ───────▶  │   Orchestrator (LangGraph state machine)  │
   (trigger)             │                                           │
                         │   ┌───────────┐  ┌───────────┐  ┌───────┐ │
                         │   │ Discovery │→ │  Research  │→ │  Fit  │ │
                         │   │  Agent    │  │   Agent    │  │ Agent │ │
                         │   └───────────┘  └───────────┘  └───┬───┘ │
                         │                                     ▼     │
                         │   ┌────────────┐  ┌───────────┐ ┌───────┐ │
                         │   │  Outreach  │◀ │  Resume    │◀│ Human │ │
                         │   │   Agent    │  │  Tailoring │ │ Gate  │ │
                         │   └─────┬──────┘  │   Agent    │ └───────┘ │
                         │         ▼          └───────────┘           │
                         │   ┌────────────┐                          │
                         │   │ Reflection │  (nightly, reads outcomes)│
                         │   │   Agent    │                          │
                         │   └────────────┘                          │
                         └─────────────────────────────────────────┘
                                         │
                          reads/writes   ▼
                         SQLite (existing) + vector store (new)
```

Each box is a LangGraph **node** with its own system prompt, tool set, and exit conditions. The
orchestrator is a graph, not a script, so nodes can loop, retry, branch, or pause for human input
— which a linear `scheduler/runner.py` loop cannot do cleanly.

---

## 2. Orchestration framework choice

| Option                              | Verdict                                                                                                                                                                                            |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **LangGraph**                       | **Recommended.** Explicit state graph, built-in persistence (checkpointer → SQLite, matches your stack), native human-in-the-loop interrupts, works with Gemini and Ollama via LangChain adapters. |
| CrewAI                              | Simpler role-based framing but weaker control over branching/interrupts; better for one-shot multi-agent tasks than a long-running, resumable pipeline.                                            |
| Raw Claude/Gemini tool-calling loop | Fine for one or two agents, but you'd re-implement checkpointing, retries, and interrupts yourself — not worth it once you have 5+ agents.                                                         |

Add `langgraph`, `langchain-google-genai`, `langchain-community` (Ollama) to `requirements.txt`.
Keep `backend/llm/client.py` as the low-level provider abstraction; LangGraph nodes call into it
(or into LangChain chat models wrapping it) rather than replacing it.

---

## 3. The agents

### 3.1 Discovery Agent (upgrades the current scraper step)

- **Today:** fixed list of ATS slugs/keywords from `config/keywords.yaml`, scraped every cycle.
- **Agentic version:** given last N cycles' results + fit scores, decides _which_ sources/queries
  are worth re-running this cycle, and can propose new keyword variants or ATS companies to add
  (e.g. "roles at similarly-sized companies to the ones you scored highest") — proposals go to a
  review queue, never auto-applied to config.
- **Tools:** existing scrapers wrapped as callables (`search_greenhouse(company)`,
  `search_remotive(query)`, etc.), plus a new `propose_keyword_change(...)` tool that writes to a
  `suggestions` table instead of `config/keywords.yaml` directly.

### 3.2 Company/Role Research Agent (new)

- For jobs above a low bar (not yet full fit score), does a light web-research pass: company
  size/stage, recent news, glassdoor-style signals, visa sponsorship history — feeding richer
  context into scoring and resume tailoring than the raw JD alone.
- **Tools:** `web_search`, `web_fetch`-equivalent, cached to `company_research` table so the same
  company isn't re-researched every cycle.

### 3.3 Fit & Prioritization Agent (upgrades scoring)

- **Today:** one-shot 0–100 score with reasoning.
- **Agentic version:** ReAct-style — can call the research tool if the JD is ambiguous, can compare
  the role against your stated goals (e.g. UK relocation, target companies, seniority) not just
  keyword overlap, and produces a structured verdict: score, reasoning, matched/missing skills,
  and a **recommended action** (tailor & apply / apply with base resume / skip / flag for manual
  review). This is where "just a score" becomes an actual decision.

### 3.4 Resume Tailoring Agent (upgrades the current generate→validate→repair loop)

- You already have validate/repair passes — this is the most "agentic-ready" part of the repo.
  Formalize it as a **generate → self-critique → repair** loop inside a LangGraph node with a
  bounded number of iterations (reuse `RESUME_REPAIR_ATTEMPTS`), where the critique step is a
  _separate_ LLM call grading the draft against the JD (not just LaTeX validity) before it's
  shown to you.

### 3.5 Outreach Agent (new — the actual "everything" beyond resumes)

- Drafts a short, personalized cold message to a hiring manager/recruiter for high-fit roles,
  using the company research + your resume data.
- **Never sends automatically.** Writes to an `outreach_messages` table with status `drafted`;
  surfaces in a new dashboard "Outreach" tab for you to edit and send yourself (or, later, a
  manual "copy to clipboard" / mailto link — sending via API is a separate, explicit opt-in).
- This directly extends the existing "you review and send" philosophy in the README instead of
  breaking it.

### 3.6 Reflection Agent (new — closes the loop)

- Runs nightly (APScheduler job). Reads `applications` + any outcome you've logged (interview,
  rejected, ghosted) and produces a short written analysis: which job attributes correlate with
  better outcomes, whether `score_threshold` or keywords should change. Writes suggestions to the
  same `suggestions` table as the Discovery Agent — always human-approved, never auto-applied.

---

## 4. Memory layer (what makes it "agentic" rather than "a longer prompt chain")

Add a lightweight vector store — **`sqlite-vec`** or **Chroma with a local persistent path** (no
new infra, stays local-first) — storing:

- Past JD + score + outcome triples, so the Fit Agent can retrieve "similar roles you scored well
  on / got rejected from" as few-shot context.
- Your resume bullet library, so the Tailoring Agent can pull the _best-matching_ bullets instead
  of relying on the LLM to remember your whole resume in one prompt.
- Company research summaries, so repeated encounters with the same company don't re-spend tokens.

This is additive to the existing SQLite schema, not a replacement.

---

## 5. New data model (additions only)

```
agent_runs        id, graph_name, started_at, finished_at, status, cost_estimate
agent_steps       run_id, node_name, input_json, output_json, tool_calls_json, timestamp
suggestions       id, source_agent, kind (keyword/threshold/etc), payload_json, status, reviewed_at
outreach_messages id, job_id, contact_name, contact_channel, draft_text, status, sent_at
company_research  company_name, summary, sources_json, fetched_at
feedback_events   job_id, event_type (interview/rejected/ghosted/offer), note, logged_at
```

`agent_steps` is your audit trail — every tool call and intermediate reasoning step, so the
dashboard can show _why_ an agent did something, which matters a lot once agents propose changes
rather than just execute a fixed script.

---

## 6. Human-in-the-loop design (critical — don't let this become a black box)

LangGraph's `interrupt()` mechanism maps cleanly onto this:

- **Discovery/Reflection suggestions** → land in a review queue, applied only on approval.
- **Outreach drafts** → never auto-sent; explicit send action required.
- **Resume tailoring** → unchanged from today (you already download/review before applying).
- **Kill switch** → a single `AGENTS_ENABLED=false` env flag that reverts to the current linear
  pipeline behavior, so you're never locked out of the simpler, predictable mode.

New dashboard pages: **Agent Activity** (trace viewer over `agent_steps`), **Suggestions** (approve/
reject queue), **Outreach**.

---

## 7. Phased rollout (matches the repo's existing "one working phase per commit" style)

| Phase | Deliverable                                                                                                                             |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | Add LangGraph dependency; wrap existing scoring call as a single-node graph with no behavior change — proves the plumbing works.        |
| 2     | Split scoring into Fit Agent with the ReAct research-tool loop (3.3); add `company_research` table + Research Agent (3.2).              |
| 3     | Formalize Tailoring Agent's critique step (3.4) — reuses existing validate/repair code, adds the JD-alignment critique.                 |
| 4     | Add `agent_runs`/`agent_steps` tables + Agent Activity dashboard page — get observability before adding more autonomy.                  |
| 5     | Discovery Agent + `suggestions` table + review queue UI (3.1, 3.6 groundwork).                                                          |
| 6     | Outreach Agent + Outreach dashboard tab (3.5) — the highest-value, highest-risk addition, so it comes after the guardrails (4–5) exist. |
| 7     | Reflection Agent (3.6) + memory/vector store (Section 4) — needs enough logged outcomes to be useful, so naturally comes last.          |

Each phase should be independently mergeable and leave `AGENTS_ENABLED=false` as a safe fallback.

---

## 8. Testing agents (different from testing scripts)

- **Golden set**: 15–20 real past JDs with a score/verdict you'd expect; run as a regression suite
  whenever prompts or the graph change (an LLM-as-judge pass, similar to the existing repair-pass
  pattern, works well here).
- **Tool-call tracing**: assert the Fit Agent only calls the research tool when the JD is genuinely
  ambiguous (cost control — you're on Ollama/Gemini free tier much of the time).
- **Cost/latency budget per run**: log `cost_estimate` in `agent_runs`; alert (log line, not push
  notification, keeping it local-first) if a cycle exceeds a token budget.

---

## 9. Immediate next step

Given the phasing above, the smallest useful first PR is **Phase 1 + first half of Phase 2**:
wrap the existing scorer in a one-node LangGraph graph, then extend it with the research tool and
a structured verdict output. This touches `backend/llm/`, adds `backend/agents/`, and one new
table (`company_research`) — small enough to land in one sitting, and it's the foundation every
later agent depends on.
