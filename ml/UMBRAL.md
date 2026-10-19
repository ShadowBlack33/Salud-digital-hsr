# Umbral crítico del modelo de riesgo de UCI posoperatoria (R20, R22)

> Números de `ml/modelo/metricas.json`, versión **`vitaldb-1`**, entrenada con **datos reales**
> de VitalDB (ver `docs/DATASETS.md`). Para revisar con Juan José, sobre todo el análisis de sesgo.

## Qué predice el modelo

La probabilidad de que un paciente quirúrgico **pase al menos un día en UCI después de la
cirugía** (en VitalDB: `icu_days > 0`). El servicio `ml` responde
`critico = probabilidad >= umbral`, y un caso crítico crea una alerta activa para el clínico
que pidió el análisis (R20).

| | |
|---|---|
| Datos | VitalDB `clinical_data.csv` (PhysioNet, CC BY 4.0): **6.331 cirugías de adultos de 6.048 pacientes**, solo casos reales. Los sintéticos por cluster (R07) no entran ni al entrenamiento ni a las métricas |
| Desenlace | 18,6 % de las cirugías terminaron con estancia en UCI |
| Partición | 75 % entrenamiento (4.735) / 25 % prueba (1.596), **separada por paciente** (`subjectid`): un paciente con varias cirugías nunca queda en los dos lados |
| Modelo | Regresión logística (`class_weight="balanced"`), con imputación por mediana y estandarización |
| Variables | edad, sexo, glucosa (`preop_gluc`, mg/dL), potasio (`preop_k`, mmol/L), hemoglobina (`preop_hb`, g/dL) |
| Variables derivadas | distancia de la glucosa a 100 mg/dL y del potasio a 4,2 mmol/L (riesgo en "U": peligrosos bajos y altos) |
| Faltantes | glucosa 5,9 %, potasio 9,7 %, hemoglobina 5,3 %: se imputan con la mediana del entrenamiento |

## Umbral elegido: **0,40**

### Criterio

En una alerta clínica, **un falso negativo cuesta más que un falso positivo**:

- **Falso negativo:** un paciente que va a necesitar UCI sale sin alerta; no se reserva la
  cama y la complicación se descubre en recuperación, cuando la UCI puede estar llena.
- **Falso positivo:** un clínico revisa un caso que no lo necesitaba y rechaza el reporte (R10).

Por eso el umbral no es el 0,5 por defecto: `entrenar.py` exige **sensibilidad ≥ 0,80** y, entre
los umbrales que la cumplen, toma el de **mayor especificidad**.

### Tabla de umbrales (conjunto de prueba, 1.596 cirugías, 276 con UCI)

| Umbral | Sensibilidad | Especificidad |
|---|---|---|
| 0,30 | 0,931 | 0,258 |
| 0,35 | 0,895 | 0,367 |
| **0,40** | **0,801** | **0,474** |
| 0,45 | 0,728 | 0,575 |
| 0,50 | 0,638 | 0,664 |

Con 0,40 el modelo avisa de 221 de los 276 pacientes que sí necesitaron UCI y se le escapan 55.
Con 0,50 se le escaparían 100. El costo: alrededor de 3 de cada 4 alertas son falsas positivas
(VPP 0,24), que el clínico revisa y rechaza.

### Métricas globales con 0,40

| AUC | Sensibilidad | Especificidad | VPP | VP / FP / FN / VN |
|---|---|---|---|---|
| **0,707** | 0,801 | 0,474 | 0,242 | 221 / 694 / 55 / 626 |

**Lectura honesta:** un AUC de 0,71 es una discriminación moderada. Es esperable con solo cinco
variables de laboratorio y demografía: el modelo sirve como **alerta temprana para revisar**,
no para decidir solo. Por eso el reporte nunca entra a la historia sin la aprobación de un
clínico (R10).

## Análisis de sesgo por subgrupo (R22)

| Subgrupo | Cirugías | Con UCI | Sensibilidad | Especificidad | AUC |
|---|---|---|---|---|---|
| Mujeres | 792 | 94 | **0,585** | 0,613 | 0,668 |
| Hombres | 804 | 182 | 0,912 | 0,318 | 0,692 |
| Edad < 40 | 185 | 18 | 0,500 | 0,928 | 0,746 |
| Edad 40–64 | 887 | 115 | 0,678 | 0,574 | 0,681 |
| Edad ≥ 65 | 524 | 143 | 0,937 | **0,073** | 0,623 |

**Hallazgos:**

1. **Sesgo por sexo, el más importante.** En mujeres el modelo detecta solo el 58,5 % de las que
   terminan en UCI, frente al 91,2 % en hombres. En VitalDB los hombres van a UCI con más
   frecuencia (23 % frente a 12 % en la prueba) y el modelo aprendió el sexo como factor de
   riesgo: con un umbral único, las mujeres quedan subprotegidas.
2. **Fatiga de alertas en mayores de 65.** Casi todos salen críticos (especificidad 0,073): el
   modelo pesa mucho la edad y, en el grupo con más cirugías, alerta incluso con laboratorios
   normales.
3. **Menores de 65 subdetectados.** La sensibilidad baja de 0,80 (0,50 y 0,68).

**Correcciones posibles** (ninguna aplicada todavía, para no cambiar el sistema antes de la
sustentación):

- **Umbrales por subgrupo** (por sexo o por rango de edad), elegidos con el mismo criterio de
  sensibilidad ≥ 0,80 en cada grupo.
- **Más variables.** Probado con los mismos datos y la misma partición: agregar **ASA** sube el
  AUC a 0,737, y ASA + urgencia a 0,742. El hospital ya guarda el ASA del paciente
  (`pacientes.riesgo_asa`), así que es la mejora siguiente. Implica actualizar la lista
  permitida de `app/services/seudonimizacion.py`.
- Evaluar si el sesgo por sexo viene de los datos (práctica del hospital coreano) o del modelo,
  antes de corregirlo con umbrales.

## Valores que garantizan el disparo (`paciente_critico` del `tester.yaml`)

| Variable | Valor | LOINC | Por qué es crítico |
|---|---|---|---|
| Edad | 78 años | — | Edad avanzada |
| Sexo | F | — | — |
| Glucosa | 42 mg/dL | 2339-0 | Hipoglucemia severa (< 54 mg/dL) |
| Potasio | 6,6 mmol/L | 2823-3 | Hiperpotasemia (> 6,0 mmol/L) |
| Hemoglobina | 6,8 g/dL | 718-7 | Anemia severa (< 7 g/dL) |

Con `vitaldb-1` dan **probabilidad 0,830** frente al umbral 0,40. Un paciente de 35 años con
valores normales (glucosa 95, potasio 4,1, hemoglobina 14) da 0,274. `entrenar.py` lo comprueba
al final de cada entrenamiento.

## Reglas de seguridad del servicio

- **Sin laboratorios no hay predicción.** Si el paciente no tiene glucosa, potasio ni
  hemoglobina, el análisis se rechaza (422): con todo imputado el modelo estaría inventando el
  riesgo.
- **Lista permitida (R12).** El modelo rechaza (422) cualquier variable que no esté en su lista,
  por ejemplo `nombre`, sin devolver el valor recibido.

## Cómo se reproduce

    Invoke-WebRequest https://physionet.org/files/vitaldb/1.0.0/clinical_data.csv -OutFile ml\datos\clinical_data.csv
    docker compose run --rm -v "${PWD}\ml:/srv" ml python entrenar.py

Imprime la tabla de umbrales, regenera `modelo/modelo.joblib` y `modelo/metricas.json`, y
comprueba `paciente_critico`.

Cita de los datos: Lee H., Jung C. (2022). *VitalDB, a high-fidelity multi-parameter vital signs
database in surgical patients* (v1.0.0). PhysioNet. https://doi.org/10.13026/czw8-9p62
