"""
Llena los valores __DOBLE_GUION__ de tester.yaml con datos reales de Neon y del .env.

    python scripts/datos_tester.py

Solo lee la base; no cambia nada en ella.
"""
import os
import re
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

url = os.getenv("DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
clave = (os.getenv("VITE_DEMO_PASSWORD") or os.getenv("DEMO_PASSWORD") or "").strip("'\"")
if not url or not clave:
    sys.exit("Falta DATABASE_URL o VITE_DEMO_PASSWORD en el .env")

with psycopg2.connect(url) as conn, conn.cursor() as cur:
    cur.execute("SELECT username, id, personal_id, paciente_id FROM usuarios "
                "WHERE username IN ('especialista01', 'paciente_demo', 'facturacion01')")
    u = {r[0]: r for r in cur.fetchall()}

faltan = [n for n in ("especialista01", "paciente_demo", "facturacion01") if n not in u]
if faltan:
    sys.exit(f"No existen en la base: {', '.join(faltan)}")

valores = {
    "__CLAVE_DEMO__": clave,
    "__ESPECIALISTA_ID__": str(u["especialista01"][2]),
    "__PACIENTE_IMAGENES_ID__": u["paciente_demo"][3],
    "__ID_CUENTA_BLOQUEO__": str(u["facturacion01"][1]),
}

ruta = RAIZ / "tester.yaml"
texto = ruta.read_text(encoding="utf-8")
for marca, valor in valores.items():
    texto = texto.replace(marca, valor)
pendientes = sorted(set(re.findall(r"__[A-Z_]+__", texto)))
ruta.write_text(texto, encoding="utf-8")

for marca, valor in valores.items():
    print(f"{marca:28} -> {'(oculta)' if 'CLAVE' in marca else valor}")
print("Sin llenar:", ", ".join(pendientes) if pendientes else "nada. tester.yaml listo.")
