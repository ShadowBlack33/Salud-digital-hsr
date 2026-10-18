#!/usr/bin/env python3
"""
Sube a MongoDB los resultados de scripts/clusters_vitaldb.py (R07).

  dataset_tabular   una fila por caso (real o sintético): id, origen, cluster, split y variables
  clusters_resumen  una fila por cluster: cluster, descripcion, n_reales, n_sinteticos, perfil

Es seguro repetirlo: reemplaza solo lo que vino de este dataset (fuente = "vitaldb").
Después de cargarlo, GET /analitica/clusters devuelve el resumen.

Conexión (en este orden): --mongo-url, MONGO_URL_HOST, o MONGO_URL del .env. Si la URL no
trae usuario y hay MONGO_PASSWORD (el Mongo del docker-compose exige usuario "hsr"), se
agrega solo. Desde tu equipo el puerto del compose es 127.0.0.1:27017.

Uso:
    python scripts/cargar_clusters.py
    python scripts/cargar_clusters.py --mongo-url "mongodb://hsr:CLAVE@localhost:27017/hsr?authSource=admin"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "data" / "vitaldb"
FUENTE = "vitaldb"


def url_mongo(explicita: str | None) -> str:
    try:
        from dotenv import load_dotenv
        load_dotenv(RAIZ / ".env")
    except ImportError:
        pass
    url = explicita or os.getenv("MONGO_URL_HOST") or os.getenv("MONGO_URL") or "mongodb://localhost:27017/hsr"
    clave = os.getenv("MONGO_PASSWORD")
    if "@" not in url and clave:
        resto = url.split("://", 1)[1]
        sep = "&" if "?" in resto else "?"
        url = f"mongodb://hsr:{quote_plus(clave)}@{resto}{sep}authSource=admin"
    return url


def cargar(datos: Path, resumen: Path, url: str, base: str | None = None) -> dict:
    import pymongo
    if not datos.exists() or not resumen.exists():
        sys.exit(f"No encuentro {datos} o {resumen}. Primero corra:  python scripts/clusters_vitaldb.py")
    df = pd.read_csv(datos)
    res = json.loads(resumen.read_text(encoding="utf-8"))
    ahora = datetime.now(timezone.utc)

    cliente = pymongo.MongoClient(url, serverSelectionTimeoutMS=5000, tz_aware=True)
    try:
        cliente.admin.command("ping")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"No se pudo conectar a MongoDB ({type(e).__name__}). ¿Está arriba el contenedor hsr-mongo y la clave es correcta?")
    db = cliente.get_database(base) if base else cliente.get_default_database("hsr")

    filas = df.astype(object).where(df.notna(), None).to_dict("records")
    for f in filas:
        f["fuente"] = FUENTE
    db["dataset_tabular"].delete_many({"fuente": FUENTE})
    db["dataset_tabular"].create_index([("fuente", 1), ("id", 1)], unique=True, name="uq_fuente_id")
    db["dataset_tabular"].create_index([("cluster", 1), ("origen", 1)], name="ix_cluster_origen")
    for i in range(0, len(filas), 2000):
        db["dataset_tabular"].insert_many(filas[i:i + 2000])

    db["clusters_resumen"].delete_many({"fuente": FUENTE})
    db["clusters_resumen"].create_index([("cluster", 1)], name="ix_cluster")
    db["clusters_resumen"].insert_many([{**r, "fuente": FUENTE, "cargado_at": ahora} for r in res])
    return {"filas": len(filas), "reales": int((df["origen"] == "real").sum()),
            "sinteticos": int((df["origen"] == "sintetico").sum()), "clusters": len(res)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Sube los clusters de VitalDB a MongoDB")
    ap.add_argument("--datos", type=Path, default=SALIDA / "vitaldb_clusters.csv")
    ap.add_argument("--resumen", type=Path, default=SALIDA / "clusters_resumen.json")
    ap.add_argument("--mongo-url")
    a = ap.parse_args()
    r = cargar(a.datos, a.resumen, url_mongo(a.mongo_url))
    print(f"Listo: {r['filas']:,} filas en dataset_tabular ({r['reales']:,} reales, {r['sinteticos']:,} sintéticas) "
          f"y {r['clusters']} clusters en clusters_resumen.")
    print("Compruebe:  GET /analitica/clusters   (con un token de admin, contable o coordinador)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
