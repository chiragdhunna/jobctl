"""Unit tests for jobctl agentic layer and memory store."""

from __future__ import annotations

import pytest
from backend.agents.memory import AgentMemoryStore
from backend.db.session import init_db, SessionLocal
from backend.db.models import Job, CompanyResearch, Suggestion


def test_memory_store_bullets():
    mem = AgentMemoryStore()
    mem.add_resume_bullets(["Built FastAPI microservices in Python", "Optimized React frontend performance"])
    results = mem.query_resume_bullets("Python FastAPI backend", k=1)
    assert len(results) == 1
    assert "FastAPI" in results[0]


def test_memory_store_jobs():
    mem = AgentMemoryStore()
    mem.add_past_job(1, "Senior Python Backend Engineer", 85.0, "tailor_apply")
    similar = mem.query_similar_jobs("Python backend", k=1)
    assert len(similar) == 1
    assert similar[0]["score"] == 85.0


def test_db_models_and_session():
    init_db()
    db = SessionLocal()
    try:
        # Test creating a test job and company research
        job = Job(source="greenhouse", title="Software Engineer", company="Acme Corp", url="https://example.com")
        db.add(job)
        db.commit()
        
        fetched = db.query(Job).filter(Job.company == "Acme Corp").first()
        assert fetched is not None
        assert fetched.title == "Software Engineer"
    finally:
        db.close()
