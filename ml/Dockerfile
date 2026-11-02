# Servicio de IA (R10, R12). Esteban es el dueño de esta carpeta: este
# Dockerfile y app.py son el esqueleto mínimo para que "docker compose up"
# funcione desde ya. Él agrega el modelo entrenado y las dependencias.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10002 ml
USER ml

# RAG: el modelo de embeddings se descarga al construir la imagen, no en la
# primera pregunta (ni en un contenedor sin internet).
ENV FASTEMBED_CACHE=/home/ml/fastembed
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='/home/ml/fastembed')"
# Reranker opcional (BAAI/bge-reranker-v2-m3-int8, unos 570 MB): solo se descarga si
# RAG_RERANKER_MODELO tiene valor en el .env (docker-compose.yml lo pasa como build arg).
ARG RAG_RERANKER_MODELO=""
ENV RAG_MODELO_RERANKER=${RAG_RERANKER_MODELO}
RUN if [ -n "$RAG_RERANKER_MODELO" ]; then python -c "import os; from fastembed.rerank.cross_encoder import TextCrossEncoder; TextCrossEncoder(os.environ['RAG_MODELO_RERANKER'], cache_dir='/home/ml/fastembed')"; fi

EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8001/salud', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
