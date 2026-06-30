# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import geopandas as gpd
import streamlit as st
from pyproj import datadir

from core.config import GEO_PATH, SIMPLIFICATION_TOLERANCE


DISPLAY_REPLACEMENTS = {
    "Agua": "Água",
    "Sao": "São",
    "Sitio": "Sítio",
    "Corrego": "Córrego",
    "Varzea": "Várzea",
    "Capao": "Capão",
    "Joao": "João",
    "Jose": "José",
}


def presentation_label(value: object) -> str:
    text = str(value or "").strip()
    for source, target in DISPLAY_REPLACEMENTS.items():
        text = text.replace(source, target)
    return text


def configure_proj_data() -> None:
    proj_data = datadir.get_data_dir()
    if proj_data:
        os.environ.setdefault("PROJ_DATA", proj_data)
        os.environ.setdefault("PROJ_LIB", proj_data)


@st.cache_data(show_spinner="Carregando geofazendas...")
def load_farms() -> gpd.GeoDataFrame:
    if not GEO_PATH.exists():
        raise FileNotFoundError(f"Shapefile não encontrado: {GEO_PATH}")

    configure_proj_data()
    try:
        gdf = gpd.read_file(GEO_PATH, engine="fiona")
    except Exception:
        gdf = gpd.read_file(GEO_PATH)

    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:31982")
    gdf = gdf.to_crs("EPSG:4326")
    if "EMPRESA" in gdf.columns:
        gdf["__EMPRESA_LABEL__"] = gdf["EMPRESA"].map(presentation_label)
    if "FAZENDA" in gdf.columns:
        gdf["__FAZENDA_LABEL__"] = gdf["FAZENDA"].map(presentation_label)
    gdf["__geometry_original__"] = gdf.geometry.copy()
    try:
        gdf["geometry"] = gdf.geometry.simplify(
            SIMPLIFICATION_TOLERANCE,
            preserve_topology=True,
        )
    except Exception:
        pass
    return gdf
