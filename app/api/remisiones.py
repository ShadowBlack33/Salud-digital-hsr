"""
Remisiones entre médicos (R08).

  POST /remisiones                 el médico remite a un especialista (devuelve id)
  GET  /remisiones                 las que envié o recibí (admin: todas)
  POST /remisiones/{id}/aceptar    el especialista destinatario la acepta
  POST /remisiones/{id}/rechazar   ... o la rechaza con un motivo (pierde el acceso)
  POST /remisiones/{id}/atender    la cierra como atendida (acceso por unos días más)
  GET  /especialistas              a quién se puede remitir

Al remitir, el paciente pasa a contar como paciente del especialista (puede
abrir su ficha e imágenes para revisarlo). El acceso se acaba si la rechaza, o
REMISION_ACCESO_DIAS después de cerrarla como atendida (app/core/deps.py).
Cada transición es atómica: el UPDATE exige el estado de origen, así dos
clics simultáneos no la cambian dos veces. Paciente y contable no tienen
ningún permiso sobre remisiones: reciben 403.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.crypto import descifrar
from app.core.deps import ContextoAcceso, RequierePermiso, get_db
from app.models import Paciente, Personal
from app.services import reactores
from app.services.auditoria import registrar

router = APIRouter(tags=["Remisiones"])


class RemisionCrear(BaseModel):
    paciente_id: str
    especialista_id: int = Field(..., description="Registro de personal del especialista")
    motivo: str = Field(..., min_length=5, max_length=1000)
    prioridad: str = Field("prioritaria", pattern="^(rutinaria|prioritaria|urgente)$")


class _Fila:
    """Objeto simple para pasarle a los reactores (tienen .id y los campos)."""
    def __init__(self, d: dict):
        self.__dict__.update(d)


def _nombre_personal(db: Session, pid: int | None) -> str | None:
    m = db.get(Personal, pid) if pid else None
    if m is None:
        return None
    return f"{descifrar(m.nombre_cifrado, 'personal.nombre')} {descifrar(m.apellido_cifrado, 'personal.apellido')}"


def _vista(db: Session, r: dict, yo: int | None) -> dict:
    p = db.get(Paciente, r["paciente_id"])
    esp = db.get(Personal, r["especialista_id"])
    return {
        "id": r["id"], "paciente_id": r["paciente_id"],
        "paciente_nombre": p and f"{descifrar(p.nombre_cifrado, 'pacientes.nombre')} {descifrar(p.apellido_cifrado, 'pacientes.apellido')}",
        "medico_id": r["medico_id"], "medico": "Usted" if yo and r["medico_id"] == yo else _nombre_personal(db, r["medico_id"]),
        "especialista_id": r["especialista_id"],
        "especialista": "Usted" if yo and r["especialista_id"] == yo else _nombre_personal(db, r["especialista_id"]),
        "especialidad": esp.especialidad.nombre if esp and esp.especialidad else None,
        "motivo": r["motivo"], "prioridad": r["prioridad"], "estado": r["estado"],
        "created_at": r["created_at"], "aceptada_at": r["aceptada_at"],
        "respuesta": r.get("respuesta"), "cerrada_at": r.get("cerrada_at"),
    }


@router.get("/especialistas", summary="Especialistas a los que se puede remitir")
def especialistas(ctx: ContextoAcceso = Depends(RequierePermiso("remision", "create")),
                  db: Session = Depends(get_db)):
    filas = db.execute(text("""
        SELECT p.id, COUNT(u.id) > 0 AS con_cuenta, MAX(u.ultimo_acceso) AS ultimo_acceso,
               MIN(u.username) AS usuario
        FROM personal p
        LEFT JOIN usuarios u ON u.personal_id = p.id AND u.activo
             AND u.rol_id = (SELECT id FROM roles WHERE codigo = 'especialista')
        WHERE p.activo AND p.tipo_personal = 'medico_especialista'
        GROUP BY p.id
    """)).mappings().all()
    salida = []
    for f in filas:
        m = db.get(Personal, f["id"])
        salida.append({"id": m.id, "nombre": _nombre_personal(db, m.id),
                       "especialidad": m.especialidad.nombre if m.especialidad else None,
                       "en_linea": bool(f["con_cuenta"]), "_ultimo": f["ultimo_acceso"],
                       # Cuenta con la que ese especialista entra (para saber a quién remitir en la demo).
                       "usuario": f["usuario"]})
    # Primero los que entraron al sistema hace poco (pueden aceptarla ya).
    salida.sort(key=lambda e: (e["_ultimo"] is None, -(e["_ultimo"].timestamp() if e["_ultimo"] else 0),
                               e["especialidad"] or "", e["nombre"]))
    hace_un_rato = datetime.now(timezone.utc) - timedelta(minutes=30)
    for e in salida:
        ultimo = e.pop("_ultimo")
        e["activo_reciente"] = ultimo is not None
        e["conectado"] = bool(ultimo and ultimo > hace_un_rato)   # entró en los últimos 30 min
    return salida


@router.post("/remisiones", status_code=status.HTTP_201_CREATED, summary="Remitir un paciente")
def remitir(datos: RemisionCrear, request: Request,
            ctx: ContextoAcceso = Depends(RequierePermiso("remision", "create")),
            db: Session = Depends(get_db)):
    p = db.get(Paciente, datos.paciente_id)
    if p is None or not p.activo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    ctx.verificar_registro(p)   # solo se remite a un paciente propio
    esp = db.get(Personal, datos.especialista_id)
    if esp is None or not esp.activo or esp.tipo_personal != "medico_especialista":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ese especialista no existe")
    yo = ctx.payload.get("personal_id")
    if yo == esp.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puede remitirse un paciente a sí mismo")
    fila = db.execute(text("""
        INSERT INTO remisiones (paciente_id, medico_id, remitido_por, especialista_id, motivo, prioridad)
        VALUES (:p, :m, :u, :e, :mo, :pr) RETURNING *
    """), {"p": p.documento_bidx, "m": yo, "u": ctx.usuario.id, "e": esp.id,
           "mo": datos.motivo.strip(), "pr": datos.prioridad}).mappings().first()
    registrar(db, ctx.usuario, "remision", fila["id"], "create",
              valor_nuevo={"especialista_id": esp.id, "prioridad": datos.prioridad}, request=request)
    try:
        reactores.al_remitir(db, _Fila(dict(fila)))
    except Exception:  # noqa: BLE001 -- un aviso que falla no tumba la remisión
        pass
    db.commit()
    return {"id": fila["id"], "estado": "pendiente", **_vista(db, dict(fila), yo)}


@router.get("/remisiones", summary="Remisiones enviadas o recibidas")
def listar(ctx: ContextoAcceso = Depends(RequierePermiso("remision", "read")),
           db: Session = Depends(get_db)):
    yo = ctx.payload.get("personal_id")
    if ctx.alcance == "all":
        filas = db.execute(text("SELECT * FROM remisiones ORDER BY created_at DESC LIMIT 200")).mappings().all()
    else:
        filas = db.execute(text("""
            SELECT * FROM remisiones
            WHERE especialista_id = :yo OR medico_id = :yo OR remitido_por = :u
            ORDER BY created_at DESC LIMIT 200
        """), {"yo": yo if yo is not None else -1, "u": ctx.usuario.id}).mappings().all()
    return {"remisiones": [_vista(db, dict(f), yo) for f in filas]}


@router.post("/remisiones/{remision_id}/aceptar", summary="Aceptar una remisión recibida")
def aceptar(remision_id: int, request: Request,
            ctx: ContextoAcceso = Depends(RequierePermiso("remision", "update")),
            db: Session = Depends(get_db)):
    r = db.execute(text("SELECT * FROM remisiones WHERE id = :i"), {"i": remision_id}).mappings().first()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Remisión no encontrada")
    yo = ctx.payload.get("personal_id")
    if ctx.alcance != "all" and r["especialista_id"] != yo:
        registrar(db, ctx.usuario, "remision", remision_id, "update", resultado="denegado", request=request)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el especialista destinatario puede aceptarla")
    if r["estado"] != "pendiente":
        raise HTTPException(status.HTTP_409_CONFLICT, f"La remisión ya está {r['estado']}")
    fila = db.execute(text("""
        UPDATE remisiones SET estado = 'aceptada', aceptada_at = :t, aceptada_por = :u
        WHERE id = :i AND estado = 'pendiente' RETURNING *
    """), {"t": datetime.now(timezone.utc), "u": ctx.usuario.id, "i": remision_id}).mappings().first()
    if fila is None:   # alguien la aceptó o rechazó entre la lectura y el UPDATE
        raise HTTPException(status.HTTP_409_CONFLICT, "La remisión ya no está pendiente")
    registrar(db, ctx.usuario, "remision", remision_id, "update",
              valor_anterior={"estado": "pendiente"}, valor_nuevo={"estado": "aceptada"}, request=request)
    try:
        reactores.al_aceptar(db, _Fila(dict(fila)))
    except Exception:  # noqa: BLE001
        pass
    db.commit()
    return _vista(db, dict(fila), yo)


class Cierre(BaseModel):
    motivo: str | None = Field(None, max_length=1000)


def _transicion(db: Session, ctx: ContextoAcceso, request: Request, remision_id: int,
                desde: str, hacia: str, respuesta: str | None) -> dict:
    """Cambia el estado solo si sigue en `desde` y quien actúa es el destinatario."""
    r = db.execute(text("SELECT * FROM remisiones WHERE id = :i"), {"i": remision_id}).mappings().first()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Remisión no encontrada")
    yo = ctx.payload.get("personal_id")
    if ctx.alcance != "all" and r["especialista_id"] != yo:
        registrar(db, ctx.usuario, "remision", remision_id, "update", resultado="denegado", request=request)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el especialista destinatario puede cambiarla")
    fila = db.execute(text("""
        UPDATE remisiones SET estado = :hacia, respuesta = COALESCE(:resp, respuesta),
               cerrada_at = :t, cerrada_por = :u
        WHERE id = :i AND estado = :desde RETURNING *
    """), {"hacia": hacia, "resp": respuesta, "t": datetime.now(timezone.utc), "u": ctx.usuario.id,
           "i": remision_id, "desde": desde}).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"La remisión está {r['estado']}: solo se puede pasar a {hacia} desde {desde}")
    registrar(db, ctx.usuario, "remision", remision_id, "update",
              valor_anterior={"estado": desde}, valor_nuevo={"estado": hacia}, request=request)
    db.commit()
    return _vista(db, dict(fila), yo)


@router.post("/remisiones/{remision_id}/rechazar", summary="Rechazar una remisión recibida (con motivo)")
def rechazar(remision_id: int, datos: Cierre, request: Request,
             ctx: ContextoAcceso = Depends(RequierePermiso("remision", "update")),
             db: Session = Depends(get_db)):
    if not datos.motivo or len(datos.motivo.strip()) < 5:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indica el motivo del rechazo (mínimo 5 caracteres)")
    return _transicion(db, ctx, request, remision_id, "pendiente", "rechazada", datos.motivo.strip())


@router.post("/remisiones/{remision_id}/atender", summary="Cerrar como atendida una remisión aceptada")
def atender(remision_id: int, request: Request, datos: Cierre | None = None,
            ctx: ContextoAcceso = Depends(RequierePermiso("remision", "update")),
            db: Session = Depends(get_db)):
    nota = datos.motivo.strip() if datos and datos.motivo else None
    return _transicion(db, ctx, request, remision_id, "aceptada", "atendida", nota)
