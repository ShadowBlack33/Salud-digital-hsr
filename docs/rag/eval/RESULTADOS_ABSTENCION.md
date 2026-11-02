# Abstención con modelo de lenguaje

Compuerta abierta (denso ≥ 0.35 o BM25 ≥ 4.0); decide el modelo.

- Preguntas sin respuesta que terminan en abstención: **15 de 15**.
- Preguntas parafraseadas respondidas citando la guía esperada: **11 de 15**.

- Llamadas al modelo que fallaron y pasaron al otro modelo (tiempo agotado, 503): 0.

| Pregunta | Esperado | Resultado | Quién decidió | Citó | ¿Bien? |
| --- | --- | --- | --- | --- | --- |
| P01 | G01 | responde | gemini:gemini-3.5-flash-lite | G01 | sí |
| P02 | G02 | responde | gemini:gemini-3.5-flash-lite | G02 | sí |
| P03 | G03 | responde | gemini:gemini-3.5-flash-lite | G03 | sí |
| P04 | G04 | abstiene | gemini:gemini-3.5-flash-lite | - | NO |
| P05 | G12 | abstiene | gemini:gemini-3.5-flash-lite | - | NO |
| P06 | G14 | responde | gemini:gemini-3.5-flash-lite | G14 | sí |
| P07 | G17 | responde | gemini:gemini-3.5-flash-lite | G08, G17 | sí |
| P08 | G13 | responde | gemini:gemini-3.5-flash-lite | G18 | NO |
| P09 | G11 | responde | gemini:gemini-3.5-flash-lite | G11 | sí |
| P10 | G09 | responde | gemini:gemini-3.5-flash-lite | G09 | sí |
| P11 | G06 | responde | gemini:gemini-3.5-flash-lite | G06 | sí |
| P12 | G07 | abstiene | gemini:gemini-3.5-flash-lite | - | NO |
| P13 | G16 | responde | gemini:gemini-3.5-flash-lite | G16 | sí |
| P14 | G18 | responde | gemini:gemini-3.5-flash-lite | G18 | sí |
| P15 | G07 | responde | gemini:gemini-3.5-flash-lite | G07 | sí |
| N01 | - | abstiene | recuperación | - | sí |
| N02 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N03 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N04 | - | abstiene | recuperación | - | sí |
| N05 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N06 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N07 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N08 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N09 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N10 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N11 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N12 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N13 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N14 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
| N15 | - | abstiene | gemini:gemini-3.5-flash-lite | - | sí |
