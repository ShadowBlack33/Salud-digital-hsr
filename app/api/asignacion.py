"""
Camas por área: quién espera cama, asignación, traslados entre áreas y alta.

  GET  /areas                          áreas con camas y cuántas tiene libres cada una
  GET  /camas/pendientes               pacientes de MI área que esperan cama, más
                                       los que salen de quirófano y necesitan una
                                       cama del tipo que tiene mi área
  POST /camas/{id}/asignar             asignar una cama de MI área
  POST /traslados                      pedir a otra área que reciba a un paciente de la mía
  GET  /traslados                      solicitudes que me llegan y las que envié
  POST /traslados/{id}/aceptar         el área destino acepta y elige la cama
  POST /traslados/{id}/rechazar        ... o la rechaza con motivo
  POST /traslados/{id}/cancelar        el área origen la retira
  POST /pacientes/{id}/alta            SOLO el médico tratante, con tipo de egreso y motivo:
                                       la cama queda "en proceso de alta"; enfermería
                                       confirma la salida y la manda a limpieza

Cada enfermero(a) jefe tiene un área (usuarios.servicio_id). El admin no tiene
área: opera todas. Reglas que impone la API, no la pantalla:
  · solo se asigna una cama disponible de mi área, no apartada para una cirugía;
    dos personas a la vez -> la segunda recibe 409 (FOR UPDATE);
  · un paciente de cirugía va a la cama del tipo que su procedimiento exige (422);
  · un paciente = una cama; un traslado abierto por paciente.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.recursos import _nombre_corto, _registrar_evento
from app.core.crypto import blind_index, descifrar
from app.core.deps import ContextoAcceso, RequierePermiso, get_db
from app.models import Cama, CatalogoProcedimiento, Encuentro, Paciente
from app.services.auditoria import registrar
from app.services.turnos import exigir_turno, programacion, turno_en

router = APIRouter(tags=["Camas por área y traslados"])

ACTIVOS = ("planned", "arrived", "triaged", "in-progress", "onleave")
EGRESOS = {"mejoria": "Mejoría", "remision_externa": "Remisión a otra institución", "voluntaria": "Alta voluntaria",
           "fallecimiento": "Fallecimiento", "otro": "Otro"}


# ------------------------------------------------------------------ utilidades
def _mi_area(db: Session, ctx: ContextoAcceso) -> int | None:
    """Área a cargo del usuario; None = todas (admin, o base sin la migración 11)."""
    if ctx.payload.get("rol") == "admin":
        return None
    try:
        return db.execute(text("SELECT servicio_id FROM usuarios WHERE id = :u"), {"u": ctx.usuario.id}).scalar()
    except Exception:  # noqa: BLE001
        db.rollback()
        return None


def _exigir_area(area: int | None, servicio_id: int | None, que: str) -> None:
    if area is not None and servicio_id != area:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"{que} no es de tu área")


def _corto(p: Paciente | None) -> str | None:
    if p is None:
        return None
    return _nombre_corto(descifrar(p.nombre_cifrado, "pacientes.nombre"),
                         descifrar(p.apellido_cifrado, "pacientes.apellido"))


def _edad(nacimiento, ahora) -> str:
    dias = (ahora.date() - nacimiento).days
    if dias < 31:
        return f"{dias} días"
    if dias < 365:
        return f"{dias // 30} meses"
    return f"{dias // 365} años"


def _estancia_activa(db: Session, paciente_id: str) -> Encuentro | None:
    return db.query(Encuentro).filter(
        Encuentro.paciente_id == paciente_id, Encuentro.activo.is_(True),
        Encuentro.tipo == "hospitalizacion", Encuentro.estado.in_(ACTIVOS),
        Encuentro.cama_id.isnot(None)).first()


def _servicio_urgencias(db: Session) -> int | None:
    return db.execute(text("SELECT id FROM servicios WHERE codigo = 'URG'")).scalar()


def _donde_esta(db: Session, paciente_id: str) -> tuple[Encuentro | None, int | None]:
    """Atención activa del paciente y el área donde está (su cama, o Urgencias si espera sin cama)."""
    est = _estancia_activa(db, paciente_id)
    if est:
        return est, db.get(Cama, est.cama_id).servicio_id
    urg = db.query(Encuentro).filter(Encuentro.paciente_id == paciente_id, Encuentro.activo.is_(True),
                                     Encuentro.tipo == "urgencias", Encuentro.estado.in_(ACTIVOS)).first()
    if urg:
        return urg, (db.get(Cama, urg.cama_id).servicio_id if urg.cama_id else _servicio_urgencias(db))
    return None, None


def _cama_libre(db: Session, cama_id: int, area: int | None, excluir_cirugia: int | None = None) -> Cama:
    cama = db.query(Cama).filter(Cama.id == cama_id, Cama.activo.is_(True)).with_for_update(of=Cama).first()
    if cama is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cama no encontrada")
    _exigir_area(area, cama.servicio_id, f"La cama {cama.codigo}")
    if cama.estado != "disponible":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"La cama {cama.codigo} está {cama.estado.replace('_', ' ')}: solo se asigna una cama disponible")
    destino = db.query(Encuentro).filter(
        Encuentro.cama_id == cama.id, Encuentro.activo.is_(True), Encuentro.tipo == "cirugia",
        Encuentro.estado.in_(("planned", "in-progress")), Encuentro.id != (excluir_cirugia or 0)).first()
    if destino:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"La cama {cama.codigo} está apartada para la recuperación de la cirugía {destino.id}. Elige otra.")
    return cama


def _ingresar(db: Session, ctx: ContextoAcceso, request: Request, cama: Cama, paciente_id: str,
              origen: Encuentro | None, motivo: str) -> Encuentro:
    """Abre la estancia en la cama y cierra lo que el paciente deja atrás."""
    if origen is not None and origen.tipo == "cirugia" and origen.procedimiento_id:
        proc = db.get(CatalogoProcedimiento, origen.procedimiento_id)
        if proc and proc.tipo_cama_requerida_id != cama.tipo_cama_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"'{proc.nombre}' necesita cama {proc.tipo_cama_requerida.nombre}; "
                                f"la {cama.codigo} es {cama.tipo_cama.nombre}")
    ahora = datetime.now(timezone.utc)
    en_quirofano = origen is not None and origen.tipo == "cirugia" and origen.estado == "in-progress"
    estancia = Encuentro(
        paciente_id=paciente_id, tipo="hospitalizacion", estado="planned" if en_quirofano else "in-progress",
        origen="urgencia" if origen is not None and (origen.tipo == "urgencias" or origen.origen == "urgencia") else "electiva",
        prioridad_clinica=origen.prioridad_clinica if origen is not None else 3,
        diagnostico_cie10_id=origen.diagnostico_cie10_id if origen is not None else None,
        medico_responsable_id=origen.medico_responsable_id if origen is not None else None,
        cama_id=cama.id, hora_programada_inicio=ahora, hora_real_inicio=None if en_quirofano else ahora,
        created_by=ctx.usuario.id)
    db.add(estancia)
    if origen is not None and origen.tipo in ("urgencias", "hospitalizacion"):
        # Sale de urgencias o de su cama anterior (traslado): esa atención se cierra
        # y la cama que deja pasa a limpieza.
        origen.estado, origen.hora_real_fin, origen.updated_at = "finished", ahora, ahora
        if origen.cama_id and origen.cama_id != cama.id:
            vieja = db.query(Cama).filter(Cama.id == origen.cama_id).with_for_update(of=Cama).first()
            if vieja and vieja.estado in ("ocupada", "en_proceso_alta", "reservada"):
                _registrar_evento(db, "cama", vieja, "en_limpieza", ctx.usuario, f"Traslado a {cama.codigo}")
    if origen is not None and origen.tipo == "cirugia":
        origen.cama_id, origen.updated_at = cama.id, ahora
    db.flush()
    nuevo = "reservada" if en_quirofano else "ocupada"
    _registrar_evento(db, "cama", cama, nuevo, ctx.usuario, motivo[:200])
    registrar(db, ctx.usuario, "cama", cama.id, "update", valor_anterior={"estado": "disponible"},
              valor_nuevo={"estado": nuevo, "encuentro_id": estancia.id,
                           "origen_encuentro_id": origen.id if origen is not None else None}, request=request)
    return estancia


# ------------------------------------------------------------------ áreas y pendientes
@router.get("/areas", summary="Áreas con camas y su disponibilidad")
def areas(ctx: ContextoAcceso = Depends(RequierePermiso("cama", "read")), db: Session = Depends(get_db)):
    filas = db.execute(text("""
        SELECT s.id, s.codigo, s.nombre, COUNT(c.id) AS total,
               COUNT(c.id) FILTER (WHERE c.estado = 'disponible' AND NOT EXISTS (
                   SELECT 1 FROM encuentros e WHERE e.cama_id = c.id AND e.activo AND e.tipo = 'cirugia'
                     AND e.estado IN ('planned', 'in-progress'))) AS disponibles,
               COUNT(c.id) FILTER (WHERE c.estado = 'en_limpieza') AS en_limpieza,
               string_agg(DISTINCT tc.nombre, ', ') AS tipos
        FROM servicios s JOIN camas c ON c.servicio_id = s.id AND c.activo
        JOIN tipos_cama tc ON tc.id = c.tipo_cama_id
        GROUP BY s.id, s.codigo, s.nombre ORDER BY s.id
    """)).mappings().all()
    mia = _mi_area(db, ctx)
    return {"mi_area": mia, "areas": [{**dict(f), "es_mia": f["id"] == mia} for f in filas]}


@router.get("/camas/pendientes", summary="Pacientes de mi área que esperan cama")
def pendientes(ctx: ContextoAcceso = Depends(RequierePermiso("cama", "update")),
               db: Session = Depends(get_db)):
    ahora = datetime.now(timezone.utc)
    area = _mi_area(db, ctx)
    urg_id = _servicio_urgencias(db)
    urg = db.query(Encuentro).filter(
        Encuentro.activo.is_(True), Encuentro.tipo == "urgencias",
        Encuentro.estado.in_(ACTIVOS), Encuentro.cama_id.is_(None)).all() if area in (None, urg_id) else []
    tipos_mi_area = None
    if area is not None:
        tipos_mi_area = {t for (t,) in db.execute(text(
            "SELECT DISTINCT tipo_cama_id FROM camas WHERE activo AND servicio_id = :s"), {"s": area})}
    qx = db.query(Encuentro).filter(
        Encuentro.activo.is_(True), Encuentro.tipo == "cirugia", Encuentro.cama_id.is_(None),
        ((Encuentro.estado == "in-progress")
         | ((Encuentro.estado == "finished") & (Encuentro.hora_real_fin > ahora - timedelta(hours=8))))).all()
    if tipos_mi_area is not None:
        qx = [e for e in qx if e.procedimiento and e.procedimiento.tipo_cama_requerida_id in tipos_mi_area]
    ids = {e.paciente_id for e in urg + qx}
    pacientes = {p.documento_bidx: p for p in db.query(Paciente).filter(Paciente.documento_bidx.in_(ids)).all()} if ids else {}
    con_estancia = {pid for pid in ids if _estancia_activa(db, pid)}
    en_traslado = {pid for (pid,) in db.execute(text(
        "SELECT paciente_id FROM traslados WHERE estado = 'pendiente'"))} if ids else set()
    salida = []
    for e in urg + qx:
        if e.paciente_id in con_estancia:
            continue
        p = pacientes.get(e.paciente_id)
        proc = e.procedimiento
        desde = e.hora_real_fin if e.tipo == "cirugia" and e.estado == "finished" else (e.hora_real_inicio or e.created_at)
        salida.append({
            "encuentro_id": e.id,
            "origen": "urgencia" if e.tipo == "urgencias" else ("posquirurgico" if e.estado == "finished" else "en_quirofano"),
            "paciente_id": e.paciente_id, "paciente": _corto(p),
            "edad": _edad(p.fecha_nacimiento, ahora) if p and p.fecha_nacimiento else None, "sexo": p.sexo if p else None,
            "triage": e.nivel_triage, "prioridad": e.prioridad_clinica,
            "procedimiento": proc.nombre if proc else None,
            "tipo_cama_requerida": proc.tipo_cama_requerida.codigo if proc and proc.tipo_cama_requerida else None,
            "tipo_cama_requerida_nombre": proc.tipo_cama_requerida.nombre if proc and proc.tipo_cama_requerida else None,
            "esperando_min": int((ahora - desde).total_seconds() // 60) if desde else None,
            "traslado_pendiente": e.paciente_id in en_traslado,
        })
    salida.sort(key=lambda x: (x["triage"] or 9, -(x["esperando_min"] or 0)))
    return {"pendientes": salida, "mi_area": area}


# ------------------------------------------------------------------ asignar
class Asignacion(BaseModel):
    encuentro_id: int | None = Field(None, description="Urgencia o cirugía pendiente")
    documento: str | None = Field(None, description="Ingreso directo: documento del paciente")
    motivo: str | None = Field(None, max_length=300)


@router.post("/camas/{cama_id}/asignar", summary="Asignar una cama de mi área a un paciente")
def asignar(cama_id: int, datos: Asignacion, request: Request,
            ctx: ContextoAcceso = Depends(RequierePermiso("cama", "update")), db: Session = Depends(get_db)):
    if not datos.encuentro_id and not datos.documento:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Elige un paciente pendiente o escribe un documento")
    area = _mi_area(db, ctx)
    cama = _cama_libre(db, cama_id, area, excluir_cirugia=datos.encuentro_id)
    exigir_turno(db, ctx, area)
    origen = None
    if datos.encuentro_id:
        org = db.query(Encuentro).filter(Encuentro.id == datos.encuentro_id, Encuentro.activo.is_(True)) \
            .with_for_update(of=Encuentro).first()
        if org is None or org.tipo not in ("urgencias", "cirugia"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese paciente ya no está pendiente de cama")
        if org.tipo == "urgencias" and (org.estado not in ACTIVOS or org.cama_id):
            raise HTTPException(status.HTTP_409_CONFLICT, "Esa urgencia ya tiene cama o ya terminó")
        if org.tipo == "cirugia" and org.cama_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Esa cirugía ya tiene cama de recuperación")
        paciente_id, origen = org.paciente_id, org
    else:
        p = db.get(Paciente, blind_index(datos.documento.strip(), "pacientes.documento"))
        if p is None or not p.activo:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay un paciente con ese documento")
        paciente_id = p.documento_bidx
    if _estancia_activa(db, paciente_id):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Ese paciente ya tiene una cama asignada. Si debe cambiar de área, solicita un traslado.")
    de_donde = ({"urgencias": "desde urgencias", "cirugia": "desde quirófano"}[origen.tipo]
                if origen is not None else "ingreso directo")
    estancia = _ingresar(db, ctx, request, cama, paciente_id, origen,
                         f"Asignada {de_donde}{': ' + datos.motivo if datos.motivo else ''}")
    db.commit()
    return {"cama": cama.codigo, "estado": cama.estado, "encuentro_id": estancia.id}


# ------------------------------------------------------------------ traslados
class SolicitudTraslado(BaseModel):
    paciente_id: str
    servicio_destino_id: int
    motivo: str = Field(..., min_length=5, max_length=500)
    prioridad: str = Field("prioritaria", pattern="^(rutinaria|prioritaria|urgente)$")


def _vista_traslado(db: Session, t: dict, area: int | None) -> dict:
    p = db.get(Paciente, t["paciente_id"])
    nombres = dict(db.execute(text("SELECT id, nombre FROM servicios")).fetchall())
    cama = db.get(Cama, t["cama_destino_id"]) if t["cama_destino_id"] else None
    return {**{k: t[k] for k in ("id", "paciente_id", "servicio_origen_id", "servicio_destino_id", "motivo",
                                 "prioridad", "estado", "respuesta", "created_at", "resuelto_at")},
            "paciente": _corto(p), "origen": nombres.get(t["servicio_origen_id"]),
            "destino": nombres.get(t["servicio_destino_id"]), "cama_destino": cama.codigo if cama else None,
            "entrante": area is None or t["servicio_destino_id"] == area,
            "saliente": area is None or t["servicio_origen_id"] == area}


@router.post("/traslados", status_code=status.HTTP_201_CREATED, summary="Pedir a otra área que reciba a un paciente")
def solicitar(datos: SolicitudTraslado, request: Request,
              ctx: ContextoAcceso = Depends(RequierePermiso("cama", "update")), db: Session = Depends(get_db)):
    area = _mi_area(db, ctx)
    enc, donde = _donde_esta(db, datos.paciente_id)
    if enc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese paciente no está en ninguna área ahora")
    _exigir_area(area, donde, "Ese paciente")
    exigir_turno(db, ctx, area)
    if datos.servicio_destino_id == donde:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El paciente ya está en esa área")
    if not db.execute(text("SELECT 1 FROM camas WHERE servicio_id = :s AND activo LIMIT 1"),
                      {"s": datos.servicio_destino_id}).first():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Esa área no tiene camas")
    if db.execute(text("SELECT 1 FROM traslados WHERE paciente_id = :p AND estado = 'pendiente'"),
                  {"p": datos.paciente_id}).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese paciente ya tiene un traslado pendiente")
    fila = db.execute(text("""
        INSERT INTO traslados (paciente_id, encuentro_origen_id, servicio_origen_id, servicio_destino_id,
                               motivo, prioridad, solicitado_por)
        VALUES (:p, :e, :o, :d, :m, :pr, :u) RETURNING *
    """), {"p": datos.paciente_id, "e": enc.id, "o": donde, "d": datos.servicio_destino_id,
           "m": datos.motivo.strip(), "pr": datos.prioridad, "u": ctx.usuario.id}).mappings().first()
    registrar(db, ctx.usuario, "traslado", fila["id"], "create",
              valor_nuevo={"origen": donde, "destino": datos.servicio_destino_id, "prioridad": datos.prioridad},
              request=request)
    db.commit()
    return _vista_traslado(db, dict(fila), area)


@router.get("/traslados", summary="Traslados que me llegan y los que envié")
def listar_traslados(ctx: ContextoAcceso = Depends(RequierePermiso("cama", "read")), db: Session = Depends(get_db)):
    area = _mi_area(db, ctx)
    filas = db.execute(text("""
        SELECT * FROM traslados
        WHERE (:a IS NULL OR servicio_origen_id = :a OR servicio_destino_id = :a)
          AND (estado = 'pendiente' OR resuelto_at > NOW() - INTERVAL '24 hours')
        ORDER BY (estado = 'pendiente') DESC,
                 CASE prioridad WHEN 'urgente' THEN 0 WHEN 'prioritaria' THEN 1 ELSE 2 END, created_at
    """), {"a": area}).mappings().all()
    return {"mi_area": area, "traslados": [_vista_traslado(db, dict(f), area) for f in filas]}


def _traslado_para_resolver(db: Session, traslado_id: int) -> dict:
    t = db.execute(text("SELECT * FROM traslados WHERE id = :i FOR UPDATE"), {"i": traslado_id}).mappings().first()
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Traslado no encontrado")
    if t["estado"] != "pendiente":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ese traslado ya está {t['estado']}")
    return dict(t)


class Aceptacion(BaseModel):
    cama_id: int


@router.post("/traslados/{traslado_id}/aceptar", summary="El área destino acepta y elige la cama")
def aceptar_traslado(traslado_id: int, datos: Aceptacion, request: Request,
                     ctx: ContextoAcceso = Depends(RequierePermiso("cama", "update")), db: Session = Depends(get_db)):
    area = _mi_area(db, ctx)
    t = _traslado_para_resolver(db, traslado_id)
    _exigir_area(area, t["servicio_destino_id"], "Ese traslado")
    exigir_turno(db, ctx, area)
    cama = _cama_libre(db, datos.cama_id, t["servicio_destino_id"])
    enc, _ = _donde_esta(db, t["paciente_id"])
    if enc is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "El paciente ya no está en el área de origen (¿le dieron de alta?)")
    origen_nombre = db.execute(text("SELECT nombre FROM servicios WHERE id = :s"), {"s": t["servicio_origen_id"]}).scalar()
    estancia = _ingresar(db, ctx, request, cama, t["paciente_id"], enc, f"Traslado desde {origen_nombre}")
    db.execute(text("""UPDATE traslados SET estado = 'aceptado', cama_destino_id = :c, resuelto_por = :u,
                       resuelto_at = NOW() WHERE id = :i"""), {"c": cama.id, "u": ctx.usuario.id, "i": traslado_id})
    registrar(db, ctx.usuario, "traslado", traslado_id, "update", valor_anterior={"estado": "pendiente"},
              valor_nuevo={"estado": "aceptado", "cama_id": cama.id, "encuentro_id": estancia.id}, request=request)
    db.commit()
    return {"id": traslado_id, "estado": "aceptado", "cama": cama.codigo}


class Respuesta(BaseModel):
    motivo: str = Field(..., min_length=5, max_length=500)


@router.post("/traslados/{traslado_id}/rechazar", summary="El área destino rechaza (con motivo)")
def rechazar_traslado(traslado_id: int, datos: Respuesta, request: Request,
                      ctx: ContextoAcceso = Depends(RequierePermiso("cama", "update")), db: Session = Depends(get_db)):
    area = _mi_area(db, ctx)
    t = _traslado_para_resolver(db, traslado_id)
    _exigir_area(area, t["servicio_destino_id"], "Ese traslado")
    exigir_turno(db, ctx, area)
    db.execute(text("""UPDATE traslados SET estado = 'rechazado', respuesta = :r, resuelto_por = :u, resuelto_at = NOW()
                       WHERE id = :i"""), {"r": datos.motivo.strip(), "u": ctx.usuario.id, "i": traslado_id})
    registrar(db, ctx.usuario, "traslado", traslado_id, "update", valor_anterior={"estado": "pendiente"},
              valor_nuevo={"estado": "rechazado"}, request=request)
    db.commit()
    return {"id": traslado_id, "estado": "rechazado"}


@router.post("/traslados/{traslado_id}/cancelar", summary="El área origen retira la solicitud")
def cancelar_traslado(traslado_id: int, request: Request,
                      ctx: ContextoAcceso = Depends(RequierePermiso("cama", "update")), db: Session = Depends(get_db)):
    area = _mi_area(db, ctx)
    t = _traslado_para_resolver(db, traslado_id)
    _exigir_area(area, t["servicio_origen_id"], "Ese traslado")
    exigir_turno(db, ctx, area)
    db.execute(text("UPDATE traslados SET estado = 'cancelado', resuelto_por = :u, resuelto_at = NOW() WHERE id = :i"),
               {"u": ctx.usuario.id, "i": traslado_id})
    registrar(db, ctx.usuario, "traslado", traslado_id, "update", valor_anterior={"estado": "pendiente"},
              valor_nuevo={"estado": "cancelado"}, request=request)
    db.commit()
    return {"id": traslado_id, "estado": "cancelado"}


# ------------------------------------------------------------------ alta médica
class AltaMedica(BaseModel):
    tipo_egreso: str = Field(..., pattern="^(mejoria|remision_externa|voluntaria|fallecimiento|otro)$")
    motivo: str = Field(..., min_length=10, max_length=1000, description="Por qué se da el alta")


@router.post("/pacientes/{paciente_id}/alta", summary="Alta médica (solo el médico tratante)")
def alta_medica(paciente_id: str, datos: AltaMedica, request: Request,
                ctx: ContextoAcceso = Depends(RequierePermiso("alta", "create")), db: Session = Depends(get_db)):
    p = db.get(Paciente, paciente_id)
    if p is None or not p.activo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    ctx.verificar_registro(p)   # solo sus pacientes (alcance assigned)
    enc, _ = _donde_esta(db, paciente_id)
    if enc is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "El paciente no tiene una atención activa para dar de alta")
    ahora = datetime.now(timezone.utc)
    nota = f"Alta ({EGRESOS[datos.tipo_egreso]}): {datos.motivo.strip()}"
    enc.estado, enc.hora_real_fin, enc.updated_at = "finished", ahora, ahora
    enc.observaciones_texto = ((enc.observaciones_texto or "") + "\n" + nota).strip()
    db.execute(text("UPDATE traslados SET estado = 'cancelado', respuesta = 'Alta médica', resuelto_at = NOW() "
                    "WHERE paciente_id = :p AND estado = 'pendiente'"), {"p": paciente_id})
    cama = None
    if enc.cama_id:
        cama = db.query(Cama).filter(Cama.id == enc.cama_id).with_for_update(of=Cama).first()
        if cama and cama.estado == "ocupada":
            # Sigue físicamente ahí: enfermería confirma la salida y la manda a limpieza.
            _registrar_evento(db, "cama", cama, "en_proceso_alta", ctx.usuario, f"Alta médica: {EGRESOS[datos.tipo_egreso]}")
    registrar(db, ctx.usuario, "encuentro", enc.id, "update", valor_anterior={"estado": "activo"},
              valor_nuevo={"estado": "finished", "tipo_egreso": datos.tipo_egreso}, request=request)
    db.commit()
    return {"encuentro_id": enc.id, "tipo_egreso": datos.tipo_egreso,
            "cama": cama.codigo if cama else None, "estado_cama": cama.estado if cama else None}


# ------------------------------------------------------------------ tablero del área
@router.get("/areas/tablero", summary="Tablero detallado de un área: camas, pacientes, pendientes")
def tablero_area(servicio_id: int | None = None,
                 ctx: ContextoAcceso = Depends(RequierePermiso("cama", "update")), db: Session = Depends(get_db)):
    """
    Lo que el enfermero(a) jefe necesita de SU área: cada cama con su paciente
    (nombre corto, edad, diagnóstico, médico, días de estancia, críticos de las
    últimas 24 h), altas pendientes de salida, camas que llevan mucho en limpieza,
    ingresos y egresos del día y los traslados en curso. El admin elige el área.
    """
    from app.api.recursos import ocupacion_camas

    area = _mi_area(db, ctx)
    if area is not None and servicio_id not in (None, area):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo ves el tablero de tu área")
    sid = area if area is not None else servicio_id
    if sid is None:
        sid = db.execute(text("SELECT MIN(servicio_id) FROM camas WHERE activo")).scalar()
    info = db.execute(text("SELECT id, codigo, nombre FROM servicios WHERE id = :s"), {"s": sid}).mappings().first()
    if info is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Área no encontrada")
    ids = {i for (i,) in db.execute(text("SELECT id FROM camas WHERE activo AND servicio_id = :s"), {"s": sid})}
    camas = [c for c in ocupacion_camas(ctx=ctx, db=db, solo_ocupadas=False) if c["cama_id"] in ids]

    ahora = datetime.now(timezone.utc)
    pacientes = [c["paciente_id"] for c in camas if c.get("encuentro_activo") and c.get("paciente_id")]
    criticos = {}
    if pacientes:
        for f in db.execute(text("""
            SELECT o.paciente_id, COUNT(*) AS n, MAX(o.fecha_hora) AS ultima
            FROM observaciones o
            WHERE o.activo AND o.es_critico AND o.paciente_id = ANY(:p) AND o.fecha_hora > NOW() - INTERVAL '24 hours'
            GROUP BY o.paciente_id"""), {"p": pacientes}).mappings():
            criticos[f["paciente_id"]] = {"n": f["n"], "ultima": f["ultima"]}
    estancias = {r["cama_id"]: r for r in db.execute(text("""
        SELECT cama_id, origen, prioridad_clinica, COALESCE(hora_real_inicio, created_at) AS desde
        FROM encuentros WHERE activo AND cama_id = ANY(:c) AND estado IN ('planned','arrived','triaged','in-progress','onleave')
          AND tipo IN ('hospitalizacion', 'urgencias')"""), {"c": list(ids) or [0]}).mappings()}
    for c in camas:
        e = estancias.get(c["cama_id"])
        c["dias_estancia"] = round((ahora - e["desde"]).total_seconds() / 86400, 1) if e and e["desde"] else None
        c["origen_ingreso"] = e["origen"] if e else None
        c["criticos_24h"] = criticos.get(c.get("paciente_id"), {}).get("n", 0)
        c["minutos_en_estado"] = int((ahora - c["estado_cama_desde"]).total_seconds() // 60) if c.get("estado_cama_desde") else None

    por_estado = {}
    for c in camas:
        por_estado[c["estado_cama"]] = por_estado.get(c["estado_cama"], 0) + 1
    utiles = len(camas) - sum(por_estado.get(e, 0) for e in ("bloqueada", "contaminada"))
    ocupadas = sum(por_estado.get(e, 0) for e in ("ocupada", "reservada", "en_proceso_alta"))
    mov = dict(db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE e.hora_real_inicio >= date_trunc('day', NOW())) AS ingresos_hoy,
               COUNT(*) FILTER (WHERE e.estado = 'finished' AND e.hora_real_fin >= date_trunc('day', NOW())) AS egresos_hoy,
               ROUND(AVG(EXTRACT(EPOCH FROM (e.hora_real_fin - e.hora_real_inicio)) / 86400)
                     FILTER (WHERE e.estado = 'finished' AND e.hora_real_fin > NOW() - INTERVAL '30 days')::numeric, 1)
                     AS estancia_promedio_dias
        FROM encuentros e JOIN camas c ON c.id = e.cama_id
        WHERE e.activo AND e.tipo = 'hospitalizacion' AND c.servicio_id = :s"""), {"s": sid}).mappings().first())

    alertas = []
    for c in camas:
        m = c["minutos_en_estado"] or 0
        if c["estado_cama"] == "en_proceso_alta" and m > 120:
            alertas.append({"nivel": "media", "cama": c["cama_codigo"], "texto": f"Alta dada hace {m // 60} h y el paciente no ha salido"})
        if c["estado_cama"] == "en_limpieza" and m > 90:
            alertas.append({"nivel": "media", "cama": c["cama_codigo"], "texto": f"En limpieza hace {m // 60} h {m % 60} min"})
        if c["criticos_24h"]:
            alertas.append({"nivel": "alta", "cama": c["cama_codigo"],
                            "texto": f"{c.get('paciente_nombre_corto') or 'Paciente'}: {c['criticos_24h']} valor(es) crítico(s) en 24 h"})
        if (c["dias_estancia"] or 0) > 10:
            alertas.append({"nivel": "baja", "cama": c["cama_codigo"],
                            "texto": f"{c.get('paciente_nombre_corto') or 'Paciente'}: estancia prolongada ({c['dias_estancia']} días)"})
    orden = {"alta": 0, "media": 1, "baja": 2}
    alertas.sort(key=lambda a: orden[a["nivel"]])

    traslados = dict(db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE servicio_destino_id = :s) AS entrantes,
               COUNT(*) FILTER (WHERE servicio_origen_id = :s) AS salientes
        FROM traslados WHERE estado = 'pendiente'"""), {"s": sid}).mappings().first())
    actual = turno_en(db, sid)
    return {
        "area": dict(info), "es_mia": area == sid, "ahora": ahora,
        "turno": {"actual": actual, "soy_yo": bool(actual and actual["usuario_id"] == ctx.usuario.id),
                  "puedo_operar": ctx.payload.get("rol") == "admin" or actual is None or actual["usuario_id"] == ctx.usuario.id,
                  "programacion": programacion(db, sid)},
        "resumen": {"total": len(camas), "utiles": utiles, "ocupadas": ocupadas,
                    "pct_ocupacion": round(100 * ocupadas / utiles, 1) if utiles else 0,
                    "por_estado": por_estado, "ingresos_hoy": int(mov["ingresos_hoy"] or 0), "egresos_hoy": int(mov["egresos_hoy"] or 0),
                    "estancia_promedio_dias": float(mov["estancia_promedio_dias"]) if mov["estancia_promedio_dias"] else None,
                    "traslados_entrantes": traslados["entrantes"], "traslados_salientes": traslados["salientes"]},
        "alertas": alertas[:20],
        "camas": sorted(camas, key=lambda c: c["cama_codigo"]),
    }


class Cobertura(BaseModel):
    motivo: str = Field(..., min_length=5, max_length=300, description="p. ej. incapacidad de la jefe de turno")


@router.post("/areas/turno/cubrir", summary="Cubrir el turno de mi área (el jefe programado no está)")
def cubrir_turno(datos: Cobertura, request: Request,
                 ctx: ContextoAcceso = Depends(RequierePermiso("cama", "update")), db: Session = Depends(get_db)):
    area = _mi_area(db, ctx)
    if area is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No tienes un área a cargo")
    actual = turno_en(db, area)
    if actual and actual["usuario_id"] == ctx.usuario.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya estás de turno")
    ahora = datetime.now(timezone.utc)
    fin = actual["fin"] if actual else ahora + timedelta(hours=6)
    fila = db.execute(text("""
        INSERT INTO turnos_area (servicio_id, usuario_id, inicio, fin, tipo, motivo, created_by)
        VALUES (:s, :u, :i, :f, 'cobertura', :m, :u) RETURNING id
    """), {"s": area, "u": ctx.usuario.id, "i": ahora, "f": fin, "m": datos.motivo.strip()}).first()
    registrar(db, ctx.usuario, "turno", fila[0], "create",
              valor_anterior={"de_turno": actual["username"] if actual else None},
              valor_nuevo={"cubre": ctx.usuario.username, "hasta": fin.isoformat()}, request=request)
    db.commit()
    return {"id": fila[0], "de_turno": ctx.usuario.username, "hasta": fin}
