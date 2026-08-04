"""Discovery Agent (Section 3.1 & 3.6 of PLAN.md)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List
from sqlalchemy.orm import Session

from backend.llm.client import generate
from backend.config import load_keywords
from backend.db.models import Suggestion, Job

logger = logging.getLogger("jobctl.agents.discovery")


def run_discovery_suggestions(db: Session) -> List[Dict[str, Any]]:
    """Analyze recent job discovery outcomes and propose keyword or ATS additions."""
    keywords = load_keywords()
    target_roles = keywords.get("target_roles", [])
    locations = keywords.get("locations", [])

    # Get recent jobs stats
    recent_jobs = db.query(Job).order_by(Job.discovered_at.desc()).limit(50).all()
    job_summaries = [f"- {j.title} at {j.company} (score: {j.fit_score})" for j in recent_jobs[:20]]

    prompt = f"""You are an autonomous Job Discovery Agent.
Current target roles: {target_roles}
Current target locations: {locations}

Recent job listings discovered:
{chr(10).join(job_summaries) if job_summaries else 'None yet.'}

Propose up to 2 valuable new keyword variants or ATS company targets that might yield high-fit roles.
Respond in JSON format as a list of suggestions:
[
  {{"kind": "keyword", "payload": {{"new_keyword": "Staff AI Engineer"}}}},
  {{"kind": "ats", "payload": {{"company_slug": "openai", "ats": "greenhouse"}}}}
]
If no suggestions are needed, return []."""

    proposals = []
    try:
        raw = generate(prompt, expect_json=True)
        data = json.loads(raw)
        if isinstance(data, list):
            for item in data:
                kind = item.get("kind", "keyword")
                payload = item.get("payload", {})
                
                # Save suggestion to DB review queue
                suggestion = Suggestion(
                    source_agent="DiscoveryAgent",
                    kind=kind,
                    payload_json=json.dumps(payload),
                    status="pending",
                )
                db.add(suggestion)
                proposals.append(item)
            db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Discovery agent suggestion generation failed: %s", exc)

    return proposals
