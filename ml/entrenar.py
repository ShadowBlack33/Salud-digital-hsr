r"""
Entrena el modelo de riesgo de UCI posoperatoria con datos REALES de VitalDB y guarda:

    modelo/modelo.joblib   {"pipeline", "variables", "umbral", "version"}
    modelo/metricas.json   métricas globales, por subgrupo y tabla de umbrales (R22)

Datos: clinical_data.csv de VitalDB (PhysioNet, CC BY 4.0; ver docs/DATASETS.md).
No se sube al repositorio: se descarga una vez a ml/datos/ (está en .gitignore):

    Invoke-WebRequest https://physionet.org/files/vitaldb/1.0.0/clinical_data.csv -OutFile ml\datos\clinical_data.csv

Uso (dentro del contenedor, con la carpeta montada para que el modelo quede en disco):
    docker compose run --rm -v "${PWD}\ml:/srv" ml python entrenar.py
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from caracteristicas import derivar

AQUI = Path(__file__).parent
ARCHIVO = AQUI / "datos" / "clinical_data.csv"
VARIABLES = ["edad", "sexo", "glucosa", "potasio", "hemoglobina"]
OBJETIVO = "uci"              # 1 = pasó al menos un día en UCI después de la cirugía (icu_days > 0)
VERSION = "vitaldb-1"

# Criterio clínico del umbral: un falso negativo (no alertar a quien termina en
# UCI) cuesta más que un falso positivo, así que se exige sensibilidad mínima y,
# entre los umbrales que la cumplen, se toma el de mayor especificidad.
SENSIBILIDAD_MINIMA = 0.80
UMBRALES = [round(u, 2) for u in np.arange(0.10, 0.91, 0.05)]

# Valores fuera de rango fisiológico se tratan como faltantes (errores de captura).
RANGOS = {"glucosa": (20, 800), "potasio": (1.5, 9.0), "hemoglobina": (3, 22)}

# paciente_critico del tester.yaml (docs/tester_ia.md): se comprueba que dispare.
PACIENTE_CRITICO = {"edad": 78, "sexo": 0, "glucosa": 42, "potasio": 6.6, "hemoglobina": 6.8}
PACIENTE_NORMAL = {"edad": 35, "sexo": 1, "glucosa": 95, "potasio": 4.1, "hemoglobina": 14}


def cargar_datos(archivo: Path = ARCHIVO) -> pd.DataFrame:
    """
    VitalDB -> tabla del modelo. Solo adultos y solo casos REALES: los sintéticos
    por cluster (R07) no entran al entrenamiento ni a las métricas.
    """
    if not archivo.exists():
        raise SystemExit(f"No encuentro {archivo}. Descárgalo con:\n"
                         "  Invoke-WebRequest https://physionet.org/files/vitaldb/1.0.0/clinical_data.csv "
                         "-OutFile ml\\datos\\clinical_data.csv")
    crudo = pd.read_csv(archivo, encoding="utf-8-sig")   # el archivo trae BOM
    df = pd.DataFrame({
        "subjectid": crudo["subjectid"],
        # La edad viene como texto (por ejemplo ">89"): se toma el número.
        "edad": pd.to_numeric(crudo["age"].astype(str).str.extract(r"(\d+\.?\d*)")[0], errors="coerce"),
        "sexo": (crudo["sex"].astype(str).str.upper().str[0] == "M").astype(int),   # F = 0, M = 1
        "glucosa": crudo["preop_gluc"],       # mg/dL
        "potasio": crudo["preop_k"],          # mmol/L
        "hemoglobina": crudo["preop_hb"],     # g/dL
        OBJETIVO: (crudo["icu_days"] > 0).astype(int),
    })
    df = df[df["edad"] >= 18].copy()
    for c, (lo, hi) in RANGOS.items():
        df.loc[(df[c] < lo) | (df[c] > hi), c] = np.nan
    return df.reset_index(drop=True)


def metricas(y_real, prob, umbral) -> dict:
    y_real = np.asarray(y_real)
    pred = prob >= umbral
    tn, fp, fn, tp = confusion_matrix(y_real, pred, labels=[0, 1]).ravel()
    return {
        "n": int(len(y_real)),
        "positivos": int(y_real.sum()),
        "sensibilidad": float(tp / (tp + fn)) if tp + fn else None,
        "especificidad": float(tn / (tn + fp)) if tn + fp else None,
        "vpp": float(tp / (tp + fp)) if tp + fp else None,
        # Un subgrupo con una sola clase no tiene AUC
        "auc": float(roc_auc_score(y_real, prob)) if len(set(y_real)) == 2 else None,
        "matriz": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def elegir_umbral(y_real, prob) -> float:
    candidatos = []
    for u in UMBRALES:
        m = metricas(y_real, prob, u)
        print(f"  umbral {u:.2f}  sensibilidad {m['sensibilidad']:.3f}  especificidad {m['especificidad']:.3f}")
        if m["sensibilidad"] >= SENSIBILIDAD_MINIMA:
            candidatos.append((m["especificidad"], u))
    if not candidatos:
        raise SystemExit(f"Ningún umbral alcanza sensibilidad {SENSIBILIDAD_MINIMA}")
    return max(candidatos)[1]


def main():
    df = cargar_datos()
    X, y = df[VARIABLES], df[OBJETIVO]
    print(f"VitalDB: {len(df)} cirugías de adultos ({df['subjectid'].nunique()} pacientes), "
          f"{y.mean():.1%} con UCI")

    # Separación por PACIENTE: un paciente con varias cirugías nunca queda en
    # entrenamiento y prueba a la vez (evita que el modelo "se lo sepa").
    entreno, prueba = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
                           .split(X, y, groups=df["subjectid"]))
    X_train, X_test = X.iloc[entreno], X.iloc[prueba]
    y_train, y_test = y.iloc[entreno], y.iloc[prueba]

    pipeline = Pipeline([
        ("derivar", FunctionTransformer(derivar)),
        ("imputar", SimpleImputer(strategy="median")),
        ("escalar", StandardScaler()),
        ("modelo", LogisticRegression(class_weight="balanced", max_iter=1000)),
    ])
    pipeline.fit(X_train, y_train)

    prob = pipeline.predict_proba(X_test)[:, 1]
    print("Tabla de umbrales (conjunto de prueba):")
    umbral = elegir_umbral(y_test, prob)
    print(f"Umbral elegido: {umbral} (sensibilidad >= {SENSIBILIDAD_MINIMA}, máxima especificidad)")

    # Análisis de sesgo por subgrupo (R22)
    sexo = X_test["sexo"].values
    edad = X_test["edad"].values
    subgrupos = {
        "sexo=0": sexo == 0,
        "sexo=1": sexo == 1,
        "edad<40": edad < 40,
        "edad 40-64": (edad >= 40) & (edad < 65),
        "edad>=65": edad >= 65,
    }
    resultado = {
        "version": VERSION,
        "datos": {
            "fuente": "VitalDB clinical_data.csv (PhysioNet, CC BY 4.0), solo casos reales de adultos",
            "objetivo": "icu_days > 0",
            "cirugias": int(len(df)), "pacientes": int(df["subjectid"].nunique()),
            "prevalencia_uci": round(float(y.mean()), 4),
            "division": "25 % de prueba, separada por paciente (subjectid)",
            "entrenamiento": int(len(entreno)), "prueba": int(len(prueba)),
            "faltantes_pct": {v: round(100 * float(df[v].isna().mean()), 1) for v in VARIABLES},
        },
        "variables": VARIABLES,
        "umbral": umbral,
        "criterio_umbral": f"sensibilidad >= {SENSIBILIDAD_MINIMA}, máxima especificidad",
        "global": metricas(y_test, prob, umbral),
        "por_subgrupo": {k: metricas(y_test.values[m], prob[m], umbral) for k, m in subgrupos.items()},
        "tabla_umbrales": {str(u): metricas(y_test, prob, u) for u in UMBRALES},
    }

    destino = AQUI / "modelo"
    destino.mkdir(exist_ok=True)
    joblib.dump({"pipeline": pipeline, "variables": VARIABLES, "umbral": umbral, "version": VERSION},
                destino / "modelo.joblib")
    (destino / "metricas.json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")

    g = resultado["global"]
    print(f"AUC {g['auc']:.3f} | sensibilidad {g['sensibilidad']:.3f} | especificidad {g['especificidad']:.3f}")
    print(f"Guardado en {destino}")

    # paciente_critico del tester.yaml: con el modelo nuevo debe seguir disparando.
    for nombre, caso, debe in (("paciente_critico", PACIENTE_CRITICO, True), ("paciente normal", PACIENTE_NORMAL, False)):
        p = float(pipeline.predict_proba(pd.DataFrame([caso], columns=VARIABLES, dtype=float))[0, 1])
        ok = (p >= umbral) == debe
        print(f"{'OK   ' if ok else 'AVISO'} {nombre}: probabilidad {p:.3f} (umbral {umbral}) -> "
              f"{'crítico' if p >= umbral else 'no crítico'}")


if __name__ == "__main__":
    main()
