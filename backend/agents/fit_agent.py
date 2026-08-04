"""Fit & Prioritization Agent (Section 3.3 of PLAN.md)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict
from sqlalchemy.orm import Session

from backend.llm.client import generate
from backend.config import load_base_resume_data, load_keywords
from backend.agents.research_agent import research_company
from backend.agents.memory import get_memory_store

logger = logging.getLogger("jobctl.agents.fit")


def evaluate_job_fit(db: Session, job_data: Dict[str, Any]) -> Dict[str, Any]:
    """ReAct-style fit evaluation with company research and structured verdict."""
    company = job_data.get("company", "")
    title = job_data.get("title", "")
    description = job_data.get("description_raw", "") or job_data.get("description", "")

    # 1. Research company context
    research = research_company(db, company, title)
    company_context = research.get("summary", "")

    # 2. Load candidate resume profile and target rules
    resume_data = load_base_resume_data()
    keywords = load_keywords()
    target_roles = keywords.get("target_roles", [])
    locations = keywords.get("locations", [])
    score_threshold = keywords.get("score_threshold", 70)

    # 3. Retrieve similar past jobs from memory
    mem = get_memory_store()
    similar_jobs = mem.query_similar_jobs(description, k=2)
    few_shot_notes = ""
    if similar_jobs:
        few_shot_notes = "Similar past evaluations:\n" + "\n".join(
            f"- Role: {j.get('text', '')[:50]}... | Score: {j.get('score')} | Outcome: {j.get('outcome')}"
            for j in similar_jobs
        )

    prompt = f"""You are an expert AI Job Fit & Prioritization Agent.
Evaluate how well the candidate fits this job description.

Candidate Resume Profile:
{json.dumps(resume_data, indent=2)}

Target Roles: {target_roles}
Preferred Locations: {locations}
Score Threshold: {score_threshold}

Company Research Context:
{company_context}

{few_shot_notes}

Job Posting:
Title: {title}
Company: {company}
Location: {job_data.get('location', 'Unknown')}
Description:
{description[:3500]}

Provide a structured verdict in JSON format with these exact keys:
{{
  "fit_score": <float 0 to 100>,
  "reasoning": "<detailed explanation of fit>",
  "matched_skills": ["skill1", ...],
  "missing_skills": ["skill1", ...],
  "recommended_action": "<one of: tailor_apply, apply_base, skip, manual_review>"
}}"""

    default_verdict = {
        "fit_score": 50.0,
        "reasoning": "Fallback evaluation due to LLM error.",
        "matched_skills": [],
        "missing_skills": [],
        "recommended_action": "manual_review",
    }

    try:
        raw = generate(prompt, expect_json=True)
        data = json.loads(raw)
        fit_score = float(data.get("fit_score", 50.0))
        reasoning = data.get("reasoning", "Evaluated successfully.")
        matched = data.get("matched_skills", [])
        missing = data.get("missing_skills", [])
        action = data.get("recommended_action", "tailor_apply if fit_score >= score_threshold else skip")

        # Normalize action
        if action not in ("tailor_apply", "apply_base", "skip", "manual_review"):
            action = "tailor_apply" if fit_score >= score_threshold else "skip"

        verdict = {
            "fit_score": fit_score,
            "reasoning": reasoning,
            "matched_skills": matched,
            "missing_skills": missing,
            "recommended_action": action,
            "company_research": company_context,
        }

        # Store in memory
        mem.add_past_job(job_data.get("id", 0), title + " " + description[:200], fit_score, action)

        return verdict
    except Exception as exc:
        logger.error("Fit evaluation failed: %s", exc)
        return default_verdict
