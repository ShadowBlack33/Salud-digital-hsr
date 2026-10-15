#!/usr/bin/env python3
"""
¿La base configurada en el .env ya tiene la migración de IA (db/13_ia.sql)?

    python scripts/estado_ia.py

Solo lee: no cambia nada en la base.
"""
import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
if not url:
    sys.exit("Falta DATABASE_URL en el .env")

with psycopg2.connect(url, connect_timeout=15) as conn, conn.cursor() as cur:
    cur.execute("SELECT to_regclass('public.reportes_ia') IS NOT NULL")
    tabla = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM permisos WHERE recurso IN ('ia', 'alerta')")
    permisos = cur.fetchone()[0]
    cur.execute("""SELECT COUNT(*) FROM information_schema.columns
                   WHERE table_name = 'alertas' AND column_name IN ('estado', 'reporte_id', 'escalada_at')""")
    columnas = cur.fetchone()[0]

print(f"Tabla reportes_ia ........ {'sí' if tabla else 'NO'}")
print(f"Permisos de IA y alertas . {permisos} de 8")
print(f"Columnas nuevas de alertas {columnas} de 3")
listo = tabla and permisos == 8 and columnas == 3
print("\nMigración 13 aplicada:", "SÍ" if listo else "NO (aplicar db/13_ia.sql)")
sys.exit(0 if listo else 1)
