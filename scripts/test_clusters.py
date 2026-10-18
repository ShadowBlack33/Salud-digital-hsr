#!/usr/bin/env python3
"""
Pruebas del pipeline de clusters (R07) y de GET /analitica/clusters.

NO usan datos reales de VitalDB: generan una tabla falsa con las mismas columnas
(tres perfiles de paciente mezclados, con faltantes, valores imposibles y
menores de edad) para comprobar que el proceso se comporta bien. Los resultados
reales salen de scripts/clusters_vitaldb.py con el archivo de VitalDB.

Uso:  pip install -r scripts/requirements-datos.txt mongomock
      python scripts/test_clusters.py
"""
from __future__ import annotations

import inspect
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from app.core.crypto import generar_clave  # noqa: E402

os.environ.setdefault("APP_ENCRYPTION_KEY", generar_clave())
os.environ.setdefault("APP_BLIND_INDEX_KEY", generar_clave())
os.environ.setdefault("JWT_SECRET_KEY", generar_clave())

import clusters_vitaldb as cv  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import clusters as api_clusters  # noqa: E402
from app.core.deps import ContextoAcceso, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import contabilidad as mongo  # noqa: E402

OK, FALLAS = 0, []


def comprobar(n: int, descripcion: str, condicion: bool, detalle: str = "") -> None:
    global OK
    if condicion:
        OK += 1
        print(f"  ✔ [{n:02d}] {descripcion}")
    else:
        FALLAS.append(n)
        print(f"  ✘ [{n:02d}] {descripcion}  {detalle}")


# ------------------------------------------------------------------ datos falsos con forma de VitalDB
def datos_falsos(n_pacientes: int = 1500, semilla: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    perfiles = [  # (peso, edad, imc, asa, urgencia, hta, dm, hb, cr, alb, gluc, servicio, p_uci)
        (0.45, 42, 24, 1.4, 0.03, 0.05, 0.02, 14.0, 0.8, 4.3, 95, "General surgery", 0.02),
        (0.35, 68, 28, 2.6, 0.08, 0.60, 0.35, 12.5, 1.1, 3.9, 135, "Urology", 0.10),
        (0.20, 61, 25, 3.4, 0.55, 0.30, 0.15, 10.2, 1.9, 3.0, 125, "Thoracic surgery", 0.45),
    ]
    filas, caso = [], 0
    for sid in range(1, n_pacientes + 1):
        p = perfiles[rng.choice(3, p=[x[0] for x in perfiles])]
        for _ in range(rng.choice([1, 1, 1, 2, 3])):  # algunos pacientes con varias cirugías
            caso += 1
            uci = rng.random() < p[12]
            filas.append({
                "caseid": caso, "subjectid": sid,
                "age": rng.normal(p[1], 9), "sex": rng.choice(["M", "F"]),
                "bmi": rng.normal(p[2], 3.5), "asa": float(np.clip(round(rng.normal(p[3], 0.6)), 1, 5)),
                "emop": float(rng.random() < p[4]), "preop_htn": float(rng.random() < p[5]), "preop_dm": float(rng.random() < p[6]),
                "preop_hb": rng.normal(p[7], 1.4), "preop_cr": abs(rng.normal(p[8], 0.3)) + 0.3,
                "preop_alb": rng.normal(p[9], 0.4), "preop_gluc": abs(rng.normal(p[10], 25)) + 50,
                "department": p[11], "los_icu": float(rng.integers(1, 9)) if uci else 0.0,
                "los_postop": float(rng.integers(2, 20)), "death_inhosp": float(rng.random() < (0.12 if uci else 0.003)),
                "opdur": abs(rng.normal(150, 50)) + 20,
            })
    df = pd.DataFrame(filas)
    # Suciedad realista
    for c in ("preop_hb", "preop_cr", "preop_alb", "preop_gluc", "bmi"):
        df.loc[rng.random(len(df)) < 0.08, c] = np.nan
    df.loc[0, "age"], df.loc[1, "bmi"], df.loc[2, "preop_cr"] = 250.0, 400.0, 99.0
    df.loc[df.sample(40, random_state=3).index, "age"] = 6.0               # menores de edad
    df.loc[df.sample(10, random_state=4).index, "department"] = np.nan     # sin servicio
    return df


def main() -> int:
    df = datos_falsos()

    print("\nLimpieza")
    d, bit = cv.preparar(df)
    comprobar(1, "solo adultos y casos con servicio; sin edades imposibles", d["age"].between(18, 100).all() and d["department"].notna().all())
    comprobar(2, "valores fuera de rango clínico pasan a faltante (BMI 400, creatinina 99)", d["bmi"].dropna().max() <= 60 and d["preop_cr"].dropna().max() <= 15)
    comprobar(3, "la bitácora cuenta lo descartado", bit["filas_originales"] == len(df) and bit["tras_quitar_edades_imposibles"] == len(d) and bit["tras_quedarse_con_adultos"] >= len(d))
    comprobar(4, "preparar() NO imputa (eso se hace después de separar entrenamiento y prueba)", d[cv.NUM].isna().any().any())

    print("\nSeparación entrenamiento / prueba por paciente")
    split = cv.dividir_por_paciente(d, 0.2, 42)
    pac_ent, pac_prueba = set(d.loc[split == "entrenamiento", "subjectid"]), set(d.loc[split == "prueba", "subjectid"])
    comprobar(5, "ningún paciente queda en entrenamiento y prueba a la vez", pac_ent.isdisjoint(pac_prueba) and pac_prueba)
    comprobar(6, "≈ 20 % de los pacientes en prueba", abs(len(pac_prueba) / (len(pac_ent) + len(pac_prueba)) - 0.2) < 0.02)
    comprobar(7, "es determinista con la misma semilla", (cv.dividir_por_paciente(d, 0.2, 42) == split).all())

    print("\nProceso completo")
    r = cv.ejecutar(df, semilla=11)
    final, p = r["final"], r["perfil"]
    comprobar(8, f"k elegido razonable (k = {r['k']}, codo sugiere {r['k_codo']})", 3 <= r["k"] <= 8)
    comprobar(9, "la tabla de k trae inercia y silueta decrecientes/válidas", r["tabla_k"]["silueta"].between(-1, 1).all() and r["tabla_k"]["inercia"].is_monotonic_decreasing)
    comprobar(10, f"estabilidad entre semillas alta (ARI = {r['estabilidad']:.2f})", 0.6 <= r["estabilidad"] <= 1.0)
    comprobar(11, "todo caso real tiene cluster; los reales son los que quedaron tras la limpieza",
              (final["origen"] == "real").sum() == len(d) and final.loc[final["origen"] == "real", "cluster"].notna().all())
    sint = final[final["origen"] == "sintetico"]
    comprobar(12, f"se generaron sintéticos ({len(sint):,}) y TODOS llevan origen=sintetico y cluster", len(sint) > 0 and sint["cluster"].notna().all())
    comprobar(13, "los sintéticos solo se derivan del entrenamiento (split = entrenamiento)", (sint["split"] == "entrenamiento").all())
    comprobar(14, "los sintéticos NO traen desenlaces inventados (UCI, mortalidad, duración)", sint[cv.DESENLACES].isna().all().all())
    comprobar(15, "los sintéticos son valores plausibles (edad 18-100, ASA 1-6, binarias 0/1)",
              sint["age"].between(18, 100).all() and sint["asa"].between(1, 6).all() and sint["emop"].isin([0, 1]).all())
    comprobar(16, "ids únicos (reales por caseid, sintéticos S-000001...)", final["id"].is_unique and sint["id"].str.match(r"^S-\d{6}$").all())
    comprobar(17, "n_reales y n_sinteticos por cluster suman los totales",
              p["n"].sum() == (final["origen"] == "real").sum() and p["n_sinteticos"].sum() == len(sint))
    con_uci = p["uci_pct"].dropna()
    comprobar(18, "los grupos separan el riesgo de UCI (diferencia clara entre el más y el menos riesgoso)", con_uci.max() >= 2 * max(con_uci.min(), 0.5),
              str(con_uci.round(1).tolist()))
    comprobar(19, "cada cluster tiene una descripción clínica no vacía", p["descripcion"].str.len().gt(5).all())
    ent = r["datos"][r["datos"]["split"] == "entrenamiento"]
    tam = (ent["cluster"].value_counts() + sint["cluster"].value_counts().reindex(ent["cluster"].value_counts().index).fillna(0))
    comprobar(20, "modo equilibrar: los grupos quedan de tamaño parecido tras el aumento", tam.max() / tam.min() < 1.6, str(tam.to_dict()))
    comprobar(21, "calidad: la media sintética queda a menos de 0.35 desv. estándar de la real", r["calidad"]["dif_en_desv"].max() < 0.35,
              str(r["calidad"]["dif_en_desv"].round(2).tolist()))

    print("\nSin fuga de información de la prueba")
    prueba_ids = set(r["datos"].loc[r["datos"]["split"] == "prueba", "subjectid"])
    df2 = df.copy()
    es_prueba = df2["subjectid"].isin(prueba_ids)
    df2.loc[es_prueba, ["age", "bmi", "preop_cr", "preop_gluc", "emop"]] = [95, 55, 14, 700, 1]
    df2.loc[es_prueba & df2["department"].notna(), "department"] = "Servicio que solo existe en prueba"
    r2 = cv.ejecutar(df2, semilla=11)
    s1 = r["final"].query("origen == 'sintetico'").reset_index(drop=True)
    s2 = r2["final"].query("origen == 'sintetico'").reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(s1, s2)
        igual = True
    except AssertionError:
        igual = False
    comprobar(22, "cambiar TODOS los casos de prueba por valores extremos no altera ni un sintético ni el k (la prueba no influye)",
              igual and r["k"] == r2["k"])
    comprobar(23, "una categoría que solo existe en prueba no aparece en los sintéticos",
              not s2["department"].str.contains("solo existe en prueba").any())

    print("\nArchivos de salida")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cv.figuras(tmp / "img", r["tabla_k"], r["k"], r["k_codo"], r["datos"])
        comprobar(24, "se generan las dos figuras (codo/silueta y perfil de grupos)",
                  (tmp / "img" / "clusters_k.png").stat().st_size > 5000 and (tmp / "img" / "clusters_perfil.png").stat().st_size > 5000)
        cv.escribir_informe(tmp / "INFORME.md", r)
        informe = (tmp / "INFORME.md").read_text(encoding="utf-8")
        comprobar(25, "el informe se genera completo, sin llaves de plantilla sin resolver ni 'nan'",
                  len(informe) > 3000 and "{r[" not in informe and "{b[" not in informe and not re.search(r"\bnan\b", informe.lower()),
                  [l for l in informe.splitlines() if re.search(r"\bnan\b", l.lower())][:2].__str__())
        comprobar(26, "el informe trae las cifras reales (casos, sintéticos, k, estabilidad) y la justificación del k",
                  f"{len(d):,}" in informe and f"{r['n_sinteticos']:,}" in informe and r["justificacion_k"] in informe and "Estabilidad" in informe)

    print("\nResumen para la API y GET /analitica/clusters")
    resumen = cv.resumen_para_api(r)
    comprobar(27, "el resumen trae cluster, descripcion, n_reales, n_sinteticos y perfil", all({"cluster", "descripcion", "n_reales", "n_sinteticos", "perfil"} <= set(x) for x in resumen))

    import mongomock
    base = mongomock.MongoClient(tz_aware=True)["hsr_prueba_clusters"]
    mongo.usar_base(base)
    dep = inspect.signature(api_clusters.clusters).parameters["ctx"].default.dependency
    app.dependency_overrides[dep] = lambda: ContextoAcceso(usuario=None, payload={}, alcance="all", recurso="analitica", accion="read", db=None, request=None)
    app.dependency_overrides[get_db] = lambda: None
    c = TestClient(app, raise_server_exceptions=False)
    r0 = c.get("/analitica/clusters")
    comprobar(28, "sin clusters cargados responde 404 con instrucciones (no una lista vacía engañosa)", r0.status_code == 404 and "cargar_clusters" in r0.text, r0.text)
    base["clusters_resumen"].insert_many([{**x, "fuente": "vitaldb"} for x in resumen])
    r1 = c.get("/analitica/clusters")
    j = r1.json()
    comprobar(29, "con datos responde exactamente {cluster, descripcion, n_reales, n_sinteticos}",
              r1.status_code == 200 and all(set(x) == {"cluster", "descripcion", "n_reales", "n_sinteticos"} for x in j) and len(j) == r["k"], r1.text[:200])
    comprobar(30, "las cifras de la API coinciden con las del proceso",
              [(x["cluster"], x["n_reales"], x["n_sinteticos"]) for x in j] == [(x["cluster"], x["n_reales"], x["n_sinteticos"]) for x in resumen])
    comprobar(31, "con ?detalle=true agrega el perfil", all("perfil" in x for x in c.get("/analitica/clusters?detalle=true").json()))

    print("\nCarga a MongoDB (conexión)")
    import cargar_clusters as cc
    os.environ.pop("MONGO_URL_HOST", None)
    os.environ["MONGO_PASSWORD"] = "p@ss:w/rd#1"
    os.environ["MONGO_URL"] = "mongodb://localhost:27017/hsr"
    url = cc.url_mongo(None)
    comprobar(32, "si la URL no trae usuario, agrega hsr y la clave codificada (caracteres especiales incluidos)",
              url == "mongodb://hsr:p%40ss%3Aw%2Frd%231@localhost:27017/hsr?authSource=admin", url)
    comprobar(33, "una URL explícita con usuario no se toca", cc.url_mongo("mongodb://u:c@h:1/b") == "mongodb://u:c@h:1/b")

    print(f"\n{OK} verificaciones correctas, {len(FALLAS)} fallidas" + (f" -> {FALLAS}" if FALLAS else ""))
    return 1 if FALLAS else 0


if __name__ == "__main__":
    sys.exit(main())
