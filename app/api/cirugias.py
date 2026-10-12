"""
Coordinación quirúrgica: programar, mover y cancelar cirugías.

La hace el enfermero(a) jefe (permisos agenda:create / agenda:update). El
caso que motiva el módulo: llega una urgencia y hay que meterla en un
quirófano que ya tiene cirugías programadas. Las opciones son

  · moverla a otro quirófano u otra hora (PATCH /cirugias/{id}/reprogramar);
  · insertar la urgencia y correr las siguientes de esa sala
    (POST /cirugias con desplazar=true);
  · cancelar con su causa (Res. 256/2016 exige medir las cancelaciones).

Cada cambio queda en la auditoría con el antes y el después, y en
eventos_estado con el motivo, igual que los cambios de camas y quirófanos.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.crypto import blind_index, descifrar
from app.core.deps import ContextoAcceso, RequierePermiso, get_db
from app.models import CatalogoProcedimiento, Encuentro, Paciente, Personal, Quirofano
from app.services.auditoria import registrar

router = APIRouter(prefix="/cirugias", tags=["Coordinación quirúrgica"])

ROTACION_MIN = 20          # limpieza y preparación entre dos cirugías de la misma sala
ACTIVAS = ("planned", "in-progress")


def _nombre(cifrado_n, cifrado_a, aad="pacientes") -> str:
    n = descifrar(cifrado_n, f"{aad}.nombre") or ""
    a = descifrar(cifrado_a, f"{aad}.apellido") or ""
    return f"{n} {a}".strip()


def _corto(p: Paciente | None) -> str | None:
    if p is None:
        return None
    n = (descifrar(p.nombre_cifrado, "pacientes.nombre") or "").strip()
    a = (descifrar(p.apellido_cifrado, "pacientes.apellido") or "").strip()
    return f"{n[:1]}. {a}" if n else a


def _fin(e: Encuentro) -> datetime:
    """Hora en que la sala queda libre (sin contar la rotación)."""
    if e.hora_programada_fin:
        return e.hora_programada_fin
    dur = e.procedimiento.duracion_estimada_min if e.procedimiento else 90
    return (e.hora_real_inicio or e.hora_programada_inicio) + timedelta(minutes=dur)


def _vista(e: Encuentro, pacientes: dict, nombres: dict) -> dict:
    return {
        "id": e.id, "estado": e.estado, "origen": e.origen, "prioridad": e.prioridad_clinica,
        "quirofano_id": e.quirofano_id,
        "paciente_id": e.paciente_id, "paciente": _corto(pacientes.get(e.paciente_id)),
        "procedimiento": e.procedimiento.nombre if e.procedimiento else None,
        "procedimiento_id": e.procedimiento_id,
        "especialidad": e.procedimiento.especialidad.nombre if e.procedimiento and e.procedimiento.especialidad else None,
        "duracion_estimada_min": e.procedimiento.duracion_estimada_min if e.procedimiento else None,
        "hora_programada_inicio": e.hora_programada_inicio, "hora_programada_fin": e.hora_programada_fin,
        "hora_real_inicio": e.hora_real_inicio, "hora_real_fin": e.hora_real_fin,
        "cirujano_id": e.medico_responsable_id, "cirujano": nombres.get(e.medico_responsable_id),
        "anestesiologo": nombres.get(e.anestesiologo_id),
    }


def _nombres_personal(db: Session, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {m.id: _nombre(m.nombre_cifrado, m.apellido_cifrado, "personal")
            for m in db.query(Personal).filter(Personal.id.in_(ids)).all()}


def _de_la_sala(db: Session, quirofano_id: int, desde: datetime, excluir: int | None = None) -> list[Encuentro]:
    q = db.query(Encuentro).filter(
        Encuentro.activo.is_(True), Encuentro.tipo == "cirugia", Encuentro.quirofano_id == quirofano_id,
        Encuentro.estado.in_(ACTIVAS),
        Encuentro.hora_programada_inicio >= desde - timedelta(hours=12))
    if excluir:
        q = q.filter(Encuentro.id != excluir)
    return sorted(q.all(), key=lambda e: e.hora_real_inicio or e.hora_programada_inicio)


def _choques(sala: list[Encuentro], ini: datetime, fin: datetime) -> list[Encuentro]:
    rot = timedelta(minutes=ROTACION_MIN)
    return [e for e in sala
            if (e.hora_real_inicio or e.hora_programada_inicio) < fin + rot and _fin(e) + rot > ini]


def _correr_siguientes(db: Session, sala: list[Encuentro], libre_desde: datetime, usuario, request,
                       motivo: str) -> list[dict]:
    """Corre en cadena las programadas de la sala que ya no caben."""
    movidas = []
    rot = timedelta(minutes=ROTACION_MIN)
    cursor = libre_desde + rot
    for e in sala:
        if e.estado != "planned":
            cursor = max(cursor, _fin(e) + rot)
            continue
        if e.hora_programada_inicio >= cursor:
            break   # desde aquí ya no hay choque
        dur = _fin(e) - e.hora_programada_inicio
        antes = {"hora_programada_inicio": e.hora_programada_inicio.isoformat()}
        e.hora_programada_inicio, e.hora_programada_fin = cursor, cursor + dur
        e.updated_at = datetime.now(timezone.utc)
        registrar(db, usuario, "encuentro", e.id, "update", valor_anterior=antes,
                  valor_nuevo={"hora_programada_inicio": cursor.isoformat(), "motivo": motivo}, request=request)
        _evento(db, e, "planned", "planned", usuario, f"Corrida: {motivo}"[:200])
        movidas.append({"id": e.id, "desde": antes["hora_programada_inicio"], "hasta": cursor.isoformat()})
        cursor = cursor + dur + rot
    return movidas


def _evento(db: Session, e: Encuentro, anterior: str, nuevo: str, usuario, motivo: str) -> None:
    db.execute(text("""
        INSERT INTO eventos_estado (entidad_tipo, entidad_id, estado_anterior, estado_nuevo, motivo, usuario_id, origen)
        VALUES ('encuentro', :id, :a, :n, :m, :u, 'manual')
    """), {"id": e.id, "a": anterior, "n": nuevo, "m": motivo[:200], "u": usuario.id})


def _validar_hora(ini: datetime) -> datetime:
    ini = ini if ini.tzinfo else ini.replace(tzinfo=timezone.utc)
    if ini < datetime.now(timezone.utc) - timedelta(minutes=5):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Esa hora ya pasó: elige una hora futura")
    return ini


def _validar_sala(qx: Quirofano | None, proc: CatalogoProcedimiento | None) -> None:
    if qx is None or not qx.activo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quirófano no encontrado")
    if qx.estado == "bloqueado":
        raise HTTPException(status.HTTP_409_CONFLICT, f"{qx.codigo} está bloqueado")
    if proc is not None and proc.requiere_arco_c and not qx.tiene_arco_c:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"'{proc.nombre}' necesita arco en C y {qx.codigo} no lo tiene")


def _error_choque(choques: list[Encuentro], db: Session) -> HTTPException:
    pacientes = {p.documento_bidx: p for p in db.query(Paciente).filter(
        Paciente.documento_bidx.in_([c.paciente_id for c in choques])).all()}
    nombres = _nombres_personal(db, [c.medico_responsable_id for c in choques])
    return HTTPException(status.HTTP_409_CONFLICT, detail=jsonable_encoder({
        "mensaje": "La sala está ocupada en ese horario. Elige otra hora u otro quirófano, "
                   "o corre las cirugías siguientes.",
        "choques": [_vista(c, pacientes, nombres) for c in choques]}))


# ------------------------------------------------------------------ catálogos
@router.get("/catalogos", summary="Quirófanos, procedimientos, cirujanos y causas de cancelación")
def catalogos(ctx: ContextoAcceso = Depends(RequierePermiso("agenda", "read")),
              db: Session = Depends(get_db)):
    procs = db.execute(text("""
        SELECT cp.id, cp.nombre, esp.nombre AS especialidad, cp.duracion_estimada_min,
               cp.requiere_arco_c, tc.nombre AS cama_requerida, cp.especialidad_id
        FROM catalogo_procedimientos cp JOIN especialidades esp ON esp.id = cp.especialidad_id
        JOIN tipos_cama tc ON tc.id = cp.tipo_cama_requerida_id
        WHERE cp.activo ORDER BY esp.nombre, cp.nombre""")).mappings().all()
    personal = db.query(Personal).filter(
        Personal.activo.is_(True), Personal.tipo_personal.in_(["medico_especialista", "anestesiologo"])).all()
    gente = [{"id": m.id, "nombre": _nombre(m.nombre_cifrado, m.apellido_cifrado, "personal"),
              "tipo": m.tipo_personal, "especialidad_id": m.especialidad_id,
              "especialidad": m.especialidad.nombre if m.especialidad else None} for m in personal]
    return {
        "quirofanos": [{"id": q.id, "codigo": q.codigo, "nombre": q.nombre, "estado": q.estado,
                        "tiene_arco_c": q.tiene_arco_c,
                        "tiene_circulacion_extracorporea": q.tiene_circulacion_extracorporea}
                       for q in db.query(Quirofano).filter(Quirofano.activo.is_(True)).order_by(Quirofano.id)],
        "procedimientos": [dict(p) for p in procs],
        "cirujanos": sorted([g for g in gente if g["tipo"] == "medico_especialista"], key=lambda g: g["nombre"]),
        "anestesiologos": sorted([g for g in gente if g["tipo"] == "anestesiologo"], key=lambda g: g["nombre"]),
        "causas_cancelacion": [dict(r) for r in db.execute(text(
            "SELECT id, codigo, descripcion, responsable FROM catalogo_causas_cancelacion ORDER BY id")).mappings()],
        "rotacion_min": ROTACION_MIN,
    }


# ------------------------------------------------------------------ agenda del día
@router.get("/dia", summary="Programación quirúrgica de un día, por sala")
def agenda_dia(fecha: date | None = Query(None, description="AAAA-MM-DD; hoy si se omite"),
               ctx: ContextoAcceso = Depends(RequierePermiso("agenda", "read")),
               db: Session = Depends(get_db)):
    ahora = datetime.now(timezone.utc)
    dia = fecha or ahora.astimezone().date()
    tz = ahora.astimezone().tzinfo
    ini = datetime.combine(dia, time(0, 0), tz)
    fin = ini + timedelta(days=1)
    cirugias = db.query(Encuentro).filter(
        Encuentro.activo.is_(True), Encuentro.tipo == "cirugia", Encuentro.quirofano_id.isnot(None),
        ((Encuentro.hora_programada_inicio >= ini) & (Encuentro.hora_programada_inicio < fin))
        | (Encuentro.estado == "in-progress")).all()
    pacientes = {p.documento_bidx: p for p in db.query(Paciente).filter(
        Paciente.documento_bidx.in_({c.paciente_id for c in cirugias})).all()} if cirugias else {}
    nombres = _nombres_personal(db, [c.medico_responsable_id for c in cirugias] + [c.anestesiologo_id for c in cirugias])
    salas = db.query(Quirofano).filter(Quirofano.activo.is_(True)).order_by(Quirofano.id).all()
    por_sala = {q.id: [] for q in salas}
    for c in sorted(cirugias, key=lambda c: c.hora_real_inicio or c.hora_programada_inicio):
        if c.quirofano_id in por_sala:
            por_sala[c.quirofano_id].append(_vista(c, pacientes, nombres))
    # Choques que ya existen (por ejemplo, una cirugía que se alargó).
    conflictos = []
    for q in salas:
        activas = [c for c in cirugias if c.quirofano_id == q.id and c.estado in ACTIVAS]
        activas.sort(key=lambda c: c.hora_real_inicio or c.hora_programada_inicio)
        for a, b in zip(activas, activas[1:]):
            if _fin(a) + timedelta(minutes=ROTACION_MIN) > (b.hora_real_inicio or b.hora_programada_inicio):
                conflictos.append({"quirofano": q.codigo, "cirugia_id": b.id, "despues_de": a.id})
    return {
        "fecha": dia.isoformat(), "ahora": ahora.isoformat(), "rotacion_min": ROTACION_MIN,
        "salas": [{"id": q.id, "codigo": q.codigo, "nombre": q.nombre, "estado": q.estado,
                   "tiene_arco_c": q.tiene_arco_c, "cirugias": por_sala[q.id]} for q in salas],
        "conflictos": conflictos,
    }


# ------------------------------------------------------------------ programar
class CirugiaCrear(BaseModel):
    paciente_id: str | None = Field(None, description="documento_bidx, si ya se conoce")
    documento: str | None = Field(None, description="Documento del paciente (se busca con el índice ciego)")
    procedimiento_id: int
    quirofano_id: int
    hora_inicio: datetime
    cirujano_id: int | None = None
    anestesiologo_id: int | None = None
    origen: str = Field("electiva", pattern="^(electiva|urgencia)$")
    prioridad: int = Field(3, ge=1, le=5)
    desplazar: bool = Field(False, description="Si choca, correr las siguientes de la sala")
    motivo: str | None = Field(None, max_length=200)


@router.post("", status_code=status.HTTP_201_CREATED, summary="Programar una cirugía (o meter una urgencia)")
def programar(datos: CirugiaCrear, request: Request,
              ctx: ContextoAcceso = Depends(RequierePermiso("agenda", "create")),
              db: Session = Depends(get_db)):
    pid = datos.paciente_id or (blind_index(datos.documento, "pacientes.documento") if datos.documento else None)
    p = db.get(Paciente, pid) if pid else None
    if p is None or not p.activo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    proc = db.get(CatalogoProcedimiento, datos.procedimiento_id)
    if proc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Procedimiento no encontrado")
    qx = db.get(Quirofano, datos.quirofano_id)
    _validar_sala(qx, proc)

    ini = _validar_hora(datos.hora_inicio)
    fin = ini + timedelta(minutes=proc.duracion_estimada_min)
    sala = _de_la_sala(db, qx.id, ini)
    choques = _choques(sala, ini, fin)
    if choques and not datos.desplazar:
        raise _error_choque(choques, db)
    if any(c.estado == "in-progress" for c in choques):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Hay una cirugía en curso en esa sala a esa hora: no se puede correr. Elige otra sala u hora.")

    e = Encuentro(paciente_id=p.documento_bidx, tipo="cirugia", estado="planned", origen=datos.origen,
                  prioridad_clinica=1 if datos.origen == "urgencia" else datos.prioridad,
                  procedimiento_id=proc.id, quirofano_id=qx.id,
                  medico_responsable_id=datos.cirujano_id, anestesiologo_id=datos.anestesiologo_id,
                  hora_programada_inicio=ini, hora_programada_fin=fin, created_by=ctx.usuario.id)
    db.add(e)
    db.flush()
    motivo = datos.motivo or ("Urgencia" if datos.origen == "urgencia" else "Programación")
    movidas = _correr_siguientes(db, sala, fin, ctx.usuario, request, f"{motivo} (cirugía {e.id})") if choques else []
    registrar(db, ctx.usuario, "encuentro", e.id, "create",
              valor_nuevo={"tipo": "cirugia", "quirofano": qx.codigo, "inicio": ini.isoformat(),
                           "origen": datos.origen, "corridas": [m["id"] for m in movidas]}, request=request)
    _evento(db, e, None, "planned", ctx.usuario, motivo)
    db.commit()
    return {"id": e.id, "quirofano": qx.codigo, "hora_programada_inicio": ini, "hora_programada_fin": fin,
            "corridas": movidas}


# ------------------------------------------------------------------ mover
class Reprogramar(BaseModel):
    quirofano_id: int | None = None
    hora_inicio: datetime | None = None
    motivo: str = Field(..., min_length=3, max_length=200)
    desplazar: bool = False


@router.patch("/{cirugia_id}/reprogramar", summary="Mover una cirugía programada a otra sala u hora")
def reprogramar(cirugia_id: int, datos: Reprogramar, request: Request,
                ctx: ContextoAcceso = Depends(RequierePermiso("agenda", "update")),
                db: Session = Depends(get_db)):
    e = db.get(Encuentro, cirugia_id)
    if e is None or not e.activo or e.tipo != "cirugia":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cirugía no encontrada")
    if e.estado != "planned":
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se mueven cirugías programadas (no en curso ni terminadas)")
    if datos.quirofano_id is None and datos.hora_inicio is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indica la nueva sala, la nueva hora o ambas")

    qx = db.get(Quirofano, datos.quirofano_id or e.quirofano_id)
    _validar_sala(qx, e.procedimiento)
    ini = _validar_hora(datos.hora_inicio) if datos.hora_inicio else e.hora_programada_inicio
    dur = _fin(e) - e.hora_programada_inicio
    fin = ini + dur
    sala = _de_la_sala(db, qx.id, ini, excluir=e.id)
    choques = _choques(sala, ini, fin)
    if choques and not datos.desplazar:
        raise _error_choque(choques, db)
    if any(c.estado == "in-progress" for c in choques):
        raise HTTPException(status.HTTP_409_CONFLICT, "Choca con una cirugía en curso: elige otra sala u hora.")

    antes = {"quirofano_id": e.quirofano_id, "hora_programada_inicio": e.hora_programada_inicio.isoformat()}
    e.quirofano_id, e.hora_programada_inicio, e.hora_programada_fin = qx.id, ini, fin
    e.updated_at = datetime.now(timezone.utc)
    movidas = _correr_siguientes(db, sala, fin, ctx.usuario, request, datos.motivo) if choques else []
    registrar(db, ctx.usuario, "encuentro", e.id, "update", valor_anterior=antes,
              valor_nuevo={"quirofano_id": qx.id, "hora_programada_inicio": ini.isoformat(),
                           "motivo": datos.motivo, "corridas": [m["id"] for m in movidas]}, request=request)
    _evento(db, e, "planned", "planned", ctx.usuario, f"Reprogramada: {datos.motivo}")
    db.commit()
    return {"id": e.id, "quirofano": qx.codigo, "hora_programada_inicio": ini, "hora_programada_fin": fin,
            "corridas": movidas}


# ------------------------------------------------------------------ cancelar
class Cancelar(BaseModel):
    causa_id: int
    detalle: str | None = Field(None, max_length=500)


@router.post("/{cirugia_id}/cancelar", summary="Cancelar una cirugía con su causa")
def cancelar(cirugia_id: int, datos: Cancelar, request: Request,
             ctx: ContextoAcceso = Depends(RequierePermiso("agenda", "update")),
             db: Session = Depends(get_db)):
    e = db.get(Encuentro, cirugia_id)
    if e is None or not e.activo or e.tipo != "cirugia":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cirugía no encontrada")
    if e.estado != "planned":
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se cancelan cirugías programadas")
    if not db.execute(text("SELECT 1 FROM catalogo_causas_cancelacion WHERE id = :i"), {"i": datos.causa_id}).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Causa de cancelación inválida")
    ahora = datetime.now(timezone.utc)
    anticipacion = int((e.hora_programada_inicio - ahora).total_seconds() // 60) if e.hora_programada_inicio else None
    db.execute(text("""
        INSERT INTO cancelaciones (encuentro_id, causa_id, detalle, minutos_anticipacion, registrado_por, costo_estimado_cop)
        SELECT :e, :c, :d, :m, :u, cp.tarifa_referencia_cop * 0.3
        FROM encuentros en LEFT JOIN catalogo_procedimientos cp ON cp.id = en.procedimiento_id WHERE en.id = :e
    """), {"e": e.id, "c": datos.causa_id, "d": datos.detalle, "m": anticipacion, "u": ctx.usuario.id})
    e.estado, e.updated_at = "cancelled", ahora
    registrar(db, ctx.usuario, "encuentro", e.id, "update", valor_anterior={"estado": "planned"},
              valor_nuevo={"estado": "cancelled", "causa_id": datos.causa_id}, request=request)
    _evento(db, e, "planned", "cancelled", ctx.usuario, datos.detalle or "Cancelada")
    db.commit()
    return {"id": e.id, "estado": "cancelled"}
