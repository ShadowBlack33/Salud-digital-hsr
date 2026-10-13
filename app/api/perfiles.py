"""
Vistas por perfil: cada rol recibe SOLO lo que necesita para su trabajo.

  /mis-pacientes        médico y especialista: sus pacientes, dónde están,
                        si tienen valores críticos y si están en cirugía.
  /mis-cirugias         especialista (y médico): cirugías de sus pacientes
                        y las que él tiene asignadas, con el papel que cumple.
  /analitica/hospital   coordinador del hospital: capacidad por área,
                        riesgo de colapso, dinero y desempeño. Sin pacientes.

La coordinación quirúrgica (programar y mover cirugías) está en cirugias.py.
"""
from __future__ import annotations

import os

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.crypto import descifrar, enmascarar
from app.core.deps import ContextoAcceso, RequierePermiso, get_db
from app.models import Paciente, Personal

router = APIRouter(tags=["Vistas por perfil"])

ACTIVOS = ("planned", "arrived", "triaged", "in-progress", "onleave")
TIPO_COBERTURA = {"contributivo": "eps", "subsidiado": "eps", "especial": "especial"}


# ------------------------------------------------------------------ utilidades
def edad(nacimiento: date | None) -> int | None:
    if not nacimiento:
        return None
    hoy = date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def cobertura(eps_codigo: str | None, eps_nombre: str | None, regimen: str | None) -> dict:
    """Particular o la entidad que responde por el paciente."""
    if not eps_codigo or eps_codigo == "PART":
        return {"tipo": "particular", "entidad": "Particular", "regimen": None}
    return {"tipo": TIPO_COBERTURA.get(regimen or "", "eps"), "entidad": eps_nombre, "regimen": regimen}


class Nombres:
    """Descifra nombres de personal una sola vez por petición."""
    def __init__(self, db: Session):
        self.db, self.cache = db, {}

    def __call__(self, personal_id: int | None) -> str | None:
        if personal_id is None:
            return None
        if personal_id not in self.cache:
            m = self.db.get(Personal, personal_id)
            self.cache[personal_id] = (
                f"{descifrar(m.nombre_cifrado, 'personal.nombre')} "
                f"{descifrar(m.apellido_cifrado, 'personal.apellido')}") if m else None
        return self.cache[personal_id]


def _pacientes_por_id(db: Session, ids) -> dict[str, Paciente]:
    ids = list(ids)
    if not ids:
        return {}
    return {p.documento_bidx: p for p in db.query(Paciente).filter(Paciente.documento_bidx.in_(ids)).all()}


def _ids_mis_pacientes(ctx: ContextoAcceso, limite: int) -> list[str]:
    """Los pacientes del usuario. Para roles con alcance total (enfermería
    jefe, admin), los que tienen un encuentro activo: no 4.000 historias."""
    if ctx.alcance_paciente() == "assigned":
        sub = ctx.pacientes_asignados_subq()
        filas = ctx.db.execute(
            select(Paciente.documento_bidx)
            .where(Paciente.activo.is_(True), Paciente.documento_bidx.in_(sub.select()))
            .limit(limite)).scalars().all()
        return list(filas)
    return list(ctx.db.execute(text(
        "SELECT DISTINCT paciente_id FROM encuentros WHERE activo AND estado = ANY(:act) LIMIT :lim"),
        {"act": list(ACTIVOS), "lim": limite}).scalars().all())


# ================================================================ MIS PACIENTES
@router.get("/mis-pacientes", summary="Mis pacientes, con ubicación, críticos y cirugía")
def mis_pacientes(ctx: ContextoAcceso = Depends(RequierePermiso("paciente", "read")),
                  db: Session = Depends(get_db), limite: int = Query(150, le=300)):
    ids = _ids_mis_pacientes(ctx, limite)
    if not ids:
        return {"pacientes": [], "total": 0}
    yo = ctx.payload.get("personal_id")
    nombres = Nombres(db)
    pacientes = _pacientes_por_id(db, ids)

    eps = {r["id"]: dict(r) for r in db.execute(text("SELECT id, codigo, nombre, regimen FROM eps")).mappings()}

    # Encuentros activos (dónde está y por qué) y cirugías de los próximos días.
    encuentros = db.execute(text("""
        SELECT e.id, e.paciente_id, e.tipo, e.estado, e.origen, e.nivel_triage, e.prioridad_clinica,
               e.medico_responsable_id, e.anestesiologo_id, e.quirofano_id,
               e.hora_programada_inicio, e.hora_real_inicio, e.hora_real_fin, e.created_at,
               cp.nombre AS procedimiento, dx.codigo AS dx_codigo, dx.descripcion AS diagnostico,
               c.codigo AS cama, tc.nombre AS tipo_cama, s.nombre AS servicio, q.codigo AS quirofano,
               q.estado AS quirofano_estado
        FROM encuentros e
        LEFT JOIN catalogo_procedimientos cp ON cp.id = e.procedimiento_id
        LEFT JOIN diagnosticos_cie10 dx ON dx.id = e.diagnostico_cie10_id
        LEFT JOIN camas c ON c.id = e.cama_id
        LEFT JOIN tipos_cama tc ON tc.id = c.tipo_cama_id
        LEFT JOIN servicios s ON s.id = c.servicio_id
        LEFT JOIN quirofanos q ON q.id = e.quirofano_id
        WHERE e.activo AND e.paciente_id = ANY(:ids)
          AND (e.estado = ANY(:act) OR e.created_at > NOW() - INTERVAL '30 days'
               OR e.hora_real_fin > NOW() - INTERVAL '30 days')
        ORDER BY COALESCE(e.hora_real_inicio, e.hora_programada_inicio, e.created_at) DESC
    """), {"ids": ids, "act": list(ACTIVOS)}).mappings().all()

    criticos = db.execute(text("""
        SELECT o.paciente_id, o.codigo_loinc, o.display_loinc, o.valor_numerico, o.valor_texto,
               o.unidad_ucum, o.fecha_hora
        FROM observaciones o
        WHERE o.activo AND o.es_critico AND o.paciente_id = ANY(:ids)
          AND o.fecha_hora > NOW() - INTERVAL '72 hours'
        ORDER BY o.fecha_hora DESC
    """), {"ids": ids}).mappings().all()

    por_pac: dict[str, dict] = {pid: {"activo": None, "cirugia": None, "ultimo": None} for pid in ids}
    for e in encuentros:
        d = por_pac[e["paciente_id"]]
        d["ultimo"] = d["ultimo"] or e
        if e["estado"] in ACTIVOS:
            if e["tipo"] == "cirugia":
                # La más próxima o la que está en curso.
                if d["cirugia"] is None or e["estado"] == "in-progress":
                    d["cirugia"] = e
            elif d["activo"] is None:
                d["activo"] = e
    crit: dict[str, list] = {}
    for o in criticos:
        crit.setdefault(o["paciente_id"], []).append({
            "codigo_loinc": o["codigo_loinc"], "nombre": o["display_loinc"],
            "valor": float(o["valor_numerico"]) if o["valor_numerico"] is not None else o["valor_texto"],
            "unidad": o["unidad_ucum"], "fecha": o["fecha_hora"]})

    # Remisiones de estos pacientes que me llegaron (o que yo envié).
    remisiones: dict[str, dict] = {}
    if yo is not None and db.execute(text("SELECT to_regclass('public.remisiones') IS NOT NULL")).scalar():
        for r in db.execute(text("""
            SELECT DISTINCT ON (paciente_id) paciente_id, id, medico_id, especialista_id, motivo, prioridad, estado, created_at
            FROM remisiones WHERE paciente_id = ANY(:ids) AND (especialista_id = :yo OR medico_id = :yo)
            ORDER BY paciente_id, created_at DESC
        """), {"ids": ids, "yo": yo}).mappings():
            remisiones[r["paciente_id"]] = dict(r)

    from app.services import pacs
    con_imagenes = pacs.pacientes_con_imagenes()

    resultado = []
    for pid in ids:
        p = pacientes.get(pid)
        if p is None:
            continue
        d, act, cx = por_pac[pid], por_pac[pid]["activo"], por_pac[pid]["cirugia"]
        e_ = eps.get(p.eps_id) or {}
        vinculo = "registrado" if p.created_by == ctx.usuario.id else None
        if yo is not None and any(x["paciente_id"] == pid and yo in (x["medico_responsable_id"], x["anestesiologo_id"])
                                  for x in encuentros):
            vinculo = "a_cargo"
        rem = remisiones.get(pid)
        if rem and rem["especialista_id"] == yo and vinculo != "a_cargo":
            vinculo = "remitido"
        vinculo = vinculo or "a_cargo"
        resultado.append({
            "paciente_id": pid,
            "nombre": descifrar(p.nombre_cifrado, "pacientes.nombre"),
            "apellido": descifrar(p.apellido_cifrado, "pacientes.apellido"),
            "tipo_documento": p.tipo_documento,
            "documento": enmascarar(descifrar(p.documento_cifrado, "pacientes.documento")),
            "edad": edad(p.fecha_nacimiento), "sexo": p.sexo,
            "cobertura": cobertura(e_.get("codigo"), e_.get("nombre"), e_.get("regimen")),
            "vinculo": vinculo,
            "encuentro": act and {
                "id": act["id"], "tipo": act["tipo"], "estado": act["estado"], "origen": act["origen"],
                "triage": act["nivel_triage"], "prioridad": act["prioridad_clinica"],
                "diagnostico": act["diagnostico"], "dx_codigo": act["dx_codigo"],
                "desde": act["hora_real_inicio"] or act["created_at"],
                "cama": act["cama"], "tipo_cama": act["tipo_cama"], "servicio": act["servicio"],
                "medico": nombres(act["medico_responsable_id"]),
                "soy_responsable": yo is not None and act["medico_responsable_id"] == yo},
            "cirugia": cx and {
                "id": cx["id"], "estado": cx["estado"], "procedimiento": cx["procedimiento"],
                "quirofano": cx["quirofano"], "quirofano_estado": cx["quirofano_estado"],
                "hora_programada_inicio": cx["hora_programada_inicio"], "hora_real_inicio": cx["hora_real_inicio"],
                "cirujano": nombres(cx["medico_responsable_id"]),
                "mi_papel": ("cirujano" if yo is not None and cx["medico_responsable_id"] == yo else
                             "anestesiologo" if yo is not None and cx["anestesiologo_id"] == yo else None)},
            "criticos": crit.get(pid, []),
            "tiene_imagenes": pid in con_imagenes,
            "remision": rem and {
                "id": rem["id"], "estado": rem["estado"], "prioridad": rem["prioridad"], "motivo": rem["motivo"],
                "fecha": rem["created_at"], "recibida": rem["especialista_id"] == yo,
                "de": nombres(rem["medico_id"]) if rem["especialista_id"] == yo else None,
                "para": nombres(rem["especialista_id"]) if rem["especialista_id"] != yo else None},
            "ultima_atencion": d["ultimo"] and (d["ultimo"]["hora_real_fin"] or d["ultimo"]["hora_real_inicio"]
                                                or d["ultimo"]["created_at"]),
        })

    # Primero lo urgente: críticos, en cirugía, hospitalizados; luego el resto.
    def prioridad(x):
        return (0 if x["criticos"] or (x["remision"] and x["remision"]["recibida"] and x["remision"]["estado"] == "pendiente") else 1,
                0 if x["cirugia"] and x["cirugia"]["estado"] == "in-progress" else 1,
                0 if x["encuentro"] else 1,
                -(x["ultima_atencion"].timestamp() if x["ultima_atencion"] else 0))
    resultado.sort(key=prioridad)
    return {"pacientes": resultado, "total": len(resultado)}


# ================================================================ MIS CIRUGÍAS
@router.get("/mis-cirugias", summary="Cirugías de mis pacientes y las que tengo asignadas")
def mis_cirugias(ctx: ContextoAcceso = Depends(RequierePermiso("encuentro", "read")),
                 db: Session = Depends(get_db), dias: int = Query(7, ge=1, le=30)):
    """
    Un especialista no necesita el tablero de 13 quirófanos: necesita saber si
    un paciente SUYO está en cirugía, cuándo, dónde y si él está asignado.
    """
    yo = ctx.payload.get("personal_id")
    ahora = datetime.now(timezone.utc)
    if ctx.alcance_paciente() == "assigned" or ctx.alcance == "assigned":
        sub = ctx.pacientes_asignados_subq()
        mios = db.execute(select(sub.c[0])).scalars().all()
    else:
        mios = []
    filas = db.execute(text("""
        SELECT e.id, e.paciente_id, e.estado, e.origen, e.prioridad_clinica,
               e.hora_programada_inicio, e.hora_programada_fin, e.hora_real_inicio, e.hora_real_fin,
               e.medico_responsable_id, e.anestesiologo_id,
               cp.nombre AS procedimiento, cp.duracion_estimada_min, esp.nombre AS especialidad,
               q.codigo AS quirofano, q.estado AS quirofano_estado,
               c.codigo AS cama_destino, tc.nombre AS cama_destino_tipo
        FROM encuentros e
        LEFT JOIN catalogo_procedimientos cp ON cp.id = e.procedimiento_id
        LEFT JOIN especialidades esp ON esp.id = cp.especialidad_id
        LEFT JOIN quirofanos q ON q.id = e.quirofano_id
        LEFT JOIN camas c ON c.id = e.cama_id
        LEFT JOIN tipos_cama tc ON tc.id = c.tipo_cama_id
        WHERE e.activo AND e.tipo = 'cirugia'
          AND (e.medico_responsable_id = :yo OR e.anestesiologo_id = :yo OR e.paciente_id = ANY(:mios))
          AND (e.estado = 'in-progress'
               OR (e.estado = 'planned' AND e.hora_programada_inicio BETWEEN :desde AND :hasta)
               OR (e.estado = 'finished' AND e.hora_real_fin > :hoy))
        ORDER BY CASE e.estado WHEN 'in-progress' THEN 0 WHEN 'planned' THEN 1 ELSE 2 END,
                 e.hora_programada_inicio
    """), {"yo": yo if yo is not None else -1, "mios": list(mios),
           "desde": ahora - timedelta(hours=2), "hasta": ahora + timedelta(days=dias),
           "hoy": ahora - timedelta(hours=18)}).mappings().all()

    pacientes = _pacientes_por_id(db, {f["paciente_id"] for f in filas})
    nombres = Nombres(db)
    salida = []
    for f in filas:
        p = pacientes.get(f["paciente_id"])
        papel = ("cirujano" if f["medico_responsable_id"] == yo else
                 "anestesiologo" if f["anestesiologo_id"] == yo else None)
        retraso = None
        if f["hora_real_inicio"] and f["hora_programada_inicio"]:
            retraso = int((f["hora_real_inicio"] - f["hora_programada_inicio"]).total_seconds() // 60)
        salida.append({
            "id": f["id"], "estado": f["estado"], "origen": f["origen"], "prioridad": f["prioridad_clinica"],
            "paciente_id": f["paciente_id"],
            "paciente": p and f"{descifrar(p.nombre_cifrado, 'pacientes.nombre')} {descifrar(p.apellido_cifrado, 'pacientes.apellido')}",
            "es_mi_paciente": f["paciente_id"] in mios,
            "mi_papel": papel,
            "procedimiento": f["procedimiento"], "especialidad": f["especialidad"],
            "duracion_estimada_min": f["duracion_estimada_min"],
            "quirofano": f["quirofano"], "quirofano_estado": f["quirofano_estado"],
            "hora_programada_inicio": f["hora_programada_inicio"], "hora_programada_fin": f["hora_programada_fin"],
            "hora_real_inicio": f["hora_real_inicio"], "hora_real_fin": f["hora_real_fin"],
            "retraso_inicio_min": retraso,
            "cirujano": nombres(f["medico_responsable_id"]),
            "anestesiologo": nombres(f["anestesiologo_id"]),
            "cama_destino": f["cama_destino"], "cama_destino_tipo": f["cama_destino_tipo"],
        })
    return {"ahora": ahora.isoformat(), "cirugias": salida}


# Supuesto del escenario de ocupación: fracción de las altas en proceso que se
# completan en las próximas 12 h. Regla configurable, no un dato medido.
FRACCION_ALTAS_12H = float(os.getenv("FRACCION_ALTAS_12H", "0.7"))


# ============================================================ TABLERO DEL HOSPITAL
@router.get("/analitica/hospital", summary="Cómo va el hospital: capacidad, riesgo, dinero, IA")
def tablero_hospital(ctx: ContextoAcceso = Depends(RequierePermiso("analitica", "read")),
                     db: Session = Depends(get_db)):
    """
    Lo que mira el coordinador del hospital. Todo es agregado: no aparece
    ningún paciente. La "ocupación proyectada" de cada área es un escenario
    con reglas configurables (no un modelo validado): ocupación actual + las
    cirugías de las próximas 12 horas que necesitan cama de ese tipo - la
    fracción de altas en proceso que se espera completar (FRACCION_ALTAS_12H).
    Una cama en alta en proceso sigue ocupada hasta que el paciente sale.
    Bandas: >= 100 % saturada, >= 90 % alta, >= 80 % vigilar.
    """
    ahora = datetime.now(timezone.utc)

    areas = [dict(r) for r in db.execute(text("""
        SELECT s.codigo, s.nombre AS area, tc.codigo AS tipo_cama, tc.nombre AS tipo_nombre,
               tc.costo_dia_cop,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE c.estado = 'ocupada') AS ocupadas,
               COUNT(*) FILTER (WHERE c.estado = 'reservada') AS reservadas,
               COUNT(*) FILTER (WHERE c.estado = 'disponible') AS disponibles,
               COUNT(*) FILTER (WHERE c.estado = 'en_proceso_alta') AS en_alta,
               COUNT(*) FILTER (WHERE c.estado = 'en_limpieza') AS en_limpieza,
               COUNT(*) FILTER (WHERE c.estado IN ('bloqueada','contaminada','aislamiento')) AS fuera_servicio,
               COALESCE(SUM(EXTRACT(EPOCH FROM (NOW() - c.estado_desde)) / 3600.0)
                        FILTER (WHERE c.estado = 'disponible'), 0) AS horas_ociosas_ahora
        FROM camas c JOIN servicios s ON s.id = c.servicio_id JOIN tipos_cama tc ON tc.id = c.tipo_cama_id
        WHERE c.activo
        GROUP BY s.codigo, s.nombre, tc.codigo, tc.nombre, tc.costo_dia_cop
        ORDER BY s.nombre
    """)).mappings()]

    demanda = {r["tipo"]: r["n"] for r in db.execute(text("""
        SELECT tc.codigo AS tipo, COUNT(*) AS n
        FROM encuentros e
        JOIN catalogo_procedimientos cp ON cp.id = e.procedimiento_id
        JOIN tipos_cama tc ON tc.id = cp.tipo_cama_requerida_id
        WHERE e.activo AND e.tipo = 'cirugia' AND e.estado = 'planned'
          AND e.hora_programada_inicio BETWEEN NOW() AND NOW() + INTERVAL '12 hours'
        GROUP BY tc.codigo
    """)).mappings()}
    # La demanda de un tipo de cama se reparte entre las áreas que lo tienen.
    areas_por_tipo: dict[str, int] = {}
    for a in areas:
        areas_por_tipo[a["tipo_cama"]] = areas_por_tipo.get(a["tipo_cama"], 0) + 1

    for a in areas:
        utiles = max(a["total"] - a["fuera_servicio"], 1)
        # La cama en alta en proceso todavía tiene paciente: cuenta como ocupada.
        ocupadas_hoy = a["ocupadas"] + a["reservadas"] + a["en_alta"]
        a["pct_ocupacion"] = round(100 * ocupadas_hoy / utiles, 1)
        a["demanda_12h"] = round(demanda.get(a["tipo_cama"], 0) / areas_por_tipo[a["tipo_cama"]])
        # Escenario: lo ocupado + lo que llega - las altas que se espera completar.
        proyectadas = ocupadas_hoy + a["demanda_12h"] - a["en_alta"] * FRACCION_ALTAS_12H
        a["pct_proyectado_12h"] = round(100 * proyectadas / utiles, 1)
        p = max(a["pct_ocupacion"], a["pct_proyectado_12h"])
        a["riesgo"] = "colapso" if p >= 100 else "alto" if p >= 90 else "medio" if p >= 80 else "bajo"
        a["costo_ocioso_hoy_cop"] = round(float(a.pop("horas_ociosas_ahora")) * float(a["costo_dia_cop"] or 0) / 24)
        a["costo_dia_cop"] = float(a["costo_dia_cop"] or 0)

    qx = dict(db.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE estado = 'en_cirugia') AS en_cirugia,
               COUNT(*) FILTER (WHERE estado = 'disponible') AS disponibles,
               COUNT(*) FILTER (WHERE estado IN ('en_preparacion','en_limpieza')) AS en_rotacion,
               COUNT(*) FILTER (WHERE estado = 'bloqueado') AS bloqueados
        FROM quirofanos WHERE activo
    """)).mappings().first())
    cirugias_hoy = dict(db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE estado = 'finished') AS terminadas,
               COUNT(*) FILTER (WHERE estado = 'in-progress') AS en_curso,
               COUNT(*) FILTER (WHERE estado = 'planned') AS pendientes,
               COUNT(*) FILTER (WHERE estado = 'cancelled') AS canceladas,
               COUNT(*) FILTER (WHERE origen = 'urgencia') AS urgencias,
               ROUND(AVG(EXTRACT(EPOCH FROM (hora_real_inicio - hora_programada_inicio)) / 60)
                     FILTER (WHERE hora_real_inicio IS NOT NULL))::INT AS retraso_promedio_min
        FROM encuentros
        WHERE activo AND tipo = 'cirugia'
          AND COALESCE(hora_real_inicio, hora_programada_inicio) >= date_trunc('day', NOW())
          AND COALESCE(hora_real_inicio, hora_programada_inicio) <  date_trunc('day', NOW()) + INTERVAL '1 day'
    """)).mappings().first())

    urgencias = dict(db.execute(text("""
        SELECT COUNT(*) AS en_espera,
               COUNT(*) FILTER (WHERE nivel_triage <= 2) AS triage_1_2,
               ROUND(AVG(EXTRACT(EPOCH FROM (NOW() - COALESCE(hora_real_inicio, created_at))) / 60))::INT AS espera_promedio_min
        FROM encuentros WHERE activo AND tipo = 'urgencias' AND estado = ANY(:act)
    """), {"act": list(ACTIVOS)}).mappings().first())

    # Dinero del mes: lo producido (procedimientos terminados + estancia) y lo
    # perdido (horas de cama ociosa y cirugías canceladas).
    dinero = dict(db.execute(text("""
        WITH proc AS (
            SELECT COALESCE(SUM(cp.tarifa_referencia_cop), 0) AS v
            FROM encuentros e JOIN catalogo_procedimientos cp ON cp.id = e.procedimiento_id
            WHERE e.activo AND e.estado = 'finished' AND e.hora_real_fin >= date_trunc('month', NOW())),
        canc AS (
            SELECT COUNT(*) AS n, COALESCE(SUM(COALESCE(ca.costo_estimado_cop, cp.tarifa_referencia_cop * 0.3)), 0) AS v
            FROM cancelaciones ca JOIN encuentros e ON e.id = ca.encuentro_id
            LEFT JOIN catalogo_procedimientos cp ON cp.id = e.procedimiento_id
            WHERE ca.created_at >= date_trunc('month', NOW())),
        ocio AS (
            SELECT COALESCE(SUM(costo_oportunidad_cop), 0) AS v FROM v_horas_ociosas_camas
            WHERE mes = date_trunc('month', NOW()))
        SELECT proc.v AS producido_procedimientos_cop, canc.n AS cancelaciones_mes,
               canc.v AS perdida_cancelaciones_cop, ocio.v AS perdida_camas_ociosas_cop
        FROM proc, canc, ocio
    """)).mappings().first())
    estancia_hoy = db.execute(text("""
        SELECT COALESCE(SUM(tc.costo_dia_cop), 0) FROM camas c JOIN tipos_cama tc ON tc.id = c.tipo_cama_id
        WHERE c.activo AND c.estado = 'ocupada'
    """)).scalar()
    cirugias_hoy_cop = db.execute(text("""
        SELECT COALESCE(SUM(cp.tarifa_referencia_cop), 0)
        FROM encuentros e JOIN catalogo_procedimientos cp ON cp.id = e.procedimiento_id
        WHERE e.activo AND e.tipo = 'cirugia' AND e.estado IN ('in-progress', 'finished')
          AND e.hora_real_inicio >= date_trunc('day', NOW())
    """)).scalar()
    dinero = {k: float(v or 0) for k, v in dinero.items()}
    dinero["cirugias_hoy_cop"] = float(cirugias_hoy_cop or 0)
    dinero["estancia_dia_actual_cop"] = float(estancia_hoy or 0)
    dinero["perdida_ociosa_hoy_cop"] = sum(a["costo_ocioso_hoy_cop"] for a in areas)

    # Desempeño de los modelos: tabla `predicciones` del Corte 1 (valor real vs
    # predicho) y, si ya existe, la de reportes de IA del Corte 2.
    ia = {"modelos": [], "reportes": None}
    for r in db.execute(text("""
        SELECT modelo, COUNT(*) AS n,
               COUNT(*) FILTER (WHERE valor_real IS NOT NULL) AS evaluadas,
               ROUND(AVG(ABS(valor_predicho - valor_real)) FILTER (WHERE valor_real IS NOT NULL), 1) AS error_medio
        FROM predicciones WHERE created_at > NOW() - INTERVAL '30 days' GROUP BY modelo
    """)).mappings():
        ia["modelos"].append({k: (float(v) if hasattr(v, "is_finite") else v) for k, v in dict(r).items()})
    if db.execute(text("SELECT to_regclass('public.reportes_ia') IS NOT NULL")).scalar():
        try:
            ia["reportes"] = dict(db.execute(text("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE estado = 'pendiente') AS pendientes,
                       COUNT(*) FILTER (WHERE estado = 'aprobado') AS aprobados,
                       COUNT(*) FILTER (WHERE estado = 'rechazado') AS rechazados
                FROM reportes_ia WHERE created_at > NOW() - INTERVAL '30 days'
            """)).mappings().first())
        except Exception:  # noqa: BLE001 -- la tabla es de otro módulo y puede cambiar
            db.rollback()

    alertas = [dict(r) for r in db.execute(text("""
        SELECT tipo, severidad, COUNT(*) AS n FROM alertas
        WHERE resuelta_at IS NULL GROUP BY tipo, severidad ORDER BY n DESC
    """)).mappings()]

    total_camas = sum(a["total"] - a["fuera_servicio"] for a in areas) or 1
    ocupadas = sum(a["ocupadas"] + a["reservadas"] for a in areas)
    # Indicador P.2.15 de la Res. 256/2016: cirugías canceladas por causas
    # atribuibles a la institución / cirugías programadas x 100. Se toma el mes
    # más reciente con volumen suficiente (el mes en curso puede estar empezando).
    canc = db.execute(text("""
        SELECT mes, programadas, canceladas, por_prestador, pct_cancelacion
        FROM v_indicador_cancelacion WHERE programadas >= 20 ORDER BY mes DESC LIMIT 1
    """)).mappings().first()
    cancelacion = None
    if canc:
        cancelacion = {
            "mes": canc["mes"].date().isoformat() if canc["mes"] else None,
            "programadas": canc["programadas"], "canceladas": canc["canceladas"],
            "pct_total": float(canc["pct_cancelacion"] or 0),
            "pct_institucion": round(100 * (canc["por_prestador"] or 0) / canc["programadas"], 2),
            "norma": "Res. 256/2016, indicador P.2.15",
        }

    return {
        "ahora": ahora.isoformat(),
        "cancelacion_cirugia": cancelacion,
        "supuestos": {
            "tipo": "escenario con reglas configurables, no modelo validado",
            "fraccion_altas_12h": FRACCION_ALTAS_12H,
            "bandas_pct": {"saturada": 100, "alta": 90, "vigilar": 80},
            "costo_ocioso": "costo día de la cama / 24 × horas libres; proxy, no pérdida contable",
        },
        "resumen": {
            "camas_utiles": total_camas, "camas_ocupadas": ocupadas,
            "pct_ocupacion": round(100 * ocupadas / total_camas, 1),
            "areas_en_riesgo": sum(1 for a in areas if a["riesgo"] in ("alto", "colapso")),
        },
        "areas": areas, "quirofanos": qx, "cirugias_hoy": cirugias_hoy,
        "urgencias": urgencias, "dinero": dinero, "ia": ia, "alertas_abiertas": alertas,
    }


# ================================================================ MI CUENTA (paciente)
# Reparto de referencia entre el paciente y su entidad. Son valores de
# demostración (el cálculo real depende del IBC del afiliado y del acuerdo de
# cada EPS); la facturación oficial la lleva el módulo de contabilidad.
REPARTO = {
    "particular": {"pct_paciente": 1.0, "tope": None, "nombre": "Pago particular"},
    "contributivo": {"pct_paciente": 0.115, "tope": 1_100_000, "nombre": "Copago (régimen contributivo)"},
    "subsidiado": {"pct_paciente": 0.10, "tope": 900_000, "nombre": "Copago (régimen subsidiado)"},
    "especial": {"pct_paciente": 0.0, "tope": None, "nombre": "Sin copago (régimen especial)"},
}
CUOTA_MODERADORA = {"contributivo": 4_700, "subsidiado": 0}
NOMBRE_TIPO = {"cirugia": "Cirugía", "urgencias": "Atención de urgencias",
               "hospitalizacion": "Hospitalización", "consulta_externa": "Consulta externa"}


@router.get("/mi-cuenta", summary="Qué se le está cobrando al paciente y a su EPS")
def mi_cuenta(ctx: ContextoAcceso = Depends(RequierePermiso("paciente", "read")),
              db: Session = Depends(get_db)):
    """
    Solo para la cuenta del propio paciente (alcance 'self'). Cada servicio
    prestado con su valor, la parte que paga la entidad y la que paga él.
    """
    from fastapi import HTTPException, status
    if ctx.alcance != "self":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta vista es solo para el paciente")
    pid = ctx.payload.get("paciente_id")
    p = db.get(Paciente, pid) if pid else None
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    e_ = dict(db.execute(text("SELECT codigo, nombre, regimen FROM eps WHERE id = :i"),
                         {"i": p.eps_id}).mappings().first() or {})
    cob = cobertura(e_.get("codigo"), e_.get("nombre"), e_.get("regimen"))
    clave = "particular" if cob["tipo"] == "particular" else (cob["regimen"] or "contributivo")
    regla = REPARTO.get(clave, REPARTO["contributivo"])

    filas = db.execute(text("""
        SELECT e.id, e.tipo, e.estado, e.hora_real_inicio, e.hora_real_fin, e.hora_programada_inicio,
               e.created_at, cp.nombre AS procedimiento, cp.codigo_cups, cp.tarifa_referencia_cop,
               tc.nombre AS tipo_cama, tc.costo_dia_cop
        FROM encuentros e
        LEFT JOIN catalogo_procedimientos cp ON cp.id = e.procedimiento_id
        LEFT JOIN camas c ON c.id = e.cama_id
        LEFT JOIN tipos_cama tc ON tc.id = c.tipo_cama_id
        WHERE e.activo AND e.paciente_id = :pid AND e.estado <> 'cancelled'
        ORDER BY COALESCE(e.hora_real_inicio, e.hora_programada_inicio, e.created_at) DESC
        LIMIT 60
    """), {"pid": pid}).mappings().all()

    ahora = datetime.now(timezone.utc)
    servicios, acumulado_paciente = [], 0.0
    for f in filas:
        if f["estado"] == "planned":
            continue   # lo programado todavía no se cobra
        items = []
        if f["procedimiento"] and f["tarifa_referencia_cop"]:
            items.append({"concepto": f["procedimiento"], "codigo": f["codigo_cups"],
                          "tipo_cobro": "procedimiento", "cantidad": 1,
                          "valor": float(f["tarifa_referencia_cop"])})
        if f["costo_dia_cop"] and f["hora_real_inicio"]:
            horas = ((f["hora_real_fin"] or ahora) - f["hora_real_inicio"]).total_seconds() / 3600
            dias = max(1, round(horas / 24 + 0.49))
            items.append({"concepto": f"Estancia · {f['tipo_cama']}", "codigo": None,
                          "tipo_cobro": "estancia", "cantidad": dias,
                          "valor": round(dias * float(f["costo_dia_cop"]))})
        if f["tipo"] in ("consulta_externa", "urgencias") and not items:
            items.append({"concepto": NOMBRE_TIPO[f["tipo"]], "codigo": "890201" if f["tipo"] == "consulta_externa" else "890701",
                          "tipo_cobro": "consulta", "cantidad": 1,
                          "valor": 68_000 if f["tipo"] == "consulta_externa" else 145_000})
        if not items:
            continue
        total = sum(i["valor"] for i in items)
        if clave in CUOTA_MODERADORA and f["tipo"] in ("consulta_externa", "urgencias"):
            a_cargo = float(CUOTA_MODERADORA[clave]); concepto = "Cuota moderadora"
        else:
            a_cargo = total * regla["pct_paciente"]; concepto = regla["nombre"]
            if regla["tope"] is not None:
                if acumulado_paciente + a_cargo > regla["tope"]:
                    concepto = "Copago hasta el tope anual (lo demás lo cubre la entidad)"
                a_cargo = min(a_cargo, max(regla["tope"] - acumulado_paciente, 0))
        a_cargo = round(a_cargo)
        acumulado_paciente += a_cargo
        servicios.append({
            "encuentro_id": f["id"], "tipo": f["tipo"], "nombre": NOMBRE_TIPO.get(f["tipo"], f["tipo"]),
            "estado": "en curso" if f["estado"] in ACTIVOS else "terminado",
            "fecha": f["hora_real_inicio"] or f["hora_programada_inicio"] or f["created_at"],
            "items": items, "valor_total": round(total),
            "a_cargo_paciente": a_cargo, "concepto_paciente": concepto,
            "a_cargo_entidad": round(total - a_cargo),
        })
    return {
        "cobertura": cob, "regla": {"porcentaje_paciente": regla["pct_paciente"], "tope_anual": regla["tope"],
                                    "nombre": regla["nombre"]},
        "servicios": servicios,
        "totales": {"valor_total": sum(s["valor_total"] for s in servicios),
                    "a_cargo_paciente": sum(s["a_cargo_paciente"] for s in servicios),
                    "a_cargo_entidad": sum(s["a_cargo_entidad"] for s in servicios)},
        "nota": "Valores de referencia del caso de estudio. El valor oficial es el de la factura emitida.",
    }


# ================================================================ MI RESUMEN (paciente)
LOINC_PACIENTE = {
    "8867-4": ("Frecuencia cardiaca", "latidos/min"), "8480-6": ("Presión sistólica", "mmHg"),
    "8462-4": ("Presión diastólica", "mmHg"), "59408-5": ("Oxígeno en sangre", "%"),
    "9279-1": ("Respiraciones", "por min"), "8310-5": ("Temperatura", "°C"),
}
TIPO_CAMA_SENCILLO = {"UCI": "Cuidados intensivos", "UCIN": "Cuidados intensivos neonatales",
                      "INTERMEDIA": "Cuidados intermedios", "GENERAL": "Hospitalización",
                      "OBSERV_URG": "Observación de urgencias"}


@router.get("/mi-resumen", summary="Portal del paciente: dónde estoy, qué sigue y quién me atiende")
def mi_resumen(ctx: ContextoAcceso = Depends(RequierePermiso("paciente", "read")),
               db: Session = Depends(get_db)):
    """Solo para la cuenta del propio paciente (alcance 'self'), en lenguaje sencillo."""
    from fastapi import HTTPException, status
    if ctx.alcance != "self":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta vista es solo para el paciente")
    pid = ctx.payload.get("paciente_id")
    p = db.get(Paciente, pid) if pid else None
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    nombres = Nombres(db)
    ahora = datetime.now(timezone.utc)

    encuentros = db.execute(text("""
        SELECT e.id, e.tipo, e.estado, e.origen, e.hora_programada_inicio, e.hora_real_inicio, e.hora_real_fin,
               e.created_at, e.medico_responsable_id, e.anestesiologo_id,
               cp.nombre AS procedimiento, cp.duracion_estimada_min, tcr.codigo AS cama_recuperacion,
               dx.descripcion AS diagnostico, c.codigo AS cama, tc.codigo AS tipo_cama, s.nombre AS servicio,
               q.codigo AS quirofano
        FROM encuentros e
        LEFT JOIN catalogo_procedimientos cp ON cp.id = e.procedimiento_id
        LEFT JOIN tipos_cama tcr ON tcr.id = cp.tipo_cama_requerida_id
        LEFT JOIN diagnosticos_cie10 dx ON dx.id = e.diagnostico_cie10_id
        LEFT JOIN camas c ON c.id = e.cama_id
        LEFT JOIN tipos_cama tc ON tc.id = c.tipo_cama_id
        LEFT JOIN servicios s ON s.id = c.servicio_id
        LEFT JOIN quirofanos q ON q.id = e.quirofano_id
        WHERE e.activo AND e.paciente_id = :pid AND e.estado <> 'cancelled'
        ORDER BY COALESCE(e.hora_real_inicio, e.hora_programada_inicio, e.created_at) DESC
        LIMIT 40
    """), {"pid": pid}).mappings().all()

    actual = next((e for e in encuentros if e["estado"] in ACTIVOS and e["tipo"] in ("hospitalizacion", "urgencias")
                   and e["hora_real_inicio"]), None)
    cirugias = sorted([e for e in encuentros if e["tipo"] == "cirugia" and e["estado"] in ("planned", "in-progress")],
                      key=lambda e: e["hora_programada_inicio"] or ahora)
    cx = cirugias[0] if cirugias else None

    equipo: dict[int, dict] = {}
    recientes = [e for e in encuentros if e["estado"] in ACTIVOS
                 or (e["hora_real_inicio"] or e["created_at"]) > ahora - timedelta(days=30)]
    for e in recientes:
        for campo, funcion in (("medico_responsable_id", "cirujano" if e["tipo"] == "cirugia" else "médico tratante"),
                               ("anestesiologo_id", "anestesiólogo")):
            mid = e[campo]
            if mid and mid not in equipo and len(equipo) < 6:
                m = db.get(Personal, mid)
                equipo[mid] = {"nombre": nombres(mid), "funcion": funcion,
                               "especialidad": m.especialidad.nombre if m and m.especialidad else None}

    signos = {}
    for o in db.execute(text("""
        SELECT DISTINCT ON (codigo_loinc) codigo_loinc, valor_numerico, fecha_hora
        FROM observaciones WHERE activo AND paciente_id = :pid AND categoria = 'vital-signs'
          AND fecha_hora > NOW() - INTERVAL '7 days'
        ORDER BY codigo_loinc, fecha_hora DESC
    """), {"pid": pid}).mappings():
        if o["codigo_loinc"] in LOINC_PACIENTE and o["valor_numerico"] is not None:
            n, u = LOINC_PACIENTE[o["codigo_loinc"]]
            signos[o["codigo_loinc"]] = {"nombre": n, "valor": float(o["valor_numerico"]), "unidad": u, "fecha": o["fecha_hora"]}

    remisiones = []
    if db.execute(text("SELECT to_regclass('public.remisiones') IS NOT NULL")).scalar():
        for r in db.execute(text("""
            SELECT especialista_id, estado, created_at FROM remisiones WHERE paciente_id = :pid
            ORDER BY created_at DESC LIMIT 5"""), {"pid": pid}).mappings():
            m = db.get(Personal, r["especialista_id"])
            remisiones.append({"especialista": nombres(r["especialista_id"]),
                               "especialidad": m.especialidad.nombre if m and m.especialidad else None,
                               "estado": r["estado"], "fecha": r["created_at"]})

    e_ = dict(db.execute(text("SELECT codigo, nombre, regimen FROM eps WHERE id = :i"), {"i": p.eps_id}).mappings().first() or {})
    return {
        "paciente": {"nombre": descifrar(p.nombre_cifrado, "pacientes.nombre"),
                     "apellido": descifrar(p.apellido_cifrado, "pacientes.apellido"),
                     "edad": edad(p.fecha_nacimiento), "sexo": p.sexo,
                     "cobertura": cobertura(e_.get("codigo"), e_.get("nombre"), e_.get("regimen"))},
        "ahora": actual and {
            "tipo": actual["tipo"], "desde": actual["hora_real_inicio"],
            "lugar": TIPO_CAMA_SENCILLO.get(actual["tipo_cama"], actual["servicio"]),
            "cama": actual["cama"], "servicio": actual["servicio"], "diagnostico": actual["diagnostico"],
            "medico": nombres(actual["medico_responsable_id"])},
        "proxima_cirugia": cx and {
            "procedimiento": cx["procedimiento"], "estado": cx["estado"],
            "fecha": cx["hora_real_inicio"] or cx["hora_programada_inicio"], "duracion_min": cx["duracion_estimada_min"],
            "quirofano": cx["quirofano"], "cirujano": nombres(cx["medico_responsable_id"]),
            "anestesiologo": nombres(cx["anestesiologo_id"]),
            "recuperacion": TIPO_CAMA_SENCILLO.get(cx["cama_recuperacion"])},
        "equipo": list(equipo.values()),
        "signos": list(signos.values()),
        "remisiones": remisiones,
        "historial": [{
            "tipo": e["tipo"], "estado": e["estado"],
            "fecha": e["hora_real_inicio"] or e["hora_programada_inicio"] or e["created_at"],
            "detalle": e["procedimiento"] or e["diagnostico"],
            "lugar": e["quirofano"] or e["cama"] or e["servicio"],
            "profesional": nombres(e["medico_responsable_id"]),
        } for e in encuentros if e["estado"] not in ("planned",)][:15],
    }
