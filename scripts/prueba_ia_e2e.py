#!/usr/bin/env python3
"""
Prueba de punta a punta de la parte de IA contra la API en marcha:
R10 (aprobación clínica), R11 (historia y PDF), R12 (canario) y R20 (alertas).

    python scripts/prueba_ia_e2e.py                       # API en http://localhost:8000
    python scripts/prueba_ia_e2e.py --api https://<url>/api

Necesita las cuentas de demostración (medico01, especialista01, contable01,
paciente_demo, admin) y la contraseña del equipo en DEMO_PASSWORD (o --clave).
Crea un paciente nuevo con datos "canario" en cada corrida.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys

import httpx

CANARIOS = {
    "nombre": "CANARIONOMBRE", "apellido": "CANARIOAPELLIDO",
    "telefono": "3009998877", "email": "canario.prueba@ejemplo.invalid",
    "direccion": "Calle CANARIO 123 sur",
}
# Valores que con el modelo provisional garantizan critico=true (paciente_critico del tester.yaml)
CRITICOS = [("2339-0", "Glucose [Mass/volume] in Blood", 42, "mg/dL"),
            ("2823-3", "Potassium [Moles/volume] in Serum", 6.6, "mmol/L"),
            ("718-7", "Hemoglobin [Mass/volume] in Blood", 6.8, "g/dL")]

fallas: list[str] = []


def ok(nombre: str, condicion: bool, detalle: str = "") -> bool:
    print(("OK    " if condicion else "FALLA ") + nombre + (f"   [{detalle}]" if detalle and not condicion else ""))
    if not condicion:
        fallas.append(nombre)
    return condicion


class Cliente:
    def __init__(self, base: str, usuario: str, clave: str):
        self.http = httpx.Client(base_url=base, timeout=30)
        r = self.http.post("/auth/login", json={"username": usuario, "password": clave})
        if r.status_code != 200:
            sys.exit(f"No se pudo entrar como {usuario}: {r.status_code} {r.text[:200]}")
        self.http.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        self.usuario = usuario

    def __getattr__(self, metodo):
        return getattr(self.http, metodo)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=os.getenv("API_URL", "http://localhost:8000"))
    ap.add_argument("--clave", default=os.getenv("DEMO_PASSWORD", "Demo#Hospital2026"))
    a = ap.parse_args()

    med, esp, cont, pac, adm = (Cliente(a.api, u, a.clave) for u in
                                ("medico01", "especialista01", "contable01", "paciente_demo", "admin"))

    print("\n== Paciente canario con valores críticos")
    r = med.post("/pacientes", json={
        "tipo_documento": "CC", "documento": str(random.randint(10**9, 2 * 10**9)),
        "fecha_nacimiento": "1948-03-02", "sexo": "F", "consentimiento_datos": True, **CANARIOS})
    if not ok("crear paciente", r.status_code == 201, f"{r.status_code} {r.text[:200]}"):
        sys.exit(1)
    pid = r.json()["paciente_id"]
    r = med.post("/encuentros", json={"paciente_id": pid, "tipo": "consulta_externa"})
    ok("crear encuentro", r.status_code == 201, r.text[:200])
    enc = r.json()["id"]
    for loinc, nombre, valor, unidad in CRITICOS:
        r = med.post("/observaciones", json={"encuentro_id": enc, "paciente_id": pid, "categoria": "laboratory",
                                             "codigo_loinc": loinc, "display_loinc": nombre,
                                             "valor_numerico": valor, "unidad_ucum": unidad, "es_critico": True})
        ok(f"observación {loinc}", r.status_code == 201, r.text[:200])

    print("\n== R10 · análisis pendiente, aprobación y rechazo")
    r = med.post("/ia/analizar", json={"paciente_id": pid})
    ok("analizar responde {id, estado: pendiente}", r.status_code == 201 and r.json().get("estado") == "pendiente",
       f"{r.status_code} {r.text[:300]}")
    rep1 = r.json()
    ok("el caso sale crítico", rep1.get("critico") is True, json.dumps(rep1))
    rep2 = med.post("/ia/analizar", json={"paciente_id": pid}).json()

    h = med.get(f"/pacientes/{pid}/historia").json()
    ok("un pendiente NO está en la historia", all(x["id"] not in (rep1["id"], rep2["id"]) for x in h["reportes_ia"]))

    ok("paciente no aprueba (403)", pac.post(f"/ia/reportes/{rep1['id']}/aprobar", json={}).status_code == 403)
    ok("contable no aprueba (403)", cont.post(f"/ia/reportes/{rep1['id']}/aprobar", json={}).status_code == 403)
    r = med.post(f"/ia/reportes/{rep1['id']}/aprobar", json={"observaciones": "Concuerda con la valoración."})
    ok("médico aprueba", r.status_code == 200 and r.json()["estado"] == "aprobado", r.text[:200])
    r = med.post(f"/ia/reportes/{rep2['id']}/rechazar", json={"observaciones": "Datos de laboratorio repetidos."})
    ok("médico rechaza", r.status_code == 200 and r.json()["estado"] == "rechazado", r.text[:200])
    ok("aprobar otra vez da 409", med.post(f"/ia/reportes/{rep1['id']}/aprobar", json={}).status_code == 409)
    ok("rechazar un aprobado da 409", med.post(f"/ia/reportes/{rep1['id']}/rechazar", json={}).status_code == 409)
    ok("el rechazado sigue existiendo", med.get(f"/ia/reportes/{rep2['id']}").json().get("estado") == "rechazado")

    h = med.get(f"/pacientes/{pid}/historia").json()
    ids = [x["id"] for x in h["reportes_ia"]]
    ok("historia: solo el aprobado", rep1["id"] in ids and rep2["id"] not in ids, str(ids))
    lista = med.get("/ia/reportes", params={"paciente_id": pid}).json()["reportes"]
    ok("listado del paciente trae los dos", {rep1["id"], rep2["id"]} <= {x["id"] for x in lista})

    print("\n== R12 · canario en el payload")
    r = med.get(f"/ia/reportes/{rep1['id']}/payload")
    ok("payload disponible", r.status_code == 200, r.text[:200])
    texto = json.dumps(r.json(), ensure_ascii=False).lower()
    for campo, valor in CANARIOS.items():
        ok(f"no viaja {campo}", valor.lower() not in texto)
    ok("no viaja el id del paciente", pid.lower() not in texto)
    print("      payload:", json.dumps(r.json()["payload"], ensure_ascii=False))

    print("\n== R11 · historia en PDF")
    r = med.get(f"/pacientes/{pid}/historia/pdf")
    ok("Content-Type application/pdf", r.headers.get("content-type", "").startswith("application/pdf"))
    try:
        from pypdf import PdfReader  # noqa: PLC0415
        import io  # noqa: PLC0415
        texto_pdf = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
        ok("el PDF contiene el nombre", CANARIOS["nombre"] in texto_pdf)
    except ImportError:
        ok("el PDF contiene el nombre (bytes)", CANARIOS["nombre"].encode() in r.content)
    ok("contable no descarga (403)", cont.get(f"/pacientes/{pid}/historia/pdf").status_code == 403)
    ok("paciente no ve la historia de otro (403/404)",
       pac.get(f"/pacientes/{pid}/historia/pdf").status_code in (403, 404))

    print("\n== R20 · alerta crítica")
    alertas = med.get("/alertas").json()["alertas"]
    mia = next((x for x in alertas if x["reporte_id"] == rep1["id"]), None)
    ok("hay alerta activa del reporte", mia is not None and mia["estado"] == "activa", json.dumps(alertas[:2], default=str))
    ok("alerta con id, paciente_id, nivel, estado",
       mia is not None and {"id", "paciente_id", "nivel", "estado"} <= set(mia))
    ok("contable no ve alertas (403)", cont.get("/alertas").status_code == 403)
    ok("paciente no ve alertas (403)", pac.get("/alertas").status_code == 403)
    ok("paciente no reconoce (403)", pac.post(f"/alertas/{mia['id']}/reconocer", json={"nota": "x" * 5}).status_code == 403)
    r = med.post(f"/alertas/{mia['id']}/reconocer", json={"nota": "Se avisa a UCI y se reserva cama."})
    ok("médico reconoce", r.status_code == 200 and r.json()["estado"] == "reconocida", r.text[:200])
    ok("reconocer otra vez da 409", med.post(f"/alertas/{mia['id']}/reconocer", json={"nota": "otra vez"}).status_code == 409)

    print("\n== R13 · auditoría")
    aud = adm.get("/auditoria", params={"limite": 500}).json()
    ids_aud = {str(x["entidad_id"]) for x in aud}
    ok("auditoría tiene el paciente", pid in ids_aud)
    ok("auditoría tiene el reporte", str(rep1["id"]) in ids_aud)
    ops = {x["operacion"] for x in aud}
    for op in ("ia_analisis", "aprobar", "rechazar", "alerta_critica", "reconocer"):
        ok(f"auditoría registra {op}", op in ops)
    ok("médico no ve la auditoría (403)", med.get("/auditoria").status_code == 403)

    print(f"\n{'TODO BIEN' if not fallas else f'{len(fallas)} FALLAS: ' + ', '.join(fallas)}")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
