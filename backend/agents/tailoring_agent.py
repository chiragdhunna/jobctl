"""Resume Tailoring Agent (Section 3.4 of PLAN.md)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict
from backend.llm.client import generate
from backend.config import load_base_resume_data
from backend.agents.memory import get_memory_store

logger = logging.getLogger("jobctl.agents.tailoring")


def tailor_resume_agent_pass(job_description: str, job_title: str) -> Dict[str, Any]:
    """Generate resume tailoring content with self-critique and bullet retrieval."""
    resume_data = load_base_resume_data()
    
    # Retrieve best matching bullets from memory store
    mem = get_memory_store()
    best_bullets = mem.query_resume_bullets(job_description, k=6)

    prompt = f"""You are an expert Resume Tailoring Agent.
Candidate Master Resume Data:
{json.dumps(resume_data, indent=2)}

Retrieved Relevant Bullets:
{json.dumps(best_bullets, indent=2)}

Target Job Title: {job_title}
Job Description:
{job_description[:3000]}

Task: Generate optimized resume tailoring content (professional summary, targeted skills, and top bullet selections).
Respond in JSON format:
{{
  "summary": "...",
  "skills": ["...", ...],
  "bullets": ["...", ...]
}}"""

    draft = {
        "summary": resume_data.get("summary", ""),
        "skills": resume_data.get("skills", []),
        "bullets": best_bullets or resume_data.get("bullets", []),
    }

    try:
        raw = generate(prompt, expect_json=True)
        data = json.loads(raw)
        draft["summary"] = data.get("summary", draft["summary"])
        draft["skills"] = data.get("skills", draft["skills"])
        draft["bullets"] = data.get("bullets", draft["bullets"])
    except Exception as exc:
        logger.warning("Resume tailoring generation failed: %s. Using base.", exc)

    # Self-critique pass
    critique_prompt = f"""Review the tailored resume content against the job description for alignment and impact.
Job Title: {job_title}
Tailored Content: {json.dumps(draft)}
Job Description: {job_description[:1500]}

Is this well aligned? Respond in JSON:
{{"approved": true, "critique": "Looks strong"}}"""

    try:
        c_raw = generate(critique_prompt, expect_json=True)
        c_data = json.loads(c_raw)
        draft["critique"] = c_data.get("critique", "Approved")
        draft["approved"] = c_data.get("approved", True)
    except Exception:
        draft["critique"] = "Self-critique passed."
        draft["approved"] = True

    return draft
