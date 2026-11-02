"""
Servicio de IA del Hospital San Rafael (R10, R12, R20).

    POST /predict   {"pseudo_id": "...", "variables": {...}}
                 -> {"clase", "probabilidad", "critico", "umbral", "modelo_version"}
    GET  /salud     estado y versión del modelo

Este servicio nunca recibe nombre, documento, correo, teléfono ni dirección:
la API le manda solo variables clínicas y un identificador seudónimo. Además,
aquí se rechaza (422) cualquier llave que no sea una variable del modelo, como
segunda barrera por si la capa de seudonimización de la API fallara.
"""
import json
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import caracteristicas  # noqa: F401 -- joblib lo necesita para cargar el pipeline

RUTA = Path(__file__).parent / "modelo" / "modelo.joblib"
ART: dict = {}   # se llena una sola vez al arrancar

# Sin al menos un laboratorio, el modelo solo vería medianas imputadas y su
# probabilidad no significaría nada: no se predice (y no se dispara una alerta).
LABORATORIOS = {"glucosa", "potasio", "hemoglobina"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if RUTA.exists():
        ART.update(joblib.load(RUTA))
    yield
    ART.clear()


app = FastAPI(title="Servicio de IA - Hospital San Rafael", version="1.0.0", lifespan=lifespan)


class Solicitud(BaseModel):
    pseudo_id: str
    # Sin tipo en los valores a propósito: primero se revisan los NOMBRES (R12) y
    # luego los valores, para no devolver en el error el dato que no debía llegar.
    variables: dict[str, object]


@app.get("/salud")
def salud():
    return {"ml": "ok", "modelo_cargado": bool(ART), "version": ART.get("version"),
            "variables": ART.get("variables"), "umbral": ART.get("umbral")}


@app.get("/metricas")
def metricas():
    """Desempeño en prueba (solo cifras agregadas, sin pacientes) para el tablero del admin."""
    ruta = Path(__file__).parent / "modelo" / "metricas.json"
    if not ruta.exists():
        raise HTTPException(404, "Aún no hay métricas: falta modelo/metricas.json")
    m = json.loads(ruta.read_text(encoding="utf-8"))
    g = m.get("global", {})
    return {"modelo": m.get("version"), "umbral": m.get("umbral"), "auc": g.get("auc"),
            "sensibilidad": g.get("sensibilidad"), "especificidad": g.get("especificidad"),
            "vpp": g.get("vpp"), "casos_de_prueba": g.get("n"),
            "criterio_umbral": m.get("criterio_umbral")}


@app.post("/predict")
def predict(sol: Solicitud):
    if not ART:
        raise HTTPException(503, "El modelo no está cargado: falta modelo/modelo.joblib")

    sobrantes = set(sol.variables) - set(ART["variables"])
    if sobrantes:
        raise HTTPException(422, f"Variables no permitidas: {sorted(sobrantes)}")

    no_numericas = sorted(k for k, v in sol.variables.items()
                          if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))))
    if no_numericas:
        raise HTTPException(422, f"Estas variables deben ser numéricas: {no_numericas}")

    presentes = {k for k, v in sol.variables.items() if v is not None}
    if not presentes & LABORATORIOS:
        raise HTTPException(422, f"Datos insuficientes: se necesita al menos uno de {sorted(LABORATORIOS)}")

    # El orden de las columnas lo fija el artefacto, no el diccionario recibido
    fila = {v: (np.nan if sol.variables.get(v) is None else sol.variables[v]) for v in ART["variables"]}
    df = pd.DataFrame([fila], columns=ART["variables"], dtype=float)
    prob = float(ART["pipeline"].predict_proba(df)[0, 1])
    critico = bool(prob >= ART["umbral"])

    return {
        "pseudo_id": sol.pseudo_id,
        "clase": "riesgo_uci" if critico else "bajo_riesgo",
        "probabilidad": round(prob, 4),
        "critico": critico,
        "umbral": ART["umbral"],
        "modelo_version": ART["version"],
        "variables_imputadas": sorted(set(ART["variables"]) - presentes),
    }


# ============================================================================
# Embeddings del RAG (Semana 12, docs/RAG.md).
#
# Mismo principio que /predict: este servicio no tiene acceso a la base de
# datos y solo recibe texto ya seudonimizado por la API. Devuelve el nombre
# del modelo para que la API rechace vectores de un modelo distinto al que
# usó para indexar.
# ============================================================================
import os as _os
from importlib.metadata import version as _version

MODELO_EMBEDDING = _os.getenv("RAG_MODELO_EMBEDDING",
                              "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
# Firma = modelo + versión de fastembed. La API solo compara vectores con la misma firma:
# entre versiones de fastembed el mismo modelo puede dar vectores distintos.
FIRMA = f"{MODELO_EMBEDDING}|fastembed=={_version('fastembed')}"
# Reranker opcional (vacío = no instalado): BAAI/bge-reranker-v2-m3-int8, Apache 2.0.
MODELO_RERANKER = _os.getenv("RAG_MODELO_RERANKER", "")
_EMBEDDER: dict = {}


class Textos(BaseModel):
    textos: list[str]


@app.post("/embed")
def embed(datos: Textos):
    if not datos.textos or len(datos.textos) > 256:
        raise HTTPException(422, "Enviar entre 1 y 256 textos")
    if "modelo" not in _EMBEDDER:
        from fastembed import TextEmbedding  # noqa: PLC0415
        _EMBEDDER["modelo"] = TextEmbedding(MODELO_EMBEDDING,
                                            cache_dir=_os.getenv("FASTEMBED_CACHE", "/home/ml/fastembed"))
    vectores = [[float(x) for x in v] for v in _EMBEDDER["modelo"].embed(datos.textos)]
    return {"modelo": MODELO_EMBEDDING, "firma": FIRMA, "dimension": len(vectores[0]), "vectores": vectores}


class Rerank(BaseModel):
    consulta: str
    textos: list[str]


@app.post("/rerank")
def rerank(datos: Rerank):
    """
    Puntaje de cada texto frente a la consulta con un cross-encoder (lee los dos
    juntos, a diferencia de los embeddings). Solo si la imagen se construyó con
    RAG_RERANKER_MODELO; si no, 503 y la API conserva el orden de la fusión.
    """
    if not MODELO_RERANKER:
        raise HTTPException(503, "Reranker no instalado: construir con --build-arg RAG_RERANKER_MODELO=...")
    if not datos.textos or len(datos.textos) > 64:
        raise HTTPException(422, "Enviar entre 1 y 64 textos")
    if "reranker" not in _EMBEDDER:
        from fastembed.rerank.cross_encoder import TextCrossEncoder  # noqa: PLC0415
        _EMBEDDER["reranker"] = TextCrossEncoder(MODELO_RERANKER,
                                                 cache_dir=_os.getenv("FASTEMBED_CACHE", "/home/ml/fastembed"))
    puntajes = [float(x) for x in _EMBEDDER["reranker"].rerank(datos.consulta, datos.textos)]
    return {"modelo": MODELO_RERANKER, "puntajes": puntajes}
