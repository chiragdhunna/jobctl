"""Company / Role Research Agent (Section 3.2 of PLAN.md)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from backend.llm.client import generate
from backend.db.models import CompanyResearch
from backend.agents.memory import get_memory_store

logger = logging.getLogger("jobctl.agents.research")


def research_company(db: Session, company_name: str, job_title: str = "") -> Dict[str, Any]:
    """Research company stage, size, industry, and signals.

    Checks `company_research` table and memory cache first. If not present,
    uses the LLM to synthesize profile info and caches it.
    """
    if not company_name:
        return {"company_name": "Unknown", "summary": "No company provided.", "sources": []}

    c_key = company_name.strip()
    
    # 1. Check DB cache
    existing = db.query(CompanyResearch).filter(CompanyResearch.company_name.ilike(c_key)).first()
    if existing:
        sources = json.loads(existing.sources_json or "[]")
        return {
            "company_name": existing.company_name,
            "summary": existing.summary,
            "sources": sources,
            "cached": True,
        }

    # 2. Check memory store
    mem = get_memory_store()
    cached_summary = mem.get_company(c_key)
    if cached_summary:
        return {
            "company_name": c_key,
            "summary": cached_summary,
            "sources": ["memory_cache"],
            "cached": True,
        }

    # 3. Generate via LLM
    prompt = f"""You are a corporate research assistant. Provide a concise corporate profile for the company "{c_key}" in the context of a potential job opening ("{job_title}").
Include:
1. Company stage / size / industry
2. Recent news or growth signals
3. Known visa sponsorship or remote work policy (if any)
Keep it under 200 words. Respond in JSON format:
{{"summary": "...", "sources": ["known industry knowledge"]}}"""

    summary_text = f"Company: {c_key}. Active in tech/software."
    sources = ["llm_knowledge"]

    try:
        raw = generate(prompt, expect_json=True)
        data = json.loads(raw)
        summary_text = data.get("summary", summary_text)
        sources = data.get("sources", sources)
    except Exception as exc:
        logger.warning("LLM company research failed for %s: %s. Using fallback.", c_key, exc)

    # Save to DB
    try:
        db_rec = CompanyResearch(
            company_name=c_key,
            summary=summary_text,
            sources_json=json.dumps(sources),
        )
        db.merge(db_rec)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Failed to save company research to DB: %s", exc)

    mem.cache_company(c_key, summary_text)

    return {
        "company_name": c_key,
        "summary": summary_text,
        "sources": sources,
        "cached": False,
    }
