#!/usr/bin/env python3
"""
Prueba de punta a punta de la abstención CON modelo de lenguaje (Semana 12).

La regla de recuperación sola no separa las preguntas con respuesta de las que no la
tienen cuando la gente pregunta con sus propias palabras (docs/rag/eval/RESULTADOS.md).
Con un modelo configurado se abre la compuerta de recuperación y el modelo decide
(responde NO_ENCONTRADO si las fuentes no alcanzan). Este script mide si eso funciona:

  · las preguntas SIN respuesta (N01-N15) deben terminar en abstención;
  · las preguntas parafraseadas (P01-P15) deben terminar respondidas y citando la guía esperada.

Usa el mismo corpus, la misma recuperación y el mismo prompt que la API, pero en memoria
(sin base de datos, sin filtros por perfil). Necesita GEMINI_API_KEY en el .env y red.
Hace una llamada por pregunta (con pausa, por el límite de la capa gratuita).

Uso:  python scripts/probar_abstencion.py            (escribe docs/rag/eval/RESULTADOS_ABSTENCION.md)

Diagnóstico de unas preguntas (no escribe el archivo): qué fragmentos recibió el modelo, qué
contestó y cómo cambia con el modelo completo y los 8 fragmentos:
      python scripts/probar_abstencion.py --ids P04,P05,P11,P12
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.core.config import get_settings  # noqa: E402
from app.services import rag  # noqa: E402
from app.services.rag_core import BM25, coseno, embeber, fragmentar, leer_documento, rrf  # noqa: E402

PAUSA = 5   # segundos entre preguntas


class _Fallos(logging.Handler):
    """Cuenta las veces que el modelo no respondió (tiempo agotado, 503...) sin imprimir el rastro."""
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.n = 0

    def emit(self, record: logging.LogRecord) -> None:
        if "no respondió" in record.getMessage():
            self.n += 1


def _crudo(pregunta: str, marco: list[dict], extensa: bool) -> str:
    """Respuesta tal cual del modelo, para ver por qué se abstuvo."""
    try:
        hecho = rag._llm(pregunta, marco, None, extensa)
        return hecho[1] + " -> " + hecho[0][:400].replace("\n", " ") if hecho else "(sin proveedor)"
    except Exception as e:  # noqa: BLE001
        return f"(falló: {type(e).__name__})"


def main() -> None:
    if rag._proveedor(True) is None:
        sys.exit("No hay GEMINI_API_KEY ni XAI_API_KEY en el .env: esta prueba necesita el modelo.")
    docs = [leer_documento(p) for p in sorted((RAIZ / "docs/rag/guias").glob("*.md"))]
    frags = [f for d in docs for f in fragmentar(d)]
    bm25 = BM25([f.texto for f in frags])
    vec = embeber([f.texto for f in frags])
    if not vec:
        sys.exit("No hay modelo de embeddings (pip install fastembed).")
    preguntas = [p for p in json.loads((RAIZ / "docs/rag/eval/preguntas.json").read_text(encoding="utf-8"))
                 if p["id"].startswith(("N", "P"))]

    ids = None
    if "--ids" in sys.argv:
        ids = set(sys.argv[sys.argv.index("--ids") + 1].split(","))
        preguntas = [p for p in preguntas if p["id"] in ids]
    fallos = _Fallos()
    logging.getLogger("app.services.rag").addHandler(fallos)
    logging.getLogger("app.services.rag").propagate = False
    filas, ok_n, n_n, ok_p, n_p = [], 0, 0, 0, 0
    for p in preguntas:
        qv = embeber([p["pregunta"]])[0]
        denso = sorted(((i, coseno(qv, v)) for i, v in enumerate(vec)), key=lambda x: -x[1])[:30]
        lex = bm25.ranking(p["pregunta"], 30)
        orden = [i for i, _ in rrf([[i for i, _ in lex], [i for i, _ in denso]],
                                   pesos=[1.0, get_settings().rag_peso_denso])]
        pasa, estricto = rag.evaluar_umbral(denso[0][1], lex[0][1] if lex else 0.0, "hibrido")
        marco = [{"documento_id": frags[i].documento_id, "titulo": frags[i].titulo, "seccion": frags[i].seccion,
                  "texto": frags[i].texto} for i in orden[:rag.TOP_K_EXTENSA]]
        if ids:
            print(f"\n== {p['id']} (esperado {p['esperado']}): {p['pregunta']}")
            print("   Lo que vio el lite (4):   " + " | ".join(f"{m['documento_id']}·{m['seccion']}" for m in marco[:rag.TOP_K]))
            print("   Lo que vio el completo (8): " + " | ".join(f"{m['documento_id']}·{m['seccion']}" for m in marco))
            print("   Lite, 4 fragmentos:     " + _crudo(p["pregunta"], marco[:rag.TOP_K], False))
            time.sleep(PAUSA)
            print("   Completo, 8 fragmentos: " + _crudo(p["pregunta"], marco, True))
            time.sleep(PAUSA)
            continue
        if not pasa:
            resultado, gen, citados = "abstiene", "recuperación", []
        else:
            r = rag.responder(p["pregunta"], marco, None, estricto)
            resultado = "abstiene" if r["abstencion"] else "responde"
            gen = r["generador"]
            citados = sorted({marco[n - 1]["documento_id"] for n in r["citas_usadas"]})
            time.sleep(PAUSA)
        if p["esperado"] is None:
            n_n += 1
            bien = resultado == "abstiene"
            ok_n += bien
        else:
            n_p += 1
            bien = resultado == "responde" and p["esperado"] in citados
            ok_p += bien
        filas.append((p["id"], p["esperado"] or "-", resultado, gen, ", ".join(citados) or "-", "sí" if bien else "NO"))
        print(f"{p['id']}: {resultado} ({gen}) {', '.join(citados)} -> {'ok' if bien else 'MAL'}", flush=True)

    if ids:
        return
    lineas = ["# Abstención con modelo de lenguaje\n",
              f"Compuerta abierta (denso ≥ {rag.UMBRAL_DENSO_LLM} o BM25 ≥ {rag.UMBRAL_BM25_LLM}); decide el modelo.\n",
              f"- Preguntas sin respuesta que terminan en abstención: **{ok_n} de {n_n}**.",
              f"- Preguntas parafraseadas respondidas citando la guía esperada: **{ok_p} de {n_p}**.\n",
              f"- Llamadas al modelo que fallaron y pasaron al otro modelo (tiempo agotado, 503): {fallos.n}.\n",
              "| Pregunta | Esperado | Resultado | Quién decidió | Citó | ¿Bien? |", "| --- | --- | --- | --- | --- | --- |"]
    lineas += [f"| {' | '.join(f)} |" for f in filas]
    salida = "\n".join(lineas) + "\n"
    (RAIZ / "docs/rag/eval/RESULTADOS_ABSTENCION.md").write_text(salida, encoding="utf-8")
    print("\n" + salida)


if __name__ == "__main__":
    main()
