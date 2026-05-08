# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Dict, List

DEFAULT_ALERT_DISTANCE_KM = 1.5

ALERT_DISTANCE_RULES: List[Dict[str, object]] = [
    {
        "uf": "MS",
        "estado": "Mato Grosso do Sul",
        "alert_distance_km": 5.0,
    },
    {
        "uf": "*",
        "estado": "Demais unidades federativas",
        "alert_distance_km": DEFAULT_ALERT_DISTANCE_KM,
    },
]


def alert_distance_for_uf(uf: object) -> float:
    normalized_uf = str(uf or "").strip().upper()
    for rule in ALERT_DISTANCE_RULES:
        if rule["uf"] == normalized_uf:
            return float(rule["alert_distance_km"])
    return DEFAULT_ALERT_DISTANCE_KM
