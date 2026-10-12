"""
Servicio de IA del Hospital San Rafael.

ESQUELETO. Esteban es el dueño: aquí se carga el modelo entrenado
(modelo.joblib) y /predict devuelve la predicción real. El contrato con la
API (ver el PDF de reparto) es:

    POST /predict   {"pseudo_id": "...", "variables": {...}}
                 -> {"clase": ..., "probabilidad": 0.0-1.0, "critico": bool}

Este servicio nunca recibe nombre, documento, correo, teléfono ni dirección
(R12): la API le manda solo variables clínicas y un identificador seudónimo.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Servicio de IA - Hospital San Rafael", version="0.0.1")

MODELO = None   # se cargará con joblib.load("modelo.joblib") al arrancar


class Solicitud(BaseModel):
    pseudo_id: str
    variables: dict[str, float | int | str | None]


@app.get("/salud")
def salud():
    return {"ml": "ok", "modelo_cargado": MODELO is not None}


@app.post("/predict")
def predict(sol: Solicitud):
    if MODELO is None:
        raise HTTPException(503, "El modelo todavía no está entrenado")
    raise HTTPException(501, "Pendiente de implementar")
