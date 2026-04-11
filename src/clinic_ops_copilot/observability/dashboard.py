"""Streamlit observability dashboard.

Read-only view over the SQLite events store. Surfaces:
- Per-agent call counts (1h / 24h / 7d windows)
- p50/p95 latency per agent
- Tool-call error rate per tool
- Recent decisions with full trace expansion
- Eval harness pass/fail trend over time

Run with: ``clinicops dashboard`` (which shells out to ``streamlit run`` on this file).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from clinic_ops_copilot.config import settings


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.events_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _events_df(window: timedelta | None = None) -> pd.DataFrame:
    with _connect() as conn:
        if window is None:
            cur = conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT 5000")
        else:
            cutoff = (datetime.now(UTC) - window).isoformat()
            cur = conn.execute(
                "SELECT * FROM events WHERE timestamp >= ? ORDER BY id DESC LIMIT 5000",
                (cutoff,),
            )
        rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        return pd.DataFrame(
            columns=[
                "id",
                "timestamp",
                "trace_id",
                "agent",
                "event_type",
                "tool_name",
                "latency_ms",
                "status",
                "payload",
            ]
        )

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def _eval_df() -> pd.DataFrame:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT timestamp, suite, case_id, passed FROM eval_runs ORDER BY id DESC LIMIT 1000"
        )
        rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        return pd.DataFrame(columns=["timestamp", "suite", "case_id", "passed"])

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["passed"] = df["passed"].astype(bool)
    return df


def _percentile(series: pd.Series, q: float) -> float:
    cleaned = series.dropna()
    if cleaned.empty:
        return 0.0
    return float(cleaned.quantile(q))


def _format_payload(raw: Any) -> str:
    if not raw:
        return ""
    try:
        return json.dumps(json.loads(raw), indent=2, default=str)
    except (TypeError, ValueError, json.JSONDecodeError):
        return str(raw)


def render() -> None:
    st.set_page_config(
        page_title="ClinicOps Copilot",
        page_icon=":hospital:",
        layout="wide",
    )
    st.title("ClinicOps Copilot - Observability")
    st.caption(f"Events store: `{settings.events_db_path}`")

    # ---- Sidebar controls ---------------------------------------------------
    window_label = st.sidebar.selectbox(
        "Time window",
        ["last 1h", "last 24h", "last 7d", "all time"],
        index=1,
    )
    window_map = {
        "last 1h": timedelta(hours=1),
        "last 24h": timedelta(hours=24),
        "last 7d": timedelta(days=7),
        "all time": None,
    }
    window = window_map[window_label]

    df = _events_df(window)

    if df.empty:
        st.info(
            "No events recorded yet. Run `clinicops` (interactive session) or `clinicops eval` to populate the dashboard."
        )
        return

    # ---- Top-line metrics ---------------------------------------------------
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total events", len(df))
    col2.metric("Unique traces", df["trace_id"].nunique())
    col3.metric("Agents active", df["agent"].nunique())
    error_count = (df["status"] == "error").sum()
    col4.metric("Errors", int(error_count))

    st.divider()

    # ---- Per-agent call counts + latency ------------------------------------
    st.subheader("Per-agent activity")
    llm_calls = df[df["event_type"] == "llm_call"]
    if not llm_calls.empty:
        per_agent = (
            llm_calls.groupby("agent")
            .agg(
                calls=("id", "count"),
                p50_ms=("latency_ms", lambda s: _percentile(s, 0.5)),
                p95_ms=("latency_ms", lambda s: _percentile(s, 0.95)),
            )
            .reset_index()
        )
        per_agent["p50_ms"] = per_agent["p50_ms"].astype(int)
        per_agent["p95_ms"] = per_agent["p95_ms"].astype(int)
        st.dataframe(per_agent, hide_index=True, use_container_width=True)
    else:
        st.write("No LLM calls in this window yet.")

    # ---- Tool-call error rate -----------------------------------------------
    st.subheader("Tool-call success rate")
    tool_calls = df[df["event_type"] == "tool_call"]
    if not tool_calls.empty:
        tool_stats = (
            tool_calls.groupby("tool_name")
            .agg(
                calls=("id", "count"),
                errors=("status", lambda s: (s == "error").sum()),
                p50_ms=("latency_ms", lambda s: _percentile(s, 0.5)),
            )
            .reset_index()
        )
        tool_stats["error_rate"] = (tool_stats["errors"] / tool_stats["calls"]).round(3)
        tool_stats["p50_ms"] = tool_stats["p50_ms"].astype(int)
        st.dataframe(tool_stats, hide_index=True, use_container_width=True)
    else:
        st.write("No tool calls in this window yet.")

    st.divider()

    # ---- Recent traces ------------------------------------------------------
    st.subheader("Recent decisions")
    trace_ids = df.drop_duplicates("trace_id").head(15)["trace_id"].tolist()
    selected_trace = st.selectbox("Select trace_id", trace_ids)
    if selected_trace:
        trace_df = df[df["trace_id"] == selected_trace].sort_values("id")
        st.write(f"**{len(trace_df)} events** in trace `{selected_trace}`")
        for _, row in trace_df.iterrows():
            label = f"`{row['event_type']}`"
            if pd.notna(row["tool_name"]) and row["tool_name"]:
                label += f"  -  **{row['tool_name']}**"
            if pd.notna(row["latency_ms"]):
                label += f"  -  {int(row['latency_ms'])}ms"
            label += f"  -  _{row['status']}_"
            with st.expander(label):
                payload = _format_payload(row["payload"])
                if payload:
                    st.code(payload, language="json")
                else:
                    st.caption("(no payload)")

    st.divider()

    # ---- Eval harness pass/fail trend ---------------------------------------
    st.subheader("Eval harness")
    evals = _eval_df()
    if evals.empty:
        st.info("No eval runs yet. Run `clinicops eval` to populate this section.")
    else:
        latest_run_ts = evals["timestamp"].max()
        latest = evals[evals["timestamp"] == latest_run_ts]
        passed = int(latest["passed"].sum())
        total = len(latest)
        pct = round(100 * passed / total, 1) if total else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("Latest run", latest_run_ts.strftime("%Y-%m-%d %H:%M"))
        c2.metric("Pass rate", f"{pct}%")
        c3.metric("Cases", f"{passed}/{total}")

        trend = (
            evals.groupby([pd.Grouper(key="timestamp", freq="1h")])
            .agg(pass_rate=("passed", "mean"), n=("case_id", "count"))
            .reset_index()
        )
        trend = trend[trend["n"] > 0]
        if not trend.empty:
            st.line_chart(trend.set_index("timestamp")["pass_rate"])


if __name__ == "__main__":
    render()
