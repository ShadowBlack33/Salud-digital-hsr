# Resultados de la evaluación del RAG

Corpus: 21 documentos (18 guías, 3 historias de evaluación), 138 fragmentos, 428 preguntas por sección indexadas. Preguntas con documento esperado: 122 (68 parafraseadas); sin respuesta: 30. Embeddings: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2|fastembed==0.9.1`. Reranker: `BAAI/bge-reranker-v2-m3-int8`.


## Todas las preguntas: 122

| Método | Recall@1 | Recall@3 | MRR |
| --- | --- | --- | --- |
| BM25 | 0.76 | 0.88 | 0.83 |
| Denso | 0.65 | 0.79 | 0.74 |
| Híbrido (RRF) | 0.79 | 0.91 | 0.85 |
| BM25 + preguntas | 0.88 | 0.98 | 0.93 |
| Denso + preguntas | 0.77 | 0.89 | 0.85 |
| Híbrido + preguntas | 0.89 | 0.97 | 0.94 |
| Híbrido + preguntas (peso del denso 0.5) | 0.89 | 0.98 | 0.94 |
| Híbrido + preguntas + reranker | 0.93 | 0.99 | 0.96 |

## Preguntas literales (con las palabras de la guía): 54

| Método | Recall@1 | Recall@3 | MRR |
| --- | --- | --- | --- |
| BM25 | 0.96 | 1.00 | 0.98 |
| Denso | 0.80 | 0.89 | 0.85 |
| Híbrido (RRF) | 0.87 | 0.94 | 0.91 |
| BM25 + preguntas | 0.91 | 0.98 | 0.95 |
| Denso + preguntas | 0.78 | 0.93 | 0.87 |
| Híbrido + preguntas | 0.91 | 0.98 | 0.95 |
| Híbrido + preguntas (peso del denso 0.5) | 0.93 | 0.98 | 0.96 |
| Híbrido + preguntas + reranker | 0.98 | 1.00 | 0.99 |

## Preguntas parafraseadas (sin las palabras de la guía): 68

| Método | Recall@1 | Recall@3 | MRR |
| --- | --- | --- | --- |
| BM25 | 0.60 | 0.78 | 0.71 |
| Denso | 0.53 | 0.71 | 0.65 |
| Híbrido (RRF) | 0.72 | 0.88 | 0.80 |
| BM25 + preguntas | 0.85 | 0.99 | 0.92 |
| Denso + preguntas | 0.76 | 0.87 | 0.83 |
| Híbrido + preguntas | 0.88 | 0.96 | 0.93 |
| Híbrido + preguntas (peso del denso 0.5) | 0.87 | 0.99 | 0.93 |
| Híbrido + preguntas + reranker | 0.90 | 0.99 | 0.94 |

## Solo las de PRUEBA (no intervinieron en ninguna elección): 61

| Método | Recall@1 | Recall@3 | MRR |
| --- | --- | --- | --- |
| BM25 | 0.74 | 0.85 | 0.81 |
| Denso | 0.69 | 0.82 | 0.77 |
| Híbrido (RRF) | 0.79 | 0.92 | 0.85 |
| BM25 + preguntas | 0.87 | 0.98 | 0.93 |
| Denso + preguntas | 0.72 | 0.89 | 0.82 |
| Híbrido + preguntas | 0.89 | 0.95 | 0.93 |
| Híbrido + preguntas (peso del denso 0.5) | 0.87 | 0.98 | 0.93 |
| Híbrido + preguntas + reranker | 0.95 | 1.00 | 0.98 |

## Elección del peso del denso en la fusión

Ajuste: 61 preguntas; prueba: 61. El peso se elige con el MRR de ajuste (a igualdad, el mayor); el de prueba no interviene.

| Peso del denso | MRR (ajuste) | MRR (prueba) | Recall@1 (prueba) |
| --- | --- | --- | --- |
| 1.0 | 0.94 | 0.93 | 0.89 |
| 0.75 | 0.94 | 0.92 | 0.87 |
| 0.5 ← | 0.95 | 0.93 | 0.87 |
| 0.35 | 0.94 | 0.93 | 0.87 |
| 0.25 | 0.94 | 0.94 | 0.89 |
| 0.15 | 0.94 | 0.96 | 0.92 |

Peso elegido: **0.5** (`RAG_PESO_DENSO` en `.env`).

## Preguntas donde el primer documento no fue el esperado

**BM25** (29): Q08 (esperado G03, obtuvo G01, G03, G10); Q45 (esperado G14, obtuvo G13, G14, H03); P01 (esperado G01, obtuvo G09, G03, G01); P07 (esperado G17, obtuvo G08, G14, H01); P08 (esperado G13, obtuvo H01, H02, H03); P12 (esperado G07, obtuvo G05, G11, G09); P14 (esperado G18, obtuvo G15, G18, G16); P16 (esperado G01, obtuvo G08, G05, G01); P17 (esperado G01, obtuvo G06, H01, G08); P18 (esperado G01, obtuvo G07, G11, G08); P20 (esperado G02, obtuvo G05, G09); P31 (esperado G06, obtuvo G18, G04, G16); P33 (esperado G06, obtuvo G15, G16, G09); P34 (esperado G07, obtuvo G05, G07, G11); P40 (esperado G08, obtuvo G14, G07, G17); P42 (esperado G09, obtuvo G05, G06, G08); P45 (esperado G10, obtuvo G09, G05, G08); P47 (esperado G11, obtuvo G10, G11); P48 (esperado G11, obtuvo G04, G02, G13); P53 (esperado G13, obtuvo G14, G07, H03); P54 (esperado G13, obtuvo G07, G14, G08); P55 (esperado G14, obtuvo G13, G14, G07); P56 (esperado G14, obtuvo G01, G14, G13); P57 (esperado G14, obtuvo H01, H02, G14); P58 (esperado G15, obtuvo G08, G07, G13); P59 (esperado G15, obtuvo G02, G15, G09); P61 (esperado G16, obtuvo G05, G16, G01); P62 (esperado G16, obtuvo G14, G16, G10); P66 (esperado G18, obtuvo G08, G18, G13)
**Denso** (43): Q03 (esperado G01, obtuvo G02, H01, G01); Q13 (esperado G04, obtuvo G11, G12, G03); Q16 (esperado G05, obtuvo G10, G11, G07); Q19 (esperado G07, obtuvo G05, G07, G10); Q22 (esperado H01, obtuvo H02, H01, H03); Q23 (esperado H01, obtuvo G02, H03, G07); Q29 (esperado G09, obtuvo G15, G09, G10); Q41 (esperado G13, obtuvo H03, G18, H02); Q43 (esperado G13, obtuvo H03, H02, H01); Q44 (esperado G14, obtuvo G08, G14, G17); Q45 (esperado G14, obtuvo G13, G10, H02); P04 (esperado G04, obtuvo G12, G07, G06); P06 (esperado G14, obtuvo G17, G08, G06); P07 (esperado G17, obtuvo G08, G17, G10); P08 (esperado G13, obtuvo G10, G16, G07); P10 (esperado G09, obtuvo G07, G11, G09); P17 (esperado G01, obtuvo H01, H02, G01); P18 (esperado G01, obtuvo G02, G01, H01); P20 (esperado G02, obtuvo H01, G01, G02); P25 (esperado G04, obtuvo G12, G07, G05); P26 (esperado G04, obtuvo G12, H03, G05); P27 (esperado G04, obtuvo G12, G15, G06); P29 (esperado G05, obtuvo H01, G16, G14); P32 (esperado G06, obtuvo G12, G06, G11); P33 (esperado G06, obtuvo G11, G12, H02); P34 (esperado G07, obtuvo G15, G06, G10); P37 (esperado G07, obtuvo G12, G05, H03); P40 (esperado G08, obtuvo G07, H03, G12); P41 (esperado G09, obtuvo G07, G06, G05); P42 (esperado G09, obtuvo G07, G15, G10); P43 (esperado G09, obtuvo G12, G09, G07); P44 (esperado G10, obtuvo G07, G10, G15); P45 (esperado G10, obtuvo G07, G02, G10); P47 (esperado G11, obtuvo G05, G07, G12); P51 (esperado G12, obtuvo H02, G12, G06); P53 (esperado G13, obtuvo G08, G07, H02); P54 (esperado G13, obtuvo G07, G06, G10); P55 (esperado G14, obtuvo H03, G07, G06); P57 (esperado G14, obtuvo G07, G14, G18); P58 (esperado G15, obtuvo G10, G06, G15); P59 (esperado G15, obtuvo G12, H03, G07); P64 (esperado G17, obtuvo G08, G03, G07); P68 (esperado G18, obtuvo G06, G07, G08)
**Híbrido (RRF)** (26): Q13 (esperado G04, obtuvo G11, G04); Q16 (esperado G05, obtuvo G09, G11, G05); Q23 (esperado H01, obtuvo H03, G02, H02); Q41 (esperado G13, obtuvo H01, G18, H02); Q43 (esperado G13, obtuvo H02, H01, G13); Q44 (esperado G14, obtuvo G08, G14, G07); Q45 (esperado G14, obtuvo G13, H02, H01); P07 (esperado G17, obtuvo G08, G17, G14); P08 (esperado G13, obtuvo G16, H01, G07); P12 (esperado G07, obtuvo G05, G07, G09); P18 (esperado G01, obtuvo G07, G02, G11); P20 (esperado G02, obtuvo G05, H01, G09); P25 (esperado G04, obtuvo G12, G04, G07); P26 (esperado G04, obtuvo H03, G07, G04); P33 (esperado G06, obtuvo G11, G09, G15); P34 (esperado G07, obtuvo G05, G07, G15); P40 (esperado G08, obtuvo G07, G14, G08); P41 (esperado G09, obtuvo G10, G05, G09); P42 (esperado G09, obtuvo G06, G14, G05); P53 (esperado G13, obtuvo G07, H01, G14); P54 (esperado G13, obtuvo G14, G07, G08); P55 (esperado G14, obtuvo G07, G10, H02); P56 (esperado G14, obtuvo G05, G10, G14); P59 (esperado G15, obtuvo H03, G15, H01); P61 (esperado G16, obtuvo G05, G16, G14); P68 (esperado G18, obtuvo G08, H01, G18)
**BM25 + preguntas** (15): Q11 (esperado G04, obtuvo H01, G04, G09); Q16 (esperado G05, obtuvo G11, G05, G09); Q29 (esperado G09, obtuvo G15, G09, G11); Q41 (esperado G13, obtuvo G14, H01, H02); Q45 (esperado G14, obtuvo G13, G14, H03); P07 (esperado G17, obtuvo G08, G17, G14); P08 (esperado G13, obtuvo G14, G13, H01); P10 (esperado G09, obtuvo G15, G09, G12); P12 (esperado G07, obtuvo G10, G07, G02); P20 (esperado G02, obtuvo G01, G02, G03); P48 (esperado G11, obtuvo G10, G11, G02); P55 (esperado G14, obtuvo G13, G14, G11); P59 (esperado G15, obtuvo G09, G15, G13); P62 (esperado G16, obtuvo G09, G16, G13); P66 (esperado G18, obtuvo G08, G14, G09)
**Denso + preguntas** (28): Q13 (esperado G04, obtuvo G11, G10, G12); Q19 (esperado G07, obtuvo G04, G02, G05); Q22 (esperado H01, obtuvo H02, H01, H03); Q23 (esperado H01, obtuvo G02, H03, G07); Q29 (esperado G09, obtuvo G15, G09, G10); Q32 (esperado G10, obtuvo G09, G10, G16); Q42 (esperado G13, obtuvo G08, G15, G18); Q43 (esperado G13, obtuvo G18, G13, H03); Q45 (esperado G14, obtuvo G13, G14, G09); Q46 (esperado G15, obtuvo G18, G15, G12); Q48 (esperado G16, obtuvo G08, G16, G13); Q49 (esperado G16, obtuvo G13, G16, G09); P04 (esperado G04, obtuvo G12, G15, G06); P07 (esperado G17, obtuvo G14, G08, G17); P10 (esperado G09, obtuvo G15, G10, G04); P12 (esperado G07, obtuvo G15, G07, G05); P20 (esperado G02, obtuvo G01, G02, H01); P26 (esperado G04, obtuvo G10, G04, G12); P32 (esperado G06, obtuvo G10, G06, G04); P37 (esperado G07, obtuvo G12, G15, G11); P40 (esperado G08, obtuvo G10, G17, G08); P41 (esperado G09, obtuvo G05, G15, G07); P42 (esperado G09, obtuvo G14, G13, G15); P47 (esperado G11, obtuvo G05, G12, G09); P54 (esperado G13, obtuvo G08, G07, G04); P62 (esperado G16, obtuvo G13, G18, G08); P66 (esperado G18, obtuvo G09, G18, G13); P68 (esperado G18, obtuvo G08, G07, G13)
**Híbrido + preguntas** (13): Q13 (esperado G04, obtuvo G11, G04, G06); Q19 (esperado G07, obtuvo G04, G07, G05); Q23 (esperado H01, obtuvo H03, G02, H02); Q29 (esperado G09, obtuvo G15, G09, G11); Q45 (esperado G14, obtuvo G13, G14, H03); P04 (esperado G04, obtuvo G12, G06, G09); P07 (esperado G17, obtuvo G08, G14, G17); P10 (esperado G09, obtuvo G15, G04, G05); P20 (esperado G02, obtuvo G01, G02, G03); P42 (esperado G09, obtuvo G14, G09, G06); P54 (esperado G13, obtuvo G07, G13, G04); P66 (esperado G18, obtuvo G09, G18, G13); P68 (esperado G18, obtuvo G08, G07, G09)
**Híbrido + preguntas (peso del denso 0.5)** (13): Q13 (esperado G04, obtuvo G11, G06, G04); Q23 (esperado H01, obtuvo H03, G02, H02); Q29 (esperado G09, obtuvo G15, G09, G11); Q45 (esperado G14, obtuvo G13, G14, H03); P02 (esperado G02, obtuvo G03, G02, H03); P04 (esperado G04, obtuvo G12, G04, G09); P07 (esperado G17, obtuvo G08, G17, G14); P10 (esperado G09, obtuvo G15, G09, G05); P20 (esperado G02, obtuvo G01, G02, G03); P42 (esperado G09, obtuvo G14, G09, G06); P54 (esperado G13, obtuvo G07, G13, G04); P66 (esperado G18, obtuvo G09, G18, G14); P68 (esperado G18, obtuvo G08, G07, G09)
**Híbrido + preguntas + reranker** (8): Q45 (esperado G14, obtuvo G13, G14, H01); P07 (esperado G17, obtuvo G08, G14, G17); P10 (esperado G09, obtuvo G15, G09, G05); P20 (esperado G02, obtuvo G01, G02, H01); P42 (esperado G09, obtuvo G14, G09, H01); P45 (esperado G10, obtuvo G02, G01, G11); P49 (esperado G11, obtuvo G04, G11, G10); P55 (esperado G14, obtuvo G07, G14, G13)

## Calibración de la abstención con BM25 (puntaje máximo)

- Preguntas con respuesta: mínimo 5.9, mediana 13.2.
- Preguntas sin respuesta en el corpus: máximo 13.3.

## Calibración de la abstención (similitud coseno máxima, con preguntas)

- Preguntas con respuesta: mínimo 0.49, mediana 0.74.
- Preguntas sin respuesta en el corpus: máximo 0.81.
- Ojo: con preguntas indexadas el coseno compara pregunta con pregunta y sube en general; los umbrales calibrados sin ellas no sirven, hay que volver a elegirlos con esta tabla.

### Reglas de abstención SIN modelo de lenguaje (denso ≥ u_d `y`/`o` BM25 ≥ u_b)

| Errores | Se abstiene sin deber | Responde sin deber | u_d | u_b | Operador |
| --- | --- | --- | --- | --- | --- |
| 15 | 1 | 14 | 0.75 | 7.0 | o |
| 15 | 1 | 14 | 0.7 | 7.0 | o |
| 16 | 2 | 14 | 0.8 | 7.0 | o |
| 17 | 4 | 13 | 0.5 | 7.0 | y |
| 17 | 3 | 14 | 0.45 | 7.0 | y |
| 17 | 3 | 14 | 0.4 | 7.0 | y |

Compuerta abierta (con modelo) que no deja fuera ninguna pregunta con respuesta: denso ≥ 0.65 o BM25 ≥ 7.0; deja pasar 17 de 30 sin respuesta, que debe rechazar el modelo (`RAG_UMBRAL_DENSO_LLM`, `RAG_UMBRAL_BM25_LLM`; comprobar con scripts/probar_abstencion.py).

Con 30 preguntas sin respuesta y 122 con respuesta, elegir un umbral sobre estos mismos datos lo ajusta a ellos: se reporta como calibración, no como garantía.

## Preguntas de evaluación parecidas a las indexadas

Similitud léxica (Jaccard de términos) ≥ 0.6 entre una pregunta de evaluación y una pregunta indexada. Si hay muchas, la mejora con preguntas está inflada: la evaluación mediría memoria y no generalización.

- 0 de 152.
