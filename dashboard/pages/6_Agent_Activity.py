"""Streamlit page: Agent Activity & Trace Viewer (PLAN.md Section 6)."""

from __future__ import annotations

import streamlit as st
import api_client as api
from theme import inject_theme, page_header

st.set_page_config(page_title="Agent Activity · jobctl", page_icon="🤖", layout="wide")
inject_theme()

page_header(
    "Agent Activity",
    cmd="jobctl agents run && jobctl traces",
    subtitle="Inspect autonomous agent execution runs, reasoning steps, and tool calls.",
)

col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("#### Autonomous Agent Runs")
with col2:
    if st.button("🤖 Run Agent Cycle Now", width="stretch"):
        with st.spinner("Running agent orchestrator cycle..."):
            try:
                res = api.run_agents()
                st.success(f"Agent run complete: {res.get('summary')}")
                st.rerun()
            except api.APIError as exc:
                st.error(str(exc))

try:
    runs = api.list_agent_runs()
    if not runs:
        st.info("No agent runs recorded yet. Click 'Run Agent Cycle Now' to start one.")
    else:
        run_options = {f"Run #{r['id']} — {r['graph_name']} ({r['status']}) [{r['started_at']}]": r["id"] for r in runs}
        selected_label = st.selectbox("Select Agent Run", list(run_options.keys()))
        selected_run_id = run_options[selected_label]

        st.divider()
        st.markdown(f"#### Trace Steps for Run #{selected_run_id}")
        steps = api.list_run_steps(selected_run_id)
        if not steps:
            st.info("No steps recorded for this run.")
        else:
            for s in steps:
                with st.expander(f"Node: `{s['node_name']}` at {s['timestamp']}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**Input Data:**")
                        st.json(s.get("input"))
                    with c2:
                        st.markdown("**Output Data / Tool Calls:**")
                        st.json(s.get("output"))
                        if s.get("tool_calls"):
                            st.markdown(f"**Tools Called:** `{s['tool_calls']}`")
except api.APIError as exc:
    st.error(f"Failed to load agent runs: {exc}")
