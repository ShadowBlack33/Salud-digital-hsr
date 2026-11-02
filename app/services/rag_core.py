"""
Núcleo del RAG de Pulso, sin base de datos (lo usan la API y la evaluación).

    leer_documento()   lee una guía o historia en Markdown con encabezado YAML simple
    fragmentar()       parte un documento por secciones y ventanas de palabras; las
                       preguntas de cada sección (bloque <!-- preguntas ... -->) viajan
                       con sus fragmentos pero no forman parte del texto
    BM25               ranking léxico (Okapi BM25) con estadísticas de un corpus de referencia
    embeber()          vectores densos (fastembed local o el servicio ml), con su firma
    reordenar()        reranker (cross-encoder) opcional sobre los candidatos
    rrf()              fusión híbrida por Reciprocal Rank Fusion
    RecuperadorMemoria la misma recuperación que la API, en memoria, para la evaluación
    metricas()         Recall@k y MRR a nivel de documento

Todo lo que entra aquí ya pasó por el filtro clínico: este módulo nunca decide
qué puede ver un usuario, solo ordena lo que se le entrega.
"""
from __future__ import annotations

import logging
import math
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("hsr.rag")

# Modelo de embeddings: multilingüe (español), 384 dimensiones, corre en CPU.
# Si se cambia, hay que reindexar TODO: vectores de modelos distintos no son
# comparables (ver docs/RAG.md). Por eso cada vector guarda su FIRMA: modelo y
# versión de fastembed. La versión importa: entre fastembed 0.7 y 0.9 este mismo
# modelo pasó de cortar el texto en 512 tokens a cortarlo en 128, así que dos
# versiones distintas dan vectores distintos para el mismo fragmento.
MODELO_EMBEDDING = os.getenv("RAG_MODELO_EMBEDDING",
                             "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
DIMENSION = 384

# Reranker (cross-encoder multilingüe): BAAI/bge-reranker-v2-m3, licencia Apache 2.0
# (permite uso comercial), que fastembed trae en ONNX, sin PyTorch. Por defecto la
# versión int8 (570 MB, pensada para CPU); "BAAI/bge-reranker-v2-m3" es la de 32 bits (2,3 GB).
MODELO_RERANKER = os.getenv("RAG_MODELO_RERANKER", "BAAI/bge-reranker-v2-m3-int8")

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
    audiencia: str = "clinica"     # guías: a qué grupo de perfiles va (app/services/rag.py)


@dataclass
class Fragmento:
    documento_id: str
    titulo: str
    seccion: str
    texto: str
    tipo: str
    fuente: str
    paciente: str | None = None
    preguntas: list[str] = field(default_factory=list)   # preguntas que responde su sección
    meta: dict = field(default_factory=dict)

    @property
    def texto_busqueda(self) -> str:
        """Lo que ve BM25: el texto más las preguntas de la sección (el modelo solo ve el texto)."""
        return " ".join([self.texto, *self.preguntas])


def leer_documento(ruta: str | Path) -> Documento:
    """Lee un .md con encabezado '---' de pares 'clave: valor' (sin depender de PyYAML)."""
    crudo = Path(ruta).read_text(encoding="utf-8").replace("\r\n", "\n")
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
                     paciente=meta.get("paciente"), audiencia=meta.get("audiencia", "clinica"))


INICIO_PREGUNTAS = "<!-- preguntas"
FIN_PREGUNTAS = "-->"


def fragmentar(doc: Documento) -> list[Fragmento]:
    """
    Una sección (## ...) es la unidad natural de una guía. Si una sección es
    larga se parte en ventanas de PALABRAS_POR_FRAGMENTO con SOLAPE, y cada
    fragmento lleva el título del documento y de la sección, para que BM25 y
    el modelo denso sepan de qué trata aunque el texto no lo repita.

    Un bloque <!-- preguntas ... --> dentro de una sección (una pregunta por
    línea) no entra al texto: son las preguntas que esa sección responde, en
    palabras de quien pregunta, y acompañan a todos sus fragmentos (ver
    scripts/generar_preguntas.py). En GitHub el bloque no se ve.
    """
    secciones: list[tuple[str, str, list[str]]] = []
    actual, lineas, preguntas = "Introducción", [], []
    en_bloque = False
    for linea in doc.texto.replace("\r\n", "\n").splitlines():
        s = linea.strip()
        if en_bloque:
            if s.startswith(FIN_PREGUNTAS):
                en_bloque = False
            elif s:
                preguntas.append(s.lstrip("-* ").strip())
            continue
        if s.startswith(INICIO_PREGUNTAS):
            en_bloque = not s.endswith(FIN_PREGUNTAS)
            continue
        if linea.startswith("## "):
            if any(x.strip() for x in lineas):
                secciones.append((actual, "\n".join(lineas).strip(), preguntas))
            actual, lineas, preguntas = linea[3:].strip(), [], []
        elif linea.startswith("# "):
            continue
        else:
            lineas.append(linea)
    if any(x.strip() for x in lineas):
        secciones.append((actual, "\n".join(lineas).strip(), preguntas))

    fragmentos: list[Fragmento] = []
    for seccion, texto, preg in secciones:
        palabras = texto.split()
        paso = PALABRAS_POR_FRAGMENTO - SOLAPE
        inicio = 0
        while True:
            trozo = " ".join(palabras[inicio:inicio + PALABRAS_POR_FRAGMENTO])
            fragmentos.append(Fragmento(
                documento_id=doc.id, titulo=doc.titulo, seccion=seccion,
                texto=f"{doc.titulo}. {seccion}. {trozo}", tipo=doc.tipo,
                fuente=doc.fuente, paciente=doc.paciente, preguntas=list(preg)))
            if inicio + PALABRAS_POR_FRAGMENTO >= len(palabras):
                break
            inicio += paso
    return fragmentos


# ------------------------------------------------------------------ BM25
class BM25:
    """
    Okapi BM25 (k1=1.5, b=0.75).

    Las estadísticas del corpus (IDF y largo medio) salen de los textos con que
    se construye, y se pueden puntuar textos distintos con `puntuar()`. La API
    construye el BM25 con las guías y puntúa solo los candidatos que el perfil
    puede ver: así el puntaje de un mismo fragmento no cambia según quién
    pregunta, y el umbral de abstención calibrado sirve para todos los perfiles
    (antes el IDF se calculaba sobre lo filtrado: con las 2 guías del contable
    los puntajes quedaban en otra escala).
    """

    def __init__(self, textos: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [tokenizar(t) for t in textos]
        self.n = len(self.docs)
        self.largo_medio = (sum(len(d) for d in self.docs) / self.n) if self.n else 0.0
        self.frecuencias = [Counter(d) for d in self.docs]
        df: Counter = Counter()
        for d in self.docs:
            df.update(set(d))
        self.idf = {t: self._idf(f) for t, f in df.items()}

    def _idf(self, f: int) -> float:
        return math.log(1 + (self.n - f + 0.5) / (f + 0.5))

    def _puntaje(self, q: list[str], frec: Counter, largo: int) -> float:
        s = 0.0
        for t in q:
            tf = frec.get(t)
            if not tf:
                continue
            idf = self.idf.get(t, self._idf(0))      # término que no está en el corpus de referencia: muy raro
            s += idf * tf * (self.k1 + 1) / (
                tf + self.k1 * (1 - self.b + self.b * largo / (self.largo_medio or 1)))
        return s

    def puntajes(self, consulta: str) -> list[float]:
        q = tokenizar(consulta)
        return [self._puntaje(q, frec, len(doc)) for frec, doc in zip(self.frecuencias, self.docs)]

    def puntuar(self, consulta: str, textos: list[str]) -> list[float]:
        """Puntajes de otros textos con las estadísticas de este corpus."""
        q = tokenizar(consulta)
        salida = []
        for t in textos:
            doc = tokenizar(t)
            salida.append(self._puntaje(q, Counter(doc), len(doc)))
        return salida

    def ranking(self, consulta: str, k: int | None = None) -> list[tuple[int, float]]:
        return ordenar(self.puntajes(consulta), k)


def ordenar(puntajes: list[float], k: int | None = None) -> list[tuple[int, float]]:
    orden = sorted(((i, s) for i, s in enumerate(puntajes) if s > 0), key=lambda x: -x[1])
    return orden[:k] if k else orden


# ------------------------------------------------------------------ denso
# None = no se ha intentado; False = fastembed local falló una vez (sin red para
# descargar el modelo, por ejemplo) y no se reintenta en cada pregunta: se usa el servicio ml.
_modelo_local = None
_reranker_local = None


def version_fastembed() -> str | None:
    try:
        from importlib.metadata import version  # noqa: PLC0415
        return version("fastembed")
    except Exception:  # noqa: BLE001
        return None


def firma(version: str | None) -> str:
    """Modelo + versión de fastembed: dos vectores solo se comparan si su firma es igual."""
    return f"{MODELO_EMBEDDING}|fastembed=={version or '?'}"


def embeber_con_firma(textos: list[str]) -> tuple[list[list[float]] | None, str | None]:
    """
    Vectores normalizados (coseno = producto punto) y su firma. Usa fastembed si
    está instalado (scripts en el PC); si no, el servicio ml (contenedor de la
    API). (None, None) si no hay forma de calcularlos: el RAG sigue con BM25.
    """
    global _modelo_local
    if not textos:
        return [], None
    if _modelo_local is not False:
        try:
            from fastembed import TextEmbedding  # noqa: PLC0415
            if _modelo_local is None:
                _modelo_local = TextEmbedding(MODELO_EMBEDDING)
            vectores = [list(map(float, v)) for v in _modelo_local.embed(textos)]
            return [_unitario(v) for v in vectores], firma(version_fastembed())
        except ImportError:
            _modelo_local = False
        except Exception:  # noqa: BLE001 -- modelo no descargable, etc.
            log.warning("fastembed local no pudo calcular los vectores; se usa el servicio ml", exc_info=True)
            _modelo_local = False
    try:
        import httpx  # noqa: PLC0415
        r = httpx.post(f"{_url_ml()}/embed", json={"textos": textos}, timeout=60)
        r.raise_for_status()
        datos = r.json()
        if datos.get("modelo") != MODELO_EMBEDDING:
            return None, None   # otro modelo: sus vectores no son comparables con los guardados
        return [_unitario(v) for v in datos["vectores"]], datos.get("firma") or firma(None)
    except Exception:  # noqa: BLE001
        return None, None


def embeber(textos: list[str]) -> list[list[float]] | None:
    return embeber_con_firma(textos)[0]


def reordenar(consulta: str, textos: list[str]) -> list[float] | None:
    """
    Puntajes del reranker (cross-encoder) para cada texto frente a la consulta;
    None si no hay reranker disponible (se conserva el orden de la fusión).
    """
    global _reranker_local
    if not textos:
        return []
    if _reranker_local is not False:
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder  # noqa: PLC0415
            if _reranker_local is None:
                _reranker_local = TextCrossEncoder(MODELO_RERANKER)
            return [float(x) for x in _reranker_local.rerank(consulta, textos)]
        except ImportError:
            _reranker_local = False
        except Exception:  # noqa: BLE001
            log.warning("El reranker local no respondió; se usa el servicio ml", exc_info=True)
            _reranker_local = False
    try:
        import httpx  # noqa: PLC0415
        r = httpx.post(f"{_url_ml()}/rerank", json={"consulta": consulta, "textos": textos}, timeout=60)
        r.raise_for_status()
        datos = r.json()
        return [float(x) for x in datos["puntajes"]] if datos.get("modelo") == MODELO_RERANKER else None
    except Exception:  # noqa: BLE001
        return None


def _url_ml() -> str:
    url = os.getenv("ML_URL")
    if url:
        return url
    try:
        from app.core.config import get_settings  # noqa: PLC0415 -- lee también el .env
        return get_settings().ml_url
    except Exception:  # noqa: BLE001 -- fuera de la API (evaluar_rag.py)
        return "http://localhost:8001"


def _unitario(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def coseno(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# ------------------------------------------------------------------ fusión y métricas
def rrf(rankings: list[list[int]], k: int = 60, pesos: list[float] | None = None) -> list[tuple[int, float]]:
    """
    Reciprocal Rank Fusion: suma peso/(k + posición) de cada lista. No necesita calibrar
    escalas. `pesos` (uno por lista, por defecto todos 1) deja darle menos voz a un método;
    se elige con scripts/evaluar_rag.py sobre preguntas separadas de las que se reportan.
    """
    pesos = pesos or [1.0] * len(rankings)
    total: dict[int, float] = {}
    for lista, w in zip(rankings, pesos):
        for pos, idx in enumerate(lista, start=1):
            total[idx] = total.get(idx, 0.0) + w / (k + pos)
    return sorted(total.items(), key=lambda x: -x[1])


def aplicar_reranker(consulta: str, orden: list[int], texto_de, n: int) -> tuple[list[int], bool]:
    """
    Reordena los primeros n candidatos con el reranker; el resto queda detrás en
    su orden. Devuelve (orden, se_aplico). Si no hay reranker, el orden no cambia.
    """
    cabeza = orden[:n]
    puntajes = reordenar(consulta, [texto_de(i) for i in cabeza])
    if not puntajes:
        return orden, False
    nueva = [i for i, _ in sorted(zip(cabeza, puntajes), key=lambda x: -x[1])]
    return nueva + orden[n:], True


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


def similitud_lexica(a: str, b: str) -> float:
    """Jaccard de tokens: para detectar preguntas de evaluación copiadas en el índice."""
    ta, tb = set(tokenizar(a)), set(tokenizar(b))
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


# ------------------------------------------------------------------ recuperación en memoria
class RecuperadorMemoria:
    """
    La recuperación de app/services/rag.py:buscar() sin base de datos, para
    scripts/evaluar_rag.py y scripts/probar_abstencion.py:
      · BM25 con estadísticas de las guías, sobre texto + preguntas de la sección;
      · denso: el mejor coseno entre el vector del fragmento y los de sus preguntas;
      · fusión RRF y, si se pide, reranker sobre los primeros candidatos.
    """

    def __init__(self, fragmentos: list[Fragmento], usar_preguntas: bool = True,
                 base: RecuperadorMemoria | None = None):
        """`base`: otro recuperador sobre los mismos fragmentos del que se reusan los vectores."""
        self.frags = fragmentos
        self.usar_preguntas = usar_preguntas
        self.bm25 = BM25([f.texto_busqueda if usar_preguntas else f.texto
                          for f in fragmentos if f.tipo == "guia"] or [f.texto for f in fragmentos])
        self._textos_bm25 = [f.texto_busqueda if usar_preguntas else f.texto for f in fragmentos]
        if base is not None:
            self.vec_frag, self.firma = base.vec_frag, base.firma
        else:
            self.vec_frag, self.firma = embeber_con_firma([f.texto for f in fragmentos])
        self.vec_preg: list[list[list[float]]] = [[] for _ in fragmentos]
        if self.vec_frag is not None and usar_preguntas:
            todas = [(i, p) for i, f in enumerate(fragmentos) for p in f.preguntas]
            if todas:
                vecs = embeber([p for _, p in todas]) or []
                for (i, _), v in zip(todas, vecs):
                    self.vec_preg[i].append(v)

    @property
    def hay_denso(self) -> bool:
        return self.vec_frag is not None

    def lexico(self, consulta: str, k: int | None = None) -> list[tuple[int, float]]:
        return ordenar(self.bm25.puntuar(consulta, self._textos_bm25), k)

    def similitudes(self, qv: list[float]) -> list[float]:
        return [max([coseno(qv, v)] + [coseno(qv, p) for p in ps])
                for v, ps in zip(self.vec_frag, self.vec_preg)]

    def denso(self, qv: list[float], k: int | None = None) -> list[tuple[int, float]]:
        sims = sorted(enumerate(self.similitudes(qv)), key=lambda x: -x[1])
        return sims[:k] if k else sims

    def hibrido(self, consulta: str, qv: list[float], k: int, peso_denso: float = 1.0,
                candidatos: int = 20) -> list[int]:
        lista = [i for i, _ in self.lexico(consulta, candidatos)]
        dens = [i for i, _ in self.denso(qv, candidatos)]
        return [i for i, _ in rrf([lista, dens], pesos=[1.0, peso_denso])][:k]

    def con_reranker(self, consulta: str, orden: list[int], n: int = 20) -> list[int]:
        return aplicar_reranker(consulta, orden, lambda i: self.frags[i].texto, n)[0]
