# Resultados de la evaluación del RAG

Corpus: 21 documentos (18 guías, 3 historias de evaluación), 138 fragmentos. Preguntas con documento esperado: 54. Modelo denso: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.

| Método | Recall@1 | Recall@3 | MRR |
| --- | --- | --- | --- |
| BM25 | 0.94 | 1.00 | 0.97 |
| Denso | 0.80 | 0.89 | 0.85 |
| Híbrido (RRF) | 0.87 | 0.94 | 0.91 |

## Preguntas donde el primer documento no fue el esperado

**BM25:** Q08 (esperado G03, obtuvo G01, G03, G10); Q16 (esperado G05, obtuvo G09, G05, H01); Q45 (esperado G14, obtuvo G13, G14, H03)
**Denso:** Q03 (esperado G01, obtuvo G02, H01, G01); Q13 (esperado G04, obtuvo G11, G12, G03); Q16 (esperado G05, obtuvo G10, G11, G07); Q19 (esperado G07, obtuvo G05, G07, G10); Q22 (esperado H01, obtuvo H02, H01, H03); Q23 (esperado H01, obtuvo G02, H03, G07); Q29 (esperado G09, obtuvo G15, G09, G10); Q41 (esperado G13, obtuvo H03, G18, H02); Q43 (esperado G13, obtuvo H03, H02, H01); Q44 (esperado G14, obtuvo G08, G14, G17); Q45 (esperado G14, obtuvo G13, G10, H02)
**Híbrido (RRF):** Q13 (esperado G04, obtuvo G11, G04, G12); Q16 (esperado G05, obtuvo G09, G11, G15); Q23 (esperado H01, obtuvo H03, G02, H02); Q41 (esperado G13, obtuvo H01, H02, G13); Q43 (esperado G13, obtuvo H02, H01, G07); Q44 (esperado G14, obtuvo G08, G14, G12); Q45 (esperado G14, obtuvo G13, H02, G14)

## Calibración de la abstención con BM25 (puntaje máximo)

- Preguntas con respuesta: mínimo 5.3, mediana 15.4.
- Preguntas sin respuesta en el corpus: máximo 4.3.
- El umbral `RAG_UMBRAL_BM25` debe quedar entre esos dos valores.

## Calibración de la abstención (similitud coseno máxima)

- Preguntas con respuesta: mínimo 0.47, mediana 0.69.
- Preguntas sin respuesta en el corpus: máximo 0.57.
- El umbral `RAG_UMBRAL_DENSO` debe quedar entre esos dos valores.

## Abstención del híbrido (denso ≥ 0.45 y BM25 ≥ 5.0)

- Preguntas con respuesta que se abstendrían por error: ninguna.
- Preguntas sin respuesta que se responderían por error: ninguna.
