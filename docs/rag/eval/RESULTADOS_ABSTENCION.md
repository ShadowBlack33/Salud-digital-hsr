# Abstención con modelo de lenguaje

Compuerta abierta (denso ≥ 0.65 o BM25 ≥ 7.0); decide el modelo. Preguntas por sección: sí; reranker: sí; temperatura: la del proveedor.

- Preguntas sin respuesta que terminan en abstención: **30 de 30**.
- Preguntas parafraseadas respondidas citando la guía esperada: **66 de 68**.

- Parafraseadas que decidió el modelo: 66 de 68 bien.
- Preguntas que quedaron sin modelo (cuota agotada o tiempo agotado): 0.
- Llamadas al modelo que fallaron en esta corrida (429, 503, tiempo agotado): 2.

| Pregunta | Esperado | Resultado | Quién decidió | Citó | ¿Bien? |
| --- | --- | --- | --- | --- | --- |
| P01 | G01 | responde | gemini:gemini-3.5-flash-lite | G01 | sí |
| P02 | G02 | responde | gemini:gemini-3.5-flash-lite | G02 | sí |
| P03 | G03 | responde | gemini:gemini-3.5-flash-lite | G03 | sí |
| P04 | G04 | responde | gemini:gemini-3.5-flash-lite | G04 | sí |
| P05 | G12 | responde | gemini:gemini-3.5-flash-lite | G12 | sí |
| P06 | G14 | responde | gemini:gemini-3.5-flash-lite | G14 | sí |
| P07 | G17 | responde | gemini:gemini-3.5-flash-lite | G08 | NO |
| P08 | G13 | responde | gemini:gemini-3.5-flash-lite | G13 | sí |
| P09 | G11 | responde | gemini:gemini-3.5-flash-lite | G11 | sí |
| P10 | G09 | responde | gemini:gemini-3.5-flash-lite | G09 | sí |
| P11 | G06 | responde | gemini:gemini-3.5-flash-lite | G06 | sí |
| P12 | G07 | responde | gemini:gemini-3.5-flash-lite | G05, G07 | sí |
| P13 | G16 | responde | gemini:gemini-3.5-flash-lite | G16 | sí |
| P14 | G18 | responde | gemini:gemini-3.5-flash-lite | G08, G18 | sí |
| P15 | G07 | responde | gemini:gemini-3.5-flash-lite | G07 | sí |
| P16 | G01 | responde | gemini:gemini-3.5-flash-lite | G01 | sí |
| P17 | G01 | responde | gemini:gemini-3.5-flash-lite | G01 | sí |
| P18 | G01 | responde | gemini:gemini-3.5-flash-lite | G01 | sí |
| P19 | G02 | responde | gemini:gemini-3.5-flash-lite | G02 | sí |
| P20 | G02 | responde | gemini:gemini-3.5-flash-lite | G02 | sí |
| P21 | G02 | responde | gemini:gemini-3.5-flash-lite | G02 | sí |
| P22 | G03 | responde | gemini:gemini-3.5-flash-lite | G03 | sí |
| P23 | G03 | responde | gemini:gemini-3.5-flash-lite | G03 | sí |
| P24 | G03 | responde | gemini:gemini-3.5-flash-lite | G03 | sí |
| P25 | G04 | responde | gemini:gemini-3.5-flash-lite | G04 | sí |
| P26 | G04 | responde | gemini:gemini-3.5-flash-lite | G04 | sí |
| P27 | G04 | responde | gemini:gemini-3.5-flash-lite | G04 | sí |
| P28 | G05 | responde | gemini:gemini-3.5-flash-lite | G05 | sí |
| P29 | G05 | responde | gemini:gemini-3.5-flash-lite | G05 | sí |
| P30 | G05 | responde | gemini:gemini-3.5-flash-lite | G05 | sí |
| P31 | G06 | responde | gemini:gemini-3.5-flash-lite | G06 | sí |
| P32 | G06 | responde | gemini:gemini-3.5-flash-lite | G06 | sí |
| P33 | G06 | responde | gemini:gemini-3.5-flash-lite | G06 | sí |
| P34 | G07 | responde | gemini:gemini-3.5-flash-lite | G07 | sí |
| P35 | G07 | responde | gemini:gemini-3.5-flash-lite | G07 | sí |
| P36 | G07 | responde | gemini:gemini-3.5-flash-lite | G07 | sí |
| P37 | G07 | responde | gemini:gemini-3.5-flash-lite | G07 | sí |
| P38 | G08 | responde | gemini:gemini-3.5-flash-lite | G08 | sí |
| P39 | G08 | responde | gemini:gemini-3.5-flash-lite | G07, G08 | sí |
| P40 | G08 | responde | gemini:gemini-3.5-flash-lite | G08 | sí |
| P41 | G09 | responde | gemini:gemini-3.5-flash-lite | G09 | sí |
| P42 | G09 | responde | gemini:gemini-3.5-flash-lite | G09 | sí |
| P43 | G09 | responde | gemini:gemini-3.5-flash-lite | G09 | sí |
| P44 | G10 | responde | gemini:gemini-3.5-flash-lite | G10 | sí |
| P45 | G10 | abstiene | gemini:gemini-3.5-flash-lite | - | NO |
| P46 | G10 | responde | gemini:gemini-3.5-flash-lite | G10 | sí |
| P47 | G11 | responde | gemini:gemini-3.5-flash-lite | G11 | sí |
| P48 | G11 | responde | gemini:gemini-3.5-flash-lite | G11 | sí |
| P49 | G11 | responde | gemini:gemini-3.5-flash-lite | G11 | sí |
| P50 | G12 | responde | gemini:gemini-3.5-flash-lite | G12 | sí |
| P51 | G12 | responde | gemini:gemini-3.5-flash-lite | G12 | sí |
| P52 | G12 | responde | gemini:gemini-3.5-flash-lite | G12 | sí |
| P53 | G13 | responde | gemini:gemini-3.5-flash-lite | G13 | sí |
| P54 | G13 | responde | gemini:gemini-3.5-flash-lite | G13 | sí |
| P55 | G14 | responde | gemini:gemini-3.5-flash-lite | G14 | sí |
| P56 | G14 | responde | gemini:gemini-3.5-flash-lite | G14 | sí |
| P57 | G14 | responde | gemini:gemini-3.5-flash-lite | G14 | sí |
| P58 | G15 | responde | gemini:gemini-3.5-flash-lite | G15 | sí |
| P59 | G15 | responde | gemini:gemini-3.5-flash-lite | G15 | sí |
| P60 | G16 | responde | gemini:gemini-3.5-flash-lite | G16 | sí |
| P61 | G16 | responde | gemini:gemini-3.5-flash-lite | G16 | sí |
| P62 | G16 | responde | gemini:gemini-3.5-flash-lite | G16 | sí |
| P63 | G17 | responde | gemini:gemini-3.5-flash-lite | G17 | sí |
| P64 | G17 | responde | gemini:gemini-3.5-flash-lite | G08, G17 | sí |
| P65 | G17 | responde | gemini:gemini-3.5-flash-lite | G17 | sí |
| P66 | G18 | responde | gemini:gemini-3.5-flash-lite | G18 | sí |
| P67 | G18 | responde | gemini:gemini-3.5-flash-lite | G18 | sí |
| P68 | G18 | responde | gemini:gemini-3.5-flash-lite | G18 | sí |
| N01 | - | abstiene | recuperación | - | sí |
| N02 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N03 | - | abstiene | recuperación | - | sí |
| N04 | - | abstiene | recuperación | - | sí |
| N05 | - | abstiene | recuperación | - | sí |
| N06 | - | abstiene | recuperación | - | sí |
| N07 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N08 | - | abstiene | recuperación | - | sí |
| N09 | - | abstiene | recuperación | - | sí |
| N10 | - | abstiene | recuperación | - | sí |
| N11 | - | abstiene | recuperación | - | sí |
| N12 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N13 | - | abstiene | recuperación | - | sí |
| N14 | - | abstiene | recuperación | - | sí |
| N15 | - | abstiene | recuperación | - | sí |
| N16 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N17 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N18 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N19 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N20 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N21 | - | abstiene | recuperación | - | sí |
| N22 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N23 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N24 | - | abstiene | recuperación | - | sí |
| N25 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N26 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N27 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N28 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N29 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N30 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
