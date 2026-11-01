"""
Consultas del sistema para el asistente: preguntas sobre la operación que NO
están en ningún documento ("¿cuántos pacientes tengo?", "¿tengo alertas?",
"¿qué te puedo preguntar?").

El RAG recupera de guías e historias; esto responde con datos en vivo de la
base, reutilizando las MISMAS funciones y permisos de las pantallas (mis
pacientes, pendientes, tablero del hospital, alertas sin atender). Así el
asistente nunca muestra algo que la pantalla de ese perfil no mostraría:

  · se detecta la intención con reglas sobre el texto normalizado (no hace
    falta un modelo de lenguaje, funciona sin la clave de Grok);
  · cada intención declara qué permiso exige; sin él, no se responde con
    datos y se dice por qué;
  · estas respuestas se arman en el servidor y NO se envían a Grok: los datos
    de pacientes no salen a un proveedor externo.

Devuelve None si la pregunta no es una consulta del sistema (sigue el RAG).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import ContextoAcceso
from app.core.security import tiene_permiso
from app.services import rag_core as core

FUENTE = "Datos en vivo de Pulso, consultados con los permisos de tu perfil"


@dataclass
class Intencion:
    id: str
    patron: re.Pattern
    permiso: tuple[str, str] | None          # (recurso, acción) que exige, o None
    responder: Callable[[Session, ContextoAcceso], str]
    titulo: str


def _ctx_con(ctx: ContextoAcceso, recurso: str, accion: str) -> ContextoAcceso:
    """El mismo usuario, con el alcance del permiso que pide esa pantalla."""
    return ContextoAcceso(ctx.usuario, ctx.payload, tiene_permiso(ctx.payload.get("permisos", []), recurso, accion),
                          recurso, accion, ctx.db, ctx.request)


def _plural(n: int, uno: str, varios: str) -> str:
    return f"{n} {uno if n == 1 else varios}"


# ------------------------------------------------------------------ respuestas
def _mis_pacientes(db: Session, ctx: ContextoAcceso) -> str:
    from app.api.perfiles import mis_pacientes   # noqa: PLC0415 -- misma lógica que la pantalla
    c = _ctx_con(ctx, "paciente", "read")
    if c.alcance == "all":   # admin y perfiles con todos los pacientes: no "a su cargo", el total
        total = db.execute(text("SELECT COUNT(*) FROM pacientes WHERE activo")).scalar()
        activos = db.execute(text("""SELECT tipo, COUNT(DISTINCT paciente_id) FROM encuentros
                                     WHERE activo AND estado NOT IN ('finished', 'cancelled') GROUP BY tipo""")).all()
        detalle = ", ".join(f"{n} en {t.replace('_', ' ')}" for t, n in activos)
        return (f"Tu perfil ve a todos los pacientes: hay {total} activos en el sistema"
                + (f"; con atención en curso: {detalle}." if detalle else "."))
    lista = mis_pacientes(ctx=c, db=db, limite=300)["pacientes"]
    if not lista:
        return "No tienes pacientes a tu cargo en este momento."
    urg = sum(1 for p in lista if p["encuentro"] and p["encuentro"]["tipo"] == "urgencias")
    hosp = sum(1 for p in lista if p["encuentro"] and p["encuentro"]["tipo"] == "hospitalizacion")
    cx = sum(1 for p in lista if p["cirugia"])
    crit = [p for p in lista if p["criticos"]]
    texto = (f"Tienes {_plural(len(lista), 'paciente', 'pacientes')} a tu cargo: "
             f"{urg} en urgencias, {hosp} hospitalizados y {_plural(cx, 'con cirugía', 'con cirugía')}.")
    if crit:
        nombres = ", ".join(f"{p['nombre']} {p['apellido']}" for p in crit[:5])
        texto += f" {_plural(len(crit), 'tiene', 'tienen')} valores críticos recientes: {nombres}" + ("…" if len(crit) > 5 else ".")
    return texto + " El detalle está en Mis pacientes."


def _pendientes(db: Session, ctx: ContextoAcceso) -> dict:
    from app.api.eventos import pendientes   # noqa: PLC0415
    return pendientes(payload=ctx.payload, usuario=ctx.usuario, db=db)


def _reportes(db: Session, ctx: ContextoAcceso) -> str:
    n = _pendientes(db, ctx)["reportes_por_revisar"]
    return ("No tienes reportes de IA por revisar." if not n else
            f"Tienes {_plural(n, 'reporte de IA pendiente', 'reportes de IA pendientes')} de aprobar o rechazar. "
            "Mientras estén pendientes no entran a la historia clínica.")


def _alertas(db: Session, ctx: ContextoAcceso) -> str:
    if tiene_permiso(ctx.payload.get("permisos", []), "alerta", "supervisar"):
        from app.api.alertas import sin_atender   # noqa: PLC0415
        d = sin_atender(ctx=_ctx_con(ctx, "alerta", "supervisar"), db=db)
        if not d["total"]:
            return "No hay alertas críticas sin atender en el hospital."
        quienes = "; ".join(f"{m['nombre']}: {m['sin_atender']}" + (f" ({m['vencidas']} vencidas)" if m["vencidas"] else "")
                            for m in d["medicos"][:5])
        return (f"Hay {_plural(d['total'], 'alerta crítica sin atender', 'alertas críticas sin atender')}, "
                f"{d['vencidas']} ya vencidas. Por médico: {quienes}.")
    n = _pendientes(db, ctx)["alertas_activas"]
    return ("No tienes alertas críticas activas." if not n else
            f"Tienes {_plural(n, 'alerta crítica activa', 'alertas críticas activas')} sin reconocer. "
            "Reconócelas escribiendo la conducta tomada; si pasan 5 minutos se avisa a los otros médicos del paciente.")


def _remisiones(db: Session, ctx: ContextoAcceso) -> str:
    yo = ctx.payload.get("personal_id")
    f = db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE especialista_id = :yo AND estado = 'pendiente') AS por_aceptar,
               COUNT(*) FILTER (WHERE especialista_id = :yo AND estado = 'aceptada') AS en_atencion,
               COUNT(*) FILTER (WHERE (medico_id = :yo OR remitido_por = :u) AND estado IN ('pendiente', 'aceptada')) AS enviadas
        FROM remisiones
    """), {"yo": yo if yo is not None else -1, "u": ctx.usuario.id}).mappings().first()
    partes = []
    if f["por_aceptar"] or f["en_atencion"]:
        partes.append(f"recibiste {_plural(f['por_aceptar'], 'remisión por aceptar', 'remisiones por aceptar')} "
                      f"y tienes {_plural(f['en_atencion'], 'en atención', 'en atención')}")
    if f["enviadas"]:
        partes.append(f"tienes {_plural(f['enviadas'], 'remisión enviada abierta', 'remisiones enviadas abiertas')}")
    return ("No tienes remisiones abiertas." if not partes else "En remisiones, " + " y ".join(partes) + ".")


def _ocupacion(db: Session, ctx: ContextoAcceso) -> str:
    f = db.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE estado = 'disponible') AS libres,
               COUNT(*) FILTER (WHERE estado = 'ocupada') AS ocupadas,
               COUNT(*) FILTER (WHERE estado = 'en_limpieza') AS limpieza
        FROM camas WHERE activo
    """)).mappings().first()
    uci = db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE c.estado = 'disponible') FROM camas c
        JOIN tipos_cama tc ON tc.id = c.tipo_cama_id WHERE c.activo AND tc.codigo LIKE 'UCI%'
    """)).scalar()
    pct = round(100 * f["ocupadas"] / f["total"]) if f["total"] else 0
    return (f"Hay {f['ocupadas']} de {f['total']} camas ocupadas ({pct} %), {f['libres']} libres "
            f"(de ellas {uci} de UCI) y {f['limpieza']} en limpieza. El detalle por área está en el tablero.")


def _ayuda(db: Session, ctx: ContextoAcceso) -> str:
    from app.api.rag import fuentes_del_perfil   # noqa: PLC0415
    fuentes = fuentes_del_perfil(db, ctx)
    consultas = [i.titulo for i in INTENCIONES if i.id != "ayuda" and _permitida(i, ctx)]
    texto = "Puedo responderte de dos formas. "
    texto += ("Con documentos, citando la fuente: " + "; ".join(fuentes) + ". " if fuentes
              else "Tu perfil no tiene documentos en el asistente. ")
    texto += ("Y con datos en vivo de Pulso: " + "; ".join(consultas) + "." if consultas
              else "Tu perfil no tiene consultas de datos en vivo.")
    return texto + (" Si algo no está en esas fuentes, te digo que no tengo la información en vez de inventarla.")


INTENCIONES: list[Intencion] = [
    Intencion("ayuda",
              re.compile(r"(que|como) (te )?(puedo|se puede|se le puede) pregunt|que (sabes|puedes|haces)\b|para que sirves|"
                         r"\bayuda\b|no tienes (la )?informacion|como funcionas|que informacion tienes"),
              None, _ayuda, "qué puedo responder"),
    Intencion("mis_pacientes",
              re.compile(r"(cuant\w*|mis|tengo|lista\w*|cuales son mis) (\w+ )?pacientes|pacientes (tengo|a mi cargo)"),
              ("paciente", "read"), _mis_pacientes, "cuántos pacientes tienes y cuáles están críticos"),
    Intencion("reportes",
              re.compile(r"(tengo|hay|cuant\w*|mis) (\w+ )?reportes?|reportes?( de (la )?ia)? (pendientes?|por (revisar|aprobar))"),
              ("ia", "approve"), _reportes, "tus reportes de IA por revisar"),
    Intencion("alertas",
              re.compile(r"(tengo|hay|cuant\w*|mis|quien tiene|quienes tienen) (\w+ ){0,2}alertas?|"
                         r"alertas? (activas|pendientes|abiertas|sin atender|sin reconocer)"),
              ("alerta", "read"), _alertas, "tus alertas críticas (o las sin atender, si supervisas)"),
    Intencion("remisiones",
              re.compile(r"(tengo|hay|cuant\w*|mis) (\w+ )?remisi\w*|remisi\w* (pendientes|abiertas|por aceptar)"),
              ("remision", "read"), _remisiones, "tus remisiones abiertas"),
    Intencion("ocupacion",
              re.compile(r"ocupaci\w*|camas? (libres?|disponibles?|ocupadas?)|cuantas camas"),
              ("cama", "read"), _ocupacion, "la ocupación de camas"),
]


def _permitida(i: Intencion, ctx: ContextoAcceso) -> bool:
    if i.permiso is None:
        return True
    permisos = ctx.payload.get("permisos", [])
    if i.id == "alertas":   # el supervisor tiene alerta:supervisar en vez de alerta:read
        return bool(tiene_permiso(permisos, "alerta", "read") or tiene_permiso(permisos, "alerta", "supervisar"))
    if i.id == "ocupacion":
        return bool(tiene_permiso(permisos, "cama", "read") or tiene_permiso(permisos, "analitica", "read"))
    if i.id == "mis_pacientes":   # solo quien tiene pacientes a cargo (no el paciente)
        return tiene_permiso(permisos, "paciente", "read") in ("assigned", "all")
    return tiene_permiso(permisos, *i.permiso) is not None


def responder(db: Session, ctx: ContextoAcceso, pregunta: str) -> dict | None:
    """{"intencion", "respuesta", "permitida"} o None si no es una consulta del sistema."""
    norm = " ".join(core.normalizar(pregunta).replace("¿", " ").replace("?", " ").split())
    for i in INTENCIONES:
        if i.patron.search(norm):
            if not _permitida(i, ctx):
                return {"intencion": i.id, "permitida": False,
                        "respuesta": f"Tu perfil no tiene acceso a {i.titulo}, así que no puedo consultarlo por ti."}
            return {"intencion": i.id, "permitida": True, "respuesta": i.responder(db, ctx)}
    return None
