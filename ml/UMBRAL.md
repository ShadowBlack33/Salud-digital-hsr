# Umbral crítico del modelo de riesgo de UCI posoperatoria (R20, R22)

> **Borrador para revisar con Juan José.** Los números salen de `ml/modelo/metricas.json`
> (versión `provisional-0`). El modelo se entrenó con **datos sintéticos** mientras se
> define el dataset tabular real (R07): las métricas muestran cómo funciona el pipeline
> y cómo se eligió el umbral, **no tienen valor clínico**. Al reentrenar con el dataset
> real, `entrenar.py` vuelve a elegir el umbral con el mismo criterio y este documento
> se actualiza con los números nuevos.

## Qué predice el modelo

La probabilidad de que un paciente quirúrgico **necesite cama de UCI en el posoperatorio**.
Con esa probabilidad, el servicio `ml` responde `critico = probabilidad >= umbral`. Un caso
crítico crea una alerta activa para el clínico que pidió el análisis (R20).

| | |
|---|---|
| Modelo | Regresión logística (`class_weight="balanced"`), con imputación por mediana y estandarización |
| Variables | edad, sexo, glucosa (mg/dL), potasio (mmol/L), hemoglobina (g/dL) |
| Variables derivadas | distancia de la glucosa a 100 mg/dL y del potasio a 4,2 mmol/L: los dos son peligrosos tanto bajos como altos (riesgo en "U") |
| Partición | 75 % entrenamiento / 25 % prueba, estratificada por la clase (750 pacientes de prueba, 133 con UCI) |

## Umbral elegido: **0,30**

### Criterio

En una alerta clínica, **un falso negativo cuesta más que un falso positivo**:

- **Falso negativo:** un paciente que va a necesitar UCI sale sin alerta. No se reserva la
  cama, y la complicación se descubre en recuperación, cuando la UCI puede estar llena.
- **Falso positivo:** un clínico revisa un caso que no lo necesitaba. Le cuesta unos
  minutos, y siempre puede rechazar el reporte (R10).

Por eso el umbral **no** es el 0,5 por defecto. `entrenar.py` exige **sensibilidad ≥ 0,80**
y, entre los umbrales que la cumplen, toma el de **mayor especificidad**.

### Tabla de umbrales (conjunto de prueba)

| Umbral | Sensibilidad | Especificidad | VPP | Falsos negativos | Falsos positivos |
|---|---|---|---|---|---|
| 0,20 | 0,962 | 0,368 | 0,247 | 5 | 390 |
| 0,25 | 0,902 | 0,446 | 0,260 | 13 | 342 |
| **0,30** | **0,872** | **0,528** | **0,285** | **17** | **291** |
| 0,35 | 0,797 | 0,585 | 0,293 | 27 | 256 |
| 0,40 | 0,752 | 0,647 | 0,314 | 33 | 218 |
| 0,50 | 0,654 | 0,757 | 0,367 | 46 | 150 |

Con 0,30, de cada 133 pacientes que sí necesitaron UCI el modelo avisa de 116 y se le
escapan 17. Con 0,50 se le escaparían 46. El costo es que alrededor de 7 de cada 10
alertas son falsas positivas (VPP 0,285): el clínico las revisa y las rechaza.

### Métricas globales con 0,30

| Sensibilidad | Especificidad | VPP | AUC | Matriz (VP / FP / FN / VN) |
|---|---|---|---|---|
| 0,872 | 0,528 | 0,285 | 0,795 | 116 / 291 / 17 / 326 |

## Análisis de sesgo por subgrupo (R22)

| Subgrupo | Pacientes | Con UCI | Sensibilidad | Especificidad | AUC |
|---|---|---|---|---|---|
| Sexo F (0) | 388 | 69 | 0,899 | 0,508 | 0,786 |
| Sexo M (1) | 362 | 64 | 0,844 | 0,550 | 0,807 |
| Edad < 40 | 213 | 13 | 0,769 | 0,850 | 0,850 |
| Edad 40–64 | 270 | 46 | 0,783 | 0,571 | 0,751 |
| Edad ≥ 65 | 267 | 74 | 0,946 | **0,145** | 0,736 |

**Lectura:**

- **Por sexo** el comportamiento es parecido (diferencia de sensibilidad de 0,055).
- **Por edad** hay un sesgo claro:
  - En **≥ 65 años** casi todos salen críticos (especificidad 0,145). El modelo usa la
    edad como factor de riesgo, así que en este grupo dispara alertas incluso con
    laboratorios normales. Riesgo práctico: **fatiga de alertas** en el grupo con más
    cirugías.
  - En **< 40 y 40–64 años** la sensibilidad baja de 0,80 (0,769 y 0,783): se escapan
    más casos que en los mayores.
- **Posibles correcciones**, a decidir con el dataset real:
  - umbrales distintos por rango de edad;
  - más variables clínicas (por ejemplo ASA, tipo de cirugía) para que la edad no domine;
  - revisar si el sesgo está en los datos o en el modelo.

En los datos sintéticos el sesgo está puesto a propósito por la regla que los generó;
lo importante es que el pipeline lo **detecta y lo reporta**.

## Valores que garantizan el disparo (`paciente_critico` del `tester.yaml`)

| Variable | Valor | LOINC | Por qué es crítico |
|---|---|---|---|
| Edad | 78 años | — | Edad avanzada |
| Sexo | F | — | (no aporta al disparo) |
| Glucosa | 42 mg/dL | 2339-0 | Hipoglucemia severa (< 54 mg/dL) |
| Potasio | 6,6 mmol/L | 2823-3 | Hiperpotasemia (> 6,0 mmol/L) |
| Hemoglobina | 6,8 g/dL | 718-7 | Anemia severa (< 7 g/dL) |

Con el modelo `provisional-0` estos valores dan **probabilidad 0,999** frente al umbral
0,30. Un paciente de 35 años con valores normales (glucosa 95, potasio 4,1, hemoglobina 14)
da 0,035.

## Reglas de seguridad del servicio

- **Sin laboratorios no hay predicción.** Si el paciente no tiene glucosa, potasio ni
  hemoglobina, el análisis se rechaza (422). Con todo imputado por la mediana, la
  probabilidad sería ~0,31, por encima del umbral: el sistema estaría inventando alertas.
- **Lista permitida (R12).** El modelo rechaza (422) cualquier variable que no esté en su
  lista, por ejemplo `nombre`, sin devolver el valor recibido.

## Cómo se reproduce

    docker compose run --rm -v "${PWD}\ml:/srv" ml python entrenar.py

Imprime la tabla de umbrales y regenera `modelo/modelo.joblib` y `modelo/metricas.json`.
