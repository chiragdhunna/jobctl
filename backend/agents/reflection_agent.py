"""Reflection Agent (Section 3.6 of PLAN.md)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List
from sqlalchemy.orm import Session

from backend.llm.client import generate
from backend.db.models import Application, Job, FeedbackEvent, Suggestion

logger = logging.getLogger("jobctl.agents.reflection")


def run_nightly_reflection(db: Session) -> Dict[str, Any]:
    """Analyze application outcomes and generate strategic recommendations."""
    applications = db.query(Application).all()
    feedback = db.query(FeedbackEvent).all()
    jobs_count = db.query(Job).count()

    app_stats = f"Total jobs: {jobs_count}, Applications: {len(applications)}, Feedback events: {len(feedback)}"

    prompt = f"""You are an AI Reflection & Strategy Agent for job search optimization.
Pipeline Statistics:
{app_stats}

Analyze outcomes and suggest strategic adjustments (e.g. adjust score_threshold, refine keywords, focus on specific company tiers).
Respond in JSON format:
{{
  "analysis": "Summary of what is working and what isn't.",
  "suggestions": [
    {{"kind": "threshold", "payload": {{"score_threshold": 75}}}},
    {{"kind": "keyword", "payload": {{"add_keyword": "Senior Platform Engineer"}}}}
  ]
}}"""

    result = {"analysis": "Pipeline is running normally.", "suggestions": []}
    try:
        raw = generate(prompt, expect_json=True)
        data = json.loads(raw)
        result["analysis"] = data.get("analysis", result["analysis"])
        sugs = data.get("suggestions", [])
        for item in sugs:
            sug = Suggestion(
                source_agent="ReflectionAgent",
                kind=item.get("kind", "strategy"),
                payload_json=json.dumps(item.get("payload", {})),
                status="pending",
            )
            db.add(sug)
        db.commit()
        result["suggestions"] = sugs
    except Exception as exc:
        db.rollback()
        logger.warning("Nightly reflection failed: %s", exc)

    return result
