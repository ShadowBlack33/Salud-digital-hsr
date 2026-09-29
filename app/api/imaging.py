"""
Imágenes médicas (PACS / DICOM vía Orthanc): listar, subir y ver.

Mismo patrón de autorización que el resto del proyecto:
  · NIVEL 1 -> RequierePermiso("imagen", accion)
  · NIVEL 2 -> ctx.verificar_registro(paciente) -- si no puede ver al
    paciente, tampoco puede ver ni subirle imágenes.

La API es el ÚNICO cliente de Orthanc (ver app/services/pacs.py). El
navegador nunca le habla directo.
"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from PIL import Image
from sqlalchemy.orm import Session

from app.core.crypto import descifrar
from app.core.deps import ContextoAcceso, RequierePermiso, get_db
from app.models import Paciente
from app.services import pacs
from app.services.auditoria import registrar

router = APIRouter(tags=["Imágenes (PACS)"])

MAX_UPLOAD = 15 * 1024 * 1024   # 15 MB, igual que en el notebook


def _buscar_paciente_activo(db: Session, paciente_id: str) -> Paciente:
    p = db.query(Paciente).filter(Paciente.documento_bidx == paciente_id,
                                  Paciente.activo.is_(True)).first()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    return p


def _paciente_para_dicom(p: Paciente) -> dict:
    """Descifra solo lo que hace falta para armar las etiquetas DICOM."""
    return {
        "documento_bidx": p.documento_bidx,
        "nombre": descifrar(p.nombre_cifrado, "pacientes.nombre"),
        "apellido": descifrar(p.apellido_cifrado, "pacientes.apellido"),
        "fecha_nacimiento": p.fecha_nacimiento,
        "sexo": p.sexo,
    }


@router.get("/pacientes/{paciente_id}/imagenes", summary="Listar imágenes de un paciente")
def listar_imagenes(paciente_id: str,
                    ctx: ContextoAcceso = Depends(RequierePermiso("imagen", "read")),
                    db: Session = Depends(get_db)):
    p = _buscar_paciente_activo(db, paciente_id)
    ctx.verificar_registro(p)   # NIVEL 2: mismo chequeo que para ver al paciente
    return {"imagenes": pacs.list_images(p.documento_bidx)}


@router.post("/pacientes/{paciente_id}/imagenes", status_code=status.HTTP_201_CREATED,
            summary="Subir una imagen al PACS")
def subir_imagen(paciente_id: str, request: Request,
                 archivo: UploadFile = File(...),
                 descripcion: str = Form("Imagen clínica"),
                 ctx: ContextoAcceso = Depends(RequierePermiso("imagen", "create")),
                 db: Session = Depends(get_db)):
    p = _buscar_paciente_activo(db, paciente_id)
    ctx.verificar_registro(p)

    datos = archivo.file.read(MAX_UPLOAD + 1)
    if len(datos) > MAX_UPLOAD:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "La imagen supera los 15 MB")

    # No confiamos en el nombre ni en el tipo que declara el archivo:
    # lo abrimos de verdad, igual que en el notebook.
    try:
        img = Image.open(io.BytesIO(datos))
        formato = img.format
        img.load()
    except Exception:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "El archivo no es una imagen válida")
    if formato not in ("PNG", "JPEG"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Solo se aceptan imágenes PNG o JPEG")

    if max(img.size) > 4096:
        img.thumbnail((4096, 4096))
    if img.mode.startswith("I"):
        img = img.point(lambda v: v / 256).convert("L")
    elif img.mode not in ("L", "RGB"):
        img = img.convert("RGB")

    # Volver a codificar la imagen elimina metadatos ocultos (EXIF, GPS, etc.)
    limpio = io.BytesIO()
    img.save(limpio, format="PNG")

    instance_id = pacs.dicomize(limpio.getvalue(), _paciente_para_dicom(p), descripcion)
    registrar(db, ctx.usuario, "imagen", instance_id, "create", request=request)
    db.commit()
    return {"instance_id": instance_id}


@router.get("/imagenes/{instance_id}/preview", summary="Ver una imagen (PNG)")
def ver_imagen(instance_id: str, request: Request,
               ctx: ContextoAcceso = Depends(RequierePermiso("imagen", "read")),
               db: Session = Depends(get_db)):
    pacs.check_instance_id(instance_id)
    bidx = pacs.instance_paciente_bidx(instance_id)
    p = _buscar_paciente_activo(db, bidx)
    ctx.verificar_registro(p)   # 404/403 si esta imagen no le corresponde

    png = pacs.orthanc("GET", f"/instances/{instance_id}/preview").content
    registrar(db, ctx.usuario, "imagen", instance_id, "read", request=request)
    db.commit()
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=300"})


@router.delete("/imagenes/{instance_id}", summary="Eliminar una imagen (solo admin)")
def eliminar_imagen(instance_id: str, request: Request,
                    ctx: ContextoAcceso = Depends(RequierePermiso("imagen", "delete")),
                    db: Session = Depends(get_db)):
    pacs.check_instance_id(instance_id)
    pacs.orthanc("DELETE", f"/instances/{instance_id}")
    registrar(db, ctx.usuario, "imagen", instance_id, "soft_delete", request=request)
    db.commit()
    return {"detail": "Imagen eliminada"}
