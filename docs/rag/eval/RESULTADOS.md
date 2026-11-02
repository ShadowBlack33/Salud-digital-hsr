# Resultados de la evaluación del RAG

Corpus: 21 documentos (18 guías, 3 historias de evaluación), 138 fragmentos. Preguntas con documento esperado: 69. Modelo denso: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.

## Todas las preguntas

| Método | Recall@1 | Recall@3 | MRR |
| --- | --- | --- | --- |
| BM25 | 0.90 | 0.96 | 0.93 |
| Denso | 0.77 | 0.87 | 0.83 |
| Híbrido (RRF, pesos iguales) | 0.86 | 0.94 | 0.90 |

## Preguntas literales (con las palabras de la guía): 54

| Método | Recall@1 | Recall@3 | MRR |
| --- | --- | --- | --- |
| BM25 | 0.94 | 1.00 | 0.97 |
| Denso | 0.80 | 0.89 | 0.85 |
| Híbrido (RRF, pesos iguales) | 0.87 | 0.94 | 0.91 |

## Preguntas parafraseadas (sin las palabras de la guía): 15

| Método | Recall@1 | Recall@3 | MRR |
| --- | --- | --- | --- |
| BM25 | 0.73 | 0.80 | 0.77 |
| Denso | 0.67 | 0.80 | 0.77 |
| Híbrido (RRF, pesos iguales) | 0.80 | 0.93 | 0.86 |

## Elección del peso del denso en la fusión

Las preguntas se reparten (una a una, dentro de cada tipo) en 35 de ajuste y 34 de prueba. El peso se elige con el MRR de las de **ajuste**; el resultado que se reporta es el de las de **prueba**, que no intervinieron en la elección.

| Peso del denso | MRR (ajuste) | MRR (prueba) | Recall@1 (prueba) |
| --- | --- | --- | --- |
| 1.0 ← | 0.89 | 0.92 | 0.88 |
| 0.75 | 0.88 | 0.92 | 0.88 |
| 0.5 | 0.88 | 0.93 | 0.91 |
| 0.35 | 0.88 | 0.93 | 0.91 |
| 0.25 | 0.88 | 0.93 | 0.91 |
| 0.15 | 0.88 | 0.91 | 0.88 |

En las de prueba: BM25 R@1 0.88 / MRR 0.92; denso R@1 0.79 / MRR 0.85.

Peso elegido: **1.0** (`RAG_PESO_DENSO` en `.env`; por defecto 1,0).

## Preguntas donde el primer documento no fue el esperado

**BM25:** Q08 (esperado G03, obtuvo G01, G03, G10); Q16 (esperado G05, obtuvo G09, G05, H01); Q45 (esperado G14, obtuvo G13, G14, H03); P01 (esperado G01, obtuvo G09, G03, G01); P07 (esperado G17, obtuvo G08, G14, H01); P08 (esperado G13, obtuvo G01, H01, H02); P12 (esperado G07, obtuvo G05, G11, G09)
**Denso:** Q03 (esperado G01, obtuvo G02, H01, G01); Q13 (esperado G04, obtuvo G11, G12, G03); Q16 (esperado G05, obtuvo G10, G11, G07); Q19 (esperado G07, obtuvo G05, G07, G10); Q22 (esperado H01, obtuvo H02, H01, H03); Q23 (esperado H01, obtuvo G02, H03, G07); Q29 (esperado G09, obtuvo G15, G09, G10); Q41 (esperado G13, obtuvo H03, G18, H02); Q43 (esperado G13, obtuvo H03, H02, H01); Q44 (esperado G14, obtuvo G08, G14, G17); Q45 (esperado G14, obtuvo G13, G10, H02); P04 (esperado G04, obtuvo G12, G07, G06); P06 (esperado G14, obtuvo G17, G08, G06); P07 (esperado G17, obtuvo G08, G17, G10); P08 (esperado G13, obtuvo G10, G16, G07); P10 (esperado G09, obtuvo G07, G11, G09)
**Híbrido (RRF, pesos iguales):** Q13 (esperado G04, obtuvo G11, G04, G12); Q16 (esperado G05, obtuvo G09, G11, G15); Q23 (esperado H01, obtuvo H03, G02, H02); Q41 (esperado G13, obtuvo H01, H02, G13); Q43 (esperado G13, obtuvo H02, H01, G07); Q44 (esperado G14, obtuvo G08, G14, G12); Q45 (esperado G14, obtuvo G13, H02, G14); P07 (esperado G17, obtuvo G08, G14, G17); P08 (esperado G13, obtuvo G01, G10, H01); P12 (esperado G07, obtuvo G05, G07, G09)

## Calibración de la abstención con BM25 (puntaje máximo)

- Preguntas con respuesta: mínimo 4.1, mediana 13.9.
- Preguntas sin respuesta en el corpus: máximo 8.0.
- El umbral `RAG_UMBRAL_BM25` debe quedar entre esos dos valores.

## Calibración de la abstención (similitud coseno máxima)

- Preguntas con respuesta: mínimo 0.26, mediana 0.67.
- Preguntas sin respuesta en el corpus: máximo 0.61.
- El umbral `RAG_UMBRAL_DENSO` debe quedar entre esos dos valores.

## Abstención del híbrido (denso ≥ 0.45 y BM25 ≥ 5.0)

- Preguntas con respuesta que se abstendrían por error: P01, P02, P06, P08.
- Preguntas sin respuesta que se responderían por error: N07, N08, N13, N15.

### Preguntas mal clasificadas (coseno máximo, BM25 máximo)

| Pregunta | Debería | Coseno | BM25 |
| --- | --- | --- | --- |
| P01 | responder | 0.63 | 4.1 |
| P02 | responder | 0.59 | 4.8 |
| P06 | responder | 0.26 | 4.9 |
| P08 | responder | 0.62 | 4.8 |
| N07 | abstenerse | 0.51 | 5.6 |
| N08 | abstenerse | 0.61 | 5.8 |
| N13 | abstenerse | 0.54 | 6.4 |
| N15 | abstenerse | 0.51 | 5.6 |

Preguntas sin respuesta (15), mayor coseno / mayor BM25: N08 0.61/5.8; N02 0.57/4.0; N09 0.55/4.7; N13 0.54/6.4; N05 0.52/4.5.

### Mejores reglas de abstención probadas (denso ≥ u_d `y`/`o` BM25 ≥ u_b)

| Errores | Se abstiene sin deber | Responde sin deber | u_d | u_b | Operador |
| --- | --- | --- | --- | --- | --- |
| 6 | 3 | 3 | 0.6 | 6.0 | o |
| 6 | 1 | 5 | 0.55 | 6.0 | o |
| 6 | 0 | 6 | 0.6 | 4.5 | o |
| 7 | 6 | 1 | 0.45 | 6.0 | y |
| 7 | 2 | 5 | 0.6 | 5.5 | o |
| 7 | 2 | 5 | 0.6 | 5.0 | o |

Con 15 preguntas sin respuesta y 69 con respuesta, elegir un umbral sobre estos mismos datos lo ajusta a ellos: se reporta como calibración, no como garantía.
