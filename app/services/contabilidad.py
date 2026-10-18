"""
Módulo de contabilidad (R09) sobre MongoDB.

Implementa el contrato de docs/CONTRATO_FACTURACION.md. Las rutas HTTP están en
app/api/contabilidad.py; aquí vive la lógica y el acceso a Mongo.

Decisiones de diseño
  * Factura automática IDEMPOTENTE: índice único (parcial) por reporte_id. Aprobar
    dos veces el mismo reporte de IA deja UNA sola factura, aunque lleguen a la
    vez (la base rechaza la segunda inserción, no solo el código).
  * Mongo nunca guarda la cédula: solo enmascarada (****6591), como la API.
  * El nombre del paciente se guarda CIFRADO (AES-256-GCM, el mismo cifrado del
    resto del sistema) y se busca con índice ciego por palabra. Sin esto, la
    colección de facturas sería una copia en claro de datos que en PostgreSQL
    están protegidos.
  * Numeración de facturas con un contador atómico (F-250001, F-250002, ...).
  * Escrituras con filtro por estado (UPDATE ... WHERE estado = origen): dos
    clics simultáneos no pagan ni anulan dos veces.

El cobro es una REFERENCIA INTERNA del caso de estudio: no es un RIPS ni una
factura electrónica de la DIAN (ver docs/CONTABILIDAD.md).
"""
from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.crypto import blind_index, cifrar, descifrar, enmascarar

log = logging.getLogger("hsr.contabilidad")

# ---------------------------------------------------------------- catálogos
ESTADOS_PAGO = ("pendiente", "radicada", "glosada", "pagada", "anulada")
TIPOS_COBRO = ("consulta", "urgencias", "hospitalizacion", "cirugia", "imagenologia",
               "laboratorio", "medicamentos", "insumos", "terapia", "ia", "remision", "otros")
TIPOS_COBERTURA = ("particular", "eps", "especial", "soat", "prepagada")
REGIMENES = ("contributivo", "subsidiado", "especial")

PARTICULAR = {"tipo": "particular", "entidad": "Particular", "regimen": None}
SERVICIO_IA = "analisis_ia"
CODIGO_IA = "IA0001"
PRIMER_NUMERO = 250000          # la primera factura es F-250001
LIMITE_LISTA = 20000            # sin paginar, nunca se devuelve más que esto

# Mismo tarifario de referencia que usa el front (front/src/lib/facturacion.js).
# Se siembra en Mongo una vez y a partir de ahí se puede editar en la base.
_TARIFA = [
    ("890201", "Consulta de medicina general", "consulta", 68000),
    ("890202", "Consulta de medicina especializada", "consulta", 115000),
    ("890203", "Consulta de anestesiología (preanestésica)", "consulta", 98000),
    ("890701", "Consulta de urgencias", "urgencias", 145000),
    ("890702", "Observación en urgencias (hasta 6 h)", "urgencias", 210000),
    ("890703", "Reanimación (triage 1)", "urgencias", 620000),
    ("S12101", "Día cama hospitalización general", "hospitalizacion", 420000),
    ("S12201", "Día cama cuidados intermedios", "hospitalizacion", 950000),
    ("S12301", "Día cama UCI adultos", "hospitalizacion", 1800000),
    ("S12302", "Día cama UCI neonatal", "hospitalizacion", 1900000),
    ("471101", "Apendicectomía", "cirugia", 3200000),
    ("512100", "Colecistectomía laparoscópica", "cirugia", 4800000),
    ("791200", "Osteosíntesis de fémur", "cirugia", 7600000),
    ("361100", "Revascularización miocárdica", "cirugia", 32000000),
    ("S40100", "Derechos de sala de cirugía (hora)", "cirugia", 520000),
    ("S40200", "Derechos de sala de recuperación", "cirugia", 260000),
    ("871121", "Radiografía de tórax (PA y lateral)", "imagenologia", 62000),
    ("879111", "Tomografía de cráneo simple", "imagenologia", 310000),
    ("881302", "Ecografía abdominal total", "imagenologia", 135000),
    ("883210", "Resonancia de columna lumbar", "imagenologia", 720000),
    ("902210", "Hemograma completo", "laboratorio", 28000),
    ("903895", "Creatinina en suero", "laboratorio", 14000),
    ("903864", "Electrolitos (Na, K, Cl)", "laboratorio", 42000),
    ("903825", "Lactato en sangre", "laboratorio", 39000),
    ("903437", "Troponina I ultrasensible", "laboratorio", 96000),
    ("904902", "Gases arteriales", "laboratorio", 88000),
    ("MED001", "Ceftriaxona 1 g ampolla", "medicamentos", 18500),
    ("MED002", "Enoxaparina 40 mg jeringa", "medicamentos", 27400),
    ("MED003", "Noradrenalina 4 mg ampolla", "medicamentos", 41200),
    ("MED004", "Omeprazol 40 mg vial", "medicamentos", 12800),
    ("MED005", "Paracetamol 1 g IV", "medicamentos", 21600),
    ("INS001", "Kit de vía central", "insumos", 312000),
    ("INS002", "Sutura absorbible 3-0", "insumos", 24500),
    ("INS003", "Malla de polipropileno", "insumos", 680000),
    ("931000", "Terapia física (sesión)", "terapia", 54000),
    ("939403", "Terapia respiratoria (sesión)", "terapia", 47000),
    ("IA0001", "Análisis de IA: predicción de cama UCI", "ia", 85000),
    ("890402", "Interconsulta por especialista", "remision", 210000),
    ("890403", "Remisión a especialista (gestión)", "remision", 45000),
    ("S99001", "Certificado e historia clínica", "otros", 18000),
]
TARIFARIO = [{"codigo": c, "nombre": n, "tipo_cobro": t, "valor": v} for c, n, t, v in _TARIFA]


class ErrorContabilidad(Exception):
    """Error de negocio; `codigo` es el HTTP que le corresponde."""
    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo, self.mensaje = codigo, mensaje


# ---------------------------------------------------------------- conexión
_lock = threading.Lock()
_estado: dict[str, Any] = {"db": None, "listo": False}


def usar_base(db) -> None:
    """Para las pruebas: usa esta base (real o simulada) en lugar de la del .env."""
    with _lock:
        _estado["db"], _estado["listo"] = db, False


def _db():
    """Base de Mongo, creada una sola vez por proceso. Los índices se aseguran al primer uso."""
    if _estado["db"] is None:
        with _lock:
            if _estado["db"] is None:
                import pymongo  # noqa: PLC0415 -- si falta, la ruta responde 503 y la API sigue viva
                cliente = pymongo.MongoClient(get_settings().mongo_url,
                                              serverSelectionTimeoutMS=3000, tz_aware=True)
                _estado["db"] = cliente.get_default_database("hsr")
    db = _estado["db"]
    if not _estado["listo"]:
        with _lock:
            if not _estado["listo"]:
                _asegurar_indices(db)
                _estado["listo"] = True
    return db


def base_mongo():
    """La base de Mongo del proyecto (la comparten contabilidad y clusters)."""
    return _db()


def _asegurar_indices(db) -> None:
    """Idempotente: crear un índice que ya existe no hace nada."""
    f = db["facturas"]
    f.create_index([("id", 1)], unique=True, name="uq_id")
    # Una sola factura por reporte de IA. Parcial: las facturas manuales no tienen reporte_id.
    f.create_index([("reporte_id", 1)], unique=True, name="uq_reporte_id",
                   partialFilterExpression={"reporte_id": {"$exists": True}})
    f.create_index([("fecha", -1)], name="ix_fecha")
    f.create_index([("tipo_cobro", 1), ("estado_pago", 1), ("fecha", -1)], name="ix_tipo_estado_fecha")
    f.create_index([("cobertura.entidad", 1), ("estado_pago", 1)], name="ix_entidad_estado")
    f.create_index([("paciente_id", 1), ("fecha", -1)], name="ix_paciente_fecha")
    f.create_index([("nombre_bidx", 1)], name="ix_nombre_bidx")
    db["tarifario"].create_index([("codigo", 1)], unique=True, name="uq_codigo")
    for t in TARIFARIO:
        db["tarifario"].update_one({"codigo": t["codigo"]}, {"$setOnInsert": t}, upsert=True)
    db["contadores"].update_one({"_id": "factura"}, {"$setOnInsert": {"seq": PRIMER_NUMERO}}, upsert=True)


def _siguiente_id(db) -> str:
    from pymongo import ReturnDocument  # noqa: PLC0415
    r = db["contadores"].find_one_and_update(
        {"_id": "factura"}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
    return f"F-{int(r['seq'])}"


# ---------------------------------------------------------------- reglas de negocio
def deducir_tipo_cobro(servicio: str | None, cups: str | None = None) -> str:
    """Mismo criterio que el front: servicio -> tipo de cobro (o por el CUPS del tarifario)."""
    if servicio == SERVICIO_IA:
        return "ia"
    if servicio in TIPOS_COBRO:
        return servicio
    for t in TARIFARIO:
        if (cups and t["codigo"] == cups) or t["tipo_cobro"] == servicio:
            return t["tipo_cobro"]
    return "otros"


def repartir(valor: float, cobertura: dict | None, tipo_cobro: str) -> tuple[int, int]:
    """
    Cuánto paga el paciente y cuánto su entidad. Reglas de REFERENCIA del caso
    de estudio (iguales a las del front), no las tablas oficiales vigentes:
      particular           -> todo el paciente
      SOAT / especial      -> todo la entidad
      prepagada            -> bono de 35.000, tope el valor
      consulta/urgencias   -> cuota moderadora 4.700 (contributivo) o 0 (subsidiado)
      demás servicios      -> copago 11,5 % (contributivo) o 10 % (subsidiado)
    """
    v = round(float(valor))
    c = cobertura or PARTICULAR
    t = c.get("tipo")
    if not t or t == "particular":
        paciente = v
    elif t in ("soat", "especial"):
        paciente = 0
    elif t == "prepagada":
        paciente = min(v, 35000)
    elif tipo_cobro in ("consulta", "urgencias"):
        paciente = 0 if c.get("regimen") == "subsidiado" else 4700
    else:
        paciente = int(v * (0.10 if c.get("regimen") == "subsidiado" else 0.115) + 0.5)
    paciente = min(paciente, v)
    return paciente, v - paciente


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _como_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _palabras(texto: str) -> list[str]:
    return [p for p in re.split(r"\W+", texto.lower()) if len(p) >= 2]


def _indice_nombre(nombre: str) -> list[str]:
    """Índice ciego por palabra: permite buscar 'caicedo' sin guardar el nombre en claro."""
    return sorted({blind_index(p, "facturas.nombre") for p in _palabras(nombre)})


def _mascara_documento(doc: str | None) -> str | None:
    """Nunca se guarda la cédula completa: si llega en claro, se enmascara aquí."""
    if not doc:
        return None
    if doc.startswith("*"):
        return doc
    return enmascarar(re.sub(r"\D", "", doc) or doc)


def _salida(doc: dict) -> dict:
    """Documento de Mongo -> JSON de la API (sin campos internos; nombre descifrado)."""
    s = {k: v for k, v in doc.items() if k not in ("_id", "paciente_nombre_cifrado", "nombre_bidx")}
    for k, v in list(s.items()):
        if isinstance(v, datetime):
            s[k] = _como_utc(v).isoformat()
    if doc.get("paciente_nombre_cifrado"):
        try:
            s["paciente_nombre"] = descifrar(doc["paciente_nombre_cifrado"].encode(), "facturas.paciente_nombre")
        except Exception:  # noqa: BLE001 -- una clave distinta no debe tumbar el listado
            log.warning("No se pudo descifrar el nombre de la factura %s", doc.get("id"))
            s["paciente_nombre"] = None
    return s


def _construir(d: dict, *, usuario_id: int | None, origen: str) -> dict:
    """Valida y completa una factura nueva (lo que no viene, se deduce como en el front)."""
    valor = round(float(d["valor"]))
    if valor <= 0:
        raise ErrorContabilidad(422, "El valor debe ser mayor que cero")
    estado = d.get("estado_pago") or "pendiente"
    if estado not in ESTADOS_PAGO or estado == "anulada":
        raise ErrorContabilidad(422, "Estado de pago inválido para una factura nueva")
    tipo = d.get("tipo_cobro") or deducir_tipo_cobro(d.get("servicio"), d.get("cups"))
    cobertura = d.get("cobertura") or dict(PARTICULAR)

    if d.get("valor_paciente") is not None:
        vp = min(max(round(float(d["valor_paciente"])), 0), valor)
        if d.get("valor_entidad") is not None and vp + round(float(d["valor_entidad"])) != valor:
            raise ErrorContabilidad(422, "valor_paciente + valor_entidad debe ser igual al valor")
        ve = valor - vp
    else:
        vp, ve = repartir(valor, cobertura, tipo)

    fecha = _como_utc(d["fecha"]) if isinstance(d.get("fecha"), datetime) else _ahora()
    doc: dict[str, Any] = {
        "paciente_id": d["paciente_id"], "servicio": d["servicio"], "valor": valor, "fecha": fecha,
        "estado_pago": estado, "tipo_cobro": tipo, "cobertura": cobertura,
        "valor_paciente": vp, "valor_entidad": ve, "origen": origen,
        "creada_por": usuario_id, "created_at": _ahora(),
    }
    for campo in ("cups", "descripcion", "cantidad", "valor_unitario", "reporte_id"):
        if d.get(campo) is not None:
            doc[campo] = d[campo]
    if d.get("paciente_documento"):
        doc["paciente_documento"] = _mascara_documento(d["paciente_documento"])
    if d.get("paciente_nombre"):
        doc["paciente_nombre_cifrado"] = cifrar(d["paciente_nombre"], "facturas.paciente_nombre").decode()
        doc["nombre_bidx"] = _indice_nombre(d["paciente_nombre"])
    return doc


# ---------------------------------------------------------------- operaciones
def crear(datos: dict, *, usuario_id: int | None) -> tuple[dict, bool]:
    """
    POST /contabilidad/facturas. Devuelve (factura, creada). Una factura manual
    siempre se crea; con reporte_id es la automática y es idempotente.
    """
    db = _db()
    if datos.get("reporte_id") is not None:
        return _facturar_reporte_con(db, datos, usuario_id)
    doc = _construir(datos, usuario_id=usuario_id, origen="manual")
    doc["id"] = _siguiente_id(db)
    db["facturas"].insert_one(doc)
    return _salida(doc), True


def facturar_reporte(reporte_id: int, paciente_id: str, *, paciente_nombre: str | None = None,
                     paciente_documento: str | None = None, cobertura: dict | None = None,
                     usuario_id: int | None = None) -> tuple[dict, bool]:
    """
    Factura automática al aprobar un reporte de IA (R19). IDEMPOTENTE.

    Devuelve (factura, creada). Si el reporte ya tenía factura devuelve la
    existente y creada=False: aprobar dos veces no cobra dos veces.
    """
    tarifa = next(t for t in TARIFARIO if t["codigo"] == CODIGO_IA)
    datos = {"paciente_id": paciente_id, "servicio": SERVICIO_IA, "valor": tarifa["valor"],
             "cups": CODIGO_IA, "descripcion": tarifa["nombre"], "tipo_cobro": "ia",
             "reporte_id": reporte_id, "paciente_nombre": paciente_nombre,
             "paciente_documento": paciente_documento, "cobertura": cobertura}
    return _facturar_reporte_con(_db(), datos, usuario_id)


def _facturar_reporte_con(db, datos: dict, usuario_id: int | None) -> tuple[dict, bool]:
    from pymongo.errors import DuplicateKeyError  # noqa: PLC0415
    rid = datos["reporte_id"]
    ya = db["facturas"].find_one({"reporte_id": rid})
    if ya:
        return _salida(ya), False
    doc = _construir(datos, usuario_id=usuario_id, origen="automatica")
    doc["id"] = _siguiente_id(db)
    try:
        db["facturas"].insert_one(doc)
    except DuplicateKeyError:
        # Otra petición se adelantó entre el find y el insert: el índice único la frenó.
        return _salida(db["facturas"].find_one({"reporte_id": rid})), False
    return _salida(doc), True


def _fecha(texto: str, fin_de_dia: bool) -> datetime:
    try:
        dt = datetime.fromisoformat(texto)
    except ValueError:
        raise ErrorContabilidad(422, f"Fecha inválida: {texto!r} (use AAAA-MM-DD o ISO 8601)") from None
    if len(texto) <= 10 and fin_de_dia:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return _como_utc(dt)


def listar(*, tipo=None, estado=None, entidad=None, q=None, desde=None, hasta=None,
           pagina: int | None = None, por_pagina: int | None = None) -> tuple[list[dict], int]:
    """
    Devuelve (facturas, total). Sin `pagina` ni `por_pagina` entrega todas las
    que cumplen el filtro (hasta LIMITE_LISTA), más recientes primero: el front
    actual las filtra y las pagina él mismo.
    """
    db = _db()
    filtro: dict[str, Any] = {}
    if tipo:
        filtro["tipo_cobro"] = tipo
    if estado:
        filtro["estado_pago"] = estado
    if entidad:
        filtro["cobertura.entidad"] = entidad
    if desde or hasta:
        rango: dict[str, datetime] = {}
        if desde:
            rango["$gte"] = _fecha(desde, False)
        if hasta:
            rango["$lte"] = _fecha(hasta, True)
        filtro["fecha"] = rango
    if q and q.strip():
        t = q.strip()
        o: list[dict] = [{"id": {"$regex": f"^{re.escape(t)}", "$options": "i"}},
                         {"cups": {"$regex": f"^{re.escape(t)}"}},
                         {"paciente_documento": {"$regex": re.escape(t)}}]
        palabras = _palabras(t)
        if palabras:   # el nombre se busca por palabra completa (índice ciego)
            o.append({"nombre_bidx": {"$all": [blind_index(p, "facturas.nombre") for p in palabras]}})
        filtro["$or"] = o

    total = db["facturas"].count_documents(filtro)
    cursor = db["facturas"].find(filtro).sort([("fecha", -1), ("id", -1)])
    if pagina is not None or por_pagina is not None:
        por = max(1, min(por_pagina or 50, 500))
        cursor = cursor.skip((max(pagina or 1, 1) - 1) * por).limit(por)
    else:
        cursor = cursor.limit(LIMITE_LISTA)
    return [_salida(d) for d in cursor], total


def pagar(factura_id: str, *, usuario_id: int | None) -> dict:
    """Marca como pagada. Solo desde pendiente, radicada o glosada (atómico)."""
    from pymongo import ReturnDocument  # noqa: PLC0415
    db = _db()
    r = db["facturas"].find_one_and_update(
        {"id": factura_id, "estado_pago": {"$in": ["pendiente", "radicada", "glosada"]}},
        {"$set": {"estado_pago": "pagada", "pagada_at": _ahora(), "pagada_por": usuario_id}},
        return_document=ReturnDocument.AFTER)
    if r is None:
        _explicar_conflicto(db, factura_id, "pagar")
    return _salida(r)


def anular(factura_id: str, motivo: str, *, usuario_id: int | None) -> dict:
    """
    Anula con motivo. Una factura ya pagada NO se anula: en la práctica se
    corrige con una nota crédito, que este prototipo no modela.
    """
    from pymongo import ReturnDocument  # noqa: PLC0415
    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise ErrorContabilidad(422, "El motivo de la anulación debe tener al menos 5 caracteres")
    db = _db()
    r = db["facturas"].find_one_and_update(
        {"id": factura_id, "estado_pago": {"$in": ["pendiente", "radicada", "glosada"]}},
        {"$set": {"estado_pago": "anulada", "anulada_at": _ahora(), "anulada_por": usuario_id,
                  "motivo_anulacion": motivo[:300]}},
        return_document=ReturnDocument.AFTER)
    if r is None:
        _explicar_conflicto(db, factura_id, "anular")
    return _salida(r)


def _explicar_conflicto(db, factura_id: str, accion: str) -> None:
    actual = db["facturas"].find_one({"id": factura_id}, {"estado_pago": 1})
    if actual is None:
        raise ErrorContabilidad(404, "Factura no encontrada")
    estado = actual["estado_pago"]
    extra = " Una factura pagada se corrige con nota crédito." if accion == "anular" and estado == "pagada" else ""
    raise ErrorContabilidad(409, f"No se puede {accion} una factura en estado '{estado}'.{extra}")


def tarifario() -> list[dict]:
    db = _db()
    return [{k: v for k, v in t.items() if k != "_id"} for t in db["tarifario"].find().sort("codigo", 1)]


# ---------------------------------------------------------------- apoyo para los reactores
def datos_para_factura(db_pg, paciente_id: str) -> dict:
    """
    Nombre, documento enmascarado y cobertura de un paciente, leídos de
    PostgreSQL en el servidor (el contable no consulta pacientes). Devuelve {}
    si el paciente no existe. Lo usan POST /contabilidad/facturas y el reactor
    al_aprobar_reporte de José David.
    """
    from app.models import Paciente  # noqa: PLC0415
    p = db_pg.get(Paciente, paciente_id)
    if p is None:
        return {}
    eps = getattr(p, "eps", None)
    if eps is None or getattr(eps, "codigo", None) in (None, "PART"):
        cob = dict(PARTICULAR)
    else:
        regimen = getattr(eps, "regimen", None)
        cob = {"tipo": "especial" if regimen == "especial" else "eps",
               "entidad": getattr(eps, "nombre", None), "regimen": regimen}
    nombre = f"{descifrar(p.nombre_cifrado, 'pacientes.nombre')} {descifrar(p.apellido_cifrado, 'pacientes.apellido')}"
    documento = descifrar(p.documento_cifrado, "pacientes.documento")
    return {"paciente_nombre": nombre, "paciente_documento": enmascarar(documento), "cobertura": cob}
