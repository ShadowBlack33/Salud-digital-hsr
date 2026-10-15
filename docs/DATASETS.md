# Datasets del proyecto (R06, R07)

Pulso trabaja sobre un caso hipotético (Hospital San Rafael), pero dos de sus
componentes usan **datos reales de acceso abierto**, para que no todo sea
inventado: las radiografías de tórax (imagen) y los casos quirúrgicos de
VitalDB (tabular). Todo lo demás (pacientes, camas, cirugías, tarifas) es
sintético y está declarado como tal.

> Los campos marcados **[COMPLETAR]** dependen de lo que quedó cargado en el
> equipo que hace la demostración. Se llenan una sola vez, con los comandos
> que aparecen en cada sección.

---

## Imagen

### Ficha

| | |
|---|---|
| **Nombre** | NIH ChestX-ray14 (también llamado ChestX-ray8 en su artículo original) |
| **Proveedor** | NIH Clinical Center (Estados Unidos) |
| **URL oficial** | https://nihcc.app.box.com/v/ChestXray-NIHCC |
| **Contenido completo** | 112.120 radiografías de tórax en proyección frontal, de 30.805 pacientes distintos, con 14 hallazgos etiquetados (atelectasia, cardiomegalia, derrame pleural, infiltrado, masa, nódulo, neumonía, neumotórax, consolidación, edema, enfisema, fibrosis, engrosamiento pleural y hernia) más la categoría "sin hallazgo" |
| **Cómo se etiquetó** | Las etiquetas se extrajeron automáticamente de los informes radiológicos (minería de texto); no las revisó un radiólogo imagen por imagen. Los autores estiman una exactitud de etiquetas superior al 90 % |
| **Licencia / condiciones de uso** | El NIH publica el conjunto sin restricciones de uso. Pide tres cosas: enlazar a su sitio de descarga, citar el artículo de abajo y reconocer al NIH Clinical Center como proveedor. Los informes radiológicos originales no son públicos |
| **Cita** | Wang X., Peng Y., Lu L., Lu Z., Bagheri M., Summers R. *ChestX-ray8: Hospital-scale chest X-ray database and benchmarks on weakly-supervised classification and localization of common thorax diseases.* CVPR 2017. DOI 10.1109/CVPR.2017.369 |

### Qué se cargó en Pulso

- **Cantidad cargada: [COMPLETAR] imágenes** (el valor por defecto del script
  son 24, de una muestra pública de unos 10 MB).
- Origen de la muestra: el repositorio `jrzech/reproduce-chexnet`, que
  redistribuye imágenes del dataset con sus etiquetas. Con `--carpeta` y
  `--etiquetas` se puede cargar un volumen mayor desde la descarga oficial
  (`Data_Entry_2017.csv` y las carpetas `images_00X`).
- Cada imagen se sube al PACS (Orthanc) como un estudio DICOM de modalidad DX,
  asignada a un paciente sintético del mismo sexo y, en lo posible, de la misma
  década de edad. La descripción del estudio lleva el hallazgo del dataset.
  El `PatientID` de DICOM es el índice ciego del paciente, nunca la cédula.
- Es seguro repetirlo: si el paciente ya tiene esa radiografía, se la salta.

Comandos:

```bash
# Automático: el contenedor `jornada` carga la muestra pública (24 imágenes)
# la primera vez que se levanta el sistema (CARGAR_RADIOGRAFIAS=false lo omite).
# Para repetirlo a mano:
docker compose run --rm jornada

# Solo las radiografías, con otra cantidad (desde Docker)
docker compose run --rm --entrypoint python jornada scripts/cargar_radiografias.py --cantidad 60

# Más volumen, desde la descarga oficial (en el equipo, con el .env apuntando a localhost)
python scripts/cargar_radiografias.py --cantidad 200 \
  --carpeta D:/nih/images --etiquetas D:/nih/Data_Entry_2017.csv

# Ver la asignación sin subir nada
python scripts/cargar_radiografias.py --simular
```

Para saber cuántas quedaron en el PACS (la clave es `ORTHANC_PASSWORD` del `.env`):

```powershell
curl.exe -s -u api:TU_CLAVE http://127.0.0.1:8042/statistics
```

El campo `CountStudies` es la cantidad de estudios y `CountInstances` la de
imágenes: ese es el número que va en **[COMPLETAR]**.

### Por qué responde al problema

El problema de partida es la cancelación de cirugías por falta de
coordinación. La radiografía de tórax preoperatoria forma parte de la
valoración de riesgo quirúrgico y anestésico, así que aparece en el recorrido
del paciente antes de entrar a quirófano: la ficha del paciente muestra su
radiografía y solo la ve quien puede ver a ese paciente.

### Limitaciones (declaradas)

- **No es un problema de capacidad quirúrgica.** ChestX-ray14 sirve para
  probar el flujo de imágenes (PACS, permisos, visor), no para predecir
  cancelaciones.
- Las radiografías son de una cohorte externa (NIH), asignadas a pacientes
  sintéticos. En pantalla se rotulan como **"imagen ilustrativa, cohorte
  externa NIH"**, nunca como "examen del hospital".
- Las etiquetas salen de minería de texto y no están validadas por
  radiólogos: no se usan para diagnosticar.

---

## Tabular

### Ficha

| | |
|---|---|
| **Nombre** | VitalDB: base de signos vitales de alta fidelidad en pacientes quirúrgicos (v1.0.0, PhysioNet) |
| **Proveedor** | Seoul National University Hospital (Corea del Sur). Autores: Hyung-Chul Lee y Chul-Woo Jung |
| **URL** | https://physionet.org/content/vitaldb/1.0.0/ · portal del proyecto: https://vitaldb.net |
| **DOI** | 10.13026/czw8-9p62 |
| **Contenido** | 6.388 casos quirúrgicos (de 7.051 elegibles, tras excluir los que no cumplían los criterios) con datos intraoperatorios, clínicos y de laboratorio |
| **Archivo que usamos** | `clinical_data.csv` (≈ 2,1 MB, una fila por caso, 71 parámetros) |
| **Licencia** | Creative Commons Attribution 4.0 (CC BY 4.0), acceso abierto en PhysioNet. Exige atribución |
| **Cita** | Lee H., Jung C. (2022). *VitalDB, a high-fidelity multi-parameter vital signs database in surgical patients* (v1.0.0). PhysioNet. https://doi.org/10.13026/czw8-9p62 · Artículo: Lee H.C. et al., *Scientific Data* 9, 279 (2022). https://doi.org/10.1038/s41597-022-01411-5 |

Variables del archivo que importan aquí: demografía (`age`, `sex`, `height`,
`weight`, `bmi`), perfil quirúrgico (`asa`, `emop`, `department`, `optype`,
`approach`, `ane_type`), comorbilidades (`preop_htn`, `preop_dm`,
`preop_arrhythmia`, `preop_pft`), laboratorio preoperatorio (`preop_hb`,
`preop_cr`, `preop_alb`, `preop_gluc`, entre otros) y resultados (`opdur`,
`los_icu`, `los_postop`, `death_inhosp`).

### Qué se cargó en Pulso

| Conjunto | Filas |
|---|---|
| Casos reales de VitalDB usados | **[COMPLETAR]** |
| Pacientes sintéticos generados por clusters (`origen = sintetico`) | **[COMPLETAR]** |
| Número de clusters elegido | **[COMPLETAR]** (justificado en `docs/INFORME_CLUSTERS.md`) |

Esos tres números los imprime `scripts/clusters_vitaldb.py` al terminar, y los
sirve el endpoint `GET /analitica/clusters` (campos `n_reales` y
`n_sinteticos` por cluster).

Cómo se construye (detalle y métricas en `docs/INFORME_CLUSTERS.md`):

1. Se descarga `clinical_data.csv` de PhysioNet.
2. Se agrupan los casos por **variables preoperatorias** (edad, IMC, ASA,
   urgencia, servicio, comorbilidades y laboratorio previo). Los resultados
   posteriores a la cirugía **no** entran al agrupamiento.
3. El número de grupos se elige con el método del codo y el coeficiente de
   silueta, y se interpreta clínicamente cada grupo.
4. Dentro de cada cluster se generan casos sintéticos que respetan la
   distribución del grupo. Cada fila queda marcada con `origen` (`real` o
   `sintetico`) y con su `cluster`.

```bash
pip install -r scripts/requirements-datos.txt
python scripts/clusters_vitaldb.py            # descarga, agrupa, genera sintéticos
python scripts/cargar_clusters.py             # los sube a MongoDB (para el endpoint)
```

### Por qué responde al problema

La cancelación evitable que levantó el trabajo de campo ocurre, entre otras
razones, porque la **cama de UCI posoperatoria no está lista**. VitalDB es una
base real de pacientes quirúrgicos con las variables que un equipo conoce
**antes** de operar (edad, ASA, tipo de cirugía, laboratorio) y con el desenlace
posterior (`los_icu`, días en UCI). Eso permite entrenar y evaluar un modelo
de necesidad de UCI posquirúrgica (R10, a cargo de IA) con datos reales, y el
aumento por clusters da volumen y cubre los grupos pequeños sin inventar
casos fuera de lo clínicamente plausible.

### Limitaciones (declaradas)

- Los pacientes son de un hospital coreano; no representan a una población
  colombiana ni al caso hipotético de 300 camas.
- Los casos sintéticos **no son evidencia clínica**: sirven para probar el
  pipeline y para balancear grupos pequeños. Toda métrica de un modelo debe
  calcularse **solo con casos reales** y separando entrenamiento y prueba por
  paciente **antes** de generar sintéticos, para que no haya fuga de información.
- Un cluster es una agrupación estadística, no un diagnóstico: cada grupo se
  interpreta clínicamente en el informe, y esa lectura debe validarla un
  profesional de la salud.

---

## Resumen

| | Imagen | Tabular |
|---|---|---|
| Dataset | NIH ChestX-ray14 | VitalDB (PhysioNet) |
| Tipo | Radiografías de tórax (DICOM al PACS) | Casos quirúrgicos (tabla) |
| Licencia | Sin restricciones; citar y reconocer al NIH | CC BY 4.0 |
| Cantidad cargada | [COMPLETAR] | [COMPLETAR] reales + [COMPLETAR] sintéticos |
| Requisito | R06 | R07 |
