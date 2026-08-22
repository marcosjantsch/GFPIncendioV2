from __future__ import annotations

import json
import os
import socket
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import streamlit as st


PROJECT_ID = os.getenv("USAGE_GCP_PROJECT", "streamelit")
DATASET_ID = os.getenv("USAGE_BIGQUERY_DATASET", "usage_analytics")
TABLE_ID = os.getenv("USAGE_BIGQUERY_TABLE", "usage_events")
ENVIRONMENT_ID = os.getenv("APP_ENVIRONMENT_ID", "streamelit-prod")


@st.cache_resource(show_spinner=False)
def _authorized_session():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return AuthorizedSession(credentials)


def _profile_value(profile: dict[str, Any], key: str, fallback: str = "") -> str:
    return str(profile.get(key) or st.session_state.get(key) or fallback)


def emit_usage_event(
    *,
    system_id: str,
    system_name: str,
    event_type: str,
    event_name: str,
    profile: dict[str, Any] | None = None,
    duration_seconds: float = 0,
    metadata: dict[str, Any] | None = None,
) -> bool:
    profile = profile or {}
    now = datetime.now(timezone.utc)
    session_id = st.session_state.setdefault("usage_session_id", str(uuid.uuid4()))
    tenant_id = _profile_value(profile, "tenant_id", "unmapped").lower()
    row = {
        "event_id": str(uuid.uuid4()),
        "event_ts": now.isoformat(),
        "event_date": now.date().isoformat(),
        "session_id": session_id,
        "system_id": system_id,
        "system_name": system_name,
        "system_version": os.getenv("APP_VERSION", ""),
        "environment": ENVIRONMENT_ID,
        "environment_id": ENVIRONMENT_ID,
        "tenant_id": tenant_id,
        "billing_account": _profile_value(profile, "billing_account", tenant_id.upper()),
        "operational_company": _profile_value(profile, "operational_company"),
        "geo_dataset": _profile_value(profile, "geo_dataset", tenant_id),
        "cost_center": _profile_value(profile, "cost_center", tenant_id.upper()),
        "gcp_project_id": PROJECT_ID,
        "username": _profile_value(profile, "username"),
        "user_name": _profile_value(profile, "name", st.session_state.get("nome", "")),
        "user_email": _profile_value(profile, "email"),
        "user_role": _profile_value(profile, "role", st.session_state.get("perfil", "")),
        "event_type": event_type,
        "event_name": event_name,
        "event_count": 1,
        "duration_seconds": float(duration_seconds or 0),
        "status": "success",
        "metadata": metadata or {},
        "app_instance_id": os.getenv("K_REVISION", os.getenv("HOSTNAME", "local")),
        "host_name": socket.gethostname(),
        "process_id": os.getpid(),
        "created_at": now.isoformat(),
    }
    payload = {"kind": "avant_usage_event", **row}
    print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)
    if os.getenv("USAGE_TRACKING_ENABLED", "true").lower() not in {"1", "true", "yes", "sim"}:
        return False
    try:
        url = (
            f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT_ID}/datasets/"
            f"{DATASET_ID}/tables/{TABLE_ID}/insertAll"
        )
        response = _authorized_session().post(url, json={"rows": [{"insertId": row["event_id"], "json": row}]}, timeout=10)
        response.raise_for_status()
        errors = (response.json() or {}).get("insertErrors") or []
        if errors:
            raise RuntimeError(str(errors))
        return True
    except Exception as exc:
        print(json.dumps({"kind": "avant_usage_error", "error": str(exc), "event_id": row["event_id"]}), flush=True)
        return False


def track_authenticated_session(system_id: str, system_name: str, profile: dict[str, Any] | None = None) -> None:
    start_key = f"usage_started_{system_id}"
    if not st.session_state.get(start_key):
        emit_usage_event(
            system_id=system_id,
            system_name=system_name,
            event_type="session",
            event_name="session_started",
            profile=profile,
        )
        st.session_state[start_key] = True
    now = time.monotonic()
    heartbeat_key = f"usage_heartbeat_{system_id}"
    last = float(st.session_state.get(heartbeat_key, 0) or 0)
    if now - last >= 60:
        emit_usage_event(
            system_id=system_id,
            system_name=system_name,
            event_type="heartbeat",
            event_name="authenticated_activity",
            profile=profile,
            duration_seconds=60,
        )
        st.session_state[heartbeat_key] = now
