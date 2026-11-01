"""
Núcleo del RAG de Pulso, sin base de datos (lo usan la API y la evaluación).

    leer_documento()   lee una guía o historia en Markdown con encabezado YAML simple
    fragmentar()       parte un documento por secciones y ventanas de palabras
    BM25               ranking léxico (Okapi BM25) sobre los fragmentos YA filtrados
    embeber()          vectores densos (fastembed local o el servicio ml)
    rrf()              fusión híbrida por Reciprocal Rank Fusion
    metricas()         Recall@k y MRR a nivel de documento

Todo lo que entra aquí ya pasó por el filtro clínico: este módulo nunca decide
qué puede ver un usuario, solo ordena lo que se le entrega.
"""
from __future__ import annotations

import math
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Modelo de embeddings: multilingüe (español), 384 dimensiones, corre en CPU.
# Si se cambia, hay que reindexar TODO: vectores de modelos distintos no son
# comparables (ver docs/RAG.md). Por eso cada fragmento guarda el modelo.
MODELO_EMBEDDING = os.getenv("RAG_MODELO_EMBEDDING",
                             "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
DIMENSION = 384

PALABRAS_POR_FRAGMENTO = 150
SOLAPE = 40

STOPWORDS = set("""
a al algo algun alguna algunas alguno algunos ante antes como con contra cual cuales cuando de del desde donde
dos el ella ellas ellos en entre era es esa esas ese eso esos esta estaba estado estan estar este esto estos fue
fueron ha han hasta hay la las le les lo los mas me mi muy no nos o otra otro para pero por porque que quien se
ser si sin sobre son su sus tambien te tiene tienen todo un una uno unos y ya cuanto cuantos cuanta cuantas
""".split())


# ------------------------------------------------------------------ texto
def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para que 'Hipoglucemia' y 'hipoglucémia' coincidan."""
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def tokenizar(texto: str) -> list[str]:
    """Palabras y números (incluye decimales con coma: '6,6' -> '6,6')."""
    tokens = re.findall(r"[a-z0-9]+(?:[.,][0-9]+)?", normalizar(texto))
    return [t for t in tokens if t not in STOPWORDS]


# ------------------------------------------------------------------ documentos
@dataclass
class Documento:
    id: str
    titulo: str
    fuente: str
    tipo: str                      # "guia" | "historia"
    texto: str
    url: str = ""
    paciente: str | None = None    # seudónimo (solo historias)


@dataclass
class Fragmento:
    documento_id: str
    titulo: str
    seccion: str
    texto: str
    tipo: str
    fuente: str
    paciente: str | None = None
    meta: dict = field(default_factory=dict)


def leer_documento(ruta: str | Path) -> Documento:
    """Lee un .md con encabezado '---' de pares 'clave: valor' (sin depender de PyYAML)."""
    crudo = Path(ruta).read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    cuerpo = crudo
    if crudo.startswith("---"):
        _, encabezado, cuerpo = crudo.split("---", 2)
        for linea in encabezado.strip().splitlines():
            if ":" in linea:
                k, v = linea.split(":", 1)
                meta[k.strip()] = v.strip()
    return Documento(id=meta["id"], titulo=meta.get("titulo", meta["id"]), fuente=meta.get("fuente", ""),
                     tipo=meta.get("tipo", "guia"), texto=cuerpo.strip(), url=meta.get("url", ""),
                     paciente=meta.get("paciente"))


def fragmentar(doc: Documento) -> list[Fragmento]:
    """
    Una sección (## ...) es la unidad natural de una guía. Si una sección es
    larga se parte en ventanas de PALABRAS_POR_FRAGMENTO con SOLAPE, y cada
    fragmento lleva el título del documento y de la sección, para que BM25 y
    el modelo denso sepan de qué trata aunque el texto no lo repita.
    """
    secciones: list[tuple[str, str]] = []
    actual, lineas = "Introducción", []
    for linea in doc.texto.splitlines():
        if linea.startswith("## "):
            if any(x.strip() for x in lineas):
                secciones.append((actual, "\n".join(lineas).strip()))
            actual, lineas = linea[3:].strip(), []
        elif linea.startswith("# "):
            continue
        else:
            lineas.append(linea)
    if any(x.strip() for x in lineas):
        secciones.append((actual, "\n".join(lineas).strip()))

    fragmentos: list[Fragmento] = []
    for seccion, texto in secciones:
        palabras = texto.split()
        paso = PALABRAS_POR_FRAGMENTO - SOLAPE
        inicio = 0
        while True:
            trozo = " ".join(palabras[inicio:inicio + PALABRAS_POR_FRAGMENTO])
            fragmentos.append(Fragmento(
                documento_id=doc.id, titulo=doc.titulo, seccion=seccion,
                texto=f"{doc.titulo}. {seccion}. {trozo}", tipo=doc.tipo,
                fuente=doc.fuente, paciente=doc.paciente))
            if inicio + PALABRAS_POR_FRAGMENTO >= len(palabras):
                break
            inicio += paso
    return fragmentos


# ------------------------------------------------------------------ BM25
class BM25:
    """Okapi BM25 (k1=1.5, b=0.75). Se construye sobre los candidatos ya filtrados."""

    def __init__(self, textos: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [tokenizar(t) for t in textos]
        self.n = len(self.docs)
        self.largo_medio = (sum(len(d) for d in self.docs) / self.n) if self.n else 0.0
        self.frecuencias = [Counter(d) for d in self.docs]
        df: Counter = Counter()
        for d in self.docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def puntajes(self, consulta: str) -> list[float]:
        q = tokenizar(consulta)
        salida = []
        for frec, doc in zip(self.frecuencias, self.docs):
            s = 0.0
            for t in q:
                if t not in frec:
                    continue
                tf = frec[t]
                s += self.idf.get(t, 0.0) * tf * (self.k1 + 1) / (
                    tf + self.k1 * (1 - self.b + self.b * len(doc) / (self.largo_medio or 1)))
            salida.append(s)
        return salida

    def ranking(self, consulta: str, k: int | None = None) -> list[tuple[int, float]]:
        p = self.puntajes(consulta)
        orden = sorted(((i, s) for i, s in enumerate(p) if s > 0), key=lambda x: -x[1])
        return orden[:k] if k else orden


# ------------------------------------------------------------------ denso
_modelo_local = None


def embeber(textos: list[str]) -> list[list[float]] | None:
    """
    Vectores normalizados (coseno = producto punto). Usa fastembed si está
    instalado (scripts en el PC); si no, el servicio ml (contenedor de la API).
    Devuelve None si no hay forma de calcularlos: el RAG sigue con BM25.
    """
    global _modelo_local
    if not textos:
        return []
    try:
        from fastembed import TextEmbedding  # noqa: PLC0415
        if _modelo_local is None:
            _modelo_local = TextEmbedding(MODELO_EMBEDDING)
        vectores = [list(map(float, v)) for v in _modelo_local.embed(textos)]
        return [_unitario(v) for v in vectores]
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 -- modelo no descargable, etc.
        return None
    try:
        import httpx  # noqa: PLC0415
        url = os.getenv("ML_URL")
        if not url:
            try:
                from app.core.config import get_settings  # noqa: PLC0415 -- lee también el .env
                url = get_settings().ml_url
            except Exception:  # noqa: BLE001 -- fuera de la API (evaluar_rag.py)
                url = "http://localhost:8001"
        r = httpx.post(f"{url}/embed", json={"textos": textos}, timeout=60)
        r.raise_for_status()
        datos = r.json()
        if datos.get("modelo") != MODELO_EMBEDDING:
            return None   # otro modelo: sus vectores no son comparables con los guardados
        return [_unitario(v) for v in datos["vectores"]]
    except Exception:  # noqa: BLE001
        return None


def _unitario(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def coseno(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# ------------------------------------------------------------------ fusión y métricas
def rrf(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion: suma 1/(k + posición) de cada lista. No necesita calibrar escalas."""
    total: dict[int, float] = {}
    for lista in rankings:
        for pos, idx in enumerate(lista, start=1):
            total[idx] = total.get(idx, 0.0) + 1.0 / (k + pos)
    return sorted(total.items(), key=lambda x: -x[1])


def documentos_en_orden(indices: list[int], fragmentos: list[Fragmento]) -> list[str]:
    """Ranking de fragmentos -> ranking de documentos (sin repetir)."""
    vistos: list[str] = []
    for i in indices:
        d = fragmentos[i].documento_id
        if d not in vistos:
            vistos.append(d)
    return vistos


def metricas(resultados: list[tuple[list[str], str]]) -> dict[str, float]:
    """resultados = [(documentos ordenados, documento esperado), ...]"""
    n = len(resultados) or 1
    r1 = sum(1 for docs, e in resultados if docs[:1] == [e]) / n
    r3 = sum(1 for docs, e in resultados if e in docs[:3]) / n
    mrr = sum((1 / (docs.index(e) + 1)) if e in docs else 0.0 for docs, e in resultados) / n
    return {"recall@1": r1, "recall@3": r3, "mrr": mrr}
