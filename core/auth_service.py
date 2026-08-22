# -*- coding: utf-8 -*-
from __future__ import annotations

from html import escape
import os
from typing import Dict, Optional

import bcrypt
import streamlit as st

from core.config import APP_TITLE, CENTRAL_AUTH_CONFIG_URI
from core.time_context import now_local
from services.central_auth_store import load_auth_config, user_has_access


def normalize_bcrypt_hash(hash_value: str) -> bytes:
    return str(hash_value).strip().replace("$2y$", "$2b$", 1).encode("utf-8")


def verify_credentials(username: str, password: str) -> Optional[Dict]:
    config = load_auth_config()
    users = config.get("credentials", {}).get("usernames", {})
    if not users:
        raise FileNotFoundError(
            "Lista central de usuários vazia ou indisponível. Configure CENTRAL_AUTH_CONFIG_URI "
            f"para a base criada pelo Avant Métricas. Valor atual: {CENTRAL_AUTH_CONFIG_URI}"
        )
    normalized_username = str(username or "").strip().lower()
    normalized_password = str(password or "").strip()
    matched_key = next((key for key in users if key.lower() == normalized_username), None)
    if not matched_key:
        return None

    profile = users[matched_key]
    allowed_tenants = {
        value.strip().lower()
        for value in os.getenv("APP_ALLOWED_TENANTS", "gfp,avant").split(",")
        if value.strip()
    }
    tenant_id = str(profile.get("tenant_id") or "gfp").strip().lower()
    if tenant_id not in allowed_tenants:
        return None
    password_hash = profile.get("password")
    if not password_hash:
        return None

    if bcrypt.checkpw(normalized_password.encode("utf-8"), normalize_bcrypt_hash(password_hash)):
        systems = profile.get("systems") if isinstance(profile.get("systems"), dict) else {}
        if not user_has_access(profile, "defcon"):
            return None
        return {
            "username": matched_key,
            "name": profile.get("name") or matched_key,
            "role": profile.get("role") or "standard",
            "email": profile.get("email") or "",
            "billing_account": profile.get("billing_account") or "",
            "operational_company": profile.get("operational_company") or profile.get("company") or "",
            "geo_dataset": profile.get("geo_dataset") or "",
            "tenant_id": tenant_id,
            "environment_id": profile.get("environment_id") or "streamelit-prod",
            "cost_center": profile.get("cost_center") or "",
            "systems": systems,
        }
    return None


def render_login_styles() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            display: none !important;
        }
        [data-testid="stHeader"] {
            background: transparent;
        }
        .block-container {
            max-width: 1180px !important;
            padding-top: 4.5rem !important;
            padding-bottom: 2.5rem !important;
        }
        .fire-login-copy,
        [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid rgba(52, 211, 153, 0.20);
            border-radius: 16px;
            box-shadow: 0 28px 70px rgba(0, 0, 0, 0.34);
        }
        .fire-login-copy {
            min-height: 540px;
            padding: 42px;
            background:
                linear-gradient(135deg, rgba(2, 6, 23, 0.94), rgba(6, 78, 59, 0.60)),
                repeating-linear-gradient(90deg, rgba(255,255,255,0.03) 0 1px, transparent 1px 44px),
                repeating-linear-gradient(0deg, rgba(255,255,255,0.025) 0 1px, transparent 1px 44px);
        }
        .fire-login-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 7px 11px;
            border-radius: 999px;
            color: #bbf7d0;
            background: rgba(5, 150, 105, 0.14);
            border: 1px solid rgba(52, 211, 153, 0.22);
            font-size: 12px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }
        .fire-login-copy h1 {
            margin: 24px 0 16px 0;
            color: #f8fafc;
            font-size: 42px;
            line-height: 1.05;
            letter-spacing: 0;
        }
        .fire-login-copy p {
            max-width: 720px;
            margin: 0 0 22px 0;
            color: #cbd5e1;
            font-size: 16px;
            line-height: 1.65;
        }
        .fire-login-points {
            display: grid;
            gap: 12px;
            margin-top: 28px;
        }
        .fire-login-point {
            padding: 14px 16px;
            border-radius: 12px;
            background: rgba(2, 6, 23, 0.62);
            border: 1px solid rgba(148, 163, 184, 0.16);
        }
        .fire-login-point strong {
            display: block;
            margin-bottom: 4px;
            color: #d1fae5;
            font-size: 14px;
        }
        .fire-login-point span {
            color: #94a3b8;
            font-size: 13px;
            line-height: 1.45;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 540px;
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(2, 6, 23, 0.98));
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] {
            gap: 1rem;
        }
        .fire-login-heading h2 {
            margin: 0 0 8px 0;
            color: #f8fafc;
            font-size: 24px;
            letter-spacing: 0;
        }
        .fire-login-heading p {
            margin: 0 0 20px 0;
            color: #94a3b8;
            font-size: 13px;
            line-height: 1.5;
        }
        .fire-login-runtime {
            margin-top: 18px;
            padding: 12px 14px;
            border-radius: 12px;
            background: rgba(16, 185, 129, 0.09);
            border: 1px solid rgba(52, 211, 153, 0.18);
            color: #a7f3d0;
            font-size: 12px;
            line-height: 1.45;
        }
        @media (max-width: 900px) {
            .block-container {
                padding-top: 2rem !important;
            }
            .fire-login-copy,
            [data-testid="stVerticalBlockBorderWrapper"] {
                min-height: auto;
            }
            .fire-login-copy {
                padding: 28px;
            }
            .fire-login-copy h1 {
                font-size: 32px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_platform_intro() -> None:
    title = escape(APP_TITLE)
    st.markdown(
        f"""
        <div class="fire-login-copy">
            <div class="fire-login-badge">Monitoramento florestal</div>
            <h1>{title}</h1>
            <p>
                Ambiente operacional para acompanhar áreas rurais e florestais,
                combinando perímetros de empresas, camadas orbitais, dados
                climáticos e indicadores de focos de calor em uma leitura única
                para apoio ao combate a incêndios.
            </p>
            <div class="fire-login-points">
                <div class="fire-login-point">
                    <strong>Mapa operacional</strong>
                    <span>Visualização das empresas selecionadas, ROI de análise,
                    camadas de satélite e dados ambientais disponíveis.</span>
                </div>
                <div class="fire-login-point">
                    <strong>Risco e detecções</strong>
                    <span>Painel com grau de risco, focos de calor, hotspots,
                    anomalias térmicas e distâncias até as fazendas monitoradas.</span>
                </div>
                <div class="fire-login-point">
                    <strong>Execução local, Codebook e container</strong>
                    <span>Configurações sensíveis são carregadas pelo ambiente,
                    mantendo o mesmo código pronto para operação local e publicação.</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_login() -> None:
    render_login_styles()
    left_col, right_col = st.columns([1.25, 0.85], gap="large")
    with left_col:
        render_platform_intro()
    with right_col:
        with st.container(border=True):
            st.markdown(
                """
                <div class="fire-login-heading">
                    <h2>Acesso seguro</h2>
                    <p>Entre com o usuário e a senha cadastrados para este ambiente.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            notice = st.session_state.pop("auth_notice", None)
            if notice:
                st.warning(str(notice))
            with st.form("login_form"):
                username = st.text_input("Usuário")
                password = st.text_input("Senha", type="password")
                submitted = st.form_submit_button("Entrar", width="stretch")
            if submitted:
                try:
                    profile = verify_credentials(username, password)
                except Exception as exc:
                    st.error(f"Falha ao carregar autenticação: {exc}")
                    st.stop()
                if not profile:
                    st.error("Usuário ou senha inválidos.")
                    st.stop()
                st.session_state["auth_user"] = profile
                st.session_state["session_local_date"] = now_local().date().isoformat()
                st.session_state.pop("session_started_at", None)
                st.session_state.pop("auth_notice", None)
                st.rerun()
            st.markdown(
                """
                <div class="fire-login-runtime">
                    Preparado para execução local, Codebook e container, usando as
                    credenciais configuradas no ambiente da aplicação.
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.stop()


def require_authentication() -> Dict:
    profile = st.session_state.get("auth_user")
    if not profile:
        render_login()
    return profile
