#!/usr/bin/env python3
"""
Evaluación de la recuperación del RAG.

Usa el mismo corpus y la misma recuperación que la API, en memoria
(RecuperadorMemoria en app/services/rag_core.py): guías de docs/rag/guias,
con las preguntas por sección si ya las tienen, y las historias de evaluación
de docs/rag/eval/historias (pacientes ficticios ya seudonimizados).

Mide Recall@1, Recall@3 y MRR a nivel de documento, en total y por tipo de
pregunta (literal / parafraseada), para:
  · BM25, denso e híbrido (RRF) solo con el texto de los fragmentos;
  · los mismos con las preguntas por sección (paso 2 de docs/RAG.md);
  · el híbrido con preguntas más el reranker (con --reranker; bge-reranker-v2-m3 int8, descarga ~570 MB).

El peso del denso en la fusión se elige con las preguntas de AJUSTE y se
reporta en las de PRUEBA. Las preguntas sin documento esperado sirven para
calibrar la abstención. Además se revisa que ninguna pregunta de la evaluación
esté copiada entre las preguntas indexadas (eso inflaría los resultados).

Uso:  python scripts/evaluar_rag.py [--reranker]   (escribe docs/rag/eval/RESULTADOS.md)
Necesita:  pip install -r scripts/requirements-datos.txt   (fastembed con la versión del servicio ml)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.services.rag_core import (  # noqa: E402
    MODELO_RERANKER, RecuperadorMemoria, documentos_en_orden, embeber, fragmentar, leer_documento, metricas,
    similitud_lexica)

K = 10                 # fragmentos que se miran para ordenar documentos
CANDIDATOS = 20        # candidatos de cada método antes de fusionar (igual que la API)
PESOS = [1.0, 0.75, 0.5, 0.35, 0.25, 0.15]   # peso del denso en la fusión (BM25 siempre 1)
UMBRAL_COPIA = 0.6     # similitud léxica a partir de la cual una pregunta indexada "copia" una de evaluación


def main() -> None:
    con_reranker = "--reranker" in sys.argv
    docs = [leer_documento(p) for p in sorted((RAIZ / "docs/rag/guias").glob("*.md"))]
    docs += [leer_documento(p) for p in sorted((RAIZ / "docs/rag/eval/historias").glob("*.md"))]
    frags = [f for d in docs for f in fragmentar(d)]
    n_preg = len({p for f in frags for p in f.preguntas})
    preguntas = json.loads((RAIZ / "docs/rag/eval/preguntas.json").read_text(encoding="utf-8"))
    con_respuesta = [p for p in preguntas if p["esperado"]]
    sin_respuesta = [p for p in preguntas if not p["esperado"]]

    con = RecuperadorMemoria(frags, usar_preguntas=True)
    sin = RecuperadorMemoria(frags, usar_preguntas=False, base=con)
    hay_denso = con.hay_denso
    qv = dict(zip([p["id"] for p in preguntas], embeber([p["pregunta"] for p in preguntas]) or [])) \
        if hay_denso else {}

    def bm25(rec):
        return lambda p: [i for i, _ in rec.lexico(p["pregunta"], K)]

    def denso(rec):
        return lambda p: [i for i, _ in rec.denso(qv[p["id"]], K)]

    def hibrido(rec, w=1.0):
        return lambda p: rec.hibrido(p["pregunta"], qv[p["id"]], K, w, CANDIDATOS)

    # Separación para elegir el peso sin ajustar sobre lo que se reporta: dentro de cada grupo
    # (literales / parafraseadas) las preguntas se reparten una a una entre "ajuste" y "prueba".
    ajuste, prueba = [], []
    for grupo in ("literal", "parafraseada"):
        del_grupo = [p for p in con_respuesta if p.get("tipo", "literal") == grupo]
        ajuste += del_grupo[0::2]
        prueba += del_grupo[1::2]

    def medir(fn, lista):
        return metricas([(documentos_en_orden(fn(p), frags), p["esperado"]) for p in lista])

    metodos = {"BM25": bm25(sin)}
    peso = 1.0
    if hay_denso:
        metodos["Denso"] = denso(sin)
        metodos["Híbrido (RRF)"] = hibrido(sin)
        if n_preg:
            metodos["BM25 + preguntas"] = bm25(con)
            metodos["Denso + preguntas"] = denso(con)
            metodos["Híbrido + preguntas"] = hibrido(con)
        final = con if n_preg else sin
        peso = max(PESOS, key=lambda w: (round(medir(hibrido(final, w), ajuste)["mrr"], 4), w))
        if peso != 1.0:
            metodos[f"Híbrido{' + preguntas' if n_preg else ''} (peso del denso {peso})"] = hibrido(final, peso)
        if con_reranker:
            base = hibrido(final, peso)
            cache_rr: dict[str, list[int]] = {}      # el reranker es lento en CPU: una vez por pregunta

            def reranker(p, final=final, peso=peso, base=base):
                if p["id"] not in cache_rr:
                    orden = final.hibrido(p["pregunta"], qv[p["id"]], CANDIDATOS, peso, CANDIDATOS)
                    cache_rr[p["id"]] = final.con_reranker(p["pregunta"], orden)[:K] or base(p)
                    if len(cache_rr) % 20 == 0:
                        print(f"  reranker: {len(cache_rr)} de {len(con_respuesta)} preguntas", flush=True)
                return cache_rr[p["id"]]
            metodos[f"Híbrido{' + preguntas' if n_preg else ''} + reranker"] = reranker

    lineas = [
        "# Resultados de la evaluación del RAG\n",
        f"Corpus: {len(docs)} documentos ({sum(d.tipo == 'guia' for d in docs)} guías, "
        f"{sum(d.tipo == 'historia' for d in docs)} historias de evaluación), {len(frags)} fragmentos, "
        f"{n_preg} preguntas por sección indexadas. Preguntas con documento esperado: {len(con_respuesta)} "
        f"({sum(p.get('tipo') == 'parafraseada' for p in con_respuesta)} parafraseadas); sin respuesta: "
        f"{len(sin_respuesta)}. Embeddings: `{con.firma or 'no disponibles'}`."
        + (f" Reranker: `{MODELO_RERANKER}`." if con_reranker else "") + "\n",
    ]
    if not hay_denso:
        lineas.append("_Sin modelo denso disponible: solo se midió BM25. Instalar con "
                      "`pip install -r scripts/requirements-datos.txt` (con internet para descargar el modelo) y repetir._\n")
    if hay_denso and not n_preg:
        lineas.append("_Las guías todavía no tienen preguntas por sección: generarlas con "
                      "`python scripts/generar_preguntas.py`, revisarlas y repetir._\n")

    for titulo, sub in (("Todas las preguntas", con_respuesta),
                        ("Preguntas literales (con las palabras de la guía)",
                         [p for p in con_respuesta if p.get("tipo", "literal") == "literal"]),
                        ("Preguntas parafraseadas (sin las palabras de la guía)",
                         [p for p in con_respuesta if p.get("tipo") == "parafraseada"]),
                        ("Solo las de PRUEBA (no intervinieron en ninguna elección)", prueba)):
        lineas += [f"\n## {titulo}: {len(sub)}\n", "| Método | Recall@1 | Recall@3 | MRR |", "| --- | --- | --- | --- |"]
        for n, fn in metodos.items():
            m = medir(fn, sub)
            lineas.append(f"| {n} | {m['recall@1']:.2f} | {m['recall@3']:.2f} | {m['mrr']:.2f} |")

    if hay_denso:
        final = con if n_preg else sin
        lineas += ["\n## Elección del peso del denso en la fusión\n",
                   f"Ajuste: {len(ajuste)} preguntas; prueba: {len(prueba)}. El peso se elige con el MRR de ajuste "
                   "(a igualdad, el mayor); el de prueba no interviene.\n",
                   "| Peso del denso | MRR (ajuste) | MRR (prueba) | Recall@1 (prueba) |", "| --- | --- | --- | --- |"]
        for w in PESOS:
            a_, t_ = medir(hibrido(final, w), ajuste), medir(hibrido(final, w), prueba)
            lineas.append(f"| {w}{' ←' if w == peso else ''} | {a_['mrr']:.2f} | {t_['mrr']:.2f} | {t_['recall@1']:.2f} |")
        lineas.append(f"\nPeso elegido: **{peso}** (`RAG_PESO_DENSO` en `.env`).")

    lineas.append("\n## Preguntas donde el primer documento no fue el esperado\n")
    for nombre, fn in metodos.items():
        fallos = [(p["id"], documentos_en_orden(fn(p), frags)[:3], p["esperado"]) for p in con_respuesta]
        fallos = [x for x in fallos if x[1][:1] != [x[2]]]
        lineas.append(f"**{nombre}** ({len(fallos)}): " + ("ninguna." if not fallos else
                      "; ".join(f"{q} (esperado {e}, obtuvo {', '.join(d) or '-'})" for q, d, e in fallos)))

    # ---------------------------------------------------------------- calibración de la abstención
    final = con if n_preg else sin
    top_bm25 = {p["id"]: (final.lexico(p["pregunta"], 1) or [(0, 0.0)])[0][1] for p in preguntas}
    con_b = sorted(top_bm25[p["id"]] for p in con_respuesta)
    sin_b = sorted(top_bm25[p["id"]] for p in sin_respuesta)
    lineas += ["\n## Calibración de la abstención con BM25 (puntaje máximo)\n",
               f"- Preguntas con respuesta: mínimo {con_b[0]:.1f}, mediana {con_b[len(con_b)//2]:.1f}.",
               f"- Preguntas sin respuesta en el corpus: máximo {sin_b[-1]:.1f}."]

    if hay_denso:
        max_sim = {p["id"]: max(final.similitudes(qv[p["id"]])) for p in preguntas}
        con_d = sorted(max_sim[p["id"]] for p in con_respuesta)
        sin_d = sorted(max_sim[p["id"]] for p in sin_respuesta)
        lineas += ["\n## Calibración de la abstención (similitud coseno máxima" + (", con preguntas" if n_preg else "") + ")\n",
                   f"- Preguntas con respuesta: mínimo {con_d[0]:.2f}, mediana {con_d[len(con_d)//2]:.2f}.",
                   f"- Preguntas sin respuesta en el corpus: máximo {sin_d[-1]:.2f}."]
        if n_preg:
            lineas.append("- Ojo: con preguntas indexadas el coseno compara pregunta con pregunta y sube en general; "
                          "los umbrales calibrados sin ellas no sirven, hay que volver a elegirlos con esta tabla.")
        senal = {i: (max_sim[i], top_bm25[i]) for i in max_sim}
        reglas = []
        for ud in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80):
            for ub in (0.0, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0):
                for op, f in (("y", lambda c, b, ud=ud, ub=ub: c >= ud and b >= ub),
                              ("o", lambda c, b, ud=ud, ub=ub: c >= ud or b >= ub)):
                    e1 = sum(1 for p in con_respuesta if not f(*senal[p["id"]]))
                    e2 = sum(1 for p in sin_respuesta if f(*senal[p["id"]]))
                    reglas.append((e1 + e2, e1, e2, ud, ub, op))
        reglas.sort(key=lambda r: (r[0], r[2], -r[3], -r[4]))
        lineas += ["\n### Reglas de abstención SIN modelo de lenguaje (denso ≥ u_d `y`/`o` BM25 ≥ u_b)\n",
                   "| Errores | Se abstiene sin deber | Responde sin deber | u_d | u_b | Operador |",
                   "| --- | --- | --- | --- | --- | --- |"]
        lineas += [f"| {t} | {a_} | {b_} | {ud} | {ub} | {op} |" for t, a_, b_, ud, ub, op in reglas[:6]]
        # Compuerta abierta (con modelo): solo descarta lo claramente ajeno. Que no deje fuera
        # ninguna pregunta con respuesta, y descartar todas las sin respuesta que se pueda.
        abiertas = sorted((r for r in reglas if r[1] == 0 and r[5] == "o"), key=lambda r: (r[2], -r[3], -r[4]))
        if abiertas:
            _, _, e2, ud, ub, _ = abiertas[0]
            lineas.append(f"\nCompuerta abierta (con modelo) que no deja fuera ninguna pregunta con respuesta: "
                          f"denso ≥ {ud} o BM25 ≥ {ub}; deja pasar {e2} de {len(sin_respuesta)} sin respuesta, "
                          "que debe rechazar el modelo (`RAG_UMBRAL_DENSO_LLM`, `RAG_UMBRAL_BM25_LLM`; "
                          "comprobar con scripts/probar_abstencion.py).")
        lineas.append(f"\nCon {len(sin_respuesta)} preguntas sin respuesta y {len(con_respuesta)} con respuesta, elegir "
                      "un umbral sobre estos mismos datos lo ajusta a ellos: se reporta como calibración, no como garantía.")

    # ---------------------------------------------------------------- fuga entre evaluación e índice
    indexadas = sorted({q for f in frags for q in f.preguntas})
    if indexadas:
        copias = []
        for p in preguntas:
            s, q = max((similitud_lexica(p["pregunta"], q), q) for q in indexadas)
            if s >= UMBRAL_COPIA:
                copias.append((p["id"], s, q))
        lineas += ["\n## Preguntas de evaluación parecidas a las indexadas\n",
                   f"Similitud léxica (Jaccard de términos) ≥ {UMBRAL_COPIA} entre una pregunta de evaluación y una "
                   "pregunta indexada. Si hay muchas, la mejora con preguntas está inflada: la evaluación mediría "
                   "memoria y no generalización.\n",
                   f"- {len(copias)} de {len(preguntas)}." + ("" if not copias else " " + "; ".join(
                       f"{i} ({s:.2f}: «{q}»)" for i, s, q in copias))]

    salida = "\n".join(lineas) + "\n"
    print(salida)
    (RAIZ / "docs/rag/eval/RESULTADOS.md").write_text(salida, encoding="utf-8")


if __name__ == "__main__":
    os.environ.setdefault("ML_URL", "http://localhost:8001")
    main()
