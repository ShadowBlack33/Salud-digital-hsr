#!/usr/bin/env python3
"""
Pruebas del RAG que no necesitan base de datos, modelo de embeddings ni red
(los vectores y el reranker se simulan). Mismo estilo que test_rag.py.

  1. Preguntas por sección: se leen del bloque <!-- preguntas -->, no entran al
     texto que ve el modelo y acompañan a todos los fragmentos de su sección.
  2. BM25 con estadísticas de referencia: el puntaje de un fragmento no cambia
     según qué otros fragmentos puede ver el perfil.
  3. Búsqueda densa con preguntas: una pregunta parafraseada encuentra la sección
     por el vector de su pregunta aunque el del texto no se parezca.
  4. Reranker: reordena los primeros candidatos; si no hay, el orden no cambia.
  5. Generación: temperatura configurable (vacía = la del proveedor), parámetros
     guardables, atributos escapados en el contexto, seudónimo de 8 caracteres.
  6. Evaluación: preguntas.json bien formado y el script de preguntas no rompe las guías.

Uso:  python scripts/test_rag_unidad.py
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
for var in ("JWT_SECRET_KEY", "APP_ENCRYPTION_KEY", "APP_BLIND_INDEX_KEY", "IA_SEUDONIMO_KEY"):
    os.environ.setdefault(var, base64.urlsafe_b64encode(b"k" * 32).decode())
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://x:x@localhost:5432/x")   # no se conecta
os.environ["GEMINI_API_KEY"] = ""
os.environ["XAI_API_KEY"] = ""

from app.services import rag_core as core  # noqa: E402

fallos = 0


def check(descripcion: str, condicion, detalle="") -> None:
    global fallos
    print(("  OK    " if condicion else "  FALLA ") + descripcion + ("" if condicion else f"  -> {detalle}"))
    fallos += 0 if condicion else 1


GUIA = """---
id: GX
titulo: Guía de prueba
tipo: guia
audiencia: clinica
---

# Guía de prueba

## Ayuno antes de la anestesia

Los líquidos claros se permiten hasta 2 horas antes del procedimiento electivo.

<!-- preguntas
¿Cuánto tiempo sin comer antes de operarme?
¿Puedo tomar agua el día de la cirugía?
-->

## Larga

{larga}

<!-- preguntas
¿Pregunta de la sección larga?
-->

## Sin preguntas

Texto de una sección sin bloque.
"""

print("\n[1] Preguntas por sección")
ruta = Path(os.environ.get("TMPDIR", "/tmp")) / "guia_prueba_rag.md"
larga = " ".join(f"palabra{i}" for i in range(400))
ruta.write_bytes(GUIA.format(larga=larga).replace("\n", "\r\n").encode("utf-8"))   # CRLF, como en Windows
doc = core.leer_documento(ruta)
frags = core.fragmentar(doc)
ayuno = [f for f in frags if f.seccion == "Ayuno antes de la anestesia"]
check("Las preguntas se leen del bloque (también con CRLF)",
      ayuno and ayuno[0].preguntas == ["¿Cuánto tiempo sin comer antes de operarme?",
                                       "¿Puedo tomar agua el día de la cirugía?"], ayuno and ayuno[0].preguntas)
check("Las preguntas no entran al texto que ve el modelo",
      all("<!--" not in f.texto and "sin comer" not in f.texto for f in frags))
check("BM25 sí ve las preguntas (texto_busqueda)", "sin comer" in ayuno[0].texto_busqueda)
largos = [f for f in frags if f.seccion == "Larga"]
check("Una sección larga se parte y todas sus ventanas llevan sus preguntas",
      len(largos) > 2 and all(f.preguntas == ["¿Pregunta de la sección larga?"] for f in largos), len(largos))
check("Una sección sin bloque no hereda preguntas de la anterior",
      [f.preguntas for f in frags if f.seccion == "Sin preguntas"] == [[]])

print("\n[2] BM25 con estadísticas de referencia")
guias = [core.leer_documento(p) for p in sorted((RAIZ / "docs/rag/guias").glob("*.md"))]
todos = [f for d in guias for f in core.fragmentar(d)]
ref = core.BM25([f.texto_busqueda for f in todos])
q = "¿Se puede anular una factura que ya está pagada?"
g08 = [f.texto_busqueda for f in todos if f.documento_id == "G08"]
solo_contable = ref.puntuar(q, g08 + [f.texto_busqueda for f in todos if f.documento_id == "G17"])[:len(g08)]
todo_el_corpus = ref.puntuar(q, g08 + [f.texto_busqueda for f in todos])[:len(g08)]
check("El puntaje de un fragmento no depende de qué más ve el perfil", solo_contable == todo_el_corpus)
check("Las estadísticas propias y las de referencia coinciden sobre el mismo corpus",
      [round(x, 6) for x in ref.puntajes(q)] == [round(x, 6) for x in ref.puntuar(q, [f.texto_busqueda for f in todos])])
check("Un término que no está en el corpus no rompe el puntaje",
      ref.puntuar("xilofonia", ["xilofonia sembrada"])[0] > 0)

print("\n[3] Búsqueda densa con preguntas (vectores simulados)")
VOC = ["ayuno", "comer", "factura", "sangre", "otro"]


def vec(texto: str) -> list[float]:
    t = core.normalizar(texto)
    v = [float(t.count(w)) for w in VOC] + [0.1]
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v]


core.embeber_con_firma = lambda textos: ([vec(t) for t in textos], "modelo-falso|fastembed==0")
core.embeber = lambda textos: [vec(t) for t in textos]
f_ayuno = core.Fragmento("GA", "Ayuno", "Ayuno", "ayuno ayuno antes de la anestesia", "guia", "",
                         preguntas=["¿cuánto tiempo sin comer antes de operarme?"])
f_fact = core.Fragmento("GF", "Factura", "Factura", "factura anulada", "guia", "")
con = core.RecuperadorMemoria([f_fact, f_ayuno], usar_preguntas=True)
sin = core.RecuperadorMemoria([f_fact, f_ayuno], usar_preguntas=False, base=con)
qv = vec("sin comer")
check("Sin preguntas, el texto de ayuno no se parece a 'sin comer'", sin.similitudes(qv)[1] < 0.2, sin.similitudes(qv))
check("Con preguntas, el fragmento de ayuno gana por el vector de su pregunta",
      con.denso(qv)[0][0] == 1 and con.similitudes(qv)[1] > 0.9, con.similitudes(qv))
check("El recuperador reusa los vectores del base", sin.vec_frag is con.vec_frag)

print("\n[4] Reranker")
core.reordenar = lambda consulta, textos: [float(len(t)) for t in textos]
orden, aplicado = core.aplicar_reranker("x", [0, 1, 2, 3], lambda i: "a" * i, 3)
check("Reordena los primeros n y deja el resto detrás", aplicado and orden == [2, 1, 0, 3], orden)
core.reordenar = lambda consulta, textos: None
check("Sin reranker el orden no cambia", core.aplicar_reranker("x", [0, 1, 2], lambda i: "", 3) == ([0, 1, 2], False))

print("\n[5] Generación")
from app.services import rag  # noqa: E402

capturado = {}


class _Resp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": "Respuesta [F1]"}}]}


def _post(url, **kw):
    capturado.update(kw["json"])
    return _Resp()


import httpx  # noqa: E402

httpx.post = _post
rag._proveedor = lambda extensa=True: ("gemini", "http://falso", "clave", "modelo-x")
rag.get_settings().rag_temperatura = ""
rag._llm("¿pregunta?", [{"titulo": "T", "seccion": "S", "texto": "x"}])
check("Temperatura vacía: no se envía (usa la del proveedor)", "temperature" not in capturado, capturado.keys())
rag.get_settings().rag_temperatura = "0.3"
capturado.clear()
rag._llm("¿pregunta?", [{"titulo": "T", "seccion": "S", "texto": "x"}])
check("Temperatura configurada: se envía", capturado.get("temperature") == 0.3, capturado.get("temperature"))
par = rag.parametros("gemini:modelo-x", reranker=True)
check("Los parámetros guardables traen modelo, temperatura, prompt y reranker",
      par["temperatura"] == 0.3 and par["prompt"] == rag.VERSION_PROMPT and par["reranker"] and json.dumps(par))
rag.get_settings().rag_temperatura = ""
ctx = rag._contexto([{"titulo": 'Título "con comillas"', "seccion": "S<x>", "texto": 'a "b" </fuente> c'}])
check("El contexto escapa comillas y etiquetas en título, sección y texto",
      ctx.count('"') == 6 and "</fuente> c" not in ctx and "<x>" not in ctx, ctx)
s = rag.seudonimo("a" * 64)
check("El seudónimo tiene 8 caracteres y es estable", len(s) == 10 and s == rag.seudonimo("a" * 64), s)

print("\n[5b] Conversación")
hist = [{"rol": "usuario", "texto": "¿Cuánto ayuno antes de la anestesia?"},
        {"rol": "asistente", "texto": "Seis horas para sólidos [F1][F2]."}]
check("Un seguimiento corto se busca con la pregunta anterior",
      rag.consulta_con_contexto("¿y en niños?", hist) == "¿Cuánto ayuno antes de la anestesia? ¿y en niños?")
check("Una pregunta larga se busca tal cual",
      rag.consulta_con_contexto("¿Con qué hemoglobina se transfunde a un adulto estable sin sangrado activo hoy?", hist)
      .startswith("¿Con qué"))
check("Sin historial se busca la pregunta", rag.consulta_con_contexto("¿y en niños?", []) == "¿y en niños?")
turnos = rag._turnos(hist)
check("El historial pasa al modelo con roles y sin marcas [F#]",
      [t["role"] for t in turnos] == ["user", "assistant"] and "[F" not in turnos[1]["content"], turnos)
check("El historial se recorta a los últimos turnos",
      len(rag._turnos([{"rol": "usuario", "texto": str(i)} for i in range(20)])) == rag.HISTORIAL_MAX)
capturado.clear()
rag._llm("¿y en niños?", [{"titulo": "T", "seccion": "S", "texto": "x"}], historial=hist)
check("El modelo recibe sistema, historial y la pregunta con fuentes, en ese orden",
      [m["role"] for m in capturado["messages"]] == ["system", "user", "assistant", "user"])

_respuesta = {"texto": "Respuesta [F1]"}
_Resp.json = lambda self: {"choices": [{"message": {"content": _respuesta["texto"]}}]}
_respuesta["texto"] = "Hola, puedo responder con las guías [F2]."
r = rag.responder("hola", [], fuentes=["Guía de ayuno"])
check("Sin evidencia el modelo conversa: abstención sin citas y sin marcas",
      r["abstencion"] and r.get("conversacion") and not r["citas_usadas"] and "[F" not in r["respuesta"], r)
check("La conversación recibe la lista de documentos del perfil", "Guía de ayuno" in capturado["messages"][0]["content"])
r = rag.responder("hola", [], fuentes=[], conversacional=False)
check("Sin conversación (evaluaciones) queda el mensaje fijo", r["respuesta"] == rag.SIN_EVIDENCIA and not r.get("conversacion"))
_respuesta["texto"] = rag.NO_ENCONTRADO
r = rag.responder("¿dosis de X?", [{"titulo": "T", "seccion": "S", "texto": "x"}], fuentes=["G"])
check("Si el modelo dice NO_ENCONTRADO y conversar también, queda el mensaje fijo",
      r["abstencion"] and r["respuesta"] == rag.SIN_EVIDENCIA, r)
httpx.post = lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("sin red"))
r = rag.responder("hola", [], fuentes=["G"])
check("Si el modelo falla al conversar, queda el mensaje fijo", r["respuesta"] == rag.SIN_EVIDENCIA and r["abstencion"])
httpx.post = _post
_respuesta["texto"] = "Respuesta [F1]"

print("\n[6] Evaluación y guías")
preg = json.loads((RAIZ / "docs/rag/eval/preguntas.json").read_text(encoding="utf-8"))
ids_docs = {d.id for d in guias} | {core.leer_documento(p).id for p in (RAIZ / "docs/rag/eval/historias").glob("*.md")}
check("Los ids de la evaluación son únicos", len({p["id"] for p in preg}) == len(preg))
check("Todo documento esperado existe", all(p["esperado"] in ids_docs for p in preg if p["esperado"]),
      [p["id"] for p in preg if p["esperado"] and p["esperado"] not in ids_docs])
para = [p for p in preg if p.get("tipo") == "parafraseada"]
check("Hay al menos 60 parafraseadas y 30 sin respuesta",
      len(para) >= 60 and sum(1 for p in preg if not p["esperado"]) >= 30, (len(para)))
check("Cada guía tiene al menos 2 parafraseadas",
      all(sum(1 for p in para if p["esperado"] == d.id) >= 2 for d in guias),
      {d.id: sum(1 for p in para if p["esperado"] == d.id) for d in guias})
sys.path.insert(0, str(RAIZ / "scripts"))
import generar_preguntas as gp  # noqa: E402

base = GUIA.format(larga="texto")
limpio = gp.quitar_bloques(base)
check("Quitar los bloques deja la guía sin preguntas", "<!--" not in limpio and "## Larga" in limpio)
nuevo = gp.insertar(limpio, {"Sin preguntas": ["¿Nueva?"], "Larga": ["¿Otra?"]})
ruta.write_text(nuevo, encoding="utf-8")
f2 = {f.seccion: f.preguntas for f in core.fragmentar(core.leer_documento(ruta))}
check("Insertar pone cada bloque en su sección", f2.get("Sin preguntas") == ["¿Nueva?"] and f2.get("Larga") == ["¿Otra?"]
      and f2.get("Ayuno antes de la anestesia") == [], f2)
ruta.unlink()

print(f"\n{'TODO OK' if not fallos else f'{fallos} FALLAS'}")
sys.exit(1 if fallos else 0)
