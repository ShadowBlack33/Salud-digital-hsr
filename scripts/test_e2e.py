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

tok_coord = login("coordinador")
tok_integracion = login("integracion_svc")

# Buscar dos médicos especialistas distintos
with SessionLocal() as db:
    filas = db.execute(text("""
        SELECT u.username FROM usuarios u
        JOIN roles r ON r.id = u.rol_id
        WHERE r.codigo = 'medico_especialista' ORDER BY u.id LIMIT 2
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
r = client.get("/camas", params={"limite": 5}, headers=h(tok_coord))
check("Listar camas -> 200", r.status_code == 200, r.text[:100])

r = client.patch("/camas/1/estado", json={"estado": "en_limpieza",
                                          "motivo": "Prueba e2e"},
                 headers=h(tok_coord))
check("Cambiar estado de cama -> 200", r.status_code == 200, r.text[:120])
if r.status_code == 200:
    check("Devuelve el código FHIR operationalStatus 'H'",
          r.json()["fhir_operational_status"]["code"] == "H")

r = client.get("/fhir/preview/cama/1", headers=h(tok_coord))
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
if r.status_code == 200 and r.json():
    pct = float(r.json()[0].get("pct_cancelacion") or 0)
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
for i in range(3):
    r = client.post("/auth/login", json={"username": "facturacion01", "password": "clave-incorrecta"})
check("3 contraseñas incorrectas seguidas -> la 3ra ya queda bloqueada",
      r.status_code == 401)

r = client.post("/auth/login", json={"username": "facturacion01", "password": PASSWORD})
check("Con la clave CORRECTA pero ya bloqueado -> 423, no deja entrar",
      r.status_code == 423)

with SessionLocal() as db:
    db.execute(text(
        "UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL "
        "WHERE username = 'facturacion01'"
    ))
    db.commit()

r = client.post("/auth/login", json={"username": "facturacion01", "password": PASSWORD})
check("Tras desbloquear, vuelve a entrar normal", r.status_code == 200)

# ---------------------------------------------------------- resumen
print("\n" + "=" * 70)
print(f"RESULTADO:  {ok} pruebas superadas, {fallos} fallidas")
print("=" * 70)
sys.exit(1 if fallos else 0)
