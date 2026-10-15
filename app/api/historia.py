"""
Historia clínica del paciente (R10, R11).

  GET /pacientes/{id}/historia       JSON: datos, encuentros, observaciones y reportes_ia
  GET /pacientes/{id}/historia/pdf   la misma historia en PDF (application/pdf)

reportes_ia trae SOLO los aprobados: un reporte pendiente o rechazado no forma
parte de la historia clínica (R10). Control de acceso: el mismo de la ficha
(paciente:read). El médico ve sus pacientes, el paciente solo la suya (403
con la de otro) y el contable no tiene paciente:read (403).
"""
from __future__ import annotations

import io
from datetime import date, datetime, timezone
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.crypto import descifrar
from app.core.deps import ContextoAcceso, RequierePermiso, get_db
from app.models import Paciente
from app.services.auditoria import registrar

router = APIRouter(prefix="/pacientes", tags=["Historia clínica"])

TIPO_ENCUENTRO = {"cirugia": "Cirugía", "consulta_externa": "Consulta externa", "urgencias": "Urgencias",
                  "hospitalizacion": "Hospitalización", "consulta": "Consulta"}
SEXO = {"F": "Femenino", "M": "Masculino", "O": "Otro"}


def _texto(cifrado, campo: str) -> str | None:
    if not cifrado:
        return None
    try:
        return descifrar(cifrado, campo)
    except Exception:  # noqa: BLE001
        return None


def _edad(nac: date) -> int:
    hoy = date.today()
    return hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day))


def construir_historia(db: Session, p: Paciente) -> dict:
    pid = p.documento_bidx
    encuentros = db.execute(text("""
        SELECT e.id, e.tipo, e.estado, e.origen,
               COALESCE(e.hora_real_inicio, e.hora_programada_inicio, e.created_at) AS fecha,
               cp.nombre AS procedimiento, dx.codigo AS cie10, dx.descripcion AS diagnostico,
               COALESCE(q.nombre, c.codigo) AS lugar
        FROM encuentros e
        LEFT JOIN catalogo_procedimientos cp ON cp.id = e.procedimiento_id
        LEFT JOIN diagnosticos_cie10 dx ON dx.id = e.diagnostico_cie10_id
        LEFT JOIN quirofanos q ON q.id = e.quirofano_id
        LEFT JOIN camas c ON c.id = e.cama_id
        WHERE e.paciente_id = :p AND e.activo
        ORDER BY fecha DESC LIMIT 50
    """), {"p": pid}).mappings().all()
    observaciones = db.execute(text("""
        SELECT id, categoria, codigo_loinc, display_loinc AS descripcion, valor_numerico, valor_texto,
               unidad_ucum AS unidad, es_critico, fecha_hora AS fecha
        FROM observaciones WHERE paciente_id = :p AND activo
        ORDER BY fecha_hora DESC LIMIT 100
    """), {"p": pid}).mappings().all()
    reportes = db.execute(text("""
        SELECT r.id, r.probabilidad, r.critico, r.modelo_version, r.observaciones,
               r.resultado->>'clase' AS clase, r.revisado_at, r.created_at, u.username AS aprobado_por
        FROM reportes_ia r LEFT JOIN usuarios u ON u.id = r.revisado_por
        WHERE r.paciente_id = :p AND r.estado = 'aprobado'
        ORDER BY r.created_at DESC
    """), {"p": pid}).mappings().all()

    return {
        "paciente_id": pid,
        "paciente": {
            "nombre": f"{_texto(p.nombre_cifrado, 'pacientes.nombre') or ''} "
                      f"{_texto(p.apellido_cifrado, 'pacientes.apellido') or ''}".strip(),
            "tipo_documento": p.tipo_documento,
            "documento": _texto(p.documento_cifrado, "pacientes.documento"),
            "fecha_nacimiento": p.fecha_nacimiento, "edad": _edad(p.fecha_nacimiento),
            "sexo": SEXO.get(p.sexo, p.sexo), "eps": p.eps.nombre if p.eps else None,
        },
        "encuentros": [{**dict(e), "descripcion": e["procedimiento"] or e["diagnostico"]
                        or TIPO_ENCUENTRO.get(e["tipo"], e["tipo"])} for e in encuentros],
        "observaciones": [{**dict(o), "valor": float(o["valor_numerico"]) if o["valor_numerico"] is not None
                           else o["valor_texto"]} for o in observaciones],
        "reportes_ia": [{**dict(r), "estado": "aprobado",
                         "probabilidad": float(r["probabilidad"]) if r["probabilidad"] is not None else None}
                        for r in reportes],
        "generado_at": datetime.now(timezone.utc),
    }


def _paciente_visible(db: Session, ctx: ContextoAcceso, paciente_id: str) -> Paciente:
    p = db.query(Paciente).filter(Paciente.documento_bidx == paciente_id, Paciente.activo.is_(True)).first()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    ctx.verificar_registro(p)
    return p


@router.get("/{paciente_id}/historia", summary="Historia clínica (solo reportes de IA aprobados)")
def historia(paciente_id: str, request: Request,
             ctx: ContextoAcceso = Depends(RequierePermiso("paciente", "read")),
             db: Session = Depends(get_db)):
    p = _paciente_visible(db, ctx, paciente_id)
    registrar(db, ctx.usuario, "paciente", p.id, "read", valor_nuevo={"vista": "historia"}, request=request)
    db.commit()
    return construir_historia(db, p)


# ---------------------------------------------------------------- PDF (R11)
def _fecha(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.astimezone().strftime("%Y-%m-%d %H:%M")
    return v.strftime("%Y-%m-%d") if isinstance(v, date) else str(v)


def generar_pdf(h: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    pac = h["paciente"]
    buf = io.BytesIO()
    # Fuentes estándar (Helvetica, codificación WinAnsi): tildes y eñes se ven bien.
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title=f"Historia clínica - {pac['nombre']}", author="Hospital San Rafael · Pulso",
                            subject=pac["nombre"])
    from reportlab.lib.styles import ParagraphStyle
    est = getSampleStyleSheet()
    est.add(ParagraphStyle("Celda", parent=est["BodyText"], fontSize=8.5, leading=10.5))
    p = lambda t, s="BodyText": Paragraph(escape(str(t)) if t is not None else "", est[s])  # noqa: E731
    c = lambda t: p(t, "Celda")  # noqa: E731  texto que puede ser largo dentro de una tabla

    def tabla(filas, anchos):
        t = Table(filas, colWidths=anchos, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF4")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8C2CC")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return t

    contenido = [
        p("Hospital San Rafael · Historia clínica", "Title"),
        p(f"Paciente: {pac['nombre']}", "Heading2"),
        p(f"{pac['tipo_documento']} {pac['documento'] or ''} · {pac['sexo']} · {pac['edad']} años "
          f"(nacimiento {_fecha(pac['fecha_nacimiento'])}) · EPS: {pac['eps'] or 'sin EPS'}"),
        p(f"Generada el {_fecha(h['generado_at'])}. Incluye solo los reportes de IA aprobados por un clínico."),
        Spacer(1, 10),
        p("Reportes de IA aprobados", "Heading3"),
    ]
    if h["reportes_ia"]:
        contenido.append(tabla(
            [["Fecha", "Riesgo UCI", "Crítico", "Modelo", "Aprobado por", "Observaciones del clínico"]] +
            [[_fecha(r["created_at"]), f"{r['probabilidad']:.0%}" if r["probabilidad"] is not None else "",
              "Sí" if r["critico"] else "No", r["modelo_version"] or "", r["aprobado_por"] or "",
              c(r["observaciones"] or "")] for r in h["reportes_ia"]],
            [2.6 * cm, 2 * cm, 1.4 * cm, 2.4 * cm, 2.4 * cm, 6.6 * cm]))
    else:
        contenido.append(p("Sin reportes aprobados."))

    contenido += [Spacer(1, 10), p("Observaciones clínicas recientes", "Heading3")]
    if h["observaciones"]:
        contenido.append(tabla(
            [["Fecha", "Código LOINC", "Descripción", "Valor", "Crítico"]] +
            [[_fecha(o["fecha"]), o["codigo_loinc"], c(o["descripcion"] or ""),
              f"{o['valor']} {o['unidad'] or ''}".strip(), "Sí" if o["es_critico"] else ""]
             for o in h["observaciones"][:40]],
            [2.8 * cm, 2.4 * cm, 6.8 * cm, 3 * cm, 2.4 * cm]))
    else:
        contenido.append(p("Sin observaciones registradas."))

    contenido += [Spacer(1, 10), p("Encuentros", "Heading3")]
    if h["encuentros"]:
        contenido.append(tabla(
            [["Fecha", "Tipo", "Descripción", "Lugar", "Estado"]] +
            [[_fecha(e["fecha"]), TIPO_ENCUENTRO.get(e["tipo"], e["tipo"]), c(e["descripcion"] or ""),
              e["lugar"] or "", e["estado"]] for e in h["encuentros"][:30]],
            [2.8 * cm, 2.6 * cm, 7 * cm, 2.6 * cm, 2.4 * cm]))
    else:
        contenido.append(p("Sin encuentros registrados."))

    doc.build(contenido)
    return buf.getvalue()


@router.get("/{paciente_id}/historia/pdf", summary="Historia clínica en PDF (R11)",
            response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def historia_pdf(paciente_id: str, request: Request,
                 ctx: ContextoAcceso = Depends(RequierePermiso("paciente", "read")),
                 db: Session = Depends(get_db)):
    p = _paciente_visible(db, ctx, paciente_id)
    pdf = generar_pdf(construir_historia(db, p))
    registrar(db, ctx.usuario, "paciente", p.id, "read", valor_nuevo={"vista": "historia_pdf"}, request=request)
    db.commit()
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="historia_clinica.pdf"'})
