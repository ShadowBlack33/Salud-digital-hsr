#!/usr/bin/env python3
"""
Prueba del sistema activo: canal en vivo, bandeja, flujos automáticos, alertas
y FHIR reactivo (R17 a R21).

Levanta la API en un servidor real (uvicorn, en un hilo) porque el canal SSE
necesita una conexión HTTP abierta; abre un canal por rol, como lo haría el
navegador, y comprueba que cada hecho llega SOLO a quien le corresponde y en
menos de ESPERA segundos, sin sondeo.

Lo que depende de servicios externos se prueba aislado:
  · MongoDB: la factura automática se prueba contra una colección simulada
    (la idempotencia y el reactor son lo que se valida, no pymongo).
  · HAPI: el registro de la Subscription se prueba con un transporte HTTP
    simulado; la Observation se entrega al receptor tal como lo hace HAPI.

Uso:  python scripts/test_tiempo_real.py        (necesita la base con db/13)
"""
from __future__ import annotations

import json
import os
import random
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

os.environ.setdefault("TAREAS_FONDO", "false")          # las tareas de fondo se invocan a mano
os.environ.setdefault("HOOK_SECRET", "secreto-de-prueba")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.deps import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.services import bandeja, eventos, facturacion_auto, fhir_reactivo, reactores  # noqa: E402

PASSWORD = "Demo#Hospital2026"
ESPERA = 8          # segundos: el máximo que fija el enunciado entre el hecho y el evento
PUERTO = 18000 + random.randint(0, 999)
BASE = f"http://127.0.0.1:{PUERTO}"
SECRETO = get_settings().hook_secret
DOC_PRUEBA = f"98{random.randint(10_000_000, 99_999_999)}"

ok = fallos = 0


def check(descripcion: str, condicion: bool, detalle: str = ""):
    global ok, fallos
    if condicion:
        ok += 1
        print(f"  PASA  {descripcion}")
    else:
        fallos += 1
        print(f"  FALLA {descripcion}  {detalle}")


# ------------------------------------------------------------------ servidor
servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PUERTO, log_level="warning",
                                         timeout_graceful_shutdown=1))
threading.Thread(target=servidor.run, daemon=True).start()
for _ in range(100):
    if servidor.started:
        break
    time.sleep(0.1)
if not servidor.started:
    print("No arrancó el servidor de prueba")
    sys.exit(2)

http = httpx.Client(base_url=BASE, timeout=20)


def entrar(usuario: str, clave: str = PASSWORD) -> str | None:
    r = http.post("/auth/login", json={"username": usuario, "password": clave})
    return r.json()["access_token"] if r.status_code == 200 else None


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class Canal:
    """Un EventSource simulado: guarda cada evento que llega por el canal."""

    def __init__(self, token: str | None, **parametros):
        self.eventos: list[dict] = []
        self.status: int | None = None
        self.tipo_contenido = ""
        self.cabeceras: dict = {}
        self.listo = threading.Event()
        self.token = token
        self.parametros = parametros
        threading.Thread(target=self._leer, daemon=True).start()
        self.listo.wait(10)

    def _leer(self):
        params = dict(self.parametros)
        if self.token:
            params["token"] = self.token
        try:
            with httpx.Client(base_url=BASE, timeout=None) as c:
                with c.stream("GET", "/eventos/stream", params=params) as r:
                    self.status = r.status_code
                    self.tipo_contenido = r.headers.get("content-type", "")
                    self.cabeceras = dict(r.headers)
                    self.listo.set()
                    if r.status_code != 200:
                        return
                    for linea in r.iter_lines():
                        if linea.startswith("data: "):
                            self.eventos.append(json.loads(linea[6:]))
        except Exception:  # noqa: BLE001
            pass
        finally:
            self.listo.set()

    def esperar(self, condicion, segundos: float = ESPERA):
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            for e in list(self.eventos):
                if condicion(e):
                    return e
            time.sleep(0.05)
        return None

    def recibio(self, condicion) -> bool:
        return any(condicion(e) for e in list(self.eventos))


def tipo(t: str):
    return lambda e: e["tipo"] == t


print("=" * 70)
print("PRUEBA DEL SISTEMA ACTIVO — canal en vivo, bandeja, flujos, FHIR")
print("=" * 70)

# ------------------------------------------------------------ cuentas y datos
tok = {rol: entrar(u) for rol, u in {"admin": "admin", "medico": "medico01", "especialista": "especialista01",
                                       "contable": "contable01", "paciente": "paciente_demo"}.items()}
print("\n[0] Preparación")
check("Los cinco roles inician sesión", all(tok.values()), str({k: bool(v) for k, v in tok.items()}))
if not all(tok.values()):
    print("Faltan cuentas de demostración (db/09_perfiles.sql y scripts/casos_demo.py).")
    sys.exit(2)

with SessionLocal() as db:
    ids = {u: i for u, i in db.execute(text("SELECT username, id FROM usuarios")).all()}
    personal_esp = db.execute(text("SELECT personal_id FROM usuarios WHERE username = 'especialista01'")).scalar()
    hay_tablas = db.execute(text("SELECT to_regclass('public.notificaciones') IS NOT NULL")).scalar()
check("La migración db/13 está aplicada", bool(hay_tablas))
if not hay_tablas:
    sys.exit(2)

# --------------------------------------------------------------- [1] canal SSE
print("\n[1] Canal en vivo: autenticación y formato (R17)")
sin = Canal(None)
check("Sin token se rechaza (401)", sin.status == 401, str(sin.status))
mal = Canal("no.es.un.jwt")
check("Con un token inválido se rechaza (401)", mal.status == 401, str(mal.status))
tok_temp = entrar("medico01")
http.post("/auth/logout", headers=h(tok_temp), json={"refresh_token": "x"})
cerrado = Canal(tok_temp)
check("Con una sesión ya cerrada se rechaza (401)", cerrado.status == 401, str(cerrado.status))

canales = {rol: Canal(t) for rol, t in tok.items()}
check("Los cinco roles abren el canal (200)", all(c.status == 200 for c in canales.values()),
      str({r: c.status for r, c in canales.items()}))
c0 = canales["medico"]
check("Es text/event-stream", c0.tipo_contenido.startswith("text/event-stream"), c0.tipo_contenido)
check("Pide a nginx que no lo bufferice (X-Accel-Buffering: no)", c0.cabeceras.get("x-accel-buffering") == "no")
check("No se cachea", "no-cache" in c0.cabeceras.get("cache-control", ""))
header_auth = Canal(None)  # sin ?token ni cabecera
check("Sin credenciales de ninguna clase -> 401", header_auth.status == 401)

# ----------------------------------------------------- [2] remisión (R19 fila 1)
print("\n[2] El médico remite: el especialista se entera solo (R19)")
nuevo = {"tipo_documento": "CC", "documento": DOC_PRUEBA, "nombre": "Canario", "apellido": "Reactivo Prueba",
         "telefono": "3001112233", "fecha_nacimiento": "1975-06-01", "sexo": "M", "consentimiento_datos": True}
r = http.post("/pacientes", json=nuevo, headers=h(tok["medico"]))
check("El médico crea un paciente (201)", r.status_code == 201, r.text[:120])
pid = r.json()["paciente_id"]

antes = http.get("/pendientes", headers=h(tok["especialista"])).json()["remisiones_recibidas"]
t0 = time.monotonic()
r = http.post("/remisiones", headers=h(tok["medico"]),
              json={"paciente_id": pid, "especialista_id": personal_esp, "motivo": "Valoración por soplo cardiaco",
                    "prioridad": "urgente"})
check("Remitir devuelve el id (201)", r.status_code == 201 and "id" in r.json(), r.text[:150])
rem_id = r.json().get("id")
ev = canales["especialista"].esperar(tipo("remision_nueva"))
demora = time.monotonic() - t0
check(f"El especialista recibe el evento en vivo ({demora:.2f} s < {ESPERA} s)", ev is not None and demora < ESPERA)
check("El evento trae tipo, mensaje, fecha y paciente_id",
      bool(ev) and all(ev.get(k) for k in ("tipo", "mensaje", "fecha", "paciente_id")), str(ev))
check("Y el id de la remisión", bool(ev) and ev.get("remision_id") == rem_id, str(ev))
check("El aviso no lleva el nombre ni el documento del paciente",
      bool(ev) and "Canario" not in json.dumps(ev) and DOC_PRUEBA not in json.dumps(ev))
time.sleep(1.5)
check("El paciente NO recibe nada por su canal", not canales["paciente"].eventos, str(canales["paciente"].eventos))
check("El contable NO recibe nada por su canal", not canales["contable"].eventos, str(canales["contable"].eventos))
check("Quien remitió no recibe su propio aviso", not canales["medico"].recibio(tipo("remision_nueva")))

# ------------------------------------------------------------ [3] bandeja
print("\n[3] Bandeja persistente y trabajo pendiente (R18)")
r = http.get("/notificaciones", headers=h(tok["especialista"]))
lista = r.json() if r.status_code == 200 else []
mia = next((n for n in lista if n.get("remision_id") == rem_id), None)
check("La remisión quedó en la bandeja del especialista", mia is not None, r.text[:150])
check("Cada notificación trae id, tipo, mensaje, leida y fecha",
      bool(mia) and all(k in mia for k in ("id", "tipo", "mensaje", "leida", "fecha")))
check("Llega sin leer", bool(mia) and mia["leida"] is False)
check("Sobrevive a reconectar: una conexión nueva sigue viendo la bandeja",
      any(n.get("remision_id") == rem_id for n in http.get("/notificaciones", headers=h(entrar("especialista01"))).json()))
for rol in ("admin", "medico", "especialista", "contable", "paciente"):
    r = http.get("/notificaciones", headers=h(tok[rol]))
    check(f"El rol {rol} tiene bandeja (200, lista)", r.status_code == 200 and isinstance(r.json(), list), r.text[:80])
    p = http.get("/pendientes", headers=h(tok[rol]))
    check(f"El rol {rol} lee sus pendientes (3 contadores)",
          p.status_code == 200 and set(p.json()) == {"reportes_por_revisar", "remisiones_recibidas", "alertas_activas"},
          p.text[:100])
check("No hay notificaciones del paciente ni del contable sobre la remisión",
      not any(n.get("remision_id") == rem_id for n in http.get("/notificaciones", headers=h(tok["paciente"])).json())
      and not any(n.get("remision_id") == rem_id for n in http.get("/notificaciones", headers=h(tok["contable"])).json()))
pend = http.get("/pendientes", headers=h(tok["especialista"])).json()
check("El contador de remisiones recibidas subió", pend["remisiones_recibidas"] == antes + 1, f"{antes} -> {pend}")
r = http.post(f"/notificaciones/{mia['id']}/leer", headers=h(tok["medico"]))
check("Otro usuario no puede marcarla como leída (404, no se revela)", r.status_code == 404, str(r.status_code))
check("... y sigue sin leer para su dueño",
      next(n for n in http.get("/notificaciones", headers=h(tok["especialista"])).json() if n["id"] == mia["id"])["leida"] is False)
r = http.post(f"/notificaciones/{mia['id']}/leer", headers=h(tok["especialista"]))
check("Su dueño la marca como leída (2xx, leida: true)", r.status_code == 200 and r.json()["leida"] is True, r.text[:100])
check("Sin token no hay bandeja (401)", http.get("/notificaciones").status_code == 401)
check("Sin token no hay pendientes (401)", http.get("/pendientes").status_code == 401)

# ------------------------------------------------------ [4] aceptar / rechazar
print("\n[4] El especialista acepta y rechaza: el médico se entera (R19)")
r = http.post(f"/remisiones/{rem_id}/aceptar", headers=h(tok["especialista"]))
check("El especialista acepta (2xx)", r.status_code == 200, r.text[:120])
ev = canales["medico"].esperar(tipo("remision_aceptada"))
check("El médico remitente recibe 'remision_aceptada' en vivo", ev is not None and ev.get("remision_id") == rem_id, str(ev))
check("Y queda en su bandeja",
      any(n["tipo"] == "remision_aceptada" and n.get("remision_id") == rem_id
          for n in http.get("/notificaciones", headers=h(tok["medico"])).json()))
check("El contador del especialista bajó al resolverla",
      http.get("/pendientes", headers=h(tok["especialista"])).json()["remisiones_recibidas"] == antes)
r = http.post("/remisiones", headers=h(tok["medico"]),
              json={"paciente_id": pid, "especialista_id": personal_esp, "motivo": "Segunda opinión", "prioridad": "rutinaria"})
rem2 = r.json().get("id")
canales["especialista"].esperar(lambda e: e["tipo"] == "remision_nueva" and e.get("remision_id") == rem2)
r = http.post(f"/remisiones/{rem2}/rechazar", headers=h(tok["especialista"]), json={"motivo": "No es de mi especialidad"})
check("El especialista la rechaza con motivo (2xx)", r.status_code == 200, r.text[:120])
ev = canales["medico"].esperar(lambda e: e["tipo"] == "remision_rechazada" and e.get("remision_id") == rem2)
check("El médico recibe 'remision_rechazada' en vivo", ev is not None, str(ev))
check("El aviso del rechazo no copia el motivo clínico", bool(ev) and "especialidad" not in ev["mensaje"])
check("Aceptar sin ser el destinatario sigue prohibido",
      http.post(f"/remisiones/{rem2}/aceptar", headers=h(tok["medico"])).status_code in (403, 409))

# --------------------------------------------------------- [5] bloqueo
print("\n[5] Cuenta bloqueada: el admin recibe el aviso (R19)")
with SessionLocal() as db:
    victima = db.execute(text("SELECT username, id FROM usuarios WHERE username LIKE 'enfe%' AND activo ORDER BY id LIMIT 1")).first()
nombre_v, id_v = victima
for _ in range(3):
    r = http.post("/auth/login", json={"username": nombre_v, "password": "incorrecta-0A!"})
check("Al tercer intento fallido la cuenta responde 423", r.status_code == 423, str(r.status_code))
ev = canales["admin"].esperar(lambda e: e["tipo"] == "cuenta_bloqueada" and e.get("usuario_afectado") == nombre_v)
check("El admin recibe 'cuenta_bloqueada' en vivo con el usuario afectado",
      ev is not None and nombre_v in ev["mensaje"], str(ev))
check("Ningún otro rol se entera", not any(canales[r_].recibio(tipo("cuenta_bloqueada"))
                                           for r_ in ("medico", "especialista", "contable", "paciente")))
check("Queda en la bandeja del admin",
      any(n["tipo"] == "cuenta_bloqueada" for n in http.get("/notificaciones", headers=h(tok["admin"])).json()))
check("Un intento correcto sobre la cuenta bloqueada se rechaza",
      http.post("/auth/login", json={"username": nombre_v, "password": PASSWORD}).status_code in (401, 403, 423, 429))
r = http.post(f"/usuarios/{id_v}/desbloquear", headers=h(tok["admin"]))
check("El admin la desbloquea", r.status_code == 200, r.text[:100])
check("Y ahora entra", http.post("/auth/login", json={"username": nombre_v, "password": PASSWORD}).status_code == 200)

# ------------------------------------------- [6] aprobar reporte -> factura
print("\n[6] Aprobar un reporte crea la factura sola, una sola vez (R19)")


class ColeccionFalsa:
    """Imita lo mínimo de pymongo.Collection que usa facturacion_auto."""
    def __init__(self):
        self.docs, self.llamadas = {}, 0

    def find_one_and_update(self, filtro, cambio, upsert=False, return_document=None):
        self.llamadas += 1
        if filtro["reporte_id"] not in self.docs and upsert:
            self.docs[filtro["reporte_id"]] = dict(cambio["$setOnInsert"], _id=object())
        return dict(self.docs[filtro["reporte_id"]])

    def find_one(self, filtro):
        return dict(self.docs.get(filtro["reporte_id"], {})) or None


col = ColeccionFalsa()
_original = facturacion_auto._coleccion
facturacion_auto._coleccion = lambda: col
reporte_id = random.randint(100_000, 999_999)


def aprobar(rid):
    with SessionLocal() as db:
        reactores.al_aprobar_reporte(db, {"id": rid, "paciente_id": pid})
        db.commit()


aprobar(reporte_id)
ev = canales["contable"].esperar(lambda e: e["tipo"] == "factura_creada" and e.get("reporte_id") == reporte_id)
check("El contable recibe 'factura_creada' en vivo", ev is not None, str(ev))
check("Hay una factura ligada al reporte (reporte_id)", reporte_id in col.docs)
f = col.docs.get(reporte_id, {})
check("Con paciente, servicio, valor, fecha y estado de pago",
      all(f.get(k) is not None for k in ("paciente_id", "servicio", "valor", "fecha", "estado_pago")), str(f))
check("Es automática", f.get("origen") == "automatica")
check("La factura guarda el documento enmascarado, no la cédula", DOC_PRUEBA not in json.dumps(f, default=str))
aprobar(reporte_id)
check("Aprobar dos veces deja UNA sola factura (idempotente)", len(col.docs) == 1, str(len(col.docs)))
check("El médico no recibe el aviso de la factura", not canales["medico"].recibio(tipo("factura_creada")))
check("Ni el paciente", not canales["paciente"].recibio(tipo("factura_creada")))
with SessionLocal() as db:
    aud = db.execute(text("SELECT COUNT(*) FROM log_auditoria WHERE entidad_tipo = 'factura' AND operacion = 'create' "
                          "AND resultado = 'exito' AND valor_nuevo->>'reporte_id' = :r"), {"r": str(reporte_id)}).scalar()
check("La factura quedó en la auditoría", aud >= 1, str(aud))

# Si MongoDB no responde: no se pierde en silencio.
fallo_id = reporte_id + 1
facturacion_auto._coleccion = lambda: (_ for _ in ()).throw(ConnectionError("mongo caído"))
aprobar(fallo_id)
ev = canales["contable"].esperar(lambda e: e["tipo"] == "factura_fallida" and e.get("reporte_id") == fallo_id)
check("Sin MongoDB, el contable recibe 'factura_fallida' (no se pierde en silencio)", ev is not None, str(ev))
check("... y el admin también", canales["admin"].esperar(lambda e: e["tipo"] == "factura_fallida", 3) is not None)
facturacion_auto._coleccion = _original

# ---------------------------------------------------- [7] alerta crítica
print("\n[7] Alerta crítica: en vivo, privada y con aviso de escalamiento (R20)")
# La tabla `alertas` la extiende db/13_ia.sql (módulo de IA). El escalamiento por
# tiempo es de app/api/alertas.py; aquí se prueba lo que es de este módulo: los
# avisos (al_alerta_critica / al_alerta_escalada) y el contador de /pendientes.
with SessionLocal() as db:
    cols = {c for (c,) in db.execute(text("SELECT column_name FROM information_schema.columns "
                                          "WHERE table_name = 'alertas'"))}
if not {"estado", "escalada_at", "paciente_id", "dirigida_a_usuario"} <= cols:
    print("  (omitido: falta aplicar db/13_ia.sql, que extiende la tabla `alertas`)")
else:
    MENSAJE = "El modelo estima 87% de riesgo (umbral 70%). Revise y reconozca la alerta."
    with SessionLocal() as db:
        fila = db.execute(text("""
            INSERT INTO alertas (tipo, severidad, titulo, mensaje, dirigida_a_usuario, paciente_id, estado)
            VALUES ('alerta_critica_ia', 'critica', 'Riesgo crítico de UCI posoperatoria', :m, :u, :p, 'activa')
            RETURNING *
        """), {"m": MENSAJE, "u": ids["medico01"], "p": pid}).mappings().first()
        aid = fila["id"]
        reactores.al_alerta_critica(db, {**dict(fila), "nivel": "critica"})
        db.commit()
    ev = canales["medico"].esperar(lambda e: e["tipo"] == "alerta_critica" and e.get("alerta_id") == aid)
    check("El clínico responsable recibe la alerta en vivo", ev is not None, str(ev))
    check("El especialista (otro clínico) no la recibe", not canales["especialista"].recibio(tipo("alerta_critica")))
    check("El paciente no la recibe", not canales["paciente"].recibio(tipo("alerta_critica")))
    check("El contable no la recibe", not canales["contable"].recibio(tipo("alerta_critica")))
    check("Sube su contador de alertas activas",
          http.get("/pendientes", headers=h(tok["medico"])).json()["alertas_activas"] >= 1)
    check("El admin aún no la ve (no se ha escalado)",
          http.get("/pendientes", headers=h(tok["admin"])).json()["alertas_activas"] == 0)

    # Lo que hace app/api/alertas.py al vencer el plazo: marca escalada_at, audita y llama al reactor.
    with SessionLocal() as db:
        db.execute(text("UPDATE alertas SET escalada_at = NOW() WHERE id = :i"), {"i": aid})
        admins = bandeja.usuarios_con_rol(db, "admin")
        reactores.al_alerta_escalada(db, {**dict(fila), "destinatarios": admins})
        db.commit()
    ev = canales["admin"].esperar(lambda e: e["tipo"] == "alerta_escalada" and e.get("alerta_id") == aid)
    check("El admin recibe 'alerta_escalada' en vivo", ev is not None, str(ev))
    check("El contable no recibe el escalamiento", not canales["contable"].recibio(tipo("alerta_escalada")))
    check("El paciente no recibe el escalamiento", not canales["paciente"].recibio(tipo("alerta_escalada")))
    check("Escalada, el admin la cuenta como activa",
          http.get("/pendientes", headers=h(tok["admin"])).json()["alertas_activas"] >= 1)
    check("... y el clínico la sigue viendo activa",
          http.get("/pendientes", headers=h(tok["medico"])).json()["alertas_activas"] >= 1)
    with SessionLocal() as db:
        db.execute(text("UPDATE alertas SET estado = 'reconocida', reconocida_at = NOW() WHERE id = :i"), {"i": aid})
        db.commit()
    check("Reconocida, deja de contar para el clínico",
          http.get("/pendientes", headers=h(tok["medico"])).json()["alertas_activas"] == 0)
    check("... y para el admin",
          http.get("/pendientes", headers=h(tok["admin"])).json()["alertas_activas"] == 0)

# --------------------------------------------------------- [8] FHIR reactivo
print("\n[8] Una Observation nueva en FHIR hace reaccionar al sistema (R21)")
fhir_id = f"prueba-{random.randint(10**6, 10**7)}"
with SessionLocal() as db:
    db.execute(text("UPDATE pacientes SET fhir_patient_id = :f WHERE documento_bidx = :p"), {"f": fhir_id, "p": pid})
    db.commit()


def observacion(oid, **extra):
    return {"resourceType": "Observation", "id": oid, "meta": {"versionId": "1"}, "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": "2339-0", "display": "Glucose"}]},
            "subject": {"reference": f"Patient/{fhir_id}"},
            "valueQuantity": {"value": 238, "unit": "mg/dL", "system": "http://unitsofmeasure.org", "code": "mg/dL"}, **extra}


oid = f"obs-{random.randint(10**6, 10**7)}"
r = http.post("/fhir-hook/observation", json=observacion(oid))
check("El receptor rechaza llamadas sin el secreto (401)", r.status_code == 401, str(r.status_code))
r = http.post("/fhir-hook/observation", json=observacion(oid), headers={"X-Hook-Secret": "otro"})
check("... y con un secreto equivocado (401)", r.status_code == 401)
check("Nada reaccionó todavía", not canales["medico"].recibio(tipo("fhir_observation")))
t0 = time.monotonic()
r = http.post("/fhir-hook/observation", json=observacion(oid), headers={"X-Hook-Secret": SECRETO})
check("Con el secreto, el receptor procesa la Observation (200)", r.status_code == 200 and r.json()["resultado"] == "procesada", r.text[:120])
ev = canales["medico"].esperar(tipo("fhir_observation"))
check(f"El médico responsable recibe el aviso en vivo ({time.monotonic() - t0:.2f} s)", ev is not None, str(ev))
check("El aviso identifica al paciente por subject.reference", bool(ev) and ev.get("paciente_id") == pid, str(ev))
check("Dice qué llegó (glucosa, LOINC 2339-0, valor)", bool(ev) and "glucosa" in ev["mensaje"] and "2339-0" in ev["mensaje"] and "238" in ev["mensaje"], str(ev))
check("El paciente no recibe el aviso clínico", not canales["paciente"].recibio(tipo("fhir_observation")))
check("El contable no recibe el aviso clínico", not canales["contable"].recibio(tipo("fhir_observation")))
with SessionLocal() as db:
    aud = db.execute(text("SELECT valor_nuevo FROM log_auditoria WHERE entidad_tipo = 'paciente' AND entidad_id = :p "
                          "AND operacion = 'evento_fhir'"), {"p": pid}).scalars().all()
check("Quedó auditado con origen FHIR y el id del paciente",
      len(aud) == 1 and aud[0].get("origen") == "fhir" and aud[0].get("observation_id") == oid, str(aud))
r = http.put(f"/fhir-hook/Observation/{oid}", json=observacion(oid), headers={"X-Hook-Secret": SECRETO})
check("Si HAPI reintenta la misma Observation, no reacciona dos veces", r.json().get("resultado") == "duplicada", r.text[:100])
check("... y el médico no recibe un segundo aviso", sum(1 for e in canales["medico"].eventos if e["tipo"] == "fhir_observation") == 1)
r = http.put(f"/fhir-hook/Observation/{oid}-eco", headers={"X-Hook-Secret": SECRETO},
             json=observacion(f"{oid}-eco", identifier=[{"system": "http://hsanrafael.co/fhir/identifier", "value": "x"}]))
check("Lo que escribió la propia API (eco) no dispara nada", r.json().get("resultado") == "origen_api", r.text[:100])
r = http.post("/fhir-hook/observation", headers={"X-Hook-Secret": SECRETO},
              json=observacion(f"{oid}-huerfana", subject={"reference": "Patient/no-existe-9"}))
check("Una Observation de un paciente desconocido se audita sin avisar a nadie", r.json().get("resultado") == "sin_paciente", r.text[:100])
check("Un ping sin cuerpo no rompe el receptor", http.post("/fhir-hook/observation", headers={"X-Hook-Secret": SECRETO}).status_code == 200)

# --- registro de la Subscription en HAPI (transporte simulado)
registro: dict = {"puts": [], "recurso": None}


def hapi(request: httpx.Request) -> httpx.Response:
    if request.method == "GET":
        if registro["recurso"]:
            return httpx.Response(200, json=registro["recurso"])
        return httpx.Response(404, json={"resourceType": "OperationOutcome"})
    cuerpo = json.loads(request.content)
    registro["puts"].append(cuerpo["criteria"])
    if cuerpo["criteria"] == fhir_reactivo.CRITERIOS[0]:
        return httpx.Response(422, json={"resourceType": "OperationOutcome"})   # HAPI rechaza el más amplio
    registro["recurso"] = dict(cuerpo, status="active")
    return httpx.Response(201, json=registro["recurso"])


cli = httpx.Client(transport=httpx.MockTransport(hapi))
check("Se registra la Subscription en HAPI", fhir_reactivo.asegurar_suscripcion(cli) == "registrada")
s = registro["recurso"] or {}
check("Es rest-hook, hacia el receptor interno de la API, con el secreto en la cabecera",
      s.get("channel", {}).get("type") == "rest-hook"
      and s["channel"]["endpoint"].endswith("/fhir-hook/observation")
      and s["channel"]["header"] == [f"X-Hook-Secret: {SECRETO}"], str(s))
check("Si HAPI rechaza un criterio, prueba el siguiente", len(registro["puts"]) == 2, str(registro["puts"]))
check("Registrarla otra vez no la duplica ni la reescribe", fhir_reactivo.asegurar_suscripcion(cli) == "ya_activa" and len(registro["puts"]) == 2)

# ----------------------------------------------------- [9] robustez de reactores
print("\n[9] Un aviso que falla no tumba la acción de negocio")
original = bandeja.notificar
bandeja.notificar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("falla simulada"))
with SessionLocal() as db:
    reactores.al_remitir(db, {"id": 1, "especialista_id": personal_esp, "remitido_por": ids["medico01"], "paciente_id": pid})
    sigue = db.execute(text("SELECT 1")).scalar()
    db.commit()
bandeja.notificar = original
check("Un reactor que lanza no deja la transacción inutilizable", sigue == 1)


@reactores._seguro
def _reactor_roto(db):
    db.execute(text("SELECT * FROM tabla_que_no_existe"))


with SessionLocal() as db:
    db.execute(text("UPDATE usuarios SET ultimo_acceso = ultimo_acceso WHERE id = :i"), {"i": ids["medico01"]})
    _reactor_roto(db)          # un error de SQL dentro del reactor aborta... solo su savepoint
    try:
        db.commit()
        confirmo = True
    except Exception:  # noqa: BLE001
        confirmo = False
check("Un error de SQL dentro del reactor no impide el commit del hecho", confirmo)

n0 = len(canales["medico"].eventos)
with SessionLocal() as db:
    bandeja.notificar(db, [ids["medico01"]], "reporte_pendiente", "Aviso que se revierte", paciente_id=pid)
    db.rollback()
time.sleep(1.2)
check("Si la transacción se revierte, el evento en vivo NO se publica", len(canales["medico"].eventos) == n0)
with SessionLocal() as db:
    bandeja.notificar(db, [ids["medico01"]], "reporte_pendiente", "Aviso que se confirma", paciente_id=pid)
    db.commit()
check("Si se confirma, sí", canales["medico"].esperar(lambda e: e["mensaje"] == "Aviso que se confirma", 4) is not None)
with SessionLocal() as db:
    bandeja.notificar(db, [ids["paciente_demo"]], "alerta_critica", "No debe llegar", paciente_id=pid)
    bandeja.notificar(db, [ids["contable01"]], "remision_nueva", "No debe llegar", paciente_id=pid)
    db.commit()
time.sleep(1)
check("Aunque un reactor se equivocara, el paciente y el contable no reciben eventos clínicos",
      not canales["paciente"].recibio(lambda e: e["mensaje"] == "No debe llegar")
      and not canales["contable"].recibio(lambda e: e["mensaje"] == "No debe llegar"))
check("Quedan conexiones abiertas registradas en el broker", eventos.conectados() >= 5)

# ------------------------------------------------------------------ resumen
print("\n" + "=" * 70)
print(f"RESULTADO:  {ok} pruebas superadas, {fallos} fallidas")
print("=" * 70)
sys.stdout.flush()
os._exit(1 if fallos else 0)
