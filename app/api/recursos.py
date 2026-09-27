"""Recursos físicos, sincronización FHIR, auditoría y analítica."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import ContextoAcceso, RequierePermiso, get_db
from app.models import (
    Cama, Encuentro, EventoEstado, LogAuditoria, Observacion, Paciente,
    Personal, Quirofano,
)
from app.services import fhir as fhir_svc
from app.services.auditoria import registrar

router = APIRouter(tags=["Recursos y operación"])

ESTADOS_CAMA = ["disponible", "reservada", "ocupada", "en_proceso_alta",
                "en_limpieza", "bloqueada", "contaminada", "aislamiento"]
ESTADOS_QX = ["disponible", "en_preparacion", "en_cirugia", "en_limpieza", "bloqueado"]


class CambioEstado(BaseModel):
    estado: str
    motivo: str | None = None


def _subtipo_de(entidad_tipo: str, obj) -> str | None:
    """
    Calcula el subtipo real del recurso, para que quede visible en la tabla
    de eventos sin tener que cruzar con camas/quirofanos cada vez.
    """
    if entidad_tipo == "cama":
        return obj.tipo_cama.codigo if obj.tipo_cama else None
    if entidad_tipo == "quirofano":
        if getattr(obj, "tiene_circulacion_extracorporea", False):
            return "CARDIOVASCULAR"
        if getattr(obj, "tiene_arco_c", False):
            return "CON_ARCO_C"
        return "GENERAL"
    return None


def _registrar_evento(db, entidad_tipo, obj, nuevo, usuario, motivo):
    """Guarda el cambio en eventos_estado con la duración del estado anterior."""
    ahora = datetime.now(timezone.utc)
    duracion = None
    if obj.estado_desde:
        duracion = int((ahora - obj.estado_desde).total_seconds() // 60)
    db.add(EventoEstado(
        entidad_tipo=entidad_tipo, entidad_id=obj.id,
        entidad_subtipo=_subtipo_de(entidad_tipo, obj),
        estado_anterior=obj.estado, estado_nuevo=nuevo,
        duracion_estado_anterior_min=duracion,
        motivo=motivo, usuario_id=usuario.id, origen="manual",
    ))
    obj.estado = nuevo
    obj.estado_desde = ahora


# ------------------------------------------------------------------- camas
@router.get("/camas", summary="Listar camas")
def listar_camas(ctx: ContextoAcceso = Depends(RequierePermiso("cama", "read")),
                 db: Session = Depends(get_db),
                 estado: str | None = None, tipo: str | None = None,
                 limite: int = Query(100, le=400)):
    q = db.query(Cama).filter(Cama.activo.is_(True))
    if estado:
        q = q.filter(Cama.estado == estado)
    camas = q.order_by(Cama.id).limit(limite).all()
    if tipo:
        camas = [c for c in camas if c.tipo_cama and c.tipo_cama.codigo == tipo]
    return [{
        "id": c.id, "codigo": c.codigo, "estado": c.estado,
        "tipo": c.tipo_cama.codigo if c.tipo_cama else None,
        "servicio": c.servicio.nombre if c.servicio else None,
        "estado_desde": c.estado_desde,
        "fhir_location_id": c.fhir_location_id,
    } for c in camas]


@router.get("/camas/ocupacion", summary="Qué paciente ocupa cada cama, desde cuándo")
def ocupacion_camas(ctx: ContextoAcceso = Depends(RequierePermiso("cama", "read")),
                    db: Session = Depends(get_db),
                    solo_ocupadas: bool = Query(True)):
    """
    Responde directamente "¿quién está en la cama X, desde cuándo, y en qué
    va su cirugía?" -- cruzando camas + encuentros + pacientes en una sola
    consulta, en vez de tener que hacerlo a mano.
    """
    from app.core.crypto import descifrar

    filas = db.execute(text("SELECT * FROM v_camas_ocupacion_detalle")).mappings().all()
    resultado = []
    for f in filas:
        if solo_ocupadas and f["estado_cama"] != "ocupada":
            continue
        item = dict(f)
        if item["paciente_id"]:
            p = db.query(Paciente).filter(
                Paciente.documento_bidx == item["paciente_id"]).first()
            item["paciente_documento"] = (
                descifrar(p.documento_cifrado, "pacientes.documento") if p else None
            )
        else:
            item["paciente_documento"] = None
        resultado.append(item)
    return resultado


@router.patch("/camas/{cama_id}/estado", summary="Cambiar estado de una cama")
def cambiar_estado_cama(cama_id: int, datos: CambioEstado, request: Request,
                        ctx: ContextoAcceso = Depends(RequierePermiso("cama", "update")),
                        db: Session = Depends(get_db)):
    if datos.estado not in ESTADOS_CAMA:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Estado inválido. Válidos: {ESTADOS_CAMA}")
    c = db.query(Cama).filter(Cama.id == cama_id, Cama.activo.is_(True)).first()
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cama no encontrada")

    anterior = c.estado
    _registrar_evento(db, "cama", c, datos.estado, ctx.usuario, datos.motivo)
    registrar(db, ctx.usuario, "cama", c.id, "update",
              valor_anterior={"estado": anterior},
              valor_nuevo={"estado": datos.estado}, request=request)
    db.commit()
    codigo_fhir, display = fhir_svc.ESTADO_LOCATION.get(datos.estado, ("U", "Unoccupied"))
    return {"id": c.id, "codigo": c.codigo,
            "estado_anterior": anterior, "estado_nuevo": c.estado,
            "fhir_operational_status": {"code": codigo_fhir, "display": display}}


# --------------------------------------------------------------- quirófanos
@router.get("/quirofanos", summary="Listar quirófanos")
def listar_quirofanos(ctx: ContextoAcceso = Depends(RequierePermiso("quirofano", "read")),
                      db: Session = Depends(get_db), estado: str | None = None):
    q = db.query(Quirofano).filter(Quirofano.activo.is_(True))
    if estado:
        q = q.filter(Quirofano.estado == estado)
    return [{
        "id": x.id, "codigo": x.codigo, "nombre": x.nombre, "estado": x.estado,
        "estado_desde": x.estado_desde, "tiene_arco_c": x.tiene_arco_c,
        "fhir_location_id": x.fhir_location_id,
    } for x in q.order_by(Quirofano.id).all()]


@router.patch("/quirofanos/{quirofano_id}/estado",
              summary="Cambiar estado de un quirófano")
def cambiar_estado_quirofano(quirofano_id: int, datos: CambioEstado, request: Request,
                             ctx: ContextoAcceso = Depends(RequierePermiso("quirofano", "update")),
                             db: Session = Depends(get_db)):
    if datos.estado not in ESTADOS_QX:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Estado inválido. Válidos: {ESTADOS_QX}")
    q = db.query(Quirofano).filter(Quirofano.id == quirofano_id,
                                   Quirofano.activo.is_(True)).first()
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quirófano no encontrado")

    anterior = q.estado
    _registrar_evento(db, "quirofano", q, datos.estado, ctx.usuario, datos.motivo)
    registrar(db, ctx.usuario, "quirofano", q.id, "update",
              valor_anterior={"estado": anterior},
              valor_nuevo={"estado": datos.estado}, request=request)
    db.commit()
    codigo_fhir, display = fhir_svc.ESTADO_LOCATION.get(datos.estado, ("U", "Unoccupied"))
    return {"id": q.id, "codigo": q.codigo,
            "estado_anterior": anterior, "estado_nuevo": q.estado,
            "fhir_operational_status": {"code": codigo_fhir, "display": display}}


# =========================================================== INTEROPERABILIDAD
fhir_router = APIRouter(prefix="/fhir", tags=["Interoperabilidad FHIR"])


@fhir_router.get("/preview/paciente/{paciente_id}",
                 summary="Previsualizar recurso Patient (sin enviar a HAPI)")
def preview_paciente(paciente_id: str,
                     ctx: ContextoAcceso = Depends(RequierePermiso("fhir", "read")),
                     db: Session = Depends(get_db)):
    p = db.query(Paciente).filter(Paciente.documento_bidx == paciente_id,
                                  Paciente.activo.is_(True)).first()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    return fhir_svc.paciente_a_fhir(p)


@fhir_router.get("/preview/cama/{cama_id}",
                 summary="Previsualizar recurso Location de una cama")
def preview_cama(cama_id: int,
                 ctx: ContextoAcceso = Depends(RequierePermiso("fhir", "read")),
                 db: Session = Depends(get_db)):
    c = db.query(Cama).filter(Cama.id == cama_id).first()
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cama no encontrada")
    return fhir_svc.cama_a_fhir(c)


@fhir_router.post("/sync/paciente/{paciente_id}",
                  summary="Sincronizar Patient hacia HAPI FHIR")
def sync_paciente(paciente_id: str, request: Request,
                  ctx: ContextoAcceso = Depends(RequierePermiso("fhir", "sync")),
                  db: Session = Depends(get_db)):
    p = db.query(Paciente).filter(Paciente.documento_bidx == paciente_id,
                                  Paciente.activo.is_(True)).first()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")

    recurso = fhir_svc.paciente_a_fhir(p)
    cliente = fhir_svc.ClienteFHIR()
    try:
        if p.fhir_patient_id:
            resultado = cliente.actualizar("Patient", p.fhir_patient_id, recurso)
        else:
            resultado = cliente.crear("Patient", recurso)
            p.fhir_patient_id = resultado.get("id")
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Error comunicando con el servidor FHIR: {e}")

    registrar(db, ctx.usuario, "paciente", p.id, "update",
              valor_nuevo={"fhir_patient_id": p.fhir_patient_id}, request=request)
    db.commit()
    return {"paciente_id": p.id, "fhir_patient_id": p.fhir_patient_id,
            "recurso": resultado}


@fhir_router.post("/sync/encuentro/{encuentro_id}",
                  summary="Sincronizar Encounter hacia HAPI FHIR")
def sync_encuentro(encuentro_id: int, request: Request,
                   ctx: ContextoAcceso = Depends(RequierePermiso("fhir", "sync")),
                   db: Session = Depends(get_db)):
    e = db.query(Encuentro).filter(Encuentro.id == encuentro_id,
                                   Encuentro.activo.is_(True)).first()
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encuentro no encontrado")

    paciente = db.query(Paciente).get(e.paciente_id)
    if paciente and not paciente.fhir_patient_id:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Sincronice primero el paciente asociado")

    recurso = fhir_svc.encuentro_a_fhir(e, paciente.fhir_patient_id if paciente else None)
    cliente = fhir_svc.ClienteFHIR()
    try:
        if e.fhir_encounter_id:
            resultado = cliente.actualizar("Encounter", e.fhir_encounter_id, recurso)
        else:
            resultado = cliente.crear("Encounter", recurso)
            e.fhir_encounter_id = resultado.get("id")
    except Exception as ex:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Error FHIR: {ex}")

    db.commit()
    return {"encuentro_id": e.id, "fhir_encounter_id": e.fhir_encounter_id,
            "recurso": resultado}


@fhir_router.post("/sync/observacion/{observacion_id}",
                  summary="Sincronizar Observation hacia HAPI FHIR")
def sync_observacion(observacion_id: int,
                     ctx: ContextoAcceso = Depends(RequierePermiso("fhir", "sync")),
                     db: Session = Depends(get_db)):
    o = db.query(Observacion).filter(Observacion.id == observacion_id,
                                     Observacion.activo.is_(True)).first()
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Observación no encontrada")

    paciente = db.query(Paciente).get(o.paciente_id)
    encuentro = db.query(Encuentro).get(o.encuentro_id)
    recurso = fhir_svc.observacion_a_fhir(
        o,
        paciente.fhir_patient_id if paciente else None,
        encuentro.fhir_encounter_id if encuentro else None,
    )
    cliente = fhir_svc.ClienteFHIR()
    try:
        resultado = cliente.crear("Observation", recurso)
        o.fhir_observation_id = resultado.get("id")
    except Exception as ex:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Error FHIR: {ex}")
    db.commit()
    return {"observacion_id": o.id, "fhir_observation_id": o.fhir_observation_id,
            "recurso": resultado}


@fhir_router.post("/sync/cama/{cama_id}",
                  summary="Sincronizar Location (estado de cama) hacia HAPI")
def sync_cama(cama_id: int,
              ctx: ContextoAcceso = Depends(RequierePermiso("fhir", "sync")),
              db: Session = Depends(get_db)):
    """
    Diferenciador de esta propuesta: el estado operativo de la cama se
    publica como Location.operationalStatus, usando el value set estándar
    HL7 v2-0116 que FHIR ya define para este propósito.
    """
    c = db.query(Cama).filter(Cama.id == cama_id).first()
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cama no encontrada")

    recurso = fhir_svc.cama_a_fhir(c)
    cliente = fhir_svc.ClienteFHIR()
    try:
        if c.fhir_location_id:
            resultado = cliente.actualizar("Location", c.fhir_location_id, recurso)
        else:
            resultado = cliente.crear("Location", recurso)
            c.fhir_location_id = resultado.get("id")
    except Exception as ex:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Error FHIR: {ex}")
    db.commit()
    return {"cama_id": c.id, "estado": c.estado,
            "fhir_location_id": c.fhir_location_id, "recurso": resultado}


@fhir_router.post("/sync/bundle/paciente/{paciente_id}",
                  summary="Sincronización atómica con Bundle transaccional")
def sync_bundle(paciente_id: str,
                ctx: ContextoAcceso = Depends(RequierePermiso("fhir", "sync")),
                db: Session = Depends(get_db)):
    """Envía Patient + sus Encounters + Observations en una sola transacción FHIR."""
    p = db.query(Paciente).filter(Paciente.documento_bidx == paciente_id,
                                  Paciente.activo.is_(True)).first()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")

    entradas = [{
        "fullUrl": f"urn:uuid:paciente-{p.id}",
        "resource": fhir_svc.paciente_a_fhir(p),
        "request": {"method": "POST", "url": "Patient"},
    }]
    encuentros = (db.query(Encuentro)
                  .filter(Encuentro.paciente_id == p.id, Encuentro.activo.is_(True))
                  .limit(5).all())
    for e in encuentros:
        rec = fhir_svc.encuentro_a_fhir(e)
        rec["subject"] = {"reference": f"urn:uuid:paciente-{p.id}"}
        entradas.append({
            "fullUrl": f"urn:uuid:encuentro-{e.id}",
            "resource": rec,
            "request": {"method": "POST", "url": "Encounter"},
        })

    try:
        resultado = fhir_svc.ClienteFHIR().transaccion(entradas)
    except Exception as ex:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Error FHIR: {ex}")
    return {"recursos_enviados": len(entradas), "respuesta": resultado}


@fhir_router.get("/Patient/{fhir_id}", summary="Consultar Patient en HAPI")
def leer_patient(fhir_id: str,
                 ctx: ContextoAcceso = Depends(RequierePermiso("fhir", "read"))):
    try:
        return fhir_svc.ClienteFHIR().leer("Patient", fhir_id)
    except Exception as ex:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Error FHIR: {ex}")


@fhir_router.get("/buscar/{tipo}", summary="Búsqueda parametrizada en HAPI")
def buscar_fhir(tipo: str, request: Request,
                ctx: ContextoAcceso = Depends(RequierePermiso("fhir", "read"))):
    """Ej: /fhir/buscar/Encounter?status=finished&_count=5"""
    params = {k: v for k, v in request.query_params.items()}
    try:
        return fhir_svc.ClienteFHIR().buscar(tipo, **params)
    except Exception as ex:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Error FHIR: {ex}")


@fhir_router.get("/{tipo}/{fhir_id}/_history",
                 summary="Historial de versiones de un recurso (FHIR nativo)")
def historial_fhir(tipo: str, fhir_id: str,
                   ctx: ContextoAcceso = Depends(RequierePermiso("fhir", "read"))):
    try:
        return fhir_svc.ClienteFHIR().historial(tipo, fhir_id)
    except Exception as ex:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Error FHIR: {ex}")


# ================================================================= AUDITORÍA
audit_router = APIRouter(prefix="/auditoria", tags=["Auditoría"])


@audit_router.get("", summary="Consultar el log de auditoría")
def listar_auditoria(ctx: ContextoAcceso = Depends(RequierePermiso("auditoria", "read")),
                     db: Session = Depends(get_db),
                     entidad_tipo: str | None = None,
                     operacion: str | None = None,
                     usuario_id: int | None = None,
                     limite: int = Query(50, le=500)):
    q = db.query(LogAuditoria)
    if entidad_tipo:
        q = q.filter(LogAuditoria.entidad_tipo == entidad_tipo)
    if operacion:
        q = q.filter(LogAuditoria.operacion == operacion)
    if usuario_id:
        q = q.filter(LogAuditoria.usuario_id == usuario_id)
    filas = q.order_by(LogAuditoria.timestamp.desc()).limit(limite).all()
    return [{
        "id": f.id, "usuario_id": f.usuario_id, "rol": f.rol_codigo,
        "entidad": f.entidad_tipo, "entidad_id": f.entidad_id,
        "operacion": f.operacion, "resultado": f.resultado,
        "endpoint": f.endpoint, "ip": str(f.ip_origen) if f.ip_origen else None,
        "timestamp": f.timestamp,
    } for f in filas]


@audit_router.get("/fhir/AuditEvent",
                  summary="Log de auditoría expuesto como recurso FHIR AuditEvent")
def auditoria_fhir(ctx: ContextoAcceso = Depends(RequierePermiso("auditoria", "read")),
                   db: Session = Depends(get_db),
                   limite: int = Query(20, le=100)):
    filas = db.query(LogAuditoria).order_by(LogAuditoria.timestamp.desc()).limit(limite).all()
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(filas),
        "entry": [{"resource": fhir_svc.auditoria_a_fhir(f)} for f in filas],
    }


# ================================================================= ANALÍTICA
analitica_router = APIRouter(prefix="/analitica", tags=["Analítica y caso de negocio"])


@analitica_router.get("/ocupacion", summary="Ocupación actual por tipo de cama")
def ocupacion(ctx: ContextoAcceso = Depends(RequierePermiso("analitica", "read")),
              db: Session = Depends(get_db)):
    filas = db.execute(text("SELECT * FROM v_ocupacion_camas")).mappings().all()
    return [dict(f) for f in filas]


@analitica_router.get("/cancelaciones", summary="Indicador de cancelación (Res. 256/2016)")
def cancelaciones(ctx: ContextoAcceso = Depends(RequierePermiso("analitica", "read")),
                  db: Session = Depends(get_db)):
    filas = db.execute(text("SELECT * FROM v_indicador_cancelacion LIMIT 12")).mappings().all()
    return [dict(f) for f in filas]


@analitica_router.get("/costo-ociosidad",
                      summary="Costo de oportunidad por camas ociosas")
def costo_ociosidad(ctx: ContextoAcceso = Depends(RequierePermiso("analitica", "read")),
                    db: Session = Depends(get_db)):
    """
    Traduce la ineficiencia de coordinación a pesos.
    Base: costo diario de la cama / 24 x horas en estado 'disponible'
    mientras existía demanda.
    """
    filas = db.execute(text("SELECT * FROM v_horas_ociosas_camas LIMIT 12")).mappings().all()
    datos = [dict(f) for f in filas]
    total = sum(float(d.get("costo_oportunidad_cop") or 0) for d in datos)
    return {"detalle": datos, "costo_total_cop": round(total, 2)}


@analitica_router.get("/gastos", summary="Gasto acumulado por paciente")
def gastos_paciente(ctx: ContextoAcceso = Depends(RequierePermiso("analitica", "read")),
                    db: Session = Depends(get_db),
                    paciente_id: str | None = Query(
                        None, description="documento_bidx de un paciente específico"),
                    limite: int = Query(20, le=200)):
    """
    Gasto = tarifa de los procedimientos ya realizados + costo estimado de
    las horas de cama ocupadas. NO incluye el costo de cancelaciones (eso es
    pérdida de la institución, no un cargo al paciente -- ver /analitica/costo-ociosidad).

    Sin paciente_id: devuelve el ranking de los que más han gastado.
    Con paciente_id: el desglose de ese paciente en particular.
    """
    if paciente_id:
        fila = db.execute(
            text("SELECT * FROM v_gastos_paciente WHERE paciente_id = :pid"),
            {"pid": paciente_id},
        ).mappings().first()
        if fila is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                "Paciente no encontrado o sin gasto registrado")
        return dict(fila)

    filas = db.execute(
        text("SELECT * FROM v_gastos_paciente ORDER BY gasto_total_cop DESC LIMIT :lim"),
        {"lim": limite},
    ).mappings().all()
    return [dict(f) for f in filas]


@analitica_router.get("/desviacion-quirurgica",
                      summary="Desviación programado vs. real (insumo del modelo)")
def desviacion(ctx: ContextoAcceso = Depends(RequierePermiso("analitica", "read")),
               db: Session = Depends(get_db)):
    filas = db.execute(text("SELECT * FROM v_desviacion_quirurgica LIMIT 25")).mappings().all()
    return [dict(f) for f in filas]