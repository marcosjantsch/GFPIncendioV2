# -*- coding: utf-8 -*-
from __future__ import annotations

from io import BytesIO

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from pyproj import Geod

from core.auth_service import require_authentication
from core.config import APP_TITLE
from core.data_service import load_farms
from ui.header import render_top_header
from ui.map_view import build_main_map
from ui.sidebar import (
    maybe_auto_refresh_analysis,
    render_sidebar,
)
from ui.styles import apply_styles
from ui.weather_tabs import render_climate_trend_tab, render_weather_forecast_tab
from services.gee_service import gee_diagnostics, load_gee_catalog


st.set_page_config(page_title=APP_TITLE, page_icon=":fire:", layout="wide")

GEOD = Geod(ellps="WGS84")


def render_technical_log(selected_companies) -> None:
    st.subheader("Log Técnico")
    cols = st.columns(2)
    with cols[0]:
        st.metric("Empresas", len(selected_companies))
    with cols[1]:
        st.metric("Camadas GE", len(st.session_state.get("gee_applied_indicators", [])))

    stage_cols = st.columns(2)
    with stage_cols[0]:
        st.markdown("#### 1. Configurar")
        st.caption("Selecione empresas e aplique camadas GE no menu lateral.")
        if selected_companies:
            st.success("Projeto com empresas selecionadas.")
        else:
            st.info("Nenhuma empresa selecionada.")
    with stage_cols[1]:
        st.markdown("#### 2. Monitorar")
        st.caption("Use o mapa operacional para visualizar perimetros, risco e hotspots.")
        if st.session_state.get("fire_detection_summary") or st.session_state.get("fire_risk_layers"):
            st.success("Dados de risco/GE aplicados.")
        else:
            st.info("Camadas GE ainda nao aplicadas.")

    if selected_companies:
        st.markdown("#### Empresas ativas")
        st.dataframe({"Empresa": selected_companies}, use_container_width=True, hide_index=True)
    if st.session_state.get("fire_risk_status"):
        st.info(st.session_state["fire_risk_status"])
    if st.session_state.get("last_goes_time"):
        st.caption(f"Ultima imagem GOES: {st.session_state['last_goes_time']}")
    if st.session_state.get("roi_limit_status"):
        st.caption(st.session_state["roi_limit_status"])

    st.markdown("#### Diagnóstico técnico")
    with st.expander("Diagnóstico de autenticação Earth Engine", expanded=False):
        st.json(gee_diagnostics())

    catalog = st.session_state.get("gee_catalog")
    if not catalog:
        catalog = load_gee_catalog()
        st.session_state["gee_catalog"] = catalog
    with st.expander("Catálogo GE carregado", expanded=False):
        st.json(catalog)

    operational_log = st.session_state.get("operational_log", [])
    if operational_log:
        with st.expander("Log operacional das fontes", expanded=False):
            st.dataframe(operational_log, use_container_width=True, hide_index=True)
    else:
        st.caption("Nenhum log operacional de fontes foi gerado nesta sessão.")

RISK_COLORS = {
    "Baixo": {"bg": "#14532d", "border": "#22c55e", "text": "#dcfce7"},
    "Moderado": {"bg": "#f59e0b", "border": "#fde68a", "text": "#111827"},
    "Alto": {"bg": "#c2410c", "border": "#fb923c", "text": "#fff7ed"},
    "Muito alto": {"bg": "#dc2626", "border": "#fecaca", "text": "#fef2f2"},
    "Sem dados": {"bg": "#1f2937", "border": "#64748b", "text": "#f8fafc"},
    "Nao calculado": {"bg": "#1f2937", "border": "#64748b", "text": "#f8fafc"},
}


def selected_farms_label(gdf, selected_companies) -> str:
    if not selected_companies:
        return "Nenhuma empresa selecionada"
    selected = set(selected_companies)
    farms = gdf[gdf["EMPRESA"].astype(str).str.strip().isin(selected)].copy()
    if farms.empty or "FAZENDA" not in farms.columns:
        return ", ".join(selected_companies)
    labels = [
        f"{row.get('EMPRESA', '')} / {row.get('FAZENDA', '')}"
        for _, row in farms[["EMPRESA", "FAZENDA"]].drop_duplicates().head(8).iterrows()
    ]
    suffix = "" if len(farms[["EMPRESA", "FAZENDA"]].drop_duplicates()) <= 8 else " ..."
    return "; ".join(labels) + suffix


def render_siren_alert(summary: dict) -> None:
    if not summary.get("fire_alert"):
        return
    distance = summary.get("fire_alert_min_distance_km")
    threshold = summary.get("fire_alert_threshold_km")
    row = summary.get("fire_alert_row") or {}
    st.warning(
        "Alerta sonoro: foco ou anomalia dentro do limite definido. "
        f"Fazenda: {row.get('fazenda', '-')}. UF: {row.get('uf', '-')}. "
        f"Distancia: {distance:.2f} km. Limite: {threshold:.1f} km."
    )
    components.html(
        """
        <script>
        (() => {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (!AudioContext) return;
            const context = new AudioContext();
            const oscillator = context.createOscillator();
            const gain = context.createGain();
            oscillator.type = "sawtooth";
            oscillator.connect(gain);
            gain.connect(context.destination);
            const start = context.currentTime;
            for (let i = 0; i < 10; i++) {
                oscillator.frequency.setValueAtTime(i % 2 === 0 ? 760 : 1180, start + i * 0.5);
                gain.gain.setValueAtTime(0.0001, start + i * 0.5);
                gain.gain.exponentialRampToValueAtTime(0.18, start + i * 0.5 + 0.05);
                gain.gain.exponentialRampToValueAtTime(0.0001, start + i * 0.5 + 0.42);
            }
            oscillator.start(start);
            oscillator.stop(start + 5);
        })();
        </script>
        """,
        height=0,
    )


def focus_bounds(lat: float, lon: float, buffer_km: float = 2.0) -> list[list[float]]:
    buffer_m = buffer_km * 1000
    west, _, _ = GEOD.fwd(lon, lat, 270, buffer_m)
    east, _, _ = GEOD.fwd(lon, lat, 90, buffer_m)
    _, south, _ = GEOD.fwd(lon, lat, 180, buffer_m)
    _, north, _ = GEOD.fwd(lon, lat, 0, buffer_m)
    return [[float(south), float(west)], [float(north), float(east)]]


def apply_hotspot_focus(row: dict) -> None:
    try:
        lat = float(row.get("latitude_foco"))
        lon = float(row.get("longitude_foco"))
    except Exception:
        return
    signature = f"{lat:.6f},{lon:.6f},{row.get('fazenda', '')},{row.get('tipo', '')}"
    if st.session_state.get("hotspot_focus_signature") == signature:
        return
    st.session_state["hotspot_focus_signature"] = signature
    st.session_state["hotspot_focus"] = {
        "lat": lat,
        "lon": lon,
        "empresa": row.get("empresa", ""),
        "fazenda": row.get("fazenda", ""),
        "municipio": row.get("municipio", ""),
        "uf": row.get("uf", ""),
        "satelite": row.get("satelite", ""),
        "tipo": row.get("tipo", ""),
        "distancia_km": row.get("distancia_km", ""),
    }
    st.session_state["viewport_fit_bounds"] = focus_bounds(lat, lon)
    st.session_state["fit_viewport_on_next_map"] = True


def distance_row_color(row) -> list[str]:
    try:
        distance = float(row.get("Distancia (km)", 999999))
    except Exception:
        distance = 999999
    if distance < 0:
        background = "#7f1d1d"
        color = "#ffffff"
    elif distance <= 5:
        background = "#fed7aa"
        color = "#7c2d12"
    elif distance <= 10:
        background = "#fef9c3"
        color = "#713f12"
    else:
        background = "#dcfce7"
        color = "#14532d"
    return [f"background-color: {background}; color: {color};" for _ in row]


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return output.getvalue()


def render_fire_detection_panel(gdf, selected_companies) -> None:
    summary = st.session_state.get("fire_detection_summary", {})
    if not summary:
        st.info("Aplique uma ROI para gerar o painel de risco e focos de calor.")
        return

    risk_value = summary.get("risk_value")
    risk_label = summary.get("risk_class", "Sem dados")
    risk_display = f"{risk_value:.1f}" if isinstance(risk_value, (int, float)) else "-"
    risk_style = RISK_COLORS.get(risk_label, RISK_COLORS["Sem dados"])

    st.markdown("### Risco de incêndios florestais para as fazendas selecionadas")
    st.caption(f"Fazendas selecionadas: {selected_farms_label(gdf, selected_companies)}")
    st.caption(f"Data e hora da análise: {st.session_state.get('analysis_reference_label', '-')}")
    image_rows = st.session_state.get("analysis_image_rows", [])
    if image_rows:
        with st.expander("Imagens e dados usados na análise", expanded=False):
            st.dataframe(image_rows, use_container_width=True, hide_index=True)
        image_rows = []
    if image_rows:
        st.markdown("#### Imagens e dados usados na análise")
        st.dataframe(image_rows, use_container_width=True, hide_index=True)

    render_siren_alert(summary)

    st.markdown(
        f"""
        <div style="
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:18px;
            width:100%;
            background:{risk_style['bg']};
            border:1px solid {risk_style['border']};
            color:{risk_style['text']};
            border-radius:10px;
            padding:10px 16px;
            margin:8px 0 12px 0;">
            <div style="font-size:13px; font-weight:700; opacity:.92;">Grau de risco</div>
            <div style="display:flex; align-items:baseline; gap:12px;">
                <span style="font-size:26px; font-weight:850; line-height:1;">{risk_display}</span>
                <span style="font-size:15px; font-weight:800;">{risk_label}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    nearest = sorted(
        summary.get("nearest_farms", []),
        key=lambda item: (float(item.get("distancia_km", 999999) or 999999), int(item.get("priority", 99) or 99)),
    )
    if nearest:
        st.markdown("#### Distancias ate focos, hotspots e anomalias")
        st.caption("Selecione ou dê dois cliques em uma linha para aproximar o mapa no foco correspondente.")
        expand_table = st.toggle(
            f"Expandir tabela completa ({len(nearest)} itens)",
            value=st.session_state.get("expand_fire_distance_table", False),
            key="expand_fire_distance_table",
        )
        visible_nearest = nearest if expand_table else nearest[:10]
        if not expand_table and len(nearest) > 10:
            st.caption(f"Exibindo os 10 focos mais proximos de {len(nearest)} registros calculados.")
        def distance_table_rows(items: list[dict]) -> list[dict]:
            return [
                {
                    "Empresa": item.get("empresa", ""),
                    "Fazenda": item.get("fazenda", ""),
                    "Municipio": item.get("municipio", ""),
                    "UF": item.get("uf", ""),
                    "Satelite": item.get("satelite", ""),
                    "Tipo": item.get("tipo", ""),
                    "Geometria": item.get("geometria_deteccao", ""),
                    "Distancia (km)": item.get("distancia_km", ""),
                    "Limite alerta (km)": item.get("distancia_alerta_km", ""),
                    "Alerta sonoro": "Sim" if item.get("alerta_sonoro") else "Nao",
                    "Latitude": item.get("latitude_foco", ""),
                    "Longitude": item.get("longitude_foco", ""),
                }
                for item in items
            ]

        table_rows = distance_table_rows(visible_nearest)
        export_df = pd.DataFrame(distance_table_rows(nearest))
        st.download_button(
            "Exportar distancias para Excel",
            data=dataframe_to_excel_bytes(export_df, "Distancias"),
            file_name="distancias_focos_hotspots.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=False,
        )
        table_df = pd.DataFrame(table_rows)
        selection = st.dataframe(
            table_df.style.apply(distance_row_color, axis=1),
            use_container_width=True,
            hide_index=True,
            key="fire_distance_table",
            on_select="rerun",
            selection_mode="single-row",
        )
        selected_rows = getattr(getattr(selection, "selection", None), "rows", [])
        if selected_rows:
            selected_index = int(selected_rows[0])
            if 0 <= selected_index < len(visible_nearest):
                apply_hotspot_focus(visible_nearest[selected_index])
    else:
        points_total = int(summary.get("points_total", 0) or 0)
        if points_total == 0:
            st.caption(
                "Nenhum foco, hotspot, anomalia ou poligono de deteccao foi amostrado nas camadas selecionadas; "
                "por isso nao ha distancia ate fazenda para calcular nesta consulta."
            )
        else:
            st.caption(
                f"{points_total} deteccao(oes) foram amostradas, mas nao foi possivel consolidar "
                "distancias para as fazendas selecionadas."
            )

    if summary.get("status"):
        st.caption(summary["status"])


def main() -> None:
    apply_styles()
    user = require_authentication()
    render_top_header(user)

    try:
        gdf = load_farms()
    except Exception as exc:
        st.error(exc)
        st.stop()

    selected_companies, range_km = render_sidebar(gdf)

    action_cols = st.columns([0.78, 0.12, 0.10])
    with action_cols[0]:
        st.caption(
            f"Empresas selecionadas: {len(selected_companies)} | "
            f"Camadas GE aplicadas: {len(st.session_state.get('gee_applied_indicators', []))}"
        )
    with action_cols[2]:
        if st.button("Sair", use_container_width=True):
            st.session_state.pop("auth_user", None)
            st.rerun()

    main_tabs = [
        "Mapa Operacional",
        "Previsao do Tempo",
        "Tendencia Climatica",
        "Log Técnico",
    ]
    if st.session_state.get("active_main_tab") not in main_tabs:
        st.session_state["active_main_tab"] = "Mapa Operacional"
    main_tab = st.radio(
        "Area principal",
        main_tabs,
        horizontal=True,
        key="active_main_tab",
    )
    maybe_auto_refresh_analysis(gdf)

    if main_tab == "Mapa Operacional":
        render_fire_detection_panel(gdf, selected_companies)
        map_output = build_main_map(
            gdf,
            selected_companies,
            range_km,
            capture_clicks=False,
        )
    elif main_tab == "Previsao do Tempo":
        render_weather_forecast_tab()
    elif main_tab == "Tendencia Climatica":
        render_climate_trend_tab()
    else:
        render_technical_log(selected_companies)


if __name__ == "__main__":
    main()
