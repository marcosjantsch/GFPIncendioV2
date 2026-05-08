# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import streamlit as st

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ).replace(second=0, microsecond=0)


def selected_datetime_local() -> datetime:
    if st.session_state.get("use_current_datetime", True):
        return now_local()
    value = st.session_state.get("analysis_datetime_iso")
    if value:
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=LOCAL_TZ)
            return parsed.astimezone(LOCAL_TZ).replace(second=0, microsecond=0)
        except Exception:
            pass
    return now_local()


def selected_datetime_utc() -> datetime:
    return selected_datetime_local().astimezone(timezone.utc)


def selected_date() -> date:
    return selected_datetime_local().date()


def selected_datetime_iso() -> str:
    return selected_datetime_utc().isoformat()


def set_manual_datetime(selected_day: date, selected_time: time) -> None:
    local_dt = datetime.combine(selected_day, selected_time).replace(tzinfo=LOCAL_TZ)
    st.session_state["analysis_datetime_iso"] = local_dt.replace(second=0, microsecond=0).isoformat()


def to_utc_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def to_local_datetime(value: str | datetime | None) -> datetime | None:
    utc_dt = to_utc_datetime(value)
    if utc_dt is None:
        return None
    try:
        return utc_dt.astimezone(LOCAL_TZ)
    except Exception:
        return None


def format_datetime_zulu(value: str | datetime | None, fallback: str = "") -> str:
    utc_dt = to_utc_datetime(value)
    if utc_dt is None:
        return fallback
    return utc_dt.strftime("%d/%m/%Y %H:%M") + " Z"


def format_period_zulu(start: str | datetime | None, end: str | datetime | None) -> str:
    start_label = format_datetime_zulu(start, fallback="-")
    end_label = format_datetime_zulu(end, fallback="-")
    return f"{start_label} a {end_label}"


def format_datetime_brasilia(value: str | datetime | None, fallback: str = "") -> str:
    local_dt = to_local_datetime(value)
    if local_dt is None:
        return fallback
    return local_dt.strftime("%d/%m/%Y %H:%M") + " (Brasilia)"


def format_period_brasilia(start: str | datetime | None, end: str | datetime | None) -> str:
    start_label = format_datetime_brasilia(start, fallback="-")
    end_label = format_datetime_brasilia(end, fallback="-")
    return f"{start_label} a {end_label}"
