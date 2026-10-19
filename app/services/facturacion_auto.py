"""
Factura automática del análisis de IA (R19, R09).

Al aprobar un reporte, el reactor crea sola una factura en MongoDB ligada al
reporte por `reporte_id`. Este módulo es la parte mínima que el flujo
automático necesita; el módulo de contabilidad (rutas /contabilidad/*, a cargo
de Sara) lee y opera la MISMA colección `facturas` con el documento de
docs/CONTRATO_FACTURACION.md.

Idempotencia: la factura de un reporte es única. Hay un índice único parcial
sobre `reporte_id` y el id de la factura se deriva del reporte (F-IA-<id>), así
que aprobar dos veces, o un reintento después de un fallo, nunca duplica el
cobro.

Para quedar de acuerdo con el módulo de Sara, la llave de lo que hace es:
  · colección `facturas` de la base de MONGO_URL
  · `id` "F-IA-<reporte_id>", `origen` "automatica", `servicio` "analisis_ia"
Si ella cambia el formato de `id`, solo se toca _ID_FACTURA.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.config import get_settings

log = logging.getLogger("hsr.facturacion")
settings = get_settings()

_cliente = None


def _id_factura(reporte_id: int) -> str:
    return f"F-IA-{reporte_id}"


def _coleccion():
    """Colección `facturas`, con su índice único por reporte (se crea una sola vez)."""
    global _cliente
    import pymongo  # noqa: PLC0415

    if _cliente is None:
        _cliente = pymongo.MongoClient(settings.mongo_url, serverSelectionTimeoutMS=3000, tz_aware=True)
    db = _cliente.get_default_database(default="hsr")
    col = db["facturas"]
    col.create_index([("reporte_id", pymongo.ASCENDING)], unique=True, name="uq_reporte_id",
                     partialFilterExpression={"reporte_id": {"$exists": True}})
    return col


def crear_por_reporte(reporte_id: int, paciente_id: str, *, paciente_nombre: str | None = None,
                      paciente_documento: str | None = None, coleccion=None) -> dict:
    """
    Crea (o devuelve, si ya existe) la factura del análisis de IA de ese reporte.
    `paciente_documento` ya viene enmascarado (****1234): nunca la cédula.
    """
    import pymongo  # noqa: PLC0415

    col = coleccion if coleccion is not None else _coleccion()
    valor = settings.tarifa_analisis_ia
    documento = {
        "id": _id_factura(reporte_id),
        "paciente_id": paciente_id,
        "servicio": "analisis_ia",
        "tipo_cobro": "ia",
        "descripcion": f"Análisis de IA (reporte {reporte_id})",
        "cantidad": 1,
        "valor_unitario": valor,
        "valor": valor,
        "fecha": datetime.now(timezone.utc),
        "estado_pago": "pendiente",
        "reporte_id": reporte_id,
        "origen": "automatica",
        "paciente_nombre": paciente_nombre,
        "paciente_documento": paciente_documento,
    }
    try:
        fila = col.find_one_and_update({"reporte_id": reporte_id}, {"$setOnInsert": documento},
                                       upsert=True, return_document=pymongo.ReturnDocument.AFTER)
    except pymongo.errors.DuplicateKeyError:
        # Dos aprobaciones simultáneas: la otra ganó el upsert; se lee su factura.
        fila = col.find_one({"reporte_id": reporte_id})
    fila.pop("_id", None)
    return fila
