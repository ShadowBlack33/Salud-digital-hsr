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
(RecuperadorMemoria, sin base de datos ni filtros por perfil): preguntas por sección según
RAG_PREGUNTAS, reranker según RAG_RERANKER y la temperatura de RAG_TEMPERATURA.
Necesita GEMINI_API_KEY en el .env y red.
Hace una llamada por pregunta (con pausa, por el límite de la capa gratuita).

Uso:  python scripts/probar_abstencion.py            (escribe docs/rag/eval/RESULTADOS_ABSTENCION.md)

Diagnóstico de unas preguntas (no escribe el archivo): qué fragmentos recibió el modelo, qué
contestó y cómo cambia con el modelo completo y los 8 fragmentos:
      python scripts/probar_abstencion.py --ids P04,P05,P11,P12

Si en una corrida se acabó la cuota gratuita (429) o hubo tiempos agotados, algunas preguntas
quedan respondidas sin modelo ("extractivo" o "ninguno") y no miden lo que se busca. Para
repetir solo esas, cuando la cuota se recupere, conservando las demás:
      python scripts/probar_abstencion.py --repetir
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
from app.services.rag_core import RecuperadorMemoria, embeber, fragmentar, leer_documento  # noqa: E402

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
        return f"(falló: {type(e).__name__} {getattr(getattr(e, 'response', None), 'status_code', '')})"


def main() -> None:
    if rag._proveedor(True) is None:
        sys.exit("No hay GEMINI_API_KEY ni XAI_API_KEY en el .env: esta prueba necesita el modelo.")
    cfg = get_settings()
    docs = [leer_documento(p) for p in sorted((RAIZ / "docs/rag/guias").glob("*.md"))]
    frags = [f for d in docs for f in fragmentar(d)]
    rec = RecuperadorMemoria(frags, usar_preguntas=cfg.rag_preguntas)
    if not rec.hay_denso:
        sys.exit("No hay modelo de embeddings (pip install -r scripts/requirements-datos.txt).")
    print(f"Preguntas por sección: {sum(len(f.preguntas) for f in frags) if cfg.rag_preguntas else 'desactivadas'}; "
          f"reranker: {'sí' if cfg.rag_reranker else 'no'}; temperatura: {rag.temperatura() or 'la del proveedor'}")
    preguntas = [p for p in json.loads((RAIZ / "docs/rag/eval/preguntas.json").read_text(encoding="utf-8"))
                 if p["id"].startswith(("N", "P"))]

    ids = None
    if "--ids" in sys.argv:
        ids = set(sys.argv[sys.argv.index("--ids") + 1].split(","))
        preguntas = [p for p in preguntas if p["id"] in ids]
    salida_md = RAIZ / "docs/rag/eval/RESULTADOS_ABSTENCION.md"
    previas: dict[str, tuple] = {}
    if "--repetir" in sys.argv:
        if not salida_md.exists():
            sys.exit("No hay resultados anteriores que repetir: correr primero sin --repetir.")
        for linea in salida_md.read_text(encoding="utf-8").splitlines():
            celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
            if len(celdas) == 6 and celdas[0][:1] in ("P", "N") and celdas[0][1:].isdigit():
                previas[celdas[0]] = tuple(celdas)
        repetir = {i for i, f in previas.items() if f[3] in ("extractivo", "ninguno")}
        print(f"Se repiten {len(repetir)} preguntas que quedaron sin modelo: {', '.join(sorted(repetir)) or 'ninguna'}")
        preguntas = [p for p in preguntas if p["id"] in repetir or p["id"] not in previas]
    # El logger del RAG es "hsr.rag": se cuentan los fallos del modelo sin imprimir el rastro.
    fallos = _Fallos()
    logging.getLogger("hsr.rag").addHandler(fallos)
    logging.getLogger("hsr.rag").propagate = False
    filas = []
    for p in preguntas:
        qv = embeber([p["pregunta"]])[0]
        denso = rec.denso(qv, rag.CANDIDATOS_DENSOS)
        lex = rec.lexico(p["pregunta"], rag.CANDIDATOS_DENSOS)
        orden = rec.hibrido(p["pregunta"], qv, rag.CANDIDATOS_DENSOS, cfg.rag_peso_denso, rag.CANDIDATOS_DENSOS)
        pasa, estricto = rag.evaluar_umbral(denso[0][1], lex[0][1] if lex else 0.0, "hibrido")
        if pasa and cfg.rag_reranker:
            orden = rec.con_reranker(p["pregunta"], orden, cfg.rag_reranker_candidatos)
        marco = [{"documento_id": frags[i].documento_id, "titulo": frags[i].titulo, "seccion": frags[i].seccion,
                  "texto": frags[i].texto} for i in orden[:rag.TOP_K_EXTENSA]]
        if ids:
            print(f"\n== {p['id']} (esperado {p['esperado']}): {p['pregunta']}")
            print("   Fragmentos recuperados: " + " | ".join(f"{m['documento_id']}·{m['seccion']}" for m in marco))
            print("   Lite:     " + _crudo(p["pregunta"], marco, False))
            time.sleep(PAUSA)
            print("   Completo: " + _crudo(p["pregunta"], marco, True))
            time.sleep(PAUSA)
            continue
        if not pasa:
            resultado, gen, citados = "abstiene", "recuperación", []
        else:
            r = rag.responder(p["pregunta"], marco, None, estricto, conversacional=False)   # sin gastar cuota
            resultado = "abstiene" if r["abstencion"] else "responde"
            gen = r["generador"]
            citados = sorted({marco[n - 1]["documento_id"] for n in r["citas_usadas"]})
            time.sleep(PAUSA)
        if p["esperado"] is None:
            bien = resultado == "abstiene"
        else:
            bien = resultado == "responde" and p["esperado"] in citados
        filas.append((p["id"], p["esperado"] or "-", resultado, gen, ", ".join(citados) or "-", "sí" if bien else "NO"))
        print(f"{p['id']}: {resultado} ({gen}) {', '.join(citados)} -> {'ok' if bien else 'MAL'}", flush=True)

    if ids:
        return
    if previas:                       # se conservan las que no se repitieron, en el orden original
        nuevas = {f[0]: f for f in filas}
        filas = [nuevas.get(i, previas[i]) for i in previas] + [f for f in filas if f[0] not in previas]
    n_n = sum(f[0].startswith("N") for f in filas)
    ok_n = sum(f[0].startswith("N") and f[5] == "sí" for f in filas)
    n_p = sum(f[0].startswith("P") for f in filas)
    ok_p = sum(f[0].startswith("P") and f[5] == "sí" for f in filas)
    con_modelo = [f for f in filas if f[0].startswith("P") and f[3] not in ("extractivo", "ninguno", "recuperación")]
    sin_modelo = [f[0] for f in filas if f[3] in ("extractivo", "ninguno")]
    lineas = ["# Abstención con modelo de lenguaje\n",
              f"Compuerta abierta (denso ≥ {rag.UMBRAL_DENSO_LLM} o BM25 ≥ {rag.UMBRAL_BM25_LLM}); decide el modelo. "
              f"Preguntas por sección: {'sí' if cfg.rag_preguntas else 'no'}; reranker: {'sí' if cfg.rag_reranker else 'no'}; "
              f"temperatura: {rag.temperatura() if rag.temperatura() is not None else 'la del proveedor'}.\n",
              f"- Preguntas sin respuesta que terminan en abstención: **{ok_n} de {n_n}**.",
              f"- Preguntas parafraseadas respondidas citando la guía esperada: **{ok_p} de {n_p}**.\n",
              f"- Parafraseadas que decidió el modelo: {sum(f[5] == 'sí' for f in con_modelo)} de {len(con_modelo)} bien.",
              f"- Preguntas que quedaron sin modelo (cuota agotada o tiempo agotado): "
              f"{len(sin_modelo)}{' (' + ', '.join(sin_modelo) + '; repetir con --repetir)' if sin_modelo else ''}.",
              f"- Llamadas al modelo que fallaron en esta corrida (429, 503, tiempo agotado): {fallos.n}.\n",
              "| Pregunta | Esperado | Resultado | Quién decidió | Citó | ¿Bien? |", "| --- | --- | --- | --- | --- | --- |"]
    lineas += [f"| {' | '.join(f)} |" for f in filas]
    salida = "\n".join(lineas) + "\n"
    salida_md.write_text(salida, encoding="utf-8")
    print("\n" + salida)


if __name__ == "__main__":
    main()
