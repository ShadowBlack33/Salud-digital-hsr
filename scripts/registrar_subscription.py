#!/usr/bin/env python3
"""
Registra (o verifica) la Subscription de HAPI que avisa a la API de cada
Observation nueva (R21), y opcionalmente prueba el camino completo.

La API ya lo hace sola al arrancar (app/services/fhir_reactivo.py); este script
sirve para comprobarlo a mano contra el HAPI real, por ejemplo antes de la
sustentación:

  python scripts/registrar_subscription.py
  python scripts/registrar_subscription.py --probar <fhir_patient_id>

--probar publica una Observation de glucosa (LOINC 2339-0) para ese paciente en
HAPI y espera unos segundos a que la tabla `eventos_fhir` registre la llegada:
si aparece, HAPI llamó al receptor y el sistema reaccionó.

Fuera de Docker, HOOK_URL_BASE debe apuntar a la API tal como la ve HAPI
(p. ej. http://host.docker.internal:8000).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.deps import SessionLocal  # noqa: E402
from app.services import fhir_reactivo  # noqa: E402

settings = get_settings()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probar", metavar="FHIR_PATIENT_ID", help="publica una glucosa para ese paciente y espera la reacción")
    args = ap.parse_args()

    base = settings.fhir_base_url.rstrip("/")
    print(f"HAPI: {base}")
    print(f"Receptor: {settings.hook_url_base.rstrip('/')}{fhir_reactivo.RUTA_HOOK}")
    estado = fhir_reactivo.asegurar_suscripcion()
    print(f"Subscription: {estado}")
    s = httpx.get(f"{base}/Subscription/{fhir_reactivo.ID_SUSCRIPCION}", timeout=15).json()
    print(f"  estado en HAPI: {s.get('status')}   criterio: {s.get('criteria')}")
    if s.get("status") not in ("active", "requested"):
        print("  ✗ HAPI no la dejó activa:", s.get("error") or s.get("status"))
        return 1
    if not args.probar:
        return 0

    oid = f"prueba-{int(time.time())}"
    obs = {"resourceType": "Observation", "id": oid, "status": "final",
           "code": {"coding": [{"system": "http://loinc.org", "code": "2339-0", "display": "Glucose"}]},
           "subject": {"reference": f"Patient/{args.probar}"},
           "valueQuantity": {"value": 238, "unit": "mg/dL", "system": "http://unitsofmeasure.org", "code": "mg/dL"}}
    r = httpx.put(f"{base}/Observation/{oid}", json=obs, headers={"Content-Type": "application/fhir+json"}, timeout=15)
    print(f"Observation {oid} publicada en HAPI: {r.status_code}")
    for _ in range(20):
        with SessionLocal() as db:
            fila = db.execute(text("SELECT resultado, paciente_id FROM eventos_fhir WHERE recurso_id = :i"), {"i": oid}).first()
        if fila:
            print(f"  ✓ HAPI avisó a la API: resultado={fila[0]}")
            return 0 if fila[0] == "procesado" else 1
        time.sleep(1)
    print("  ✗ HAPI no avisó en 20 s. Revisa: docker compose logs hapi-fhir | grep -i subscription")
    return 1


if __name__ == "__main__":
    sys.exit(main())
