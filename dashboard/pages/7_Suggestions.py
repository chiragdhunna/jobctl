"""Streamlit page: Suggestions & Human Review Queue (PLAN.md Section 6)."""

from __future__ import annotations

import streamlit as st
import api_client as api
from theme import inject_theme, page_header

st.set_page_config(page_title="Suggestions · jobctl", page_icon="💡", layout="wide")
inject_theme()

page_header(
    "Suggestions Queue",
    cmd="jobctl suggestions review",
    subtitle="Human-in-the-loop review queue for autonomous agent proposals (keywords, ATS targets, strategy).",
)

try:
    suggestions = api.list_suggestions(status="pending")
    if not suggestions:
        st.info("No pending suggestions in the review queue. Agents propose additions here after running.")
    else:
        st.markdown(f"#### Pending Proposals ({len(suggestions)})")
        for s in suggestions:
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 1])
                with c1:
                    st.markdown(f"**Agent:** `{s['source_agent']}` · **Kind:** `{s['kind']}`")
                    st.json(s["payload"])
                    st.caption(f"Proposed at: {s['created_at']}")
                with c2:
                    st.markdown("")
                with c3:
                    st.markdown("")
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✅ Approve", key=f"app_{s['id']}"):
                            try:
                                api.review_suggestion(s["id"], "approve")
                                st.success("Approved!")
                                st.rerun()
                            except api.APIError as exc:
                                st.error(str(exc))
                    with b2:
                        if st.button("❌ Reject", key=f"rej_{s['id']}"):
                            try:
                                api.review_suggestion(s["id"], "reject")
                                st.warning("Rejected.")
                                st.rerun()
                            except api.APIError as exc:
                                st.error(str(exc))
except api.APIError as exc:
    st.error(f"Failed to load suggestions: {exc}")
