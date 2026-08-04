"""FastAPI router for agent control, runs, suggestions, and traces."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models import AgentRun, AgentStep, Suggestion, CompanyResearch
from backend.agents.orchestrator import AgentOrchestrator
from backend.agents.research_agent import research_company

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/run")
def trigger_agent_run(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Trigger an autonomous agent pipeline cycle."""
    orch = AgentOrchestrator(db)
    result = orch.run_pipeline_cycle()
    return {"status": "success", "summary": result}


@router.get("/runs")
def list_agent_runs(limit: int = 50, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    runs = db.query(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit).all()
    out = []
    for r in runs:
        out.append({
            "id": r.id,
            "graph_name": r.graph_name,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "status": r.status,
            "cost_estimate": r.cost_estimate,
        })
    return out


@router.get("/runs/{run_id}/steps")
def list_run_steps(run_id: int, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    steps = db.query(AgentStep).filter(AgentStep.run_id == run_id).order_by(AgentStep.timestamp.asc()).all()
    out = []
    for s in steps:
        out.append({
            "id": s.id,
            "node_name": s.node_name,
            "input": json.loads(s.input_json) if s.input_json else None,
            "output": json.loads(s.output_json) if s.output_json else None,
            "tool_calls": json.loads(s.tool_calls_json) if s.tool_calls_json else None,
            "timestamp": s.timestamp.isoformat() if s.timestamp else None,
        })
    return out


@router.get("/suggestions")
def list_suggestions(status: Optional[str] = None, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    query = db.query(Suggestion)
    if status:
        query = query.filter(Suggestion.status == status)
    sugs = query.order_by(Suggestion.created_at.desc()).all()
    out = []
    for s in sugs:
        out.append({
            "id": s.id,
            "source_agent": s.source_agent,
            "kind": s.kind,
            "payload": json.loads(s.payload_json),
            "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None,
        })
    return out


class ReviewRequest(BaseModel):
    action: str  # approve / reject


@router.post("/suggestions/{suggestion_id}/review")
def review_suggestion(suggestion_id: int, req: ReviewRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    sug = db.query(Suggestion).filter(Suggestion.id == suggestion_id).first()
    if not sug:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    
    if req.action.lower() in ("approve", "approved"):
        sug.status = "approved"
    elif req.action.lower() in ("reject", "rejected"):
        sug.status = "rejected"
    else:
        raise HTTPException(status_code=400, detail="Invalid review action")

    sug.reviewed_at = dt.datetime.utcnow()
    db.commit()
    return {"status": "success", "suggestion_id": suggestion_id, "new_status": sug.status}


@router.get("/research/{company_name}")
def get_company_profile(company_name: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return research_company(db, company_name)
