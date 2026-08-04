"""LangGraph Orchestrator and Agent Runner (Sections 1, 2, 6, 7 of PLAN.md)."""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.db.models import AgentRun, AgentStep, Job
from backend.agents.fit_agent import evaluate_job_fit
from backend.agents.research_agent import research_company
from backend.agents.tailoring_agent import tailor_resume_agent_pass
from backend.agents.outreach_agent import draft_outreach_message
from backend.agents.discovery_agent import run_discovery_suggestions
from backend.agents.reflection_agent import run_nightly_reflection

logger = logging.getLogger("jobctl.agents.orchestrator")


class AgentOrchestrator:
    """Orchestrates agent runs and records steps in agent_runs / agent_steps."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _log_step(self, run_id: int, node_name: str, input_data: Any, output_data: Any, tools: Optional[List[str]] = None) -> None:
        try:
            step = AgentStep(
                run_id=run_id,
                node_name=node_name,
                input_json=json.dumps(input_data) if input_data else None,
                output_json=json.dumps(output_data) if output_data else None,
                tool_calls_json=json.dumps(tools) if tools else None,
            )
            self.db.add(step)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.warning("Failed to log agent step %s: %s", node_name, exc)

    def run_pipeline_cycle(self) -> Dict[str, Any]:
        """Run the end-to-end agentic workflow cycle."""
        run = AgentRun(graph_name="jobctl_orchestrator", status="running", started_at=dt.datetime.utcnow())
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        run_id = run.id
        summary = {"run_id": run_id, "scored": 0, "outreach": 0, "suggestions": 0}

        try:
            # 1. Discovery Suggestions Node
            self._log_step(run_id, "discovery_node", {}, {"status": "started"}, ["run_discovery_suggestions"])
            sugs = run_discovery_suggestions(self.db)
            summary["suggestions"] = len(sugs)
            self._log_step(run_id, "discovery_node", {}, {"suggestions_count": len(sugs)})

            # 2. Evaluate unscored jobs
            unscored = self.db.query(Job).filter(Job.fit_score == None).limit(5).all()
            for job in unscored:
                job_dict = {
                    "id": job.id,
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "description_raw": job.description_raw,
                }
                self._log_step(run_id, "fit_eval_node", job_dict, {}, ["research_company", "evaluate_job_fit"])
                
                verdict = evaluate_job_fit(self.db, job_dict)
                job.fit_score = verdict.get("fit_score")
                job.score_details_json = json.dumps(verdict)
                
                action = verdict.get("recommended_action", "skip")
                if action == "tailor_apply":
                    job.status = "queued"
                    # Draft outreach if high fit
                    if verdict.get("fit_score", 0) >= 80:
                        draft_outreach_message(self.db, job.id)
                        summary["outreach"] += 1
                else:
                    job.status = "skipped"

                self.db.commit()
                summary["scored"] += 1
                self._log_step(run_id, "fit_eval_node", job_dict, verdict)

            run.status = "success"
            run.finished_at = dt.datetime.utcnow()
            self.db.commit()
        except Exception as exc:
            run.status = "failed"
            run.finished_at = dt.datetime.utcnow()
            self.db.commit()
            logger.error("Agent orchestrator run failed: %s", exc)
            summary["error"] = str(exc)

        return summary
