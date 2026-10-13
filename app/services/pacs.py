"""
Cliente del PACS (Orthanc).

Regla de arquitectura (igual que en el notebook de la Semana 8): el navegador
NUNCA habla con Orthanc directamente. Solo esta API lo hace, después de haber
comprobado el token y el rol. Orthanc queda dentro de la red de Docker.

Diferencia deliberada frente al notebook: el paciente se identifica en DICOM
con `PatientID = documento_bidx` (el índice ciego), no con la cédula en texto
plano. Es el mismo principio de privacidad que ya rige el resto del proyecto
-- no sembrar el documento real como llave de búsqueda en un sistema más.
"""
from __future__ import annotations

import base64
import re

import httpx
from fastapi import HTTPException

from app.core.config import get_settings

settings = get_settings()

# Los IDs de instancia de Orthanc son 5 grupos de 8 caracteres hexadecimales
# separados por guiones. Este ID llega desde la URL y lo pegamos en otra URL
# hacia Orthanc -- hay que validarlo, igual que en el notebook, para que
# nadie intente colar una ruta como ../../algo.
INSTANCE_ID = re.compile(r"^[0-9a-f]{8}(-[0-9a-f]{8}){4}$")


def _auth() -> tuple[str, str]:
    return (settings.orthanc_user, settings.orthanc_password)


def orthanc(method: str, path: str, **kwargs) -> httpx.Response:
    """Petición a Orthanc, traduciendo sus fallos a errores HTTP claros."""
    try:
        r = httpx.request(method, settings.orthanc_url + path, auth=_auth(),
                          timeout=30, **kwargs)
    except httpx.HTTPError:
        raise HTTPException(status_code=503,
                            detail="El servidor de imágenes (PACS) no está disponible")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    if r.status_code >= 400:
        raise HTTPException(status_code=502,
                            detail=f"El PACS respondió con error {r.status_code}")
    return r


def is_alive() -> bool:
    try:
        return httpx.get(settings.orthanc_url + "/system", auth=_auth(),
                         timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


def check_instance_id(instance_id: str) -> None:
    if not INSTANCE_ID.match(instance_id):
        raise HTTPException(status_code=404, detail="Imagen no encontrada")


def list_images(paciente_documento_bidx: str) -> list[dict]:
    """Imágenes de un paciente, buscando por PatientID = documento_bidx."""
    ids = orthanc("POST", "/tools/find",
                  json={"Level": "Instance",
                        "Query": {"PatientID": paciente_documento_bidx}}).json()
    images = []
    for instance_id in ids:
        t = orthanc("GET", f"/instances/{instance_id}/simplified-tags").json()
        desc = t.get("SeriesDescription") or t.get("StudyDescription") or "Imagen"
        images.append({
            "id": instance_id,   # el contrato del tester pide `id` o `url`
            "instance_id": instance_id,
            "description": desc,
            # Procedencia honesta: las de la demo son reales pero de una cohorte
            # externa, vinculadas a un paciente sintético (no son sus exámenes).
            "origen": ("Imagen real de cohorte externa (NIH ChestX-ray14), vinculada a un caso sintético"
                       if "NIH" in desc else t.get("InstitutionName") or "Cargada en Pulso"),
            "ilustrativa": "NIH" in desc,
            "modality": t.get("Modality"),
            "date": t.get("StudyDate"),
            "time": t.get("StudyTime") or "",
            "rows": int(t.get("Rows") or 0),
            "columns": int(t.get("Columns") or 0),
        })
    images.sort(key=lambda i: (i["date"] or "", i["time"]), reverse=True)
    return images


def instance_paciente_bidx(instance_id: str) -> str:
    """¿De qué paciente es esta imagen? Para decidir si el usuario puede verla."""
    tags = orthanc("GET", f"/instances/{instance_id}/simplified-tags").json()
    return tags.get("PatientID", "")


def dicomize(png_bytes: bytes, paciente, descripcion: str, modalidad: str = "OT",
             extra: dict | None = None) -> str:
    """
    Convierte un PNG en una instancia DICOM dentro de Orthanc y devuelve su ID.

    `paciente` es un objeto Paciente ya con sus campos descifrados a mano por
    quien llama (ver imaging.py) -- este módulo no descifra nada, solo arma
    las etiquetas DICOM con lo que le pasan.
    """
    descripcion = "".join(ch for ch in descripcion if ch.isprintable())[:64] or "Imagen clínica"
    body = {
        "Content": "data:image/png;base64," + base64.b64encode(png_bytes).decode(),
        "Tags": {
            "PatientID": paciente["documento_bidx"],
            "PatientName": f"{paciente['apellido']}^{paciente['nombre']}"[:64],
            "PatientBirthDate": paciente["fecha_nacimiento"].strftime("%Y%m%d"),
            "PatientSex": paciente["sexo"],
            "StudyDescription": descripcion,
            "SeriesDescription": descripcion,
            # OT = "Other" para lo que sube un usuario; DX para las radiografías
            # del dataset NIH ChestX-ray14 (scripts/cargar_radiografias.py).
            "Modality": modalidad,
            **(extra or {}),
        },
    }
    return orthanc("POST", "/tools/create-dicom", json=body).json()["ID"]


_CACHE_CON_IMAGENES: dict = {"t": 0.0, "ids": set()}


def pacientes_con_imagenes() -> set[str]:
    """documento_bidx de los pacientes con algún estudio en el PACS.

    Una sola consulta a Orthanc (no una por paciente), guardada 60 s. Si el
    PACS no responde devuelve un conjunto vacío: la lista de pacientes no
    debe caerse por eso.
    """
    import time
    if time.monotonic() - _CACHE_CON_IMAGENES["t"] < 60:
        return _CACHE_CON_IMAGENES["ids"]
    try:
        r = httpx.post(settings.orthanc_url + "/tools/find", auth=_auth(), timeout=4,
                       json={"Level": "Patient", "Query": {}, "Expand": True})
        ids = {p.get("MainDicomTags", {}).get("PatientID") for p in r.json()} if r.status_code == 200 else set()
    except (httpx.HTTPError, ValueError):
        ids = set()
    _CACHE_CON_IMAGENES.update(t=time.monotonic(), ids={i for i in ids if i})
    return _CACHE_CON_IMAGENES["ids"]
