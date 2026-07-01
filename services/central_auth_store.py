# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

import os
import yaml

from core.config import CENTRAL_AUTH_CONFIG_URI


ACCESS_ALIASES = {
    "combate_incendio": {"combate_incendio", "torres", "incendio", "fire"},
    "torres": {"combate_incendio", "torres", "incendio", "fire"},
}


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    value = str(uri or "").strip()
    if not value.startswith("gs://"):
        raise ValueError("URI GCS inválida.")
    bucket_blob = value[5:]
    bucket, _, blob = bucket_blob.partition("/")
    if not bucket or not blob:
        raise ValueError("URI GCS deve estar no formato gs://bucket/caminho.yaml.")
    return bucket, blob


def read_text(uri: str = CENTRAL_AUTH_CONFIG_URI) -> str:
    value = str(uri or "").strip()
    if value.startswith("gs://"):
        from google.cloud import storage  # type: ignore

        bucket_name, blob_name = _parse_gcs_uri(value)
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT") or "avantv3site"
        return storage.Client(project=project).bucket(bucket_name).blob(blob_name).download_as_text(encoding="utf-8")
    path = Path(value)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_auth_config(uri: str = CENTRAL_AUTH_CONFIG_URI) -> dict[str, Any]:
    raw = read_text(uri)
    if not raw.strip():
        return {"credentials": {"usernames": {}}}
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("credentials", {})
    data["credentials"].setdefault("usernames", {})
    return data


def user_has_access(profile: dict[str, Any], system_id: str) -> bool:
    if profile.get("disabled"):
        return False
    systems = profile.get("systems")
    if not isinstance(systems, dict):
        return True
    aliases = ACCESS_ALIASES.get(system_id, {system_id})
    return any(bool(systems.get(alias)) for alias in aliases)
