# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Dict

import streamlit as st

from core.config import APP_TITLE


def render_top_header(user: Dict) -> None:
    st.markdown(
        f"""
        <div class="fire-header">
            <div>
                <div class="fire-title">{APP_TITLE}</div>
                <div class="fire-subtitle">Seleção de projeto, indicadores GE e triangulação em um único mapa operacional.</div>
            </div>
            <div class="fire-session">
                <strong>Sessão atual</strong><br>
                Usuário: {user["name"]} | Perfil: {user["role"]} | Login: {user["username"]}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
