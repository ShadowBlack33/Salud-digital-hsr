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
                 headers=h(tok_admin))
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
# El último mes cerrado con volumen suficiente (el mes en curso está incompleto
# y puede tener solo cirugías de la demo o de la simulación).
from datetime import date as _date  # noqa: E402
_mes_actual = _date.today().strftime("%Y-%m")
meses = [m for m in (r.json() if r.status_code == 200 else [])
         if (m.get("programadas") or 0) >= 20 and not str(m.get("mes", "")).startswith(_mes_actual)]
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
r = client.patch("/mis-datos", json={"telefono": "3109876543", "direccion": "Calle 5 # 38-20, Cali"},
                 headers=h(tok_paciente))
check("El paciente actualiza sus propios datos de contacto (Ley 1581, art. 8)",
      r.status_code == 200 and r.json().get("telefono") == "3109876543", r.text[:120])
check("Sus datos actualizados se leen de nuevo (cifrados en la base)",
      client.get("/mis-datos", headers=h(tok_paciente)).json().get("direccion") == "Calle 5 # 38-20, Cali")
check("Un correo inválido se rechaza -> 422",
      client.patch("/mis-datos", json={"email": "no-es-correo"}, headers=h(tok_paciente)).status_code == 422)
check("Un médico no usa 'mis datos' de paciente -> 403",
      client.patch("/mis-datos", json={"telefono": "3000000000"}, headers=h(tok_m01)).status_code == 403)

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
    equipo = client.get(f"/remisiones?paciente_id={pac_m}", headers=h(tok_e01))
    check("Quien ve al paciente ve todo su equipo de especialistas (?paciente_id=)",
          equipo.status_code == 200 and any(x["id"] == rid for x in equipo.json()["remisiones"]), equipo.text[:120])
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
    client.patch(f"/camas/{cid}/estado", headers=h(tok_admin), json={"estado": "disponible", "motivo": "preparar prueba"})
codigos = a_la_vez(4, lambda: client.patch(f"/camas/{cid}/estado", headers=h(tok_admin), json={
    "estado": "reservada", "motivo": "Prueba concurrencia", "estado_esperado": "disponible"}))
check("4 personas reservan la misma cama libre a la vez -> 1 lo logra, 3 con 409",
      sorted(codigos) == [200, 409, 409, 409], str(codigos))
client.patch(f"/camas/{cid}/estado", headers=h(tok_admin), json={"estado": "disponible", "motivo": "fin prueba"})

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

# ---------------------------------------------------------- 20. ServiceRequest y Res. 256
print("\n[20] Remisión en FHIR e indicador de cancelación")
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

# ---------------------------------------------------------- 21. Rendimiento (admin)
print("\n[21] El admin ve cómo funciona el sistema")
r = client.get("/admin/rendimiento", headers=h(tok_admin))
check("Rendimiento -> 200 con API, seguridad, uso e IA",
      r.status_code == 200 and {"api", "seguridad", "uso_por_perfil", "ia"} <= set(r.json()), r.text[:150])
if r.status_code == 200:
    check("Mide peticiones y latencia de la API", r.json()["api"]["ultima_hora"]["peticiones"] > 0)
    check("No expone identificadores de pacientes en las rutas medidas",
          not any("documento" in x["ruta"] or any(c.isdigit() for c in x["ruta"].split(" ")[-1]) for x in r.json()["api"]["rutas"]))
for quien in ("medico01", "coordinador", "contable01"):
    check(f"{quien} no ve el rendimiento -> 403", client.get("/admin/rendimiento", headers=h(login(quien))).status_code == 403)

# ---------------------------------------------------------- 22. Camas por área, traslados y alta médica
print("\n[22] Cada jefe asigna camas de su área, traslados entre áreas y alta médica")
tok_urg, tok_uci, tok_p5 = login("jefe_urg"), login("jefe_uci"), login("jefe_piso5")
pac = client.get("/pacientes/buscar", params={"documento": DOC_PRUEBA}, headers=h(tok_admin))
pid_prueba = pac.json().get("paciente_id") if pac.status_code == 200 else None


def cama_libre(servicio_codigo, tipo=None):
    with SessionLocal() as s_db:
        return s_db.execute(text("""
            SELECT c.id FROM camas c JOIN servicios s ON s.id = c.servicio_id JOIN tipos_cama t ON t.id = c.tipo_cama_id
            WHERE c.activo AND c.estado = 'disponible' AND s.codigo = :s AND (:t IS NULL OR t.codigo = :t)
              AND NOT EXISTS (SELECT 1 FROM encuentros e WHERE e.cama_id = c.id AND e.activo AND e.tipo = 'cirugia'
                              AND e.estado IN ('planned','in-progress'))
            ORDER BY c.id LIMIT 1"""), {"s": servicio_codigo, "t": tipo}).scalar()


def asegurar_cama_libre(servicio_codigo):
    """Si el área está llena (la simulación la mantiene así), libera una cama en limpieza."""
    c = cama_libre(servicio_codigo)
    if c:
        return c
    with SessionLocal() as s_db:
        c = s_db.execute(text("""SELECT c.id FROM camas c JOIN servicios s ON s.id = c.servicio_id
            WHERE c.activo AND s.codigo = :s AND c.estado IN ('en_limpieza', 'bloqueada')
              AND NOT EXISTS (SELECT 1 FROM encuentros e WHERE e.cama_id = c.id AND e.activo
                              AND e.estado IN ('planned','arrived','triaged','in-progress','onleave'))
            ORDER BY c.id LIMIT 1"""),
            {"s": servicio_codigo}).scalar()
    if c:
        client.patch(f"/camas/{c}/estado", headers=h(tok_admin), json={"estado": "disponible", "motivo": "preparar prueba"})
    return cama_libre(servicio_codigo)


def nueva_urgencia():
    return client.post("/encuentros", headers=h(tok_admin), json={"paciente_id": pid_prueba, "tipo": "urgencias",
                       "origen": "urgencia", "nivel_triage": 2, "prioridad_clinica": 2}).json()["id"]


if pid_prueba and tok_urg and tok_uci:
    # El turno rota: para la prueba, jefe_urg y jefe_uci cubren el turno de su área.
    for t_ in (tok_urg, tok_uci):
        client.post("/areas/turno/cubrir", headers=h(t_), json={"motivo": "Prueba e2e"})
    areas_ = {a["codigo"]: a for a in client.get("/areas", headers=h(tok_urg)).json()["areas"]}
    check("Las áreas muestran sus camas libres", "UCI_ADU" in areas_ and "disponibles" in areas_["UCI_ADU"])
    uid = nueva_urgencia()
    check("El jefe de Urgencias ve la urgencia que espera cama",
          any(x["encuentro_id"] == uid for x in client.get("/camas/pendientes", headers=h(tok_urg)).json()["pendientes"]))
    check("El jefe de UCI no la ve en sus pendientes (no es de su área)",
          not any(x["encuentro_id"] == uid for x in client.get("/camas/pendientes", headers=h(tok_uci)).json()["pendientes"]))
    check("Un médico no asigna camas -> 403", client.get("/camas/pendientes", headers=h(tok_m01)).status_code == 403)
    c_uci, c_urg = asegurar_cama_libre("UCI_ADU"), asegurar_cama_libre("URG")
    check("El jefe de Urgencias no asigna camas de UCI -> 403",
          client.post(f"/camas/{c_uci}/asignar", headers=h(tok_urg), json={"encuentro_id": uid}).status_code == 403)
    r = client.post(f"/camas/{c_urg}/asignar", headers=h(tok_urg), json={"encuentro_id": uid})
    check("El jefe de Urgencias asigna una cama de su área", r.status_code == 200 and r.json()["estado"] == "ocupada", r.text[:150])
    check("La misma cama otra vez -> 409",
          client.post(f"/camas/{c_urg}/asignar", headers=h(tok_urg), json={"documento": DOC_PRUEBA}).status_code == 409)
    r = client.post("/traslados", headers=h(tok_urg), json={"paciente_id": pid_prueba, "servicio_destino_id": areas_["UCI_ADU"]["id"],
                                                          "motivo": "Deterioro respiratorio, requiere UCI", "prioridad": "urgente"})
    check("Urgencias solicita el traslado a UCI", r.status_code == 201 and r.json()["estado"] == "pendiente", r.text[:150])
    tid = r.json().get("id")
    check("Un segundo traslado del mismo paciente -> 409",
          client.post("/traslados", headers=h(tok_urg), json={"paciente_id": pid_prueba, "servicio_destino_id": areas_["HOSP_2"]["id"],
                                                             "motivo": "duplicado"}).status_code == 409)
    check("La solicitud le llega al jefe de UCI",
          any(t["id"] == tid and t["entrante"] for t in client.get("/traslados", headers=h(tok_uci)).json()["traslados"]))
    check("El jefe del piso 5 no puede aceptarla -> 403",
          client.post(f"/traslados/{tid}/aceptar", headers=h(tok_p5), json={"cama_id": c_uci}).status_code == 403)
    r = client.post(f"/traslados/{tid}/aceptar", headers=h(tok_uci), json={"cama_id": c_uci})
    check("UCI acepta y elige la cama", r.status_code == 200 and r.json()["estado"] == "aceptado", r.text[:150])
    with SessionLocal() as s_db:
        est = dict(s_db.execute(text("SELECT id, estado FROM camas WHERE id IN (:a, :b)"), {"a": c_urg, "b": c_uci}).fetchall())
    check("La cama de Urgencias queda en limpieza y la de UCI ocupada",
          est.get(c_urg) == "en_limpieza" and est.get(c_uci) == "ocupada", str(est))
    check("Aceptarla otra vez -> 409",
          client.post(f"/traslados/{tid}/aceptar", headers=h(tok_uci), json={"cama_id": c_uci}).status_code == 409)
    check("Un enfermero no da altas -> 403",
          client.post(f"/pacientes/{pid_prueba}/alta", headers=h(tok_uci),
                      json={"tipo_egreso": "mejoria", "motivo": "Paciente estable"}).status_code == 403)
    check("Un médico que no lo atiende no le da el alta",
          client.post(f"/pacientes/{pid_prueba}/alta", headers=h(tok_m01),
                      json={"tipo_egreso": "mejoria", "motivo": "Paciente estable"}).status_code in (403, 404))
    check("Alta sin motivo -> 422",
          client.post(f"/pacientes/{pid_prueba}/alta", headers=h(tok_admin), json={"tipo_egreso": "mejoria"}).status_code == 422)
    r = client.post(f"/pacientes/{pid_prueba}/alta", headers=h(tok_admin),
                    json={"tipo_egreso": "mejoria", "motivo": "Estable 48 h, tolera vía oral, sin oxígeno"})
    check("Alta médica con motivo -> la cama queda en proceso de alta",
          r.status_code == 200 and r.json()["estado_cama"] == "en_proceso_alta", r.text[:150])
    check("Enfermería confirma la salida y la cama pasa a limpieza",
          client.patch(f"/camas/{c_uci}/estado", headers=h(tok_uci),
                       json={"estado": "en_limpieza", "motivo": "Salió", "estado_esperado": "en_proceso_alta"}).status_code == 200)
    uid2 = nueva_urgencia()
    r = client.post("/traslados", headers=h(tok_urg), json={"paciente_id": pid_prueba, "servicio_destino_id": areas_["UCI_ADU"]["id"],
                                                          "motivo": "Valoración por UCI"})
    t2 = r.json().get("id")
    check("UCI rechaza sin motivo -> 422", client.post(f"/traslados/{t2}/rechazar", headers=h(tok_uci), json={}).status_code == 422)
    check("UCI rechaza con motivo", client.post(f"/traslados/{t2}/rechazar", headers=h(tok_uci),
                                                json={"motivo": "Sin camas con ventilador"}).json().get("estado") == "rechazado")
    r = client.post("/traslados", headers=h(tok_urg), json={"paciente_id": pid_prueba, "servicio_destino_id": areas_["HOSP_2"]["id"],
                                                          "motivo": "Hospitalización general"})
    check("Urgencias puede retirar su solicitud",
          client.post(f"/traslados/{r.json()['id']}/cancelar", headers=h(tok_urg)).json().get("estado") == "cancelado")
    client.post(f"/pacientes/{pid_prueba}/alta", headers=h(tok_admin), json={"tipo_egreso": "otro", "motivo": "Fin de la prueba e2e"})
    for c in (c_urg, c_uci):
        client.patch(f"/camas/{c}/estado", headers=h(tok_admin), json={"estado": "disponible", "motivo": "fin prueba"})
    procs = client.get("/cirugias/catalogos", headers=h(tok_jefe)).json()["procedimientos"]
    uci = next((p for p in procs if (p.get("cama_requerida") or "").startswith("Unidad de Cuidados Intensivos")), None)
    general = cama_libre("HOSP_2", "GENERAL")
    if uci and general:
        cx = client.post("/encuentros", headers=h(tok_admin), json={"paciente_id": pid_prueba, "tipo": "cirugia",
                                                                    "procedimiento_id": uci["id"]}).json()["id"]
        check("Paciente de cirugía que necesita UCI en cama general -> 422",
              client.post(f"/camas/{general}/asignar", headers=h(tok_admin), json={"encuentro_id": cx}).status_code == 422)
else:
    print("  (faltan las cuentas por área: aplicar db/11_areas_traslados.sql)")

# ---------------------------------------------------------- 23. Tablero del área y turnos
print("\n[23] Tablero del área y turnos de los jefes")
tok_uci2 = login("jefe_uci2")
if tok_uci and tok_uci2:
    client.post("/areas/turno/cubrir", headers=h(tok_uci), json={"motivo": "Prueba e2e"})
    tb = client.get("/areas/tablero", headers=h(tok_uci))
    j = tb.json() if tb.status_code == 200 else {}
    check("El jefe de UCI ve el tablero de su área con camas y turno",
          tb.status_code == 200 and j["area"]["codigo"] == "UCI_ADU" and j["camas"] and j["turno"]["soy_yo"], tb.text[:150])
    check("Todas las camas del tablero son de su área", all(c["cama_codigo"].startswith("UCI") for c in j.get("camas", [])))
    urg_id = next(a["id"] for a in client.get("/areas", headers=h(tok_uci)).json()["areas"] if a["codigo"] == "URG")
    check("No puede abrir el tablero de otra área -> 403",
          client.get("/areas/tablero", params={"servicio_id": urg_id}, headers=h(tok_uci)).status_code == 403)
    tb2 = client.get("/areas/tablero", headers=h(tok_uci2)).json()
    check("Otro jefe de UCI que no está de turno ve el área en solo lectura", tb2["turno"]["puedo_operar"] is False)
    libre = next((c for c in tb2["camas"] if c["estado_cama"] in ("disponible", "en_limpieza")), None)
    if libre:
        r = client.patch(f"/camas/{libre['cama_id']}/estado", headers=h(tok_uci2),
                         json={"estado": libre["estado_cama"], "motivo": "x"})
        check("... y si intenta operar recibe 403 'no estás de turno'", r.status_code == 403 and "turno" in r.text, r.text[:120])
    r = client.post("/areas/turno/cubrir", headers=h(tok_uci2), json={"motivo": "Relevo por incapacidad (prueba)"})
    check("Puede cubrir el turno con motivo", r.status_code == 200 and r.json()["de_turno"] == "jefe_uci2", r.text[:120])
    check("Ahora el que no está de turno es el primero",
          client.get("/areas/tablero", headers=h(tok_uci)).json()["turno"]["puedo_operar"] is False)
    check("Cubrir sin motivo -> 422", client.post("/areas/turno/cubrir", headers=h(tok_uci), json={}).status_code == 422)
    check("Un médico no ve tableros de área -> 403", client.get("/areas/tablero", headers=h(tok_m01)).status_code == 403)

# ---------------------------------------------------------- 24. Buscar paciente por nombre
print("\n[24] Buscar paciente por nombre o documento (nombres cifrados)")
r = client.get("/pacientes/sugerir", params={"q": "prueba delgado"}, headers=h(tok_admin))
check("Por nombre encuentra pacientes que coinciden (sin importar tildes ni mayúsculas)",
      r.status_code == 200 and r.json() and all("prueba delgado" in x["nombre"].lower() for x in r.json()), r.text[:150])
check("El documento sale enmascarado", r.status_code == 200 and all("*" in (x["documento"] or "*") for x in r.json()))
r = client.get("/pacientes/sugerir", params={"q": DOC_PRUEBA}, headers=h(tok_admin))
check("Por documento exacto (índice ciego)", r.status_code == 200 and len(r.json()) == 1, r.text[:120])
check("Menos de 3 letras -> 422", client.get("/pacientes/sugerir", params={"q": "ab"}, headers=h(tok_admin)).status_code == 422)
check("Un contable no busca pacientes -> 403",
      client.get("/pacientes/sugerir", params={"q": "prueba"}, headers=h(login("contable01"))).status_code == 403)
r = client.get("/pacientes/sugerir", params={"q": "prueba delgado"}, headers=h(tok_m01))
check("Un médico solo encuentra a sus propios pacientes",
      r.status_code == 200 and not any(x["paciente_id"] == pid_prueba for x in r.json()), r.text[:120])

# ---------------------------------------------------------- resumen
print("\n" + "=" * 70)
print(f"RESULTADO:  {ok} pruebas superadas, {fallos} fallidas")
print("=" * 70)
sys.exit(1 if fallos else 0)
