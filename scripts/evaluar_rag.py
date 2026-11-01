#!/usr/bin/env python3
"""
Evaluación de la recuperación del RAG (Semana 12, punto 3).

Usa el mismo corpus y el mismo código de recuperación que la API
(app/services/rag_core.py): guías de docs/rag/guias y las historias de
evaluación de docs/rag/eval/historias (pacientes ficticios ya seudonimizados).

Mide Recall@1, Recall@3 y MRR a nivel de documento para BM25, denso e
híbrido (RRF), sobre las preguntas de docs/rag/eval/preguntas.json que
tienen documento esperado. Las preguntas sin documento esperado sirven para
calibrar la abstención: se reporta la similitud máxima que alcanzan.

Uso:  python scripts/evaluar_rag.py            (imprime y escribe docs/rag/eval/RESULTADOS.md)
Necesita:  pip install fastembed   (para el método denso; sin él solo mide BM25)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.services.rag_core import (  # noqa: E402
    BM25, MODELO_EMBEDDING, coseno, documentos_en_orden, embeber, fragmentar, leer_documento, metricas, rrf)

K = 10


def main() -> None:
    docs = [leer_documento(p) for p in sorted((RAIZ / "docs/rag/guias").glob("*.md"))]
    docs += [leer_documento(p) for p in sorted((RAIZ / "docs/rag/eval/historias").glob("*.md"))]
    frags = [f for d in docs for f in fragmentar(d)]
    preguntas = json.loads((RAIZ / "docs/rag/eval/preguntas.json").read_text(encoding="utf-8"))
    con_respuesta = [p for p in preguntas if p["esperado"]]
    sin_respuesta = [p for p in preguntas if not p["esperado"]]

    bm25 = BM25([f.texto for f in frags])
    vec_frags = embeber([f.texto for f in frags])
    vec_preg = embeber([p["pregunta"] for p in preguntas]) if vec_frags else None
    vec_por_id = {p["id"]: v for p, v in zip(preguntas, vec_preg)} if vec_preg else {}

    def rank_bm25(q: str) -> list[int]:
        return [i for i, _ in bm25.ranking(q, K)]

    def rank_denso(pid: str) -> list[int]:
        qv = vec_por_id[pid]
        sims = sorted(((i, coseno(qv, v)) for i, v in enumerate(vec_frags)), key=lambda x: -x[1])
        return [i for i, _ in sims[:K]]

    metodos = {"BM25": lambda p: rank_bm25(p["pregunta"])}
    if vec_frags:
        metodos["Denso"] = lambda p: rank_denso(p["id"])
        metodos["Híbrido (RRF)"] = lambda p: [i for i, _ in rrf([rank_bm25(p["pregunta"]), rank_denso(p["id"])])][:K]

    filas, fallos = [], {}
    for nombre, fn in metodos.items():
        res = [(documentos_en_orden(fn(p), frags), p["esperado"]) for p in con_respuesta]
        m = metricas(res)
        filas.append((nombre, m))
        fallos[nombre] = [(p["id"], docs[:3], p["esperado"]) for p, (docs, _) in zip(con_respuesta, res)
                          if docs[:1] != [p["esperado"]]]

    lineas = [
        f"# Resultados de la evaluación del RAG\n",
        f"Corpus: {len(docs)} documentos ({sum(d.tipo == 'guia' for d in docs)} guías, "
        f"{sum(d.tipo == 'historia' for d in docs)} historias de evaluación), {len(frags)} fragmentos. "
        f"Preguntas con documento esperado: {len(con_respuesta)}. Modelo denso: `{MODELO_EMBEDDING}`.\n",
        "| Método | Recall@1 | Recall@3 | MRR |", "| --- | --- | --- | --- |",
    ]
    lineas += [f"| {n} | {m['recall@1']:.2f} | {m['recall@3']:.2f} | {m['mrr']:.2f} |" for n, m in filas]
    if not vec_frags:
        lineas.append("\n_Sin modelo denso disponible: solo se midió BM25. Instalar con `pip install fastembed` (con internet para descargar el modelo) y repetir._")

    lineas.append("\n## Preguntas donde el primer documento no fue el esperado\n")
    for nombre, lista in fallos.items():
        lineas.append(f"**{nombre}:** " + ("ninguna." if not lista else
                      "; ".join(f"{q} (esperado {e}, obtuvo {', '.join(d)})" for q, d, e in lista)))

    top_bm25 = lambda q: (bm25.ranking(q, 1) or [(0, 0.0)])[0][1]
    con_b = sorted(top_bm25(p["pregunta"]) for p in con_respuesta)
    sin_b = sorted(top_bm25(p["pregunta"]) for p in sin_respuesta)
    lineas.append("\n## Calibración de la abstención con BM25 (puntaje máximo)\n")
    lineas.append(f"- Preguntas con respuesta: mínimo {con_b[0]:.1f}, mediana {con_b[len(con_b)//2]:.1f}.")
    lineas.append(f"- Preguntas sin respuesta en el corpus: máximo {sin_b[-1]:.1f}.")
    lineas.append("- El umbral `RAG_UMBRAL_BM25` debe quedar entre esos dos valores.")

    if vec_frags:
        lineas.append("\n## Calibración de la abstención (similitud coseno máxima)\n")
        def max_sim(pid):
            return max(coseno(vec_por_id[pid], v) for v in vec_frags)
        con = sorted(max_sim(p["id"]) for p in con_respuesta)
        sin = sorted(max_sim(p["id"]) for p in sin_respuesta)
        lineas.append(f"- Preguntas con respuesta: mínimo {con[0]:.2f}, mediana {con[len(con)//2]:.2f}.")
        lineas.append(f"- Preguntas sin respuesta en el corpus: máximo {sin[-1]:.2f}.")
        lineas.append("- El umbral `RAG_UMBRAL_DENSO` debe quedar entre esos dos valores.")

    salida = "\n".join(lineas) + "\n"
    print(salida)
    (RAIZ / "docs/rag/eval/RESULTADOS.md").write_text(salida, encoding="utf-8")


if __name__ == "__main__":
    os.environ.setdefault("ML_URL", "http://localhost:8001")
    main()
