-- ============================================================================
-- 03_rag.sql · Todo lo del RAG de Pulso en un solo archivo
--
--   · extensión vector (pgvector) para los vectores
--   · rag_fragmentos: guías e historias aprobadas ya seudonimizadas, con su
--     vector, la firma del vector (modelo + versión de fastembed) y la audiencia
--     (perfiles que pueden recuperar cada guía)
--   · rag_preguntas: las preguntas que responde cada sección, con su propio
--     vector (se borran solas con su fragmento)
--   · rag_consultas: quién preguntó qué, con qué fuentes, si hubo abstención y
--     con qué parámetros (modelo, temperatura, prompt, embeddings, reranker)
--
-- Sirve para una base nueva y para una que ya existe (la compartida en Neon):
-- todo es "si no existe", así que se puede correr cuantas veces haga falta.
--
-- Base nueva, en orden:
--   python scripts/aplicar_sql.py db/esquema_completo.sql
--   python scripts/aplicar_sql.py db/03_rag.sql
--   python scripts/generar_datos.py
--   python scripts/aplicar_sql.py db/01_datos_sinteticos.sql
--   python scripts/rag_indexar.py
-- Base que ya existe (la compartida en Neon):
--   python scripts/aplicar_sql.py db/03_rag.sql
--   python scripts/rag_indexar.py      (firmas nuevas, preguntas y seudónimos de 8)
--
-- Reúne lo que antes estaba en db/historial/15_rag.sql, la parte RAG de
-- db/04_perfiles_rag_remisiones_fhir.sql y lo nuevo de la versión 2 (docs/RAG.md §10).
-- ============================================================================
BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

-- ------------------------------------------------------------------ fragmentos
CREATE TABLE IF NOT EXISTS rag_fragmentos (
    id               BIGSERIAL   PRIMARY KEY,
    documento_id     TEXT        NOT NULL,                 -- G01..G18 o HIST-<seudónimo>
    tipo             TEXT        NOT NULL CHECK (tipo IN ('guia', 'historia')),
    paciente_id      TEXT,                                 -- índice ciego; NULL en guías
    estado           TEXT        NOT NULL DEFAULT 'aprobado'
                                 CHECK (estado IN ('aprobado', 'pendiente', 'rechazado')),
    titulo           TEXT        NOT NULL,
    seccion          TEXT        NOT NULL DEFAULT '',
    fuente           TEXT        NOT NULL DEFAULT '',
    texto            TEXT        NOT NULL,                 -- ya seudonimizado
    embedding        vector(384),                          -- NULL si se indexó sin modelo denso
    modelo_embedding TEXT,                                 -- firma: modelo|fastembed==versión
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    audiencia        TEXT[],                               -- perfiles (roles.codigo); NULL en historias
    CHECK ((tipo = 'guia' AND paciente_id IS NULL) OR (tipo = 'historia' AND paciente_id IS NOT NULL))
);
ALTER TABLE rag_fragmentos ADD COLUMN IF NOT EXISTS audiencia TEXT[];       -- bases anteriores al Corte 2

-- El filtro clínico corre antes del ranking: estos índices lo hacen barato.
CREATE INDEX IF NOT EXISTS ix_rag_frag_filtro ON rag_fragmentos (tipo, estado, paciente_id);
CREATE INDEX IF NOT EXISTS ix_rag_frag_documento ON rag_fragmentos (documento_id);
CREATE INDEX IF NOT EXISTS ix_rag_frag_audiencia ON rag_fragmentos USING gin (audiencia);
-- Con pocos miles de fragmentos la búsqueda exacta es suficiente; si el corpus crece:
--   CREATE INDEX ix_rag_frag_hnsw ON rag_fragmentos USING hnsw (embedding vector_cosine_ops);

-- ------------------------------------------------------------------ preguntas por sección
CREATE TABLE IF NOT EXISTS rag_preguntas (
    id               BIGSERIAL   PRIMARY KEY,
    fragmento_id     BIGINT      NOT NULL REFERENCES rag_fragmentos(id) ON DELETE CASCADE,
    pregunta         TEXT        NOT NULL,
    embedding        vector(384),
    modelo_embedding TEXT,                                 -- misma firma que el fragmento
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rag_preg_fragmento ON rag_preguntas (fragmento_id);

-- ------------------------------------------------------------------ consultas (auditoría)
CREATE TABLE IF NOT EXISTS rag_consultas (
    id             BIGSERIAL   PRIMARY KEY,
    usuario_id     INTEGER     NOT NULL,
    rol            TEXT,
    pregunta       TEXT        NOT NULL,
    paciente_id    TEXT,                                   -- filtro pedido, si lo hubo
    metodo         TEXT        NOT NULL,
    fuentes        JSONB       NOT NULL DEFAULT '[]'::jsonb, -- ids de fragmentos citados
    abstencion     BOOLEAN     NOT NULL,
    confianza      REAL,
    generador      TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    parametros     JSONB       NOT NULL DEFAULT '{}'::jsonb  -- modelo, temperatura, prompt, embeddings, reranker
);
ALTER TABLE rag_consultas ADD COLUMN IF NOT EXISTS parametros JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS ix_rag_consultas_usuario ON rag_consultas (usuario_id, created_at DESC);

COMMIT;
