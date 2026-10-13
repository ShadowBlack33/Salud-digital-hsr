#!/usr/bin/env python3
"""
Prueba end-to-end del backend.

Valida exactamente lo que exige la rúbrica de la Semana 6:
  · Autenticación por rol
  · Control de acceso NIVEL 1 (endpoint) y NIVEL 2 (registro)
  · soft delete / soft edit con historial / restauración solo-admin
  · Log de auditoría
  · Cifrado real de datos sensibles en la base

Uso:  python scripts/test_e2e.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.deps import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402

import random as _random

# Documento único por ejecución: permite correr el test las veces que haga falta
DOC_PRUEBA = f"99{_random.randint(10_000_000, 99_999_999)}"

client = TestClient(app)
PASSWORD = "Demo#Hospital2026"

ok = fallos = 0


def check(descripcion: str, condicion: bool, detalle: str = ""):
    global ok, fallos
    if condicion:
        ok += 1
        print(f"  PASA  {descripcion}")
    else:
        fallos += 1
        print(f"  FALLA {descripcion}  {detalle}")


def login(username: str) -> str | None:
    r = client.post("/auth/login", json={"username": username, "password": PASSWORD})
    if r.status_code != 200:
        print(f"  (no se pudo autenticar '{username}': {r.status_code} {r.text[:120]})")
        return None
    return r.json()["access_token"]


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


print("=" * 70)
print("PRUEBA END-TO-END — API Hospital San Rafael")
print("=" * 70)

# ---------------------------------------------------------------- 1. Salud
print("\n[1] Disponibilidad")
r = client.get("/salud")
check("GET /salud responde 200", r.status_code == 200)
check("Base de datos conectada", r.json().get("base_datos") == "ok", r.text[:80])

# ------------------------------------------------------- 2. Autenticación
print("\n[2] Autenticación")
r = client.post("/auth/login", json={"username": "admin", "password": "incorrecta"})
check("Contraseña incorrecta -> 401", r.status_code == 401)

r = client.post("/auth/login", json={"username": "noexiste", "password": PASSWORD})
check("Usuario inexistente -> 401 (mensaje genérico)", r.status_code == 401)

tok_admin = login("admin")
check("Login de admin exitoso", tok_admin is not None)

tok_coord = login("coordinador")      # coordinador del hospital: no ve pacientes
tok_jefe = login("jefe01")            # enfermero(a) jefe: camas, quirófanos y agenda
tok_integracion = login("integracion_svc")

# Buscar dos médicos especialistas distintos
with SessionLocal() as db:
    filas = db.execute(text("""
        SELECT u.username FROM usuarios u
        JOIN roles r ON r.id = u.rol_id
        WHERE r.codigo = 'especialista' AND u.personal_id IS NOT NULL ORDER BY u.id LIMIT 2
    """)).fetchall()
med_a = login(filas[0][0]) if filas else None
med_b = login(filas[1][0]) if len(filas) > 1 else None
check("Login de dos médicos distintos", med_a is not None and med_b is not None)

r = client.get("/auth/yo", headers=h(tok_admin))
check("GET /auth/yo devuelve rol admin", r.json().get("rol") == "admin")
n_permisos_admin = len(r.json().get("permisos", []))

r = client.get("/auth/yo", headers=h(tok_integracion))
permisos_integracion = r.json().get("permisos", [])
check("Cuenta técnica tiene menos permisos que admin",
      len(permisos_integracion) < n_permisos_admin,
      f"({len(permisos_integracion)} vs {n_permisos_admin})")

# -------------------------------------------------- 3. Acceso sin token
print("\n[3] Acceso no autenticado")
r = client.get("/pacientes")
check("Sin token -> 401", r.status_code == 401)

# ------------------------------------------- 4. Creación y NIVEL 2 de RBAC
print("\n[4] Autorización de dos niveles")
nuevo = {
    "tipo_documento": "CC", "documento": DOC_PRUEBA,
    "nombre": "Ana María", "apellido": "Prueba Delgado",
    "telefono": "3001234567", "fecha_nacimiento": "1988-04-12",
    "sexo": "F", "consentimiento_datos": True,
}
r = client.post("/pacientes", json=nuevo, headers=h(med_a))
check("Médico A crea paciente -> 201", r.status_code == 201, r.text[:120])
paciente_id = r.json()["paciente_id"] if r.status_code == 201 else None

r = client.post("/pacientes", json=nuevo, headers=h(med_a))
check("Documento duplicado -> 409", r.status_code == 409)

if paciente_id:
    r = client.put(f"/pacientes/{paciente_id}",
                   json={"telefono": "3009999999"}, headers=h(med_b))
    check("NIVEL 2: médico B NO puede editar paciente de A -> 403",
          r.status_code == 403, r.text[:120])

    r = client.put(f"/pacientes/{paciente_id}",
                   json={"telefono": "3007777777"}, headers=h(med_a))
    check("Médico A SÍ puede editar su propio paciente -> 200",
          r.status_code == 200, r.text[:120])

    r = client.get(f"/pacientes/{paciente_id}/historial", headers=h(med_a))
    check("Soft edit dejó historial de cambios",
          r.status_code == 200 and len(r.json()) > 0)

# ------------------------------------------------ 5. NIVEL 1 de RBAC
print("\n[5] Restricción por rol (NIVEL 1)")
r = client.get("/pacientes", headers=h(tok_integracion))
check("Cuenta técnica puede leer pacientes (permiso concedido)",
      r.status_code == 200, r.text[:100])

r = client.delete(f"/pacientes/{paciente_id}", headers=h(tok_integracion))
check("Cuenta técnica NO puede eliminar -> 403", r.status_code == 403)

r = client.get("/auditoria", headers=h(med_a))
check("Médico NO puede ver auditoría -> 403", r.status_code == 403)

r = client.get("/auditoria", headers=h(tok_admin))
check("Admin SÍ puede ver auditoría -> 200", r.status_code == 200)

# ------------------------------------------------- 6. Soft delete/restore
print("\n[6] Soft delete y restauración")
if paciente_id:
    r = client.delete(f"/pacientes/{paciente_id}", headers=h(med_b))
    check("Médico B NO puede borrar paciente de A -> 403", r.status_code == 403)

    r = client.delete(f"/pacientes/{paciente_id}", headers=h(med_a))
    check("Médico A borra su propio paciente -> 200", r.status_code == 200)

    r = client.get(f"/pacientes/{paciente_id}", headers=h(tok_admin))
    check("Tras soft delete el GET devuelve 404", r.status_code == 404)

    with SessionLocal() as db:
        fila = db.execute(text(
            "SELECT activo, deleted_at IS NOT NULL AS marcado FROM pacientes WHERE documento_bidx=:i"
        ), {"i": paciente_id}).fetchone()
    check("El registro SIGUE en la base (no se borró físicamente)",
          fila is not None and fila[0] is False and fila[1] is True)

    r = client.post(f"/pacientes/{paciente_id}/restaurar", headers=h(med_a))
    check("Médico NO puede restaurar -> 403", r.status_code == 403)

    r = client.post(f"/pacientes/{paciente_id}/restaurar", headers=h(tok_coord))
    check("Coordinador NO puede restaurar -> 403", r.status_code == 403)

    r = client.post(f"/pacientes/{paciente_id}/restaurar", headers=h(tok_admin))
    check("SOLO admin restaura -> 200", r.status_code == 200, r.text[:120])

    r = client.get(f"/pacientes/{paciente_id}", headers=h(tok_admin))
    check("Tras restaurar el paciente vuelve a ser accesible", r.status_code == 200)

# --------------------------------------------------------- 7. Cifrado
print("\n[7] Cifrado de datos sensibles")
r = client.get("/pacientes/buscar", params={"documento": DOC_PRUEBA},
               headers=h(tok_admin))
check("Búsqueda por blind index encuentra al paciente", r.status_code == 200,
      r.text[:100])
check("El documento se descifra correctamente al leer",
      r.status_code == 200 and r.json().get("documento") == DOC_PRUEBA)

with SessionLocal() as db:
    fila = db.execute(text(
        "SELECT documento_cifrado, nombre_cifrado FROM pacientes WHERE documento_bidx=:i"
    ), {"i": paciente_id}).fetchone()
crudo = bytes(fila[0]).decode(errors="ignore") if fila else ""
check("En la BD el documento NO está en claro", DOC_PRUEBA not in crudo,
      f"crudo={crudo[:40]}")
check("El ciphertext usa el formato versionado v1:", crudo.startswith("v1:"))
crudo_nombre = bytes(fila[1]).decode(errors="ignore") if fila else ""
check("En la BD el nombre NO está en claro", "Ana María" not in crudo_nombre)

r = client.get("/pacientes", params={"limite": 3}, headers=h(tok_admin))
if r.status_code == 200 and r.json():
    check("En listados el documento va enmascarado",
          r.json()[0]["documento"].startswith("*"))

# ---------------------------------------------- 8. Regla clínica de camas
print("\n[8] Regla de negocio: procedimiento vs. tipo de cama")
with SessionLocal() as db:
    proc = db.execute(text("""
        SELECT cp.id, cp.nombre FROM catalogo_procedimientos cp
        JOIN tipos_cama tc ON tc.id = cp.tipo_cama_requerida_id
        WHERE tc.codigo = 'UCI' LIMIT 1
    """)).fetchone()
    cama_gen = db.execute(text("""
        SELECT c.id FROM camas c JOIN tipos_cama tc ON tc.id = c.tipo_cama_id
        WHERE tc.codigo = 'GENERAL' LIMIT 1
    """)).fetchone()

if proc and cama_gen and paciente_id:
    r = client.post("/encuentros", headers=h(med_a), json={
        "paciente_id": paciente_id, "tipo": "cirugia", "origen": "electiva",
        "procedimiento_id": proc[0], "cama_id": cama_gen[0],
    })
    check("Cirugía que requiere UCI con cama GENERAL -> 422",
          r.status_code == 422, r.text[:150])

# -------------------------------------------------------- 9. Recursos
print("\n[9] Estado de recursos y mapeo FHIR")
r = client.get("/camas", params={"limite": 5}, headers=h(tok_jefe))
check("Listar camas -> 200", r.status_code == 200, r.text[:100])

r = client.patch("/camas/1/estado", json={"estado": "en_limpieza",
                                          "motivo": "Prueba e2e"},
                 headers=h(tok_jefe))
check("Cambiar estado de cama -> 200", r.status_code == 200, r.text[:120])
if r.status_code == 200:
    check("Devuelve el código FHIR operationalStatus 'H'",
          r.json()["fhir_operational_status"]["code"] == "H")

r = client.get("/fhir/preview/cama/1", headers=h(tok_jefe))
check("Preview del recurso Location -> 200", r.status_code == 200)
if r.status_code == 200:
    j = r.json()
    check("Location tiene operationalStatus del sistema v2-0116",
          j.get("operationalStatus", {}).get("system", "").endswith("v2-0116"))
    check("Location.physicalType = 'bd' (bed)",
          j["physicalType"]["coding"][0]["code"] == "bd")

if paciente_id:
    r = client.get(f"/fhir/preview/paciente/{paciente_id}", headers=h(tok_admin))
    check("Preview del recurso Patient -> 200", r.status_code == 200)
    if r.status_code == 200:
        check("Patient bien formado (resourceType + identifier)",
              r.json().get("resourceType") == "Patient"
              and len(r.json().get("identifier", [])) > 0)

# -------------------------------------------------------- 10. Analítica
print("\n[10] Analítica y caso de negocio")
r = client.get("/analitica/ocupacion", headers=h(tok_admin))
check("Ocupación por tipo de cama -> 200", r.status_code == 200)

r = client.get("/analitica/cancelaciones", headers=h(tok_admin))
# El mes más reciente con volumen suficiente (el mes en curso puede tener solo
# las cirugías de la demo y dar 0 %).
meses = [m for m in (r.json() if r.status_code == 200 else []) if (m.get("programadas") or 0) >= 20]
if meses:
    pct = float(meses[0].get("pct_cancelacion") or 0)
    check(f"Tasa de cancelación en rango realista ({pct} %)", 1.0 < pct < 12.0)

r = client.get("/analitica/costo-ociosidad", headers=h(tok_admin))
check("Costo de ociosidad calculado -> 200", r.status_code == 200)
if r.status_code == 200:
    check("Costo total > 0", r.json().get("costo_total_cop", 0) > 0)

# ------------------------------------------------------- 11. Auditoría
print("\n[11] Auditoría")
r = client.get("/auditoria", params={"limite": 100}, headers=h(tok_admin))
if r.status_code == 200:
    ops = {f["operacion"] for f in r.json()}
    check("Auditoría registró soft_delete", "soft_delete" in ops)
    check("Auditoría registró restore", "restore" in ops)
    check("Auditoría registró login", "login" in ops)
    denegados = [f for f in r.json() if f["resultado"] == "denegado"]
    check("Auditoría registró intentos denegados", len(denegados) > 0)

r = client.get("/auditoria/fhir/AuditEvent", headers=h(tok_admin))
check("Auditoría expuesta como Bundle FHIR", r.status_code == 200)
if r.status_code == 200:
    check("Bundle contiene recursos AuditEvent",
          r.json()["entry"][0]["resource"]["resourceType"] == "AuditEvent")

with SessionLocal() as db:
    try:
        db.execute(text("UPDATE log_auditoria SET operacion='hack' WHERE id=1"))
        db.commit()
        check("Log de auditoría es inmutable (append-only)", False,
              "el UPDATE fue permitido")
    except Exception:
        db.rollback()
        check("Log de auditoría es inmutable (append-only)", True)

print("\n[12] Bloqueo de cuenta tras intentos fallidos")
malo = {"username": "facturacion01", "password": "clave-incorrecta"}
r1 = client.post("/auth/login", json=malo)
check("1er intento fallido -> 401 y le quedan 2 intentos",
      r1.status_code == 401 and r1.json().get("intentos_restantes") == 2, r1.text[:100])
r2 = client.post("/auth/login", json=malo)
check("2do intento fallido -> 401 y le queda 1",
      r2.status_code == 401 and r2.json().get("intentos_restantes") == 1, r2.text[:100])
r3 = client.post("/auth/login", json=malo)
# Corte 2 (R02): el bloqueo dura hasta que el admin lo quite, así que la
# respuesta trae requiere_admin en vez de una hora de desbloqueo.
check("3er intento fallido -> 423: la cuenta queda bloqueada en ese momento",
      r3.status_code == 423 and (bool(r3.json().get("bloqueado_hasta"))
                                 or r3.json().get("requiere_admin") is True), r3.text[:100])

r = client.post("/auth/login", json={"username": "facturacion01", "password": PASSWORD})
check("Con la clave CORRECTA pero ya bloqueado -> 423, no deja entrar",
      r.status_code == 423)

r = client.post("/auth/login", json={"username": "usuario_que_no_existe", "password": "x"})
check("Usuario inexistente -> 401 genérico, sin contador",
      r.status_code == 401 and "intentos_restantes" not in r.json())

# Solo el admin desbloquea (R02), por el endpoint y no con SQL a mano.
with SessionLocal() as db:
    id_bloqueado = db.execute(text(
        "SELECT id FROM usuarios WHERE username = 'facturacion01'")).scalar()
r = client.post(f"/usuarios/{id_bloqueado}/desbloquear", headers=h(tok_coord))
check("Un rol distinto de admin no puede desbloquear -> 403", r.status_code == 403)
r = client.post(f"/usuarios/{id_bloqueado}/desbloquear", headers=h(tok_admin))
check("El admin desbloquea la cuenta -> 200", r.status_code == 200, r.text[:100])

r = client.post("/auth/login", json={"username": "facturacion01", "password": PASSWORD})
check("Tras desbloquear, vuelve a entrar normal", r.status_code == 200)

with SessionLocal() as db:
    ops = {fila[0] for fila in db.execute(text(
        "SELECT operacion FROM log_auditoria WHERE entidad_tipo = 'usuario' "
        "AND entidad_id = :id"), {"id": str(id_bloqueado)})}
check("Bloqueo y desbloqueo quedan en la auditoría",
      {"bloqueo", "desbloqueo"} <= ops, str(ops))

print("\n[13] Tablero: camas y quirófanos con datos del momento")
r = client.get("/camas/ocupacion?solo_ocupadas=false", headers=h(tok_admin))
camas_todas = r.json() if r.status_code == 200 else []
check("Ocupación devuelve las 300 camas", r.status_code == 200 and len(camas_todas) == 300,
      f"{r.status_code} {len(camas_todas)}")
if camas_todas:
    check("Cada cama trae tipo, costo y si su encuentro está activo",
          all(k in camas_todas[0] for k in ("tipo_nombre", "costo_dia_cop", "encuentro_activo")))
    activas = [c for c in camas_todas if c["encuentro_activo"] and c["paciente_nombre_corto"]]
    if activas:
        nombre = activas[0]["paciente_nombre_corto"]
        check("El nombre en el tablero es corto (inicial + apellido), nunca completo",
              len(nombre.split(" ")) <= 2 and nombre[1:3] == ". ", nombre)
r = client.get("/quirofanos/agenda", headers=h(tok_admin))
agenda = r.json() if r.status_code == 200 else {}
check("La agenda trae los 13 quirófanos y la hora del servidor",
      r.status_code == 200 and len(agenda.get("quirofanos", [])) == 13 and "ahora" in agenda)
tok_paciente = login("paciente_demo")
check("Un rol sin permiso de quirófanos (el paciente) no ve la agenda -> 403",
      client.get("/quirofanos/agenda", headers=h(tok_paciente)).status_code == 403)

# ---------------------------------------------------------- 14. Perfiles
print("\n[14] Cada perfil ve solo lo suyo")
roles = {}
with SessionLocal() as db:
    for codigo, n in db.execute(text("SELECT r.codigo, COUNT(*) FROM roles r GROUP BY r.codigo")).fetchall():
        roles[codigo] = n
check("Sin roles duplicados del Corte 1 (medico_general, medico_especialista, facturacion)",
      not ({"medico_general", "medico_especialista", "facturacion", "coordinador_quirurgico"} & set(roles)),
      str(sorted(roles)))
check("Existen los cinco roles del Corte 2 y el coordinador del hospital",
      {"admin", "medico", "especialista", "paciente", "contable", "coordinador"} <= set(roles))

# Un paciente creado por el médico A es suyo; el médico B no lo ve.
if med_a and med_b and paciente_id:
    check("El médico que registró al paciente lo ve -> 200",
          client.get(f"/pacientes/{paciente_id}", headers=h(med_a)).status_code == 200)
    check("Otro médico no lo ve: no está a su cargo -> 403",
          client.get(f"/pacientes/{paciente_id}", headers=h(med_b)).status_code == 403)
    r = client.get("/pacientes", params={"limite": 200}, headers=h(med_b))
    check("La lista del otro médico no lo incluye",
          r.status_code == 200 and paciente_id not in [p["paciente_id"] for p in r.json()])
tok_m01 = login("medico01")
r = client.get("/mis-pacientes", headers=h(tok_m01))
check("medico01 tiene su lista de pacientes", r.status_code == 200 and "pacientes" in r.json(), r.text[:120])
r = client.get("/mis-cirugias", headers=h(login("especialista01")))
check("especialista01 ve las cirugías de sus pacientes", r.status_code == 200 and "cirugias" in r.json(), r.text[:120])

check("El coordinador del hospital no consulta pacientes -> 403",
      client.get("/pacientes", headers=h(tok_coord)).status_code == 403)
r = client.get("/analitica/hospital", headers=h(tok_coord))
check("El coordinador ve el tablero del hospital", r.status_code == 200 and "areas" in r.json(), r.text[:120])
if r.status_code == 200:
    check("El tablero del hospital no trae datos de pacientes",
          "paciente" not in r.text.lower().replace("pacientes", ""), "")

r = client.get("/cirugias/dia", headers=h(tok_jefe))
check("El enfermero jefe ve la programación quirúrgica", r.status_code == 200 and len(r.json()["salas"]) == 13)
check("Un médico no reprograma cirugías -> 403",
      client.patch("/cirugias/1/reprogramar", json={"motivo": "prueba", "hora_inicio": "2030-01-01T10:00:00Z"},
                   headers=h(tok_m01)).status_code == 403)
r = client.get("/mi-cuenta", headers=h(tok_paciente))
check("El paciente ve qué se le cobra a él y a su entidad",
      r.status_code == 200 and {"cobertura", "servicios", "totales"} <= set(r.json()), r.text[:120])
check("Un médico no puede abrir 'mi cuenta' de paciente -> 403",
      client.get("/mi-cuenta", headers=h(tok_m01)).status_code == 403)

# ---------------------------------------------------------- 15. Remisiones (R08)
print("\n[15] Remisión del médico al especialista")
tok_e01 = login("especialista01")
r = client.get("/mis-pacientes", headers=h(tok_m01))
pac_m = r.json()["pacientes"][0]["paciente_id"] if r.status_code == 200 and r.json()["pacientes"] else None
esp = client.get("/especialistas", headers=h(tok_m01))
check("El médico ve la lista de especialistas", esp.status_code == 200 and len(esp.json()) > 0)
yo_esp = client.get("/auth/yo", headers=h(tok_e01)).json().get("personal_id")
if pac_m and yo_esp:
    r = client.post("/remisiones", headers=h(tok_m01), json={"paciente_id": pac_m, "especialista_id": yo_esp,
                                                             "motivo": "Prueba e2e de remisión", "prioridad": "urgente"})
    check("El médico remite -> 201 con id", r.status_code == 201 and "id" in r.json(), r.text[:120])
    rid = r.json().get("id")
    check("El especialista ya puede abrir la ficha del remitido",
          client.get(f"/pacientes/{pac_m}", headers=h(tok_e01)).status_code == 200)
    check("La remisión aparece en la bandeja del especialista",
          any(x["id"] == rid for x in client.get("/remisiones", headers=h(tok_e01)).json()["remisiones"]))
    check("El médico remitente no puede aceptarla -> 403",
          client.post(f"/remisiones/{rid}/aceptar", headers=h(tok_m01)).status_code == 403)
    r = client.post(f"/remisiones/{rid}/aceptar", headers=h(tok_e01))
    check("El especialista la acepta", r.status_code == 200 and r.json()["estado"] == "aceptada", r.text[:120])
for quien, tok in (("paciente", tok_paciente), ("contable", login("contable01"))):
    check(f"Un {quien} no puede remitir -> 403",
          client.post("/remisiones", headers=h(tok), json={"paciente_id": "x", "especialista_id": 1, "motivo": "xxxxxx"}).status_code == 403)

# ---------------------------------------------------------- 16. Concurrencia
# Los jurados entran a la vez desde sus celulares: dos personas que reservan lo
# mismo al mismo tiempo nunca deben quedar las dos confirmadas.
print("\n[16] Concurrencia: reservas simultáneas")
from concurrent.futures import ThreadPoolExecutor  # noqa: E402


def a_la_vez(n, fn):
    with ThreadPoolExecutor(max_workers=n) as ex:
        rs = list(ex.map(lambda _: fn(), range(n)))
    creadas.extend(r.json()["id"] for r in rs if r.status_code == 201)
    return [r.status_code for r in rs]


creadas: list[int] = []   # cirugías de prueba: se desactivan al final para no ensuciar los indicadores


cat = client.get("/cirugias/catalogos", headers=h(tok_jefe)).json()
proc = next(p for p in cat["procedimientos"] if not p["requiere_arco_c"])
salas = [q for q in cat["quirofanos"] if q["estado"] != "bloqueado"]
cir, anest = cat["cirujanos"][0]["id"], cat["anestesiologos"][0]["id"]
hora = f"2031-{_random.randint(1, 12):02d}-{_random.randint(1, 28):02d}T{_random.randint(7, 15):02d}:00:00Z"
cuerpo = {"documento": DOC_PRUEBA, "procedimiento_id": proc["id"], "quirofano_id": salas[0]["id"],
          "hora_inicio": hora, "cirujano_id": cir, "anestesiologo_id": anest}
codigos = a_la_vez(5, lambda: client.post("/cirugias", json=cuerpo, headers=h(tok_jefe)))
check("5 reservas simultáneas del mismo quirófano y hora -> 1 confirmada, 4 con 409",
      sorted(codigos) == [201, 409, 409, 409, 409], str(codigos))
r = client.post("/cirugias", headers=h(tok_jefe), json={**cuerpo, "quirofano_id": salas[1]["id"]})
check("Mismo cirujano en otra sala a la misma hora -> 409", r.status_code == 409, r.text[:150])
r = client.post("/cirugias", headers=h(tok_jefe), json={**cuerpo, "quirofano_id": salas[1]["id"],
                                                         "cirujano_id": cat["cirujanos"][1]["id"],
                                                         "anestesiologo_id": cat["anestesiologos"][1]["id"]})
check("Otra sala con otro equipo a la misma hora -> 201", r.status_code == 201, r.text[:150])
if r.status_code == 201:
    creadas.append(r.json()["id"])
if creadas:
    with SessionLocal() as s_:
        s_.execute(text("UPDATE encuentros SET activo = false WHERE id = ANY(:ids)"), {"ids": creadas})
        s_.commit()

libres = client.get("/camas", params={"estado": "disponible", "limite": 1}, headers=h(tok_jefe)).json()
cid = libres[0]["id"] if libres else 1
if not libres:
    client.patch(f"/camas/{cid}/estado", headers=h(tok_jefe), json={"estado": "disponible", "motivo": "preparar prueba"})
codigos = a_la_vez(4, lambda: client.patch(f"/camas/{cid}/estado", headers=h(tok_jefe), json={
    "estado": "reservada", "motivo": "Prueba concurrencia", "estado_esperado": "disponible"}))
check("4 personas reservan la misma cama libre a la vez -> 1 lo logra, 3 con 409",
      sorted(codigos) == [200, 409, 409, 409], str(codigos))
client.patch(f"/camas/{cid}/estado", headers=h(tok_jefe), json={"estado": "disponible", "motivo": "fin prueba"})

if pac_m and yo_esp:
    r = client.post("/remisiones", headers=h(tok_m01), json={"paciente_id": pac_m, "especialista_id": yo_esp,
                                                             "motivo": "Prueba de concurrencia", "prioridad": "rutinaria"})
    rid2 = r.json().get("id")
    codigos = a_la_vez(3, lambda: client.post(f"/remisiones/{rid2}/aceptar", headers=h(tok_e01)))
    check("Aceptar la misma remisión 3 veces a la vez -> 1 aceptada, 2 con 409",
          sorted(codigos) == [200, 409, 409], str(codigos))

# ---------------------------------------------------------- 17. Cierre de remisiones y vigencia del acceso
print("\n[17] Remisión rechazada o atendida: el acceso del especialista se cierra")
ajenos = []
if tok_m01 and tok_e01 and yo_esp:
    mios = [x["paciente_id"] for x in client.get("/mis-pacientes", headers=h(tok_m01)).json().get("pacientes", [])]
    ajenos = [p for p in mios if client.get(f"/pacientes/{p}", headers=h(tok_e01)).status_code != 200]
if ajenos:
    pac_r = ajenos[0]
    rid3 = client.post("/remisiones", headers=h(tok_m01), json={"paciente_id": pac_r, "especialista_id": yo_esp,
                                                                "motivo": "Prueba de rechazo", "prioridad": "rutinaria"}).json()["id"]
    check("Con la remisión pendiente el especialista abre la ficha",
          client.get(f"/pacientes/{pac_r}", headers=h(tok_e01)).status_code == 200)
    check("Rechazar sin motivo -> 422",
          client.post(f"/remisiones/{rid3}/rechazar", headers=h(tok_e01), json={}).status_code == 422)
    check("El médico remitente no puede rechazarla -> 403",
          client.post(f"/remisiones/{rid3}/rechazar", headers=h(tok_m01), json={"motivo": "no me toca"}).status_code == 403)
    r = client.post(f"/remisiones/{rid3}/rechazar", headers=h(tok_e01), json={"motivo": "No corresponde a mi especialidad"})
    check("El especialista la rechaza con motivo", r.status_code == 200 and r.json()["estado"] == "rechazada", r.text[:120])
    check("Tras rechazarla pierde el acceso a la ficha",
          client.get(f"/pacientes/{pac_r}", headers=h(tok_e01)).status_code in (403, 404))
    check("No se puede aceptar una rechazada -> 409",
          client.post(f"/remisiones/{rid3}/aceptar", headers=h(tok_e01)).status_code == 409)
else:
    print("  (sin paciente del médico ajeno al especialista: se omite el rechazo)")
if pac_m and yo_esp:
    r = client.post(f"/remisiones/{rid2}/atender", headers=h(tok_e01))
    check("Cerrar como atendida una remisión aceptada", r.status_code == 200 and r.json()["estado"] == "atendida", r.text[:120])
    check("Atenderla otra vez -> 409", client.post(f"/remisiones/{rid2}/atender", headers=h(tok_e01)).status_code == 409)

# ---------------------------------------------------------- 18. Puerta del servidor FHIR
print("\n[18] /fhir: qué se puede sin token")


def puerta(metodo, ruta, token=None):
    hd = {"X-Original-Method": metodo, "X-Original-URI": ruta}
    if token:
        hd["Authorization"] = f"Bearer {token}"
    return client.get("/interno/puerta-fhir", headers=hd).status_code


check("POST /fhir/Observation sin token pasa (R21)", puerta("POST", "/fhir/Observation") == 204)
check("GET /fhir/metadata sin token pasa", puerta("GET", "/fhir/metadata") == 204)
check("GET /fhir/Patient (listar) sin token -> 401", puerta("GET", "/fhir/Patient?_count=5") == 401)
check("Búsqueda exacta por identificador sin token pasa (R15)", puerta("GET", "/fhir/Patient?identifier=123456") == 204)
check("Identificador con otros parámetros sin token -> 401", puerta("GET", "/fhir/Patient?identifier=1&_count=50") == 401)
check("Leer Patient/{id} sin token -> 401", puerta("GET", "/fhir/Patient/1") == 401)
check("GET /fhir/Patient con token clínico pasa", puerta("GET", "/fhir/Patient", tok_m01) == 204)
check("Un paciente no lee FHIR -> 403", puerta("GET", "/fhir/Patient", tok_paciente) == 403)
check("Un médico no escribe Patient en FHIR -> 403", puerta("POST", "/fhir/Patient", tok_m01) == 403)
check("La cuenta de integración sí escribe", puerta("PUT", "/fhir/Patient/1", tok_integracion) == 204)
check("DELETE nunca pasa, ni con integración -> 403", puerta("DELETE", "/fhir/Patient/1", tok_integracion) == 403)
check("PUT /fhir/Observation/1 sin token -> 401", puerta("PUT", "/fhir/Observation/1") == 401)

# ---------------------------------------------------------- 19. Sesiones y auditoría
print("\n[19] Cierre de sesión y auditoría sin datos sensibles")
r = client.post("/auth/login", json={"username": "medico02", "password": PASSWORD})
if r.status_code == 200:
    acc, ref = r.json()["access_token"], r.json()["refresh_token"]
    check("Con sesión abierta el token sirve", client.get("/auth/yo", headers=h(acc)).status_code == 200)
    client.post("/auth/logout", headers=h(acc), json={"refresh_token": ref})
    check("Tras cerrar sesión el access token deja de servir de inmediato -> 401",
          client.get("/auth/yo", headers=h(acc)).status_code == 401)
    check("Tras cerrar sesión el refresh token no renueva -> 401",
          client.post("/auth/refresh", json={"refresh_token": ref}).status_code == 401)
r = client.post("/auth/login", json={"username": "medico02", "password": PASSWORD})
if r.status_code == 200:
    acc, ref = r.json()["access_token"], r.json()["refresh_token"]
    nuevo = client.post("/auth/refresh", json={"refresh_token": ref})
    check("Al renovar, el access token anterior queda revocado -> 401",
          nuevo.status_code == 200 and client.get("/auth/yo", headers=h(acc)).status_code == 401)
    check("... y el nuevo sí sirve", client.get("/auth/yo", headers=h(nuevo.json()["access_token"])).status_code == 200)

from app.services.auditoria import _sanear  # noqa: E402
s_ = _sanear({"username": "x", "password": "Secreta#1", "nombre": "Ana", "detalle": {"documento": "123"},
              "valor_texto": "dolor torácico", "nota": "z" * 500, "motivo": "y" * 500})
check("La auditoría nunca guarda contraseña, nombre, documento ni texto clínico",
      s_["password"] == s_["nombre"] == s_["detalle"]["documento"] == s_["valor_texto"] == "<protegido>"
      and s_["username"] == "x")
check("Los textos largos se cortan en la auditoría", len(s_["motivo"]) <= 201)
with SessionLocal() as s_db:
    filas = s_db.execute(text("SELECT valor_nuevo::text FROM log_auditoria WHERE valor_nuevo IS NOT NULL "
                              "ORDER BY id DESC LIMIT 300")).scalars().all()
check("Las últimas 300 entradas de auditoría no tienen contraseñas ni tokens",
      not any('"password"' in f and "<protegido>" not in f for f in filas)
      and not any("eyJ" in f for f in filas))

# ---------------------------------------------------------- 20. Ingeniería biomédica, ServiceRequest y Res. 256
print("\n[20] Ingeniería biomédica sin datos clínicos, remisión en FHIR e indicador de cancelación")
tok_bio = login("biomedico01")
if tok_bio:
    check("biomedico01 ve el estado de las camas", client.get("/camas", headers=h(tok_bio)).status_code == 200)
    occ = client.get("/camas/ocupacion?solo_ocupadas=true", headers=h(tok_bio))
    check("... pero no quién las ocupa",
          occ.status_code == 200 and all(not x.get("paciente_nombre_corto") and not x.get("paciente_documento")
                                         and not x.get("diagnostico") for x in occ.json()), occ.text[:150])
    check("biomedico01 no consulta pacientes -> 403", client.get("/pacientes", headers=h(tok_bio)).status_code == 403)
    qx = client.get("/quirofanos", headers=h(tok_bio)).json()
    libre = next(q for q in qx if q["estado"] in ("disponible", "en_limpieza", "en_preparacion"))
    check("biomedico01 NO puede mandar a limpieza ni cambiar estados a mano -> 403",
          client.patch(f"/quirofanos/{libre['id']}/estado", headers=h(tok_bio),
                       json={"estado": "en_limpieza", "motivo": "x"}).status_code == 403)
    r = client.post("/biomedica/fuera-servicio", headers=h(tok_bio), json={
        "recurso_tipo": "quirofano", "recurso_id": libre["id"], "equipo": "Arco en C",
        "tipo": "falla", "descripcion": "No genera imagen (prueba e2e)"})
    check("Saca el quirófano de servicio por falla de un equipo", r.status_code == 201, r.text[:150])
    fid = r.json().get("id")
    check("El quirófano queda bloqueado",
          next(q for q in client.get("/quirofanos", headers=h(tok_bio)).json() if q["id"] == libre["id"])["estado"] == "bloqueado")
    check("No se puede sacar dos veces el mismo -> 409", client.post("/biomedica/fuera-servicio", headers=h(tok_bio), json={
        "recurso_tipo": "quirofano", "recurso_id": libre["id"], "equipo": "Lámpara", "tipo": "falla",
        "descripcion": "otra falla"}).status_code == 409)
    con_pac = client.get("/camas", params={"estado": "ocupada", "limite": 1}, headers=h(tok_bio)).json()
    if con_pac:
        check("Una cama con paciente no se saca de servicio -> 409", client.post("/biomedica/fuera-servicio", headers=h(tok_bio), json={
            "recurso_tipo": "cama", "recurso_id": con_pac[0]["id"], "equipo": "Monitor", "tipo": "falla",
            "descripcion": "pantalla apagada"}).status_code == 409)
    lst = client.get("/biomedica/fuera-servicio", headers=h(tok_bio)).json()
    check("Aparece en la lista de equipos fuera de servicio", any(f["id"] == fid and f["abierta"] for f in lst["fuera_servicio"]))
    check("Enfermería jefe no usa el módulo biomédico -> 403",
          client.post(f"/biomedica/fuera-servicio/{fid}/devolver", headers=h(tok_jefe)).status_code == 403)
    r = client.post(f"/biomedica/fuera-servicio/{fid}/devolver", headers=h(tok_bio), json={"nota": "Se cambió el tubo"})
    check("Al devolverlo queda en limpieza (enfermería lo habilita)", r.status_code == 200 and r.json()["estado"] == "en_limpieza", r.text[:120])
    check("Devolverlo otra vez -> 409", client.post(f"/biomedica/fuera-servicio/{fid}/devolver", headers=h(tok_bio)).status_code == 409)
    client.patch(f"/quirofanos/{libre['id']}/estado", headers=h(tok_jefe), json={"estado": libre["estado"], "motivo": "fin prueba"})
else:
    print("  (sin cuenta biomedico01: aplicar db/11_ingeniero_biomedico.sql)")
if pac_m and yo_esp:
    r = client.get(f"/remisiones/{rid2}/fhir", headers=h(tok_m01))
    j = r.json() if r.status_code == 200 else {}
    check("La remisión se expresa como ServiceRequest FHIR",
          j.get("resourceType") == "ServiceRequest" and j.get("status") == "completed" and "subject" in j, r.text[:150])
    check("El ServiceRequest no lleva nombre ni documento del paciente",
          not any(k in r.text for k in ("documento", "pacientes.nombre")))
    check("Un contable no ve la remisión en FHIR -> 403",
          client.get(f"/remisiones/{rid2}/fhir", headers=h(login("contable01"))).status_code == 403)
r = client.get("/analitica/hospital", headers=h(tok_coord))
c = r.json().get("cancelacion_cirugia") if r.status_code == 200 else None
check("El tablero trae el indicador de cancelación (Res. 256/2016)",
      c is not None and 0 <= c["pct_institucion"] <= c["pct_total"], str(c)[:150])

# ---------------------------------------------------------- resumen
print("\n" + "=" * 70)
print(f"RESULTADO:  {ok} pruebas superadas, {fallos} fallidas")
print("=" * 70)
sys.exit(1 if fallos else 0)
