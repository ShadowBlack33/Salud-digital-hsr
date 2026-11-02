#!/usr/bin/env python3
"""
Genera las preguntas por sección de las guías del RAG (paso 2 de docs/RAG.md).

Para cada sección (## ...) de cada guía de docs/rag/guias, el modelo de lenguaje
escribe 4 preguntas que esa sección responde, como las haría quien la consulta
(médico, enfermera, paciente, contable...), con palabras propias y no copiadas
del texto. Se guardan en la misma guía, al final de su sección:

    <!-- preguntas
    ¿...?
    -->

GitHub no muestra el bloque. La API las indexa con su propio vector (rag_preguntas)
y las suma al BM25; el modelo que redacta las respuestas NO las ve.

Para no inflar la evaluación, el modelo nunca ve docs/rag/eval/preguntas.json, y
cualquier pregunta generada muy parecida a una de la evaluación se descarta.

LAS PREGUNTAS LAS REVISA EL EQUIPO antes de hacer commit (git diff docs/rag/guias):
una pregunta mal asignada a una sección hace que el RAG recupere la sección equivocada.

Uso:  python scripts/generar_preguntas.py                  (solo secciones sin preguntas)
      python scripts/generar_preguntas.py --guias G01,G12  (solo esas guías)
      python scripts/generar_preguntas.py --rehacer        (reemplaza las existentes)
      python scripts/generar_preguntas.py --prueba         (muestra, no escribe)
      python scripts/generar_preguntas.py --completo       (usa primero el modelo completo)
Necesita GEMINI_API_KEY (o XAI_API_KEY) en el .env y red. Una llamada por guía.
Después: python scripts/rag_indexar.py --guias
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.services import rag  # noqa: E402
from app.services.rag_core import FIN_PREGUNTAS, INICIO_PREGUNTAS, leer_documento, similitud_lexica  # noqa: E402

POR_GUIA = 4          # preguntas por sección
PAUSA = 6             # segundos entre llamadas (capa gratuita)
UMBRAL_COPIA = 0.6    # igual que en scripts/evaluar_rag.py
QUIEN = {
    "clinica": "un médico, una enfermera o un anestesiólogo del hospital",
    "operativa": "un médico, una enfermera o el coordinador del hospital",
    "facturacion": "una persona del área de facturación",
    "paciente": "un paciente o su familiar, sin conocimientos médicos",
    "coordinacion": "el coordinador o el director del hospital",
    "admin": "el administrador del sistema",
}

PROMPT = """Vas a escribir las preguntas que responde cada sección de una guía de un hospital colombiano.
Las preguntas sirven para que un buscador encuentre la sección correcta cuando alguien pregunta con
sus propias palabras.

Guía: {titulo}
Quién la consulta: {quien}

Reglas:
1. Escribe exactamente {n} preguntas por sección, en español de Colombia, como las haría quien la consulta.
2. Cada pregunta debe poder responderse SOLO con su sección.
3. Usa palabras cotidianas y distintas a las del texto (sinónimos, rodeos, cómo lo diría alguien en
   el pasillo o en la consulta). No copies frases de la guía. Varía la forma de preguntar.
4. Entre 6 y 22 palabras cada una, con signos de interrogación.
5. No incluyas la respuesta dentro de la pregunta.

Responde SOLO con un objeto JSON cuyas claves son los títulos de las secciones, copiados exactamente,
y cuyos valores son listas de preguntas.

Secciones:
{secciones}"""


def secciones(texto: str) -> list[tuple[str, str]]:
    """(título, texto) de cada sección ## de la guía, sin bloques de preguntas."""
    salida, actual, lineas, en_bloque = [], None, [], False
    for linea in texto.splitlines():
        s = linea.strip()
        if en_bloque:
            en_bloque = not s.startswith(FIN_PREGUNTAS)
            continue
        if s.startswith(INICIO_PREGUNTAS):
            en_bloque = not s.endswith(FIN_PREGUNTAS)
            continue
        if linea.startswith("## "):
            if actual:
                salida.append((actual, "\n".join(lineas).strip()))
            actual, lineas = linea[3:].strip(), []
        elif actual:
            lineas.append(linea)
    if actual:
        salida.append((actual, "\n".join(lineas).strip()))
    return salida


def tiene_preguntas(texto: str, titulo: str) -> bool:
    bloque = re.search(rf"^## {re.escape(titulo)}\n(.*?)(?=^## |\Z)", texto, re.S | re.M)
    return bool(bloque and INICIO_PREGUNTAS in bloque.group(1))


def quitar_bloques(texto: str) -> str:
    return re.sub(rf"\n*{re.escape(INICIO_PREGUNTAS)}.*?{re.escape(FIN_PREGUNTAS)}[ \t]*", "", texto, flags=re.S)


def insertar(texto: str, por_seccion: dict[str, list[str]]) -> str:
    """Pone cada bloque al final de su sección (antes del siguiente ##)."""
    lineas = texto.split("\n")
    titulos = [(i, l[3:].strip()) for i, l in enumerate(lineas) if l.startswith("## ")]
    for n in range(len(titulos) - 1, -1, -1):
        i, titulo = titulos[n]
        if titulo not in por_seccion:
            continue
        fin = titulos[n + 1][0] if n + 1 < len(titulos) else len(lineas)
        while fin > i + 1 and not lineas[fin - 1].strip():
            fin -= 1
        bloque = ["", INICIO_PREGUNTAS, *por_seccion[titulo], FIN_PREGUNTAS]
        lineas[fin:fin] = bloque
    return "\n".join(lineas)


REINTENTOS = 3                      # por modelo, ante 429 / 500 / 503 / tiempo agotado
ESPERAS = (10, 25, 50)              # segundos entre reintentos


def _clave(texto: str) -> str:
    """Título normalizado para comparar: sin '#', numeración, tildes ni mayúsculas."""
    from app.services.rag_core import normalizar  # noqa: PLC0415
    t = re.sub(r"^[#\s\d.)-]+", "", str(texto)).strip().strip("*").strip()
    return " ".join(normalizar(t).split())


def _aplanar(respuesta) -> dict[str, list[str]]:
    """
    Acepta las formas en que el modelo suele responder:
      {"Sección": ["¿...?"]}, {"secciones": {...}}, [{"seccion": "...", "preguntas": [...]}],
      y preguntas como texto o como {"pregunta": "..."}.
    """
    if isinstance(respuesta, dict) and len(respuesta) == 1:
        unico = next(iter(respuesta.values()))
        if isinstance(unico, dict) or (isinstance(unico, list) and unico and all(isinstance(x, dict) for x in unico)):
            respuesta = unico
    pares = []
    if isinstance(respuesta, dict):
        pares = list(respuesta.items())
    elif isinstance(respuesta, list):
        for item in respuesta:
            if isinstance(item, dict):
                titulo = next((item[k] for k in ("seccion", "sección", "titulo", "título", "section", "title") if k in item), "")
                preg = next((item[k] for k in ("preguntas", "questions") if k in item), [])
                pares.append((titulo, preg))
    salida: dict[str, list[str]] = {}
    for titulo, preg in pares:
        if isinstance(preg, str):
            preg = [preg]
        lista = []
        for q in preg or []:
            if isinstance(q, dict):
                q = next((q[k] for k in ("pregunta", "question", "texto", "text") if k in q), "")
            lista.append(str(q))
        salida[_clave(titulo)] = lista
    return salida


def _llamar(prov, prompt: str) -> dict:
    _, base, clave, modelo = prov
    import httpx  # noqa: PLC0415
    cuerpo = {"model": modelo, "messages": [{"role": "user", "content": prompt}]}
    r = httpx.post(f"{base.rstrip('/')}/chat/completions", timeout=120,
                   headers={"Authorization": f"Bearer {clave}"}, json=cuerpo)
    r.raise_for_status()
    contenido = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", contenido, re.S)
    return json.loads(m.group(0) if m else contenido)


def pedir(prompt: str) -> dict:
    """
    Primero el modelo lite (escribir preguntas cortas no necesita el completo, y el
    completo es el que más se satura) y, si falla, el completo; con --completo, al
    revés. Un 503 (servicio no disponible) o un 429 (límite de la capa gratuita) son
    pasajeros: se reintenta con esperas crecientes antes de rendirse con esa guía.
    """
    import httpx  # noqa: PLC0415
    orden = (True, False) if "--completo" in sys.argv else (False, True)
    proveedores = [p for p in (rag._proveedor(orden[0]), rag._proveedor(orden[1])) if p]
    if not proveedores:
        sys.exit("No hay GEMINI_API_KEY ni XAI_API_KEY en el .env.")
    proveedores = list(dict.fromkeys(proveedores))      # sin repetir si lite == completo
    ultimo: Exception | None = None
    for prov in proveedores:
        for intento in range(REINTENTOS):
            try:
                return _llamar(prov, prompt)
            except httpx.HTTPStatusError as e:
                ultimo = e
                if e.response.status_code not in (429, 500, 502, 503, 504):
                    raise
            except (httpx.TimeoutException, httpx.TransportError, json.JSONDecodeError) as e:
                ultimo = e
            espera = ESPERAS[min(intento, len(ESPERAS) - 1)]
            print(f"   {prov[3]}: {type(ultimo).__name__} "
                  f"{getattr(getattr(ultimo, 'response', None), 'status_code', '')}; reintento en {espera} s")
            time.sleep(espera)
    raise ultimo or RuntimeError("sin respuesta")


def main() -> None:
    prueba, rehacer = "--prueba" in sys.argv, "--rehacer" in sys.argv
    solo = set(sys.argv[sys.argv.index("--guias") + 1].split(",")) if "--guias" in sys.argv else None
    evaluacion = [p["pregunta"] for p in
                  json.loads((RAIZ / "docs/rag/eval/preguntas.json").read_text(encoding="utf-8"))]
    total = descartadas = 0
    for ruta in sorted((RAIZ / "docs/rag/guias").glob("*.md")):
        doc = leer_documento(ruta)
        if solo and doc.id not in solo:
            continue
        crudo = ruta.read_bytes().decode("utf-8")
        crlf = "\r\n" in crudo
        texto = crudo.replace("\r\n", "\n")
        if rehacer:
            texto = quitar_bloques(texto)
        pendientes = [(t, s) for t, s in secciones(texto) if not tiene_preguntas(texto, t)]
        if not pendientes:
            print(f"{doc.id}: ya tiene preguntas en todas sus secciones")
            continue
        quien = " o ".join(QUIEN.get(a.strip(), a) for a in doc.audiencia.split(","))
        prompt = PROMPT.format(titulo=doc.titulo, quien=quien, n=POR_GUIA,
                               secciones="\n\n".join(f"### {t}\n{s}" for t, s in pendientes))
        try:
            respuesta = pedir(prompt)
        except Exception as e:  # noqa: BLE001
            print(f"{doc.id}: falló la llamada ({type(e).__name__}: {e}); se sigue con la siguiente")
            time.sleep(PAUSA)
            continue
        por_seccion: dict[str, list[str]] = {}
        planas = _aplanar(respuesta)
        for titulo, _ in pendientes:
            buenas = []
            for q in planas.get(_clave(titulo), []):
                q = " ".join(str(q).split()).strip(' "-*')
                if len(q.split()) < 4:
                    continue
                if not q.endswith("?"):
                    q += "?"
                if q.count("¿") > 1:                  # "¿Si ..., ¿...?" -> "Si ..., ¿...?"
                    q = q.lstrip("¿")
                if max((similitud_lexica(q, e) for e in evaluacion), default=0) >= UMBRAL_COPIA:
                    descartadas += 1          # demasiado parecida a una pregunta de la evaluación
                    continue
                buenas.append(q if q.startswith("¿") else "¿" + q)
            if buenas:
                por_seccion[titulo] = buenas[:POR_GUIA]
        faltan = [t for t, _ in pendientes if t not in por_seccion]
        if len(faltan) == len(pendientes):
            print(f"   (no se reconoció ninguna sección en la respuesta; inicio: {json.dumps(respuesta, ensure_ascii=False)[:400]})")
        total += sum(len(v) for v in por_seccion.values())
        print(f"{doc.id}: {sum(len(v) for v in por_seccion.values())} preguntas en {len(por_seccion)} secciones"
              + (f"; sin preguntas: {faltan}" if faltan else ""))
        if prueba:
            for t, qs in por_seccion.items():
                print(f"  ## {t}\n" + "\n".join(f"     {q}" for q in qs))
        else:
            nuevo = insertar(texto, por_seccion)
            ruta.write_bytes((nuevo.replace("\n", "\r\n") if crlf else nuevo).encode("utf-8"))
        time.sleep(PAUSA)
    print(f"\nTotal: {total} preguntas; descartadas por parecerse a la evaluación: {descartadas}.")
    if not prueba:
        print("Revisar con: git diff docs/rag/guias   y luego: python scripts/rag_indexar.py --guias")


if __name__ == "__main__":
    main()
