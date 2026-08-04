"""Outreach Agent (Section 3.5 of PLAN.md)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from backend.llm.client import generate
from backend.db.models import OutreachDraft, OutreachContact, Job
from backend.agents.research_agent import research_company

logger = logging.getLogger("jobctl.agents.outreach")


def draft_outreach_message(db: Session, job_id: int) -> Optional[OutreachDraft]:
    """Draft a cold outreach message for a job posting. NEVER sent automatically."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return None

    # Check if draft already exists
    existing = db.query(OutreachDraft).filter(OutreachDraft.job_id == job_id).first()
    if existing:
        return existing

    # Find or create contact
    contact = db.query(OutreachContact).filter(OutreachContact.job_id == job_id).first()
    contact_name = contact.name if contact and contact.name else "Hiring Manager"

    research = research_company(db, job.company, job.title)
    company_summary = research.get("summary", "")

    prompt = f"""You are an expert Executive Outreach Agent.
Draft a concise, highly personalized cold outreach message for a candidate applying to this role.
Never sound spammy or overly formal. Keep it under 120 words.

Job Title: {job.title}
Company: {job.company}
Company Context: {company_summary}
Recipient: {contact_name}

Respond in JSON format:
{{
  "subject": "Quick question regarding {job.title} role",
  "draft_text": "Hi {contact_name},\\n\\nI saw the {job.title} opening at {job.company}...\\n\\nBest,\\nCandidate"
}}"""

    subject = f"Inquiry regarding {job.title} at {job.company}"
    draft_text = f"Hi {contact_name},\n\nI noticed the {job.title} role at {job.company} and would love to connect.\n\nBest regards,"

    try:
        raw = generate(prompt, expect_json=True)
        data = json.loads(raw)
        subject = data.get("subject", subject)
        draft_text = data.get("draft_text", draft_text)
    except Exception as exc:
        logger.warning("Outreach drafting failed for job %s: %s", job_id, exc)

    draft = OutreachDraft(
        job_id=job_id,
        contact_id=contact.id if contact else None,
        channel="linkedin_message",
        draft_text=draft_text,
        subject=subject,
        status="draft",
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft
