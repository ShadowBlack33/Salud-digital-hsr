#!/usr/bin/env python3
"""
Base tabular real (VitalDB) y aumento de datos por clusters (R07).

Qué hace, en orden:
  1. Carga clinical_data.csv de VitalDB (PhysioNet, CC BY 4.0). Si no se indica
     --archivo, lo descarga de PhysioNet (o de la API de VitalDB) a data/vitaldb/.
  2. Limpia y se queda con las variables que se conocen ANTES de operar.
  3. Separa entrenamiento y prueba POR PACIENTE (subjectid) antes de todo lo
     demás (incluida la imputación de faltantes): el agrupamiento y los
     sintéticos solo ven el entrenamiento.
  4. Elige el número de grupos con el método del codo y el coeficiente de silueta.
  5. Agrupa con k-means, describe cada grupo en lenguaje clínico y mide la
     estabilidad del agrupamiento.
  6. Genera pacientes sintéticos DENTRO de cada cluster (solo desde el
     entrenamiento) y los marca con origen = "sintetico" y su cluster.
  7. Escribe los resultados y el informe docs/INFORME_CLUSTERS.md con las cifras reales.

Los desenlaces (días en UCI, mortalidad, duración) NO entran al agrupamiento ni
se inventan para los sintéticos: se usan solo para describir cada grupo. Un
modelo no debe medirse con casos sintéticos (ver docs/DATASETS.md).

Uso:
    pip install -r scripts/requirements-datos.txt
    python scripts/clusters_vitaldb.py                         # descarga y corre todo
    python scripts/clusters_vitaldb.py --archivo D:/vitaldb/clinical_data.csv
    python scripts/clusters_vitaldb.py --k 4                   # fijar el número de grupos
    python scripts/clusters_vitaldb.py --modo proporcional     # 1 sintético por cada real

Después:  python scripts/cargar_clusters.py   (sube los resultados a MongoDB)

Fuente de los datos: Lee H., Jung C. (2022). VitalDB, a high-fidelity multi-parameter
vital signs database in surgical patients (v1.0.0). PhysioNet. https://doi.org/10.13026/czw8-9p62
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SALIDA_DEF = RAIZ / "data" / "vitaldb"
URL_PHYSIONET = "https://physionet.org/files/vitaldb/1.0.0/clinical_data.csv"
URL_API = "https://api.vitaldb.net/cases"

# ------------------------------------------------------------------ variables
# Solo lo que se conoce antes de la cirugía. Los desenlaces quedan fuera a propósito.
NUM = ["age", "bmi", "asa", "preop_hb", "preop_cr", "preop_alb", "preop_gluc"]
BIN = ["emop", "preop_htn", "preop_dm", "sex_m"]
CAT = ["department"]
DESENLACES = ["los_icu", "los_postop", "death_inhosp", "opdur"]
REQUERIDAS = ["caseid", "age", "sex", "asa", "department"]
# Valores plausibles; fuera de rango se tratan como dato faltante (error de captura).
RANGOS = {"age": (18, 100), "bmi": (12, 60), "asa": (1, 6), "preop_hb": (3, 20),
          "preop_cr": (0.2, 15), "preop_alb": (1, 6), "preop_gluc": (30, 800)}
DECIMALES = {"age": 0, "bmi": 1, "asa": 0, "preop_hb": 1, "preop_cr": 2, "preop_alb": 1, "preop_gluc": 0}

ETIQUETA = {  # (frase si el grupo está por encima, frase si está por debajo)
    "age": ("mayor edad", "más jóvenes"),
    "bmi": ("IMC alto", "IMC bajo"),
    "asa": ("ASA más alto (más riesgo anestésico)", "ASA bajo (pacientes sanos)"),
    "preop_hb": ("hemoglobina más alta", "hemoglobina más baja (posible anemia)"),
    "preop_cr": ("creatinina más alta (función renal reducida)", "creatinina baja"),
    "preop_alb": ("albúmina más alta", "albúmina baja (desnutrición o inflamación)"),
    "preop_gluc": ("glucosa alta", "glucosa más baja"),
    "emop": ("más cirugías de urgencia", "casi solo cirugías programadas"),
    "preop_htn": ("más hipertensos", "casi sin hipertensión"),
    "preop_dm": ("más diabéticos", "casi sin diabetes"),
    "sex_m": ("predominio masculino", "predominio femenino"),
}


# ------------------------------------------------------------------ carga y limpieza
def descargar(destino: Path) -> Path:
    """Descarga clinical_data.csv (≈ 2 MB). Primero PhysioNet; si falla, la API de VitalDB."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and destino.stat().st_size > 100_000:
        return destino
    errores = []
    for url in (URL_PHYSIONET, URL_API):
        try:
            print(f"Descargando {url}")
            urllib.request.urlretrieve(url, destino)
            if destino.stat().st_size > 100_000:
                return destino
        except Exception as e:  # noqa: BLE001
            errores.append(f"{url}: {e}")
    sys.exit("No se pudo descargar VitalDB:\n  " + "\n  ".join(errores) +
             f"\nDescargue clinical_data.csv de {URL_PHYSIONET.rsplit('/', 1)[0]}/ y use --archivo.")


def cargar(archivo: Path | None) -> pd.DataFrame:
    ruta = archivo or descargar(SALIDA_DEF / "clinical_data.csv")
    df = pd.read_csv(ruta)
    falta = [c for c in REQUERIDAS if c not in df.columns]
    if falta:
        sys.exit(f"{ruta} no parece el clinical_data.csv de VitalDB: faltan columnas {falta}")
    return df


def preparar(df: pd.DataFrame, incluir_menores: bool = False) -> tuple[pd.DataFrame, dict]:
    """
    Limpia y construye la tabla de trabajo. Devuelve (tabla, bitácora) donde la
    bitácora cuenta qué se descartó y cuánto se imputó (va al informe).
    """
    bit: dict = {"filas_originales": int(len(df))}
    d = df.copy()
    if "subjectid" not in d.columns:
        d["subjectid"] = d["caseid"]
    d = d.dropna(subset=["age", "sex", "asa", "department"])
    bit["tras_quitar_faltantes_esenciales"] = int(len(d))
    for c in ("preop_htn", "preop_dm", "emop"):
        if c not in d.columns:
            d[c] = np.nan
    d["sex_m"] = (d["sex"].astype(str).str.upper().str[0] == "M").astype(float)
    if not incluir_menores:
        d = d[d["age"] >= 18]
    bit["tras_quedarse_con_adultos"] = int(len(d))
    # El desenlace de UCI debe existir para poder describir los grupos.
    for c in DESENLACES:
        if c not in d.columns:
            d[c] = np.nan

    # Fuera de rango -> faltante. La imputación NO se hace aquí: se hace después de
    # separar entrenamiento y prueba, con las medianas del entrenamiento (ver imputar()).
    for c, (lo, hi) in RANGOS.items():
        if c not in d.columns:
            d[c] = np.nan
        d.loc[(d[c] < lo) | (d[c] > hi), c] = np.nan
    # Una edad imposible (p. ej. 250) es un error de captura: el caso no sirve, se descarta.
    d = d.dropna(subset=["age"])
    bit["tras_quitar_edades_imposibles"] = int(len(d))
    bit["faltantes_pct"] = {c: round(100 * float(d[c].isna().mean()), 1) for c in NUM + BIN}
    cols = ["caseid", "subjectid"] + NUM + BIN + CAT + DESENLACES
    return d[cols].reset_index(drop=True), bit


def imputar(d: pd.DataFrame, entrenamiento: pd.DataFrame) -> pd.DataFrame:
    """Rellena faltantes con la mediana del ENTRENAMIENTO (la prueba no aporta nada)."""
    medianas = entrenamiento[NUM + BIN].median()
    d = d.copy()
    d[NUM + BIN] = d[NUM + BIN].fillna(medianas)
    return d


# ------------------------------------------------------------------ separación por paciente
def dividir_por_paciente(d: pd.DataFrame, prop_prueba: float = 0.2, semilla: int = 42) -> pd.Series:
    """
    'entrenamiento' / 'prueba' por PACIENTE (subjectid): un mismo paciente con
    varias cirugías nunca queda en los dos lados. Se hace ANTES de agrupar y de
    generar sintéticos, para que nada de la prueba influya en ellos.
    """
    rng = np.random.default_rng(semilla)
    pacientes = d["subjectid"].unique()
    rng.shuffle(pacientes)
    n_prueba = max(1, int(round(len(pacientes) * prop_prueba)))
    en_prueba = set(pacientes[:n_prueba])
    return d["subjectid"].map(lambda s: "prueba" if s in en_prueba else "entrenamiento")


# ------------------------------------------------------------------ matriz de variables
def matriz(d: pd.DataFrame, columnas_dep: list[str] | None = None, media=None, desv=None, limites=None):
    """
    Variables numéricas y binarias estandarizadas + departamento en one-hot.
    Se ajusta con el entrenamiento y se reutiliza (media, desv, límites,
    columnas) para transformar la prueba sin mirarla.
    """
    x = d[NUM + BIN].astype(float).copy()
    if limites is None:  # winsorización 1–99 %: un valor extremo no debe mover un centroide
        limites = {c: (x[c].quantile(0.01), x[c].quantile(0.99)) for c in NUM}
    for c in NUM:
        x[c] = x[c].clip(*limites[c])
    dep = pd.get_dummies(d["department"].astype(str), prefix="dep").astype(float)
    if columnas_dep is None:
        columnas_dep = sorted(dep.columns)
    dep = dep.reindex(columns=columnas_dep, fill_value=0.0)
    x = pd.concat([x, dep], axis=1)
    if media is None:
        media, desv = x.mean(), x.std(ddof=0).replace(0, 1.0)
    return ((x - media) / desv), {"columnas_dep": columnas_dep, "media": media, "desv": desv, "limites": limites}


# ------------------------------------------------------------------ elegir el número de grupos
def evaluar_k(X: np.ndarray, k_max: int, semilla: int) -> pd.DataFrame:
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    filas = []
    for k in range(2, k_max + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=semilla).fit(X)
        sil = silhouette_score(X, km.labels_, sample_size=min(5000, len(X)), random_state=semilla)
        filas.append({"k": k, "inercia": float(km.inertia_), "silueta": float(sil),
                      "min_grupo_pct": round(100 * np.bincount(km.labels_).min() / len(X), 1)})
    return pd.DataFrame(filas)


def k_codo(ks: np.ndarray, inercias: np.ndarray) -> int:
    """Método del codo: el punto más alejado de la recta entre el primer y el último k."""
    x = (ks - ks.min()) / max(ks.max() - ks.min(), 1)
    y = (inercias - inercias.min()) / max(inercias.max() - inercias.min(), 1e-12)
    # distancia de cada punto (x, y) a la recta que une (0, y0) con (1, y_final)
    p0, p1 = np.array([x[0], y[0]]), np.array([x[-1], y[-1]])
    v = p1 - p0
    dist = np.abs(v[0] * (y - p0[1]) - v[1] * (x - p0[0])) / np.hypot(*v)
    return int(ks[int(np.argmax(dist))])


def elegir_k(tabla_k: pd.DataFrame, k_min_util: int = 3, min_grupo_pct: float = 3.0) -> tuple[int, int, str]:
    """
    Devuelve (k elegido, k del codo, justificación). Criterio: mayor silueta
    entre k >= 3 (con k=2 casi cualquier base se parte en dos y no dice nada
    clínico) cuyo grupo más pequeño tenga al menos 3 % de los casos.
    """
    k_c = k_codo(tabla_k["k"].to_numpy(), tabla_k["inercia"].to_numpy())
    candidatos = tabla_k[(tabla_k["k"] >= k_min_util) & (tabla_k["min_grupo_pct"] >= min_grupo_pct)]
    if candidatos.empty:
        candidatos = tabla_k[tabla_k["k"] >= k_min_util]
    fila = candidatos.loc[candidatos["silueta"].idxmax()]
    k = int(fila["k"])
    acuerdo = "coincide con" if abs(k - k_c) == 0 else ("está a un grupo del" if abs(k - k_c) == 1 else "difiere del")
    texto = (f"Se eligió k = {k}: tiene la mayor silueta ({fila['silueta']:.3f}) entre los k ≥ {k_min_util} "
             f"con grupos de al menos {min_grupo_pct:.0f} % de los casos. El método del codo sugiere k = {k_c}; "
             f"la elección {acuerdo} codo.")
    return k, k_c, texto


# ------------------------------------------------------------------ ajuste, estabilidad y perfil
def ajustar(X: np.ndarray, k: int, semilla: int):
    from sklearn.cluster import KMeans
    return KMeans(n_clusters=k, n_init=20, random_state=semilla).fit(X)


def estabilidad(X: np.ndarray, k: int, semilla: int, repeticiones: int = 6) -> float:
    """Índice de Rand ajustado promedio entre agrupamientos con semillas distintas (1 = idénticos)."""
    from itertools import combinations
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score
    etiquetas = [KMeans(n_clusters=k, n_init=3, random_state=semilla + 1 + i).fit_predict(X) for i in range(repeticiones)]
    return float(np.mean([adjusted_rand_score(a, b) for a, b in combinations(etiquetas, 2)]))


def perfilar(d: pd.DataFrame) -> pd.DataFrame:
    """Una fila por cluster: tamaño, perfil preoperatorio y desenlaces (solo para describir)."""
    filas = []
    for c, g in d.groupby("cluster"):
        dep = g["department"].value_counts(normalize=True)
        filas.append({
            "cluster": int(c), "n": int(len(g)), "pct": round(100 * len(g) / len(d), 1),
            "edad": g["age"].mean(), "imc": g["bmi"].mean(), "asa": g["asa"].mean(),
            "hombres_pct": 100 * g["sex_m"].mean(), "urgencia_pct": 100 * g["emop"].mean(),
            "hta_pct": 100 * g["preop_htn"].mean(), "dm_pct": 100 * g["preop_dm"].mean(),
            "hb": g["preop_hb"].mean(), "creatinina": g["preop_cr"].mean(),
            "albumina": g["preop_alb"].mean(), "glucosa": g["preop_gluc"].mean(),
            "servicio_principal": str(dep.index[0]), "servicio_principal_pct": round(100 * float(dep.iloc[0]), 1),
            # desenlaces: solo existen en casos reales
            "uci_pct": 100 * float((g["los_icu"] > 0).mean()) if g["los_icu"].notna().any() else np.nan,
            "dias_uci_media": g.loc[g["los_icu"] > 0, "los_icu"].mean() if (g["los_icu"] > 0).any() else 0.0,
            "mortalidad_pct": 100 * g["death_inhosp"].mean() if g["death_inhosp"].notna().any() else np.nan,
            "duracion_cirugia_min": g["opdur"].mean(),
        })
    return pd.DataFrame(filas).sort_values("cluster").reset_index(drop=True)


def describir(d: pd.DataFrame, cluster: int, max_rasgos: int = 3, umbral_z: float = 0.4) -> str:
    """Descripción clínica corta: las variables en que el grupo más se aleja del conjunto."""
    g = d[d["cluster"] == cluster]
    zs = {}
    for c in NUM + BIN:
        s = d[c].std(ddof=0)
        if s > 0:
            zs[c] = (g[c].mean() - d[c].mean()) / s
    rasgos = [(abs(z), c, z) for c, z in zs.items() if abs(z) >= umbral_z]
    rasgos.sort(reverse=True)
    frases = [ETIQUETA[c][0 if z > 0 else 1] for _, c, z in rasgos[:max_rasgos]]
    dep = g["department"].value_counts(normalize=True)
    base = d["department"].value_counts(normalize=True)
    if dep.iloc[0] >= 0.5 and dep.iloc[0] > base.get(dep.index[0], 0) + 0.10:
        frases.append(f"predomina {dep.index[0]} ({100 * dep.iloc[0]:.0f} %)")
    return "; ".join(frases) if frases else "perfil cercano al promedio del conjunto"


# ------------------------------------------------------------------ aumento por clusters
def sintetizar(g: pd.DataFrame, n: int, rng: np.random.Generator) -> pd.DataFrame:
    """
    n pacientes sintéticos con la distribución del cluster (solo de casos de
    ENTRENAMIENTO): normal multivariada para las variables continuas (con
    media y covarianza del grupo, recortadas al rango observado), Bernoulli
    para las binarias y muestreo categórico para el servicio. No inventa
    desenlaces: la etiqueta solo existe en casos reales.
    """
    cont = [c for c in NUM]
    mu = g[cont].mean().to_numpy()
    if len(g) >= 10:
        cov = np.cov(g[cont].to_numpy().T) + np.eye(len(cont)) * 1e-6
    else:  # muy pocos casos: sin correlaciones, para no inventar estructura
        cov = np.diag(g[cont].var(ddof=0).to_numpy() + 1e-6)
    x = rng.multivariate_normal(mu, cov, size=n)
    out = pd.DataFrame(x, columns=cont)
    for c in cont:
        out[c] = out[c].clip(g[c].min(), g[c].max()).round(DECIMALES[c])
    for c in BIN:
        out[c] = (rng.random(n) < g[c].mean()).astype(float)
    dep = g["department"].value_counts(normalize=True)
    out["department"] = rng.choice(dep.index.to_numpy(), size=n, p=dep.to_numpy())
    return out


def aumentar(real_entrenamiento: pd.DataFrame, modo: str, factor: float, tope: float, semilla: int) -> pd.DataFrame:
    """
    modo 'equilibrar': cada cluster sube hasta el tamaño del más grande (con un
                       tope de `tope` veces sus casos reales, para no inventar de más).
    modo 'proporcional': `factor` sintéticos por cada caso real de entrenamiento.
    """
    rng = np.random.default_rng(semilla + 7)
    tamanos = real_entrenamiento["cluster"].value_counts()
    grande = int(tamanos.max())
    partes = []
    for c, n_real in tamanos.sort_index().items():
        n_sint = int(min(grande - n_real, tope * n_real)) if modo == "equilibrar" else int(round(factor * n_real))
        if n_sint <= 0:
            continue
        s = sintetizar(real_entrenamiento[real_entrenamiento["cluster"] == c], n_sint, rng)
        s["cluster"] = int(c)
        partes.append(s)
    if not partes:
        return pd.DataFrame(columns=NUM + BIN + CAT + ["cluster"])
    return pd.concat(partes, ignore_index=True)


def calidad_sintetica(real: pd.DataFrame, sint: pd.DataFrame) -> pd.DataFrame:
    """
    Compara real (entrenamiento) y sintético DENTRO de cada cluster (el sintético imita a su
    grupo, no al conjunto: en modo 'equilibrar' el total cambia a propósito). Se reporta el
    promedio ponderado por la cantidad de sintéticos de cada grupo: diferencia de medias en
    desviaciones estándar del grupo real y estadístico KS.
    """
    from scipy.stats import ks_2samp
    filas = []
    pesos = sint["cluster"].value_counts()
    for v in NUM + BIN:
        mr, ms, dif, ks = 0.0, 0.0, 0.0, 0.0
        for c, w in pesos.items():
            a, b = real.loc[real["cluster"] == c, v], sint.loc[sint["cluster"] == c, v]
            s = a.std(ddof=0) or 1.0
            mr += w * a.mean()
            ms += w * b.mean()
            dif += w * abs(a.mean() - b.mean()) / s
            ks += w * float(ks_2samp(a, b).statistic)
        n = float(pesos.sum())
        filas.append({"variable": v, "media_real": mr / n, "media_sintetica": ms / n,
                      "dif_en_desv": dif / n, "ks": ks / n})
    return pd.DataFrame(filas)


# ------------------------------------------------------------------ informe
def _tabla_md(df: pd.DataFrame, formatos: dict[str, str] | None = None) -> str:
    formatos = formatos or {}
    enc = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    filas = []
    for _, r in df.iterrows():
        celdas = []
        for c in df.columns:
            v = r[c]
            celdas.append(formatos.get(c, "{}").format(v) if not (isinstance(v, float) and np.isnan(v)) else "—")
        filas.append("| " + " | ".join(celdas) + " |")
    return enc + "\n".join(filas) + "\n"


def escribir_informe(ruta: Path, r: dict) -> None:
    p = r["perfil"]
    resumen = p[["cluster", "n", "pct", "n_sinteticos", "descripcion"]].rename(
        columns={"n": "Casos reales", "pct": "% reales", "n_sinteticos": "Sintéticos", "descripcion": "Descripción"})
    resumen.columns = ["Cluster", "Casos reales", "% de los reales", "Sintéticos", "Descripción"]
    perfil = p[["cluster", "edad", "imc", "asa", "hombres_pct", "urgencia_pct", "hta_pct", "dm_pct", "hb", "creatinina", "albumina", "glucosa"]]
    perfil.columns = ["Cluster", "Edad", "IMC", "ASA", "% hombres", "% urgencia", "% HTA", "% DM", "Hb", "Creat.", "Alb.", "Gluc."]
    desen = p[["cluster", "servicio_principal", "servicio_principal_pct", "uci_pct", "dias_uci_media", "mortalidad_pct", "duracion_cirugia_min"]]
    desen.columns = ["Cluster", "Servicio principal", "% del servicio", "% con estancia en UCI", "Días de UCI (media, los que pasaron)", "% mortalidad intrahospitalaria", "Duración de la cirugía (min)"]
    k_t = r["tabla_k"][["k", "inercia", "silueta", "min_grupo_pct"]]
    k_t.columns = ["k", "Inercia", "Silueta", "Grupo más pequeño (%)"]
    calidad = r["calidad"][["variable", "media_real", "media_sintetica", "dif_en_desv", "ks"]]
    calidad.columns = ["Variable", "Media real", "Media sintética", "Diferencia (desv. estándar)", "KS"]
    b = r["bitacora"]
    imp = ", ".join(f"{k} {v} %" for k, v in b["faltantes_pct"].items() if v > 0) or "ninguno"
    txt = f"""# Informe de clusters y aumento de datos (R07)

*Generado automáticamente por `scripts/clusters_vitaldb.py` el {date.today().isoformat()}. Semilla {r['semilla']}.*
*Los números de este informe son los de la corrida real: si se vuelve a ejecutar con otro archivo o semilla, cambian.*

## 1. Datos de partida

- **Fuente:** VitalDB (PhysioNet, v1.0.0), Seoul National University Hospital. Licencia CC BY 4.0.
  Cita: Lee H., Jung C. (2022). https://doi.org/10.13026/czw8-9p62
- Filas del archivo: **{b['filas_originales']:,}**. Tras quitar casos sin edad, sexo, ASA o servicio:
  **{b['tras_quitar_faltantes_esenciales']:,}**. Tras quedarse con adultos (≥ 18 años): **{b['tras_quedarse_con_adultos']:,}**.
  Tras descartar edades imposibles (error de captura): **{b['tras_quitar_edades_imposibles']:,}** casos reales.
- **Variables usadas para agrupar** (todas conocidas *antes* de operar): edad, IMC, ASA, hemoglobina,
  creatinina, albúmina y glucosa preoperatorias, cirugía de urgencia, hipertensión, diabetes, sexo y servicio quirúrgico.
- **Variables que NO se usan para agrupar:** los desenlaces (días en UCI, mortalidad, duración de la cirugía).
  Se emplean solo para describir cada grupo, así el agrupamiento no "sabe" lo que se quiere predecir.
- Valores fuera de rango clínico se tomaron como faltantes. Los faltantes (porcentaje por variable: {imp})
  se rellenaron con la **mediana del conjunto de entrenamiento**, calculada después de separar entrenamiento y prueba.

## 2. Separación entrenamiento / prueba

Antes de agrupar y de generar sintéticos, los casos se separaron **por paciente** (`subjectid`):
**{r['n_entrenamiento']:,}** casos de entrenamiento y **{r['n_prueba']:,}** de prueba ({r['n_pacientes_prueba']:,} pacientes en prueba).
Un paciente con varias cirugías nunca queda de los dos lados. El agrupamiento y los sintéticos usan **solo el
entrenamiento**; los casos de prueba se asignan al cluster más cercano sin haber influido en él. Cualquier métrica
de un modelo debe calcularse únicamente con casos reales de prueba (columna `split = prueba`).

## 3. Número de grupos

Variables estandarizadas (media 0, desviación 1; extremos recortados al percentil 1–99) y k-means con 10 inicializaciones.

{_tabla_md(k_t, {'Inercia': '{:,.0f}', 'Silueta': '{:.3f}', 'Grupo más pequeño (%)': '{:.1f}'})}
{r['justificacion_k']}

**Estabilidad:** repitiendo el agrupamiento con {r['rep_estab']} semillas distintas, el índice de Rand ajustado
promedio entre corridas fue **{r['estabilidad']:.3f}** (1 = siempre los mismos grupos).{' Es alto: los grupos no dependen del azar de la inicialización.' if r['estabilidad'] >= 0.9 else ' Es moderado: los límites entre algunos grupos son difusos, y debe leerse con cautela.'}

![Codo y silueta](img/clusters_k.png)

## 4. Los grupos y su lectura clínica

{_tabla_md(resumen, {'Casos reales': '{:,.0f}', '% de los reales': '{:.1f}', 'Sintéticos': '{:,.0f}'})}
**Perfil preoperatorio (medias; los porcentajes son de cada grupo):**

{_tabla_md(perfil, {'Edad': '{:.1f}', 'IMC': '{:.1f}', 'ASA': '{:.2f}', '% hombres': '{:.0f}', '% urgencia': '{:.0f}', '% HTA': '{:.0f}', '% DM': '{:.0f}', 'Hb': '{:.1f}', 'Creat.': '{:.2f}', 'Alb.': '{:.1f}', 'Gluc.': '{:.0f}'})}
**Desenlaces observados en casos reales** (no se usaron para formar los grupos):

{_tabla_md(desen, {'% del servicio': '{:.0f}', '% con estancia en UCI': '{:.1f}', 'Días de UCI (media, los que pasaron)': '{:.1f}', '% mortalidad intrahospitalaria': '{:.1f}', 'Duración de la cirugía (min)': '{:.0f}'})}
![Perfil de los grupos](img/clusters_perfil.png)

### Interpretación (borrador a validar por el área clínica)

{r['interpretacion']}

> Un cluster es una agrupación estadística, no un diagnóstico. Esta lectura es un borrador generado a partir de
> los promedios; debe revisarla y firmarla el ingeniero biomédico o un profesional de la salud antes de la sustentación.

## 5. Aumento de datos

- Modo: **{r['modo']}**{(' (cada grupo sube hasta el tamaño del más grande, con un máximo de ' + str(r['tope']) + ' veces sus casos reales)') if r['modo'] == 'equilibrar' else (' (' + str(r['factor']) + ' sintético por cada caso real de entrenamiento)')}.
- Se generaron **{r['n_sinteticos']:,}** pacientes sintéticos, todos marcados `origen = sintetico`, con su `cluster`
  y `split = entrenamiento`. Dentro de cada grupo: variables continuas con distribución normal multivariada
  (media y covarianza del grupo, recortadas al rango observado), variables binarias con la frecuencia del grupo y
  servicio quirúrgico con las proporciones del grupo.
- **No se inventan desenlaces:** los sintéticos no traen días de UCI ni mortalidad. Sirven para balancear
  grupos pequeños y probar el pipeline; la etiqueta solo existe en casos reales.

**Calidad de los sintéticos frente a los reales de entrenamiento** (diferencia pequeña y KS bajo = se parecen):

{_tabla_md(calidad, {'Media real': '{:.2f}', 'Media sintética': '{:.2f}', 'Diferencia (desv. estándar)': '{:.3f}', 'KS': '{:.3f}'})}
## 6. Limitaciones

- Los datos son de un hospital coreano: no representan a una población colombiana ni al caso hipotético de 300 camas.
- Los sintéticos conservan la estructura de los grupos pero **no son evidencia clínica**. No se usan para medir modelos.
- Los grupos dependen de las variables elegidas y de k-means (grupos redondeados, de tamaño parecido); otro método podría dar otra partición.
- Los desenlaces de UCI de VitalDB reflejan las prácticas de ese hospital.

## 7. Cómo reproducirlo

```bash
pip install -r scripts/requirements-datos.txt
python scripts/clusters_vitaldb.py --semilla {r['semilla']}
python scripts/cargar_clusters.py
```
"""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(txt, encoding="utf-8")


def interpretacion(p: pd.DataFrame, total_uci_pct: float) -> str:
    """Lectura breve por grupo, solo con lo que muestran los números."""
    lineas = []
    for _, f in p.iterrows():
        riesgo = ""
        if not np.isnan(f["uci_pct"]):
            if f["uci_pct"] >= 1.5 * total_uci_pct:
                riesgo = f" Es el tipo de paciente con **mayor** pasaje por UCI ({f['uci_pct']:.1f} % frente a {total_uci_pct:.1f} % del conjunto): conviene reservar cama de UCI con anticipación."
            elif f["uci_pct"] <= 0.5 * total_uci_pct:
                riesgo = f" Pasa poco por UCI ({f['uci_pct']:.1f} % frente a {total_uci_pct:.1f} % del conjunto)."
            else:
                riesgo = f" Su pasaje por UCI ({f['uci_pct']:.1f} %) es cercano al del conjunto ({total_uci_pct:.1f} %)."
        lineas.append(f"- **Cluster {int(f['cluster'])}** ({int(f['n']):,} casos, {f['pct']:.1f} %): {f['descripcion']}.{riesgo}")
    return "\n".join(lineas)


# ------------------------------------------------------------------ figuras
def figuras(carpeta: Path, tabla_k: pd.DataFrame, k_elegido: int, k_c: int, d: pd.DataFrame) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib no está instalado: se omiten las figuras.")
        return
    carpeta.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    ax[0].plot(tabla_k["k"], tabla_k["inercia"], "o-")
    ax[0].axvline(k_c, ls="--", c="gray")
    ax[0].set(title=f"Método del codo (sugiere k = {k_c})", xlabel="k", ylabel="Inercia")
    ax[1].plot(tabla_k["k"], tabla_k["silueta"], "o-", c="tab:green")
    ax[1].axvline(k_elegido, ls="--", c="gray")
    ax[1].set(title=f"Silueta (se eligió k = {k_elegido})", xlabel="k", ylabel="Coeficiente de silueta")
    fig.tight_layout()
    fig.savefig(carpeta / "clusters_k.png", dpi=140)
    plt.close(fig)

    cols = NUM + BIN
    z = pd.DataFrame({c: ((g[cols].mean() - d[cols].mean()) / d[cols].std(ddof=0).replace(0, 1))
                      for c, g in d.groupby("cluster")}).T
    fig, ax = plt.subplots(figsize=(9, 0.6 * len(z) + 1.8))
    im = ax.imshow(z.to_numpy(), cmap="RdBu_r", vmin=-1.5, vmax=1.5, aspect="auto")
    ax.set_xticks(range(len(cols)), cols, rotation=40, ha="right")
    ax.set_yticks(range(len(z)), [f"Cluster {int(i)}" for i in z.index])
    for i in range(z.shape[0]):
        for j in range(z.shape[1]):
            ax.text(j, i, f"{z.iloc[i, j]:+.1f}", ha="center", va="center", fontsize=8)
    ax.set_title("Diferencia de cada grupo frente al conjunto (en desviaciones estándar)")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(carpeta / "clusters_perfil.png", dpi=140)
    plt.close(fig)


# ------------------------------------------------------------------ flujo completo
def ejecutar(df_crudo: pd.DataFrame, *, k_fijo: int = 0, k_max: int = 10, modo: str = "equilibrar",
             factor: float = 1.0, tope: float = 5.0, semilla: int = 42, incluir_menores: bool = False) -> dict:
    """Todo el proceso sobre un DataFrame; devuelve los resultados (la CLI y el notebook lo usan)."""
    d, bit = preparar(df_crudo, incluir_menores)
    if len(d) < 200:
        sys.exit(f"Quedaron solo {len(d)} casos tras la limpieza: no alcanzan para agrupar de forma estable.")
    d["split"] = dividir_por_paciente(d, 0.2, semilla)
    d = imputar(d, d[d["split"] == "entrenamiento"])
    ent = d[d["split"] == "entrenamiento"].copy()
    X_ent, aj = matriz(ent)
    tabla_k = evaluar_k(X_ent.to_numpy(), min(k_max, 12), semilla)
    if k_fijo:
        k, k_c = k_fijo, k_codo(tabla_k["k"].to_numpy(), tabla_k["inercia"].to_numpy())
        just = f"Se fijó k = {k} por parámetro (--k). El método del codo sugiere k = {k_c}."
    else:
        k, k_c, just = elegir_k(tabla_k)
    km = ajustar(X_ent.to_numpy(), k, semilla)
    estab = estabilidad(X_ent.to_numpy(), k, semilla)
    # todos los casos (también la prueba) se asignan al centroide más cercano, sin refitear
    X_todo, _ = matriz(d, aj["columnas_dep"], aj["media"], aj["desv"], aj["limites"])
    d["cluster"] = km.predict(X_todo.to_numpy())
    ent = d[d["split"] == "entrenamiento"]

    sint = aumentar(ent, modo, factor, tope, semilla)
    p = perfilar(d)
    p["descripcion"] = [describir(d, int(c)) for c in p["cluster"]]
    ns = sint["cluster"].value_counts() if len(sint) else pd.Series(dtype=int)
    p["n_sinteticos"] = [int(ns.get(int(c), 0)) for c in p["cluster"]]
    total_uci = 100 * float((d["los_icu"] > 0).mean()) if d["los_icu"].notna().any() else float("nan")

    reales = d.copy()
    reales["origen"] = "real"
    reales["id"] = reales["caseid"].astype(str)
    sint = sint.copy()
    sint["origen"], sint["split"] = "sintetico", "entrenamiento"
    sint["id"] = [f"S-{i:06d}" for i in range(1, len(sint) + 1)]
    sint["subjectid"] = np.nan
    final = pd.concat([reales, sint], ignore_index=True)
    final["sex"] = np.where(final["sex_m"] >= 0.5, "M", "F")
    cols = ["id", "origen", "cluster", "split", "subjectid"] + NUM + BIN + ["sex"] + CAT + DESENLACES
    final = final[cols]

    calidad = calidad_sintetica(ent, sint) if len(sint) else pd.DataFrame(columns=["variable", "media_real", "media_sintetica", "dif_en_desv", "ks"])
    return {
        "datos": d, "final": final, "perfil": p, "tabla_k": tabla_k, "k": k, "k_codo": k_c,
        "justificacion_k": just, "estabilidad": estab, "rep_estab": 6, "calidad": calidad,
        "bitacora": bit, "semilla": semilla, "modo": modo, "factor": factor, "tope": tope,
        "n_entrenamiento": int((d["split"] == "entrenamiento").sum()), "n_prueba": int((d["split"] == "prueba").sum()),
        "n_pacientes_prueba": int(d.loc[d["split"] == "prueba", "subjectid"].nunique()),
        "n_sinteticos": int(len(sint)), "n_reales": int(len(d)),
        "interpretacion": interpretacion(p, total_uci),
    }


def resumen_para_api(r: dict) -> list[dict]:
    """Lo que sirve GET /analitica/clusters: cluster, descripcion, n_reales, n_sinteticos (+ perfil)."""
    p = r["perfil"]
    campos = ["edad", "imc", "asa", "hombres_pct", "urgencia_pct", "hta_pct", "dm_pct", "hb", "creatinina",
              "albumina", "glucosa", "servicio_principal", "uci_pct", "mortalidad_pct"]
    salida = []
    for _, f in p.iterrows():
        salida.append({
            "cluster": int(f["cluster"]), "descripcion": f["descripcion"],
            "n_reales": int(f["n"]), "n_sinteticos": int(f["n_sinteticos"]),
            "perfil": {c: (None if (isinstance(f[c], float) and np.isnan(f[c])) else (round(float(f[c]), 2) if not isinstance(f[c], str) else f[c])) for c in campos},
        })
    return salida


def main() -> int:
    ap = argparse.ArgumentParser(description="Clusters y aumento de datos sobre VitalDB (R07)")
    ap.add_argument("--archivo", type=Path, help="clinical_data.csv local (si no, se descarga)")
    ap.add_argument("--k", type=int, default=0, help="número de grupos (0 = elegirlo con codo y silueta)")
    ap.add_argument("--k-max", type=int, default=10)
    ap.add_argument("--modo", choices=["equilibrar", "proporcional"], default="equilibrar")
    ap.add_argument("--factor", type=float, default=1.0, help="sintéticos por caso real (modo proporcional)")
    ap.add_argument("--tope", type=float, default=5.0, help="máximo de sintéticos por caso real (modo equilibrar)")
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--incluir-menores", action="store_true", help="no filtrar a adultos (≥ 18 años)")
    ap.add_argument("--salida", type=Path, default=SALIDA_DEF)
    ap.add_argument("--informe", type=Path, default=RAIZ / "docs" / "INFORME_CLUSTERS.md")
    a = ap.parse_args()

    r = ejecutar(cargar(a.archivo), k_fijo=a.k, k_max=a.k_max, modo=a.modo, factor=a.factor,
                 tope=a.tope, semilla=a.semilla, incluir_menores=a.incluir_menores)
    a.salida.mkdir(parents=True, exist_ok=True)
    r["final"].to_csv(a.salida / "vitaldb_clusters.csv", index=False)
    (a.salida / "clusters_resumen.json").write_text(
        json.dumps(resumen_para_api(r), ensure_ascii=False, indent=2), encoding="utf-8")
    figuras(a.informe.parent / "img", r["tabla_k"], r["k"], r["k_codo"], r["datos"])
    escribir_informe(a.informe, r)

    print(f"\nCasos reales: {r['n_reales']:,}  ·  sintéticos: {r['n_sinteticos']:,}  ·  clusters: {r['k']} (codo sugiere {r['k_codo']})")
    print(f"Estabilidad (ARI): {r['estabilidad']:.3f}")
    print(r["perfil"][["cluster", "n", "n_sinteticos", "descripcion"]].to_string(index=False))
    print(f"\nEscrito: {a.salida / 'vitaldb_clusters.csv'}\n         {a.salida / 'clusters_resumen.json'}\n         {a.informe}")
    print("Complete en docs/DATASETS.md los campos [COMPLETAR] de la sección Tabular con estas cifras.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
