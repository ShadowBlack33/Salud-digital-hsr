"""
Variables derivadas que usa el modelo. Vive en su propio módulo porque el
pipeline guardado en modelo.joblib apunta a esta función: entrenar.py y app.py
la importan del mismo sitio, y así joblib la encuentra al cargar el modelo.

Glucosa y potasio tienen riesgo en "U": son peligrosos tanto bajos como altos.
Una regresión logística solo traza rectas, así que se le entrega la DISTANCIA
al valor normal, no el valor crudo.
"""
import pandas as pd

GLUCOSA_NORMAL = 100.0   # mg/dL
POTASIO_NORMAL = 4.2     # mmol/L


def derivar(X: pd.DataFrame) -> pd.DataFrame:
    X = X.copy()
    X["glucosa_desvio"] = (X["glucosa"] - GLUCOSA_NORMAL).abs()
    X["potasio_desvio"] = (X["potasio"] - POTASIO_NORMAL).abs()
    return X
