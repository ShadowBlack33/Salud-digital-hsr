#!/usr/bin/env python3
"""
Evaluación de la recuperación del RAG (Semana 12, punto 3).

Usa el mismo corpus y el mismo código de recuperación que la API
(app/services/rag_core.py): guías de docs/rag/guias y las historias de
evaluación de docs/rag/eval/historias (pacientes ficticios ya seudonimizados).

Mide Recall@1, Recall@3 y MRR a nivel de documento (en total y por tipo de pregunta) para BM25, denso e
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

    PESOS = [1.0, 0.75, 0.5, 0.35, 0.25, 0.15]   # peso del denso en la fusión (BM25 siempre 1)

    def hibrido(p, w):
        return [i for i, _ in rrf([rank_bm25(p["pregunta"]), rank_denso(p["id"])], pesos=[1.0, w])][:K]

    # Separación para elegir el peso sin ajustar sobre lo que se reporta: dentro de cada
    # grupo (literales / parafraseadas) las preguntas se reparten una a una entre
    # "ajuste" (elige el peso) y "prueba" (se reporta). Es determinista.
    ajuste, prueba = [], []
    for grupo in ("literal", "parafraseada"):
        del_grupo = [p for p in con_respuesta if p.get("tipo", "literal") == grupo]
        ajuste += del_grupo[0::2]
        prueba += del_grupo[1::2]

    def medir(fn, preguntas):
        return metricas([(documentos_en_orden(fn(p), frags), p["esperado"]) for p in preguntas])

    metodos = {"BM25": lambda p: rank_bm25(p["pregunta"])}
    peso_elegido = 1.0
    if vec_frags:
        metodos["Denso"] = lambda p: rank_denso(p["id"])
        metodos["Híbrido (RRF, pesos iguales)"] = lambda p: hibrido(p, 1.0)
        # El peso se elige con el MRR de las preguntas de ajuste; a igualdad, el mayor peso.
        peso_elegido = max(PESOS, key=lambda w: (round(medir(lambda p: hibrido(p, w), ajuste)["mrr"], 4), w))
        if peso_elegido != 1.0:
            metodos[f"Híbrido (RRF, peso del denso {peso_elegido})"] = lambda p: hibrido(p, peso_elegido)

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
        "## Todas las preguntas\n",
        "| Método | Recall@1 | Recall@3 | MRR |", "| --- | --- | --- | --- |",
    ]
    lineas += [f"| {n} | {m['recall@1']:.2f} | {m['recall@3']:.2f} | {m['mrr']:.2f} |" for n, m in filas]
    if not vec_frags:
        lineas.append("\n_Sin modelo denso disponible: solo se midió BM25. Instalar con `pip install fastembed` (con internet para descargar el modelo) y repetir._")

    # Por tipo de pregunta: literales (usan las palabras de la guía) y parafraseadas (palabras propias).
    for grupo, titulo in (("literal", "Preguntas literales (con las palabras de la guía)"),
                          ("parafraseada", "Preguntas parafraseadas (sin las palabras de la guía)")):
        sub = [p for p in con_respuesta if p.get("tipo", "literal") == grupo]
        lineas += [f"\n## {titulo}: {len(sub)}\n", "| Método | Recall@1 | Recall@3 | MRR |", "| --- | --- | --- | --- |"]
        for n, fn in metodos.items():
            m = medir(fn, sub)
            lineas.append(f"| {n} | {m['recall@1']:.2f} | {m['recall@3']:.2f} | {m['mrr']:.2f} |")

    if vec_frags:
        lineas += [f"\n## Elección del peso del denso en la fusión\n",
                   f"Las preguntas se reparten (una a una, dentro de cada tipo) en {len(ajuste)} de ajuste y {len(prueba)} de prueba. "
                   "El peso se elige con el MRR de las de **ajuste**; el resultado que se reporta es el de las de **prueba**, que no intervinieron en la elección.\n",
                   "| Peso del denso | MRR (ajuste) | MRR (prueba) | Recall@1 (prueba) |", "| --- | --- | --- | --- |"]
        for w in PESOS:
            a_, t_ = medir(lambda p: hibrido(p, w), ajuste), medir(lambda p: hibrido(p, w), prueba)
            lineas.append(f"| {w}{' ←' if w == peso_elegido else ''} | {a_['mrr']:.2f} | {t_['mrr']:.2f} | {t_['recall@1']:.2f} |")
        b_, d_ = medir(metodos["BM25"], prueba), medir(metodos["Denso"], prueba)
        lineas.append(f"\nEn las de prueba: BM25 R@1 {b_['recall@1']:.2f} / MRR {b_['mrr']:.2f}; denso R@1 {d_['recall@1']:.2f} / MRR {d_['mrr']:.2f}.")
        lineas.append(f"\nPeso elegido: **{peso_elegido}** (`RAG_PESO_DENSO` en `.env`; por defecto 1,0).")

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

        # El híbrido se abstiene si CUALQUIERA de las dos señales queda bajo su umbral.
        u_d = float(os.getenv("RAG_UMBRAL_DENSO", "0.45"))
        u_b = float(os.getenv("RAG_UMBRAL_BM25", "5.0"))
        pasa = lambda p: max_sim(p["id"]) >= u_d and top_bm25(p["pregunta"]) >= u_b
        malas_con = [p["id"] for p in con_respuesta if not pasa(p)]
        malas_sin = [p["id"] for p in sin_respuesta if pasa(p)]
        lineas.append(f"\n## Abstención del híbrido (denso ≥ {u_d} y BM25 ≥ {u_b})\n")
        lineas.append(f"- Preguntas con respuesta que se abstendrían por error: {', '.join(malas_con) or 'ninguna'}.")
        lineas.append(f"- Preguntas sin respuesta que se responderían por error: {', '.join(malas_sin) or 'ninguna'}.")

        # Señales de cada pregunta que la regla actual clasifica mal, y búsqueda de una regla mejor.
        senal = {p["id"]: (max_sim(p["id"]), top_bm25(p["pregunta"])) for p in preguntas}
        if malas_con or malas_sin:
            lineas += ["\n### Preguntas mal clasificadas (coseno máximo, BM25 máximo)\n", "| Pregunta | Debería | Coseno | BM25 |", "| --- | --- | --- | --- |"]
            for p in preguntas:
                if p["id"] in malas_con + malas_sin:
                    lineas.append(f"| {p['id']} | {'responder' if p['esperado'] else 'abstenerse'} | {senal[p['id']][0]:.2f} | {senal[p['id']][1]:.1f} |")
        sin_ids = [p["id"] for p in sin_respuesta]
        lineas.append(f"\nPreguntas sin respuesta ({len(sin_ids)}), mayor coseno / mayor BM25: "
                      + "; ".join(f"{i} {senal[i][0]:.2f}/{senal[i][1]:.1f}" for i in sorted(sin_ids, key=lambda i: -senal[i][0])[:5]) + ".")
        reglas = []
        for ud in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60):
            for ub in (0.0, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0):
                for op, f in (("y", lambda c, b, ud=ud, ub=ub: c >= ud and b >= ub), ("o", lambda c, b, ud=ud, ub=ub: c >= ud or b >= ub)):
                    e1 = sum(1 for p in con_respuesta if not f(*senal[p["id"]]))
                    e2 = sum(1 for p in sin_respuesta if f(*senal[p["id"]]))
                    reglas.append((e1 + e2, e1, e2, ud, ub, op))
        reglas.sort(key=lambda r: (r[0], r[2], -r[3], -r[4]))
        lineas += ["\n### Mejores reglas de abstención probadas (denso ≥ u_d `y`/`o` BM25 ≥ u_b)\n",
                   "| Errores | Se abstiene sin deber | Responde sin deber | u_d | u_b | Operador |", "| --- | --- | --- | --- | --- | --- |"]
        lineas += [f"| {t} | {a_} | {b_} | {ud} | {ub} | {op} |" for t, a_, b_, ud, ub, op in reglas[:6]]
        lineas.append(f"\nCon {len(sin_respuesta)} preguntas sin respuesta y {len(con_respuesta)} con respuesta, elegir un umbral sobre estos mismos datos lo ajusta a ellos: se reporta como calibración, no como garantía.")

    salida = "\n".join(lineas) + "\n"
    print(salida)
    (RAIZ / "docs/rag/eval/RESULTADOS.md").write_text(salida, encoding="utf-8")


if __name__ == "__main__":
    os.environ.setdefault("ML_URL", "http://localhost:8001")
    main()
