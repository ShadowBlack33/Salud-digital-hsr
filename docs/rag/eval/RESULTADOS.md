# Resultados de la evaluación del RAG

Corpus: 11 documentos (8 guías, 3 historias de evaluación), 64 fragmentos. Preguntas con documento esperado: 28. Modelo denso: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.

| Método | Recall@1 | Recall@3 | MRR |
| --- | --- | --- | --- |
| BM25 | 0.96 | 1.00 | 0.98 |
| Denso | 0.79 | 0.96 | 0.88 |
| Híbrido (RRF) | 0.96 | 0.96 | 0.97 |

## Preguntas donde el primer documento no fue el esperado

**BM25:** Q08 (esperado G03, obtuvo G01, G03, G02)
**Denso:** Q03 (esperado G01, obtuvo G02, H01, G01); Q13 (esperado G04, obtuvo G03, G04, G06); Q16 (esperado G05, obtuvo G07, G05, H02); Q19 (esperado G07, obtuvo G05, G07, G01); Q22 (esperado H01, obtuvo H02, H01, H03); Q23 (esperado H01, obtuvo G02, H03, G07)
**Híbrido (RRF):** Q23 (esperado H01, obtuvo H03, G02, H02)

## Calibración de la abstención con BM25 (puntaje máximo)

- Preguntas con respuesta: mínimo 5.4, mediana 12.2.
- Preguntas sin respuesta en el corpus: máximo 4.6.
- El umbral `RAG_UMBRAL_BM25` debe quedar entre esos dos valores.

## Calibración de la abstención (similitud coseno máxima)

- Preguntas con respuesta: mínimo 0.49, mediana 0.72.
- Preguntas sin respuesta en el corpus: máximo 0.57.
- El umbral `RAG_UMBRAL_DENSO` debe quedar entre esos dos valores.
