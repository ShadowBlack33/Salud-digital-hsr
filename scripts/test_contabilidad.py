#!/usr/bin/env python3
"""
Pruebas del módulo de contabilidad (R09). No necesitan PostgreSQL ni la API arriba.

Prueba las rutas /contabilidad/* con el cliente de pruebas de FastAPI: la
autenticación se reemplaza por un usuario falso con el rol que se quiera, y el
servicio de contabilidad se conecta a:

  * un MongoDB simulado (mongomock)  -> por defecto:    pip install mongomock
  * un MongoDB real                  -> con MONGO_URL_PRUEBA, por ejemplo el del compose:
        MONGO_URL_PRUEBA="mongodb://hsr:<MONGO_PASSWORD>@localhost:27017/?authSource=admin" \\
        python scripts/test_contabilidad.py
    (usa una base temporal "hsr_prueba_xxxx" y la borra al terminar)

La prueba de concurrencia (20 aprobaciones simultáneas del mismo reporte) solo
corre contra Mongo real, porque comprueba el índice único de la base.

Uso:  python scripts/test_contabilidad.py
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import threading
import uuid
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

# Claves de prueba ANTES de importar la app (nunca las reales).
from app.core.crypto import generar_clave  # noqa: E402

os.environ.setdefault("APP_ENCRYPTION_KEY", generar_clave())
os.environ.setdefault("APP_BLIND_INDEX_KEY", generar_clave())
os.environ.setdefault("JWT_SECRET_KEY", generar_clave())

from fastapi.testclient import TestClient  # noqa: E402

from app.api import contabilidad as api  # noqa: E402
from app.core.crypto import enmascarar  # noqa: E402
from app.core.deps import ContextoAcceso, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import LogAuditoria  # noqa: E402
from app.services import contabilidad as svc  # noqa: E402

# ------------------------------------------------------------------ infraestructura de la prueba
OK, FALLAS = 0, []


def comprobar(n: int, descripcion: str, condicion: bool, detalle: str = "") -> None:
    global OK
    if condicion:
        OK += 1
        print(f"  ✔ [{n:02d}] {descripcion}")
    else:
        FALLAS.append(n)
        print(f"  ✘ [{n:02d}] {descripcion}  {detalle}")


class BDFalsa:
    """Sustituye a la sesión de PostgreSQL: solo guarda lo que se audita."""
    def __init__(self):
        self.agregados, self.commits = [], 0

    def add(self, obj):
        self.agregados.append(obj)

    def commit(self):
        self.commits += 1

    def auditoria(self, **filtro):
        return [a for a in self.agregados if isinstance(a, LogAuditoria)
                and all(getattr(a, k) == v for k, v in filtro.items())]


BD = BDFalsa()
ROL = {"actual": "contable"}
PACIENTES = {
    "pac_contrib": {"paciente_nombre": "Andrés Caicedo", "paciente_documento": "****6591",
                    "cobertura": {"tipo": "eps", "entidad": "EPS Alfa", "regimen": "contributivo"}},
    "pac_subs": {"paciente_nombre": "María Mosquera", "paciente_documento": "****1180",
                 "cobertura": {"tipo": "eps", "entidad": "EPS Gamma", "regimen": "subsidiado"}},
    "pac_part": {"paciente_nombre": "Luz Valencia", "paciente_documento": "****7742",
                 "cobertura": {"tipo": "particular", "entidad": "Particular", "regimen": None}},
}


def _ctx_falso():
    usuario = SimpleNamespace(id=7, rol=SimpleNamespace(codigo=ROL["actual"]))
    return ContextoAcceso(usuario=usuario, payload={}, alcance="all", recurso="facturacion",
                          accion="read", db=BD, request=None)


# El nivel 1 (RequierePermiso) se reemplaza por un usuario falso; el chequeo de ROL es el real.
_dep_permiso = inspect.signature(api.contable).parameters["ctx"].default.dependency
app.dependency_overrides[_dep_permiso] = _ctx_falso
app.dependency_overrides[get_db] = lambda: BD
svc.datos_para_factura = lambda db, pid: dict(PACIENTES.get(pid, {}))   # PostgreSQL simulado

# ------------------------------------------------------------------ Mongo (simulado o real)
REAL = bool(os.getenv("MONGO_URL_PRUEBA"))
if REAL:
    import pymongo
    _cliente = pymongo.MongoClient(os.environ["MONGO_URL_PRUEBA"], serverSelectionTimeoutMS=4000, tz_aware=True)
    _nombre_bd = f"hsr_prueba_{uuid.uuid4().hex[:8]}"
    BASE = _cliente[_nombre_bd]
else:
    try:
        import mongomock
    except ImportError:
        sys.exit("Falta mongomock:  pip install mongomock   (o defina MONGO_URL_PRUEBA para usar un Mongo real)")
    BASE = mongomock.MongoClient(tz_aware=True)["hsr_prueba"]
svc.usar_base(BASE)

c = TestClient(app, raise_server_exceptions=False)


def post(**campos):
    base = {"paciente_id": "pac_contrib", "servicio": "laboratorio", "valor": 100000}
    return c.post("/contabilidad/facturas", json={**base, **campos})


# ------------------------------------------------------------------ pruebas
def main() -> int:
    print(f"\nMongo: {'REAL (' + _nombre_bd + ')' if REAL else 'simulado (mongomock)'}\n")

    print("Lista vacía y esquema")
    r = c.get("/contabilidad/facturas")
    comprobar(1, "GET /facturas sin datos devuelve lista vacía", r.status_code == 200 and r.json() == [], r.text)
    nombres_ix = set(BASE["facturas"].index_information())
    comprobar(2, "índices creados (id, reporte_id, fecha, tipo/estado, entidad, paciente)",
              {"uq_id", "uq_reporte_id", "ix_fecha", "ix_tipo_estado_fecha", "ix_entidad_estado", "ix_paciente_fecha"} <= nombres_ix,
              str(nombres_ix))

    print("\nCrear facturas y reparto paciente/entidad")
    r = post(servicio="cirugia", valor=1_000_000)
    f1 = r.json()
    comprobar(3, "POST crea la factura (201) con id F-250001", r.status_code == 201 and f1.get("id") == "F-250001", r.text)
    comprobar(4, "campos obligatorios del enunciado presentes",
              all(k in f1 for k in ("id", "paciente_id", "servicio", "valor", "fecha", "estado_pago")), str(f1))
    comprobar(5, "copago 11,5 % contributivo: paciente 115.000, entidad 885.000",
              (f1.get("valor_paciente"), f1.get("valor_entidad")) == (115000, 885000), str(f1))
    comprobar(6, "se completan nombre, documento enmascarado y cobertura desde el paciente",
              f1.get("paciente_nombre") == "Andrés Caicedo" and f1.get("paciente_documento") == "****6591"
              and f1["cobertura"]["entidad"] == "EPS Alfa", str(f1))
    crudo = BASE["facturas"].find_one({"id": "F-250001"})
    texto_crudo = json.dumps(crudo, default=str, ensure_ascii=False)
    comprobar(7, "en Mongo el nombre NO está en claro (va cifrado) y hay índice ciego",
              "Caicedo" not in texto_crudo and "Andrés" not in texto_crudo
              and crudo["paciente_nombre_cifrado"].startswith("v1:") and crudo["nombre_bidx"], texto_crudo[:200])

    casos = [
        ("subsidiado + consulta -> cuota 0", dict(paciente_id="pac_subs", servicio="consulta", valor=68000), (0, 68000)),
        ("contributivo + urgencias -> cuota moderadora 4.700", dict(servicio="urgencias", valor=145000), (4700, 140300)),
        ("subsidiado + hospitalización -> copago 10 %", dict(paciente_id="pac_subs", servicio="hospitalizacion", valor=420000), (42000, 378000)),
        ("particular -> paga todo", dict(paciente_id="pac_part", servicio="imagenologia", valor=62000), (62000, 0)),
        ("SOAT -> paga todo la entidad", dict(servicio="cirugia", valor=500000, cobertura={"tipo": "soat", "entidad": "SOAT", "regimen": None}), (0, 500000)),
        ("prepagada -> bono de 35.000", dict(servicio="cirugia", valor=500000, cobertura={"tipo": "prepagada", "entidad": "Prepagada X", "regimen": None}), (35000, 465000)),
    ]
    for i, (texto, campos, esperado) in enumerate(casos, start=8):
        r = post(**campos)
        j = r.json()
        comprobar(i, f"reparto: {texto}", r.status_code == 201 and (j.get("valor_paciente"), j.get("valor_entidad")) == esperado, r.text)

    print("\nDeducción de tipo de cobro y datos sensibles")
    comprobar(14, "servicio 'laboratorio' -> tipo laboratorio", post(servicio="laboratorio").json()["tipo_cobro"] == "laboratorio")
    comprobar(15, "CUPS 904902 (gases) con servicio libre -> laboratorio",
              post(servicio="examen", cups="904902").json()["tipo_cobro"] == "laboratorio")
    comprobar(16, "servicio desconocido -> 'otros'", post(servicio="algo raro").json()["tipo_cobro"] == "otros")
    comprobar(17, "servicio analisis_ia -> tipo 'ia'", post(servicio="analisis_ia").json()["tipo_cobro"] == "ia")
    f = post(paciente_documento="1130456591").json()
    comprobar(18, "una cédula completa se guarda enmascarada igual que en el resto del sistema (******6591)",
              f.get("paciente_documento") == enmascarar("1130456591") == "******6591"
              and "1130456591" not in json.dumps(BASE["facturas"].find_one({"id": f["id"]}), default=str), str(f))

    print("\nValidaciones")
    comprobar(19, "valor <= 0 -> 422", post(valor=0).status_code == 422)
    comprobar(20, "paciente inexistente -> 404", post(paciente_id="no_existe").status_code == 404)
    comprobar(21, "reparto que no suma el valor -> 422",
              post(valor=100000, valor_paciente=30000, valor_entidad=30000).status_code == 422)
    comprobar(22, "estado 'anulada' no se puede usar al crear", post(estado_pago="anulada").status_code == 422)

    print("\nFactura automática de un reporte de IA (idempotente)")
    r1 = c.post("/contabilidad/facturas", json={"paciente_id": "pac_contrib", "servicio": "analisis_ia", "valor": 85000, "reporte_id": 412})
    r2 = c.post("/contabilidad/facturas", json={"paciente_id": "pac_contrib", "servicio": "analisis_ia", "valor": 85000, "reporte_id": 412})
    comprobar(23, "primera aprobación: 201; segunda del mismo reporte: 200 con la MISMA factura",
              r1.status_code == 201 and r2.status_code == 200 and r1.json()["id"] == r2.json()["id"], f"{r1.status_code} {r2.status_code}")
    comprobar(24, "queda UNA sola factura con reporte_id=412 y es automática",
              BASE["facturas"].count_documents({"reporte_id": 412}) == 1 and r1.json()["origen"] == "automatica")
    f_a, creada_a = svc.facturar_reporte(500, "pac_contrib", paciente_nombre="X Y")
    f_b, creada_b = svc.facturar_reporte(500, "pac_contrib", paciente_nombre="X Y")
    comprobar(25, "facturar_reporte() (la función del reactor) también es idempotente",
              creada_a is True and creada_b is False and f_a["id"] == f_b["id"] and f_a["valor"] == 85000)
    if REAL:
        resultados: list[bool] = []
        def aprobar():
            resultados.append(svc.facturar_reporte(999, "pac_contrib")[1])
        hilos = [threading.Thread(target=aprobar) for _ in range(20)]
        [h.start() for h in hilos]
        [h.join() for h in hilos]
        comprobar(26, "20 aprobaciones SIMULTÁNEAS del mismo reporte -> una sola factura",
                  sum(resultados) == 1 and BASE["facturas"].count_documents({"reporte_id": 999}) == 1,
                  f"creadas={sum(resultados)}")
    else:
        print("  - [26] concurrencia: omitida (necesita Mongo real: MONGO_URL_PRUEBA)")

    print("\nPagar y anular")
    base_id = post(valor=200000).json()["id"]
    r = c.patch(f"/contabilidad/facturas/{base_id}/pagar")
    comprobar(27, "pagar una pendiente -> 200 y estado pagada", r.status_code == 200 and r.json()["estado_pago"] == "pagada", r.text)
    comprobar(28, "pagar otra vez -> 409", c.patch(f"/contabilidad/facturas/{base_id}/pagar").status_code == 409)
    r = c.patch(f"/contabilidad/facturas/{base_id}/anular", json={"motivo": "Error de digitación"})
    comprobar(29, "anular una PAGADA -> 409 (se corrige con nota crédito)", r.status_code == 409 and "nota crédito" in r.text, r.text)
    comprobar(30, "pagar una inexistente -> 404", c.patch("/contabilidad/facturas/F-1/pagar").status_code == 404)
    otra = post(valor=50000).json()["id"]
    comprobar(31, "anular sin motivo suficiente -> 422", c.patch(f"/contabilidad/facturas/{otra}/anular", json={"motivo": "no"}).status_code == 422)
    r = c.patch(f"/contabilidad/facturas/{otra}/anular", json={"motivo": "Paciente equivocado"})
    comprobar(32, "anular una pendiente con motivo -> 200, estado anulada y motivo guardado",
              r.status_code == 200 and r.json()["estado_pago"] == "anulada" and r.json()["motivo_anulacion"] == "Paciente equivocado", r.text)
    comprobar(33, "pagar una anulada -> 409", c.patch(f"/contabilidad/facturas/{otra}/pagar").status_code == 409)

    print("\nListado y filtros")
    todas = c.get("/contabilidad/facturas").json()
    comprobar(34, "sin parámetros devuelve una LISTA con todas (lo que espera el front)",
              isinstance(todas, list) and len(todas) == BASE["facturas"].count_documents({}))
    comprobar(35, "más recientes primero", [x["fecha"] for x in todas] == sorted((x["fecha"] for x in todas), reverse=True))
    comprobar(36, "filtro por tipo=cirugia", all(x["tipo_cobro"] == "cirugia" for x in c.get("/contabilidad/facturas?tipo=cirugia").json()))
    comprobar(37, "filtro por estado=anulada", [x["id"] for x in c.get("/contabilidad/facturas?estado=anulada").json()] == [otra])
    comprobar(38, "filtro por entidad", all(x["cobertura"]["entidad"] == "EPS Gamma" for x in c.get("/contabilidad/facturas?entidad=EPS Gamma").json()))
    comprobar(39, "búsqueda por número de factura", [x["id"] for x in c.get("/contabilidad/facturas?q=F-250001").json()] == ["F-250001"])
    comprobar(40, "búsqueda por CUPS", all(x.get("cups") == "904902" for x in c.get("/contabilidad/facturas?q=904902").json()))
    por_doc = c.get("/contabilidad/facturas?q=6591").json()
    comprobar(41, "búsqueda por documento (últimos dígitos)",
              len(por_doc) > 0 and all(x["paciente_documento"].endswith("6591") for x in por_doc))
    por_nombre = c.get("/contabilidad/facturas?q=caicedo").json()
    comprobar(42, "búsqueda por nombre (palabra completa, sin acentos ni mayúsculas) vía índice ciego",
              len(por_nombre) > 0 and all("Caicedo" in x["paciente_nombre"] for x in por_nombre))
    comprobar(43, "búsqueda 'andres' encuentra 'Andrés'", len(c.get("/contabilidad/facturas?q=andres").json()) == len(por_nombre))
    hoy = todas[0]["fecha"][:10]
    comprobar(44, "rango de fechas: hasta=hoy incluye hoy; hasta=2000-01-01 no incluye nada",
              len(c.get(f"/contabilidad/facturas?desde={hoy}&hasta={hoy}").json()) == len(todas)
              and c.get("/contabilidad/facturas?hasta=2000-01-01").json() == [])
    r = c.get("/contabilidad/facturas?pagina=1&por_pagina=5")
    comprobar(45, "con paginación responde {facturas, total}", r.status_code == 200 and len(r.json()["facturas"]) == 5
              and r.json()["total"] == len(todas), r.text[:120])
    comprobar(46, "fecha inválida -> 422", c.get("/contabilidad/facturas?desde=ayer").status_code == 422)

    print("\nTarifario")
    t = c.get("/contabilidad/tarifario").json()
    comprobar(47, f"tarifario con {len(svc.TARIFARIO)} servicios, ordenado por código, con IA0001 = 85.000",
              len(t) == len(svc.TARIFARIO) and [x["codigo"] for x in t] == sorted(x["codigo"] for x in t)
              and any(x["codigo"] == "IA0001" and x["valor"] == 85000 for x in t))

    print("\nPermisos por rol y auditoría")
    for rol in ("admin", "contable"):
        ROL["actual"] = rol
        comprobar({"admin": 48, "contable": 49}[rol], f"rol {rol}: puede operar", c.get("/contabilidad/facturas").status_code == 200)
    n_denegados = len(BD.auditoria(resultado="denegado"))
    for i, rol in enumerate(("coordinador", "medico", "enfermero_jefe", "especialista"), start=50):
        ROL["actual"] = rol
        r_get, r_post, r_pat = c.get("/contabilidad/facturas"), post(), c.patch("/contabilidad/facturas/F-250001/pagar")
        comprobar(i, f"rol {rol}: 403 en lectura, creación y pago",
                  (r_get.status_code, r_post.status_code, r_pat.status_code) == (403, 403, 403))
    ROL["actual"] = "contable"
    comprobar(54, "cada intento denegado queda auditado", len(BD.auditoria(resultado="denegado")) - n_denegados == 12)
    creaciones = BD.auditoria(entidad_tipo="factura", operacion="create")
    comprobar(55, "crear, pagar y anular quedan auditados (entidad 'factura')",
              len(creaciones) > 0 and any(a.valor_nuevo and a.valor_nuevo.get("estado_pago") == "pagada" for a in BD.auditoria(operacion="update"))
              and any(a.valor_nuevo and a.valor_nuevo.get("estado_pago") == "anulada" for a in BD.auditoria(operacion="update")))
    comprobar(56, "la auditoría nunca guarda nombre ni documento del paciente",
              not any("Caicedo" in json.dumps(a.valor_nuevo or {}, default=str) or "6591" in json.dumps(a.valor_nuevo or {}, default=str)
                      for a in BD.auditoria(entidad_tipo="factura")))

    import re
    js = (RAIZ / "front" / "src" / "lib" / "facturacion.js").read_text(encoding="utf-8")
    bloque = js.split("export const TARIFARIO", 1)[1].split("].map(", 1)[0]
    del_front = [(a, b, tipo, int(v)) for a, b, tipo, v in re.findall(r'\["([^"]+)", "([^"]+)", "([^"]+)", (\d+)\]', bloque)]
    comprobar(58, f"el tarifario coincide exactamente con el del front ({len(del_front)} servicios)",
              del_front == svc._TARIFA, f"front={len(del_front)} api={len(svc._TARIFA)}")

    print("\nMongo caído")
    original = svc.listar
    def caido(**_):
        import pymongo.errors
        raise pymongo.errors.ServerSelectionTimeoutError("sin conexión")
    svc.listar = caido
    r = c.get("/contabilidad/facturas")
    svc.listar = original
    comprobar(57, "si MongoDB no responde, la ruta contesta 503 (la API sigue viva)", r.status_code == 503, r.text)

    print(f"\n{OK} verificaciones correctas, {len(FALLAS)} fallidas" + (f" -> {FALLAS}" if FALLAS else ""))
    return 1 if FALLAS else 0


if __name__ == "__main__":
    try:
        codigo = main()
    finally:
        if REAL:
            _cliente.drop_database(_nombre_bd)
    sys.exit(codigo)
