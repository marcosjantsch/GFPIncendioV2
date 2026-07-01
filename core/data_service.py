# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

import geopandas as gpd
import streamlit as st
from pyproj import datadir

from core.config import APP_ENVIRONMENT, GEO_DATA_ROOT, GEO_DATASET_PATHS, GEO_PATH, SIMPLIFICATION_TOLERANCE


DATASET_LABELS = {
    "gfp": "GFP",
    "braspine": "Braspine",
    "avant": "Avant",
}

DATASET_ALIASES = {
    "gfp": "gfp",
    "gfpa": "gfp",
    "valor": "gfp",
    "valorflorestal": "gfp",
    "streamlit": "gfp",
    "streamelit": "gfp",
    "braspine": "braspine",
    "braspime": "braspine",
    "braspi": "braspine",
    "moraspire": "braspine",
    "avant": "avant",
    "avante": "avant",
    "avantv2": "avant",
    "avantev2": "avant",
    "avantv02": "avant",
    "avantev02": "avant",
    "avantv3": "avant",
    "avantv3site": "avant",
}

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


def _clean_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "").replace("_", "").replace(" ", "")


def normalize_geo_dataset(value: Any) -> str:
    return DATASET_ALIASES.get(_clean_key(value), "")


def _user_field(user: Mapping[str, Any] | None, *keys: str) -> str:
    user = user or {}
    for key in keys:
        value = str(user.get(key) or "").strip()
        if value:
            return value
    return ""


def default_geo_dataset() -> str:
    explicit = normalize_geo_dataset(os.getenv("APP_GEO_DATASET") or os.getenv("GEO_DATASET"))
    if explicit:
        return explicit
    environment = normalize_geo_dataset(APP_ENVIRONMENT)
    if environment:
        return environment
    return "gfp"


def resolve_geo_dataset(user: Mapping[str, Any] | None = None) -> str:
    user_dataset = normalize_geo_dataset(
        _user_field(
            user,
            "geo_dataset",
            "geo_base",
            "geo_environment",
            "operational_company",
            "company",
            "client",
            "billing_account",
        )
    )
    if user_dataset:
        return user_dataset
    return default_geo_dataset()


def _join_geo_uri(root: str, dataset: str) -> str:
    root = str(root or "").strip()
    if root.startswith("gs://"):
        return f"{root.rstrip('/')}/{dataset}/Geo.shp"
    return str(Path(root) / dataset / "Geo.shp")


def geo_path_for_dataset(dataset: str) -> str:
    dataset = normalize_geo_dataset(dataset) or default_geo_dataset()
    configured = str(GEO_DATASET_PATHS.get(dataset) or "").strip()
    if configured:
        return configured
    root = str(GEO_DATA_ROOT or "").strip()
    if root:
        return _join_geo_uri(root, dataset)
    return str(GEO_PATH)


def resolve_geo_context(user: Mapping[str, Any] | None = None) -> dict[str, str]:
    dataset = resolve_geo_dataset(user)
    return {
        "dataset": dataset,
        "label": DATASET_LABELS.get(dataset, dataset.upper()),
        "geo_path": geo_path_for_dataset(dataset),
    }


def _split_gcs_uri(uri: str) -> tuple[str, str]:
    bucket_blob = uri[5:]
    bucket_name, _, blob_name = bucket_blob.partition("/")
    if not bucket_name or not blob_name:
        raise ValueError("URI GCS inválida para Geo: use gs://bucket/pasta/Geo.shp")
    return bucket_name, blob_name


@st.cache_data(show_spinner=False)
def _materialize_gcs_shapefile(uri: str) -> str:
    from google.cloud import storage  # type: ignore

    bucket_name, blob_name = _split_gcs_uri(uri)
    prefix = blob_name.rsplit("/", 1)[0] if blob_name.lower().endswith(".shp") else blob_name.rstrip("/")
    shp_name = Path(blob_name).name if blob_name.lower().endswith(".shp") else "Geo.shp"
    cache_key = hashlib.sha1(uri.encode("utf-8")).hexdigest()
    target_dir = Path(tempfile.gettempdir()) / "avant_geo_cache" / cache_key
    target_dir.mkdir(parents=True, exist_ok=True)

    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT") or "avantv3site"
    bucket = storage.Client(project=project).bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=f"{prefix}/"))
    if not blobs:
        raise FileNotFoundError(f"Nenhum arquivo Geo encontrado em {uri}")

    for blob in blobs:
        if blob.name.endswith("/"):
            continue
        relative = blob.name[len(prefix) :].lstrip("/")
        if not relative:
            continue
        destination = target_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or destination.stat().st_size != int(blob.size or 0):
            blob.download_to_filename(str(destination))
    return str(target_dir / shp_name)


def materialize_geo_path(geo_uri: str) -> Path:
    value = str(geo_uri or GEO_PATH).strip()
    if value.startswith("gs://"):
        return Path(_materialize_gcs_shapefile(value))
    return Path(value)


@st.cache_data(show_spinner="Carregando geofazendas...")
def load_farms(geo_uri: str | None = None) -> gpd.GeoDataFrame:
    geo_path = materialize_geo_path(str(geo_uri or GEO_PATH))
    if not geo_path.exists():
        raise FileNotFoundError(f"Shapefile não encontrado: {geo_path}")

    configure_proj_data()
    try:
        gdf = gpd.read_file(geo_path, engine="fiona")
    except Exception:
        gdf = gpd.read_file(geo_path)

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
