-- ============================================================================
-- 15_rag.sql · RAG de Pulso (Semana 12)
--   · pgvector para los vectores de los fragmentos
--   · rag_fragmentos: guías e historias aprobadas ya seudonimizadas
--   · rag_consultas: quién preguntó qué, con qué fuentes y si hubo abstención
-- Idempotente. Uso (solo Carlos sobre la base compartida):
--   python scripts/aplicar_sql.py db/15_rag.sql
-- En Neon la extensión vector está disponible; en local hace falta la imagen
-- pgvector/pgvector:pg16 (docker-compose.yml).
-- ============================================================================
BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_fragmentos (
    id               BIGSERIAL PRIMARY KEY,
    documento_id     TEXT        NOT NULL,                 -- G01..G07 o HIST-<seudónimo>
    tipo             TEXT        NOT NULL CHECK (tipo IN ('guia', 'historia')),
    paciente_id      TEXT,                                 -- índice ciego; NULL en guías
    estado           TEXT        NOT NULL DEFAULT 'aprobado'
                                 CHECK (estado IN ('aprobado', 'pendiente', 'rechazado')),
    titulo           TEXT        NOT NULL,
    seccion          TEXT        NOT NULL DEFAULT '',
    fuente           TEXT        NOT NULL DEFAULT '',
    texto            TEXT        NOT NULL,                 -- ya seudonimizado
    embedding        vector(384),                          -- NULL si se indexó sin modelo denso
    modelo_embedding TEXT,                                 -- con qué modelo se calculó el vector
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((tipo = 'guia' AND paciente_id IS NULL) OR (tipo = 'historia' AND paciente_id IS NOT NULL))
);

-- El filtro clínico corre antes del ranking: estos índices lo hacen barato.
CREATE INDEX IF NOT EXISTS ix_rag_frag_filtro ON rag_fragmentos (tipo, estado, paciente_id);
CREATE INDEX IF NOT EXISTS ix_rag_frag_documento ON rag_fragmentos (documento_id);
-- Con pocos miles de fragmentos la búsqueda exacta es suficiente; si el corpus
-- crece, crear un índice HNSW:
--   CREATE INDEX ix_rag_frag_hnsw ON rag_fragmentos USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS rag_consultas (
    id             BIGSERIAL PRIMARY KEY,
    usuario_id     INTEGER     NOT NULL,
    rol            TEXT,
    pregunta       TEXT        NOT NULL,
    paciente_id    TEXT,                                   -- filtro pedido, si lo hubo
    metodo         TEXT        NOT NULL,
    fuentes        JSONB       NOT NULL DEFAULT '[]'::jsonb, -- ids de fragmentos citados
    abstencion     BOOLEAN     NOT NULL,
    confianza      REAL,
    generador      TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rag_consultas_usuario ON rag_consultas (usuario_id, created_at DESC);

COMMIT;
