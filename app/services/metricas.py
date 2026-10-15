"""
Métricas de funcionamiento de la API, en memoria (se reinician con el proceso).

El middleware de app/main.py llama a `anotar` en cada petición con la ruta
como plantilla (/pacientes/{paciente_id}, no el id real: así no se guardan
identificadores) y el tiempo de respuesta. El admin las ve en Rendimiento.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_inicio = time.time()
_ultimas = deque(maxlen=5000)                  # (instante, ruta, status, ms)
_por_ruta = defaultdict(lambda: {"n": 0, "err4": 0, "err5": 0, "ms": deque(maxlen=500)})

_IGNORAR = ("/salud", "/interno/")


def anotar(ruta: str, status: int, ms: float) -> None:
    if ruta.startswith(_IGNORAR):
        return
    with _lock:
        _ultimas.append((time.time(), ruta, status, ms))
        r = _por_ruta[ruta]
        r["n"] += 1
        r["err4"] += 400 <= status < 500
        r["err5"] += status >= 500
        r["ms"].append(ms)


def _pct(valores, p):
    if not valores:
        return None
    v = sorted(valores)
    return round(v[min(len(v) - 1, int(len(v) * p))], 1)


def resumen() -> dict:
    ahora = time.time()
    with _lock:
        ultimas = list(_ultimas)
        rutas = {k: {"n": v["n"], "err4": v["err4"], "err5": v["err5"], "ms": list(v["ms"])} for k, v in _por_ruta.items()}
    hora = [u for u in ultimas if ahora - u[0] <= 3600]
    ms = [u[3] for u in hora]
    top = sorted(rutas.items(), key=lambda kv: -kv[1]["n"])[:12]
    return {
        "desde": _inicio,
        "minutos_activo": round((ahora - _inicio) / 60),
        "ultima_hora": {
            "peticiones": len(hora),
            "errores_cliente": sum(1 for u in hora if 400 <= u[2] < 500),
            "errores_servidor": sum(1 for u in hora if u[2] >= 500),
            "p50_ms": _pct(ms, 0.5), "p95_ms": _pct(ms, 0.95),
        },
        "rutas": [{"ruta": k, "peticiones": v["n"], "errores_4xx": v["err4"], "errores_5xx": v["err5"],
                   "p50_ms": _pct(v["ms"], 0.5), "p95_ms": _pct(v["ms"], 0.95)} for k, v in top],
    }
