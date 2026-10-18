"""
Entrena el modelo de riesgo de UCI posoperatoria y guarda:

    modelo/modelo.joblib   {"pipeline", "variables", "umbral", "version"}
    modelo/metricas.json   métricas globales, por subgrupo y tabla de umbrales (R22)

Uso (dentro del contenedor, con la carpeta montada para que el modelo quede en disco):
    docker compose run --rm -v "${PWD}\\ml:/srv" ml python entrenar.py
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from caracteristicas import derivar

AQUI = Path(__file__).parent
VARIABLES = ["edad", "sexo", "glucosa", "potasio", "hemoglobina"]
OBJETIVO = "uci"              # 1 = necesitó UCI posoperatoria
VERSION = "provisional-0"     # cambia cuando uses el dataset real

# Criterio clínico del umbral: un falso negativo (no alertar a quien termina en
# UCI) cuesta más que un falso positivo, así que se exige sensibilidad mínima y,
# entre los umbrales que la cumplen, se toma el de mayor especificidad.
SENSIBILIDAD_MINIMA = 0.80
UMBRALES = [round(u, 2) for u in np.arange(0.10, 0.91, 0.05)]


def cargar_datos(n: int = 3000) -> pd.DataFrame:
    """PROVISIONAL: datos inventados mientras se define el dataset real (VitalDB).
    Cuando esté: return pd.read_csv(AQUI / "datos" / "vitaldb.csv") con las columnas renombradas."""
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "edad": rng.integers(18, 90, n),
        "sexo": rng.integers(0, 2, n),
        "glucosa": rng.normal(105, 30, n).clip(30, 400),
        "potasio": rng.normal(4.2, 0.6, n).clip(2.0, 7.5),
        "hemoglobina": rng.normal(13, 2, n).clip(5, 19),
    })
    # El riesgo sube con la edad, glucosa y potasio lejos de lo normal y hemoglobina baja
    puntaje = (-4.0 + 0.04 * (df.edad - 50)
               + 0.04 * (df.glucosa - 100).abs()
               + 1.5 * (df.potasio - 4.2).abs()
               + 0.5 * (12 - df.hemoglobina).clip(lower=0))
    df["uci"] = (rng.random(n) < 1 / (1 + np.exp(-puntaje))).astype(int)
    return df


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
    print(f"{len(df)} pacientes, {y.mean():.1%} con UCI")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, stratify=y, random_state=42)

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


if __name__ == "__main__":
    main()
