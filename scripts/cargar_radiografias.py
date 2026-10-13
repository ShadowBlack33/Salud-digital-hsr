#!/usr/bin/env python3
"""
Radiografías reales del dataset NIH ChestX-ray14 asignadas a pacientes.

Cada imagen se sube al PACS (Orthanc) como un estudio DICOM de radiografía
de tórax (modalidad DX) del paciente al que se le asigna, con el hallazgo
del dataset en la descripción: "Rx tórax PA · Derrame pleural · NIH
00000075_000". Así, en la ficha del paciente, la pestaña Imágenes muestra
radiografías de verdad, y solo las ve quien puede ver a ese paciente (el
médico tratante, el especialista, el admin): la API revisa el permiso antes
de pedirle la imagen a Orthanc.

A quién se asignan:
  1. Primero a los pacientes de medico01 y especialista01 (la demo).
  2. Luego a hospitalizados al azar.
  Se respeta el sexo y, en lo posible, la década de edad del dataset.

De dónde salen las imágenes:
  · --carpeta: una carpeta con PNG del dataset (por ejemplo, la muestra de
    Kaggle "nih-chest-xrays/sample" o un images_00X de la descarga oficial)
    y --etiquetas con Data_Entry_2017.csv.
  · Sin --carpeta: descarga una muestra pública (24 imágenes, ~10 MB) del
    repositorio jrzech/reproduce-chexnet, que redistribuye imágenes del
    dataset con sus etiquetas, y la guarda en data/rx_nih/ (no se sube a git).

Es seguro correrlo varias veces: si el paciente ya tiene esa radiografía, se
la salta.

Uso:
    python scripts/cargar_radiografias.py                       # muestra pública, 24 imágenes
    python scripts/cargar_radiografias.py --cantidad 40 --carpeta D:/nih/images --etiquetas D:/nih/Data_Entry_2017.csv
    python scripts/cargar_radiografias.py --simular             # muestra la asignación sin subir nada

Fuente: Wang X. et al. ChestX-ray8, CVPR 2017. NIH Clinical Center.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import random
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
load_dotenv(RAIZ / ".env")

from app.core.crypto import descifrar  # noqa: E402

REPO = "https://raw.githubusercontent.com/jrzech/reproduce-chexnet/master"
CACHE = Path(os.getenv("RX_CACHE") or RAIZ / "data" / "rx_nih")

HALLAZGOS = {
    "Atelectasis": "Atelectasia", "Cardiomegaly": "Cardiomegalia", "Effusion": "Derrame pleural",
    "Infiltration": "Infiltrado", "Mass": "Masa", "Nodule": "Nódulo", "Pneumonia": "Neumonía",
    "Pneumothorax": "Neumotórax", "Consolidation": "Consolidación", "Edema": "Edema",
    "Emphysema": "Enfisema", "Fibrosis": "Fibrosis", "Pleural_Thickening": "Engrosamiento pleural",
    "Hernia": "Hernia",
}


# ------------------------------------------------------------------ etiquetas
def leer_etiquetas(ruta: Path) -> dict[str, dict]:
    """Acepta Data_Entry_2017.csv (oficial) o nih_labels.csv (columnas 0/1)."""
    salida = {}
    with open(ruta, newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            nombre = fila.get("Image Index")
            if not nombre:
                continue
            if "Finding Labels" in fila:
                hallazgos = [h for h in fila["Finding Labels"].split("|") if h and h != "No Finding"]
            else:
                hallazgos = [k for k in HALLAZGOS if fila.get(k) == "1"]
            edad = "".join(ch for ch in (fila.get("Patient Age") or "") if ch.isdigit())
            salida[nombre] = {
                "hallazgos": [HALLAZGOS.get(h, h) for h in hallazgos],
                "edad": int(edad) if edad else None,
                "sexo": (fila.get("Patient Gender") or "").strip()[:1].upper() or None,
                "vista": (fila.get("View Position") or "PA").strip(),
            }
    return salida


def descargar_muestra(cantidad: int) -> tuple[Path, Path]:
    CACHE.mkdir(parents=True, exist_ok=True)
    etiquetas = CACHE / "nih_labels.csv"
    lista = CACHE / "starter_images.csv"
    for destino, url in ((etiquetas, f"{REPO}/nih_labels.csv"), (lista, f"{REPO}/starter_images.csv")):
        if not destino.exists():
            print(f"Descargando {url}")
            urllib.request.urlretrieve(url, destino)
    nombres = [l.strip() for l in lista.read_text().splitlines()[1:] if l.strip().endswith(".png")]
    # Variedad: primero una imagen por cada combinación de hallazgos distinta
    # (la lista viene ordenada por hallazgo y las primeras son todas iguales).
    etq = leer_etiquetas(etiquetas)
    random.Random(7).shuffle(nombres)
    vistos, elegidas, resto = set(), [], []
    for n in nombres:
        clave = tuple(etq.get(n, {}).get("hallazgos", ()))
        (resto if clave in vistos else elegidas).append(n)
        vistos.add(clave)
    for nombre in (elegidas + resto)[:cantidad]:
        destino = CACHE / nombre
        if not destino.exists():
            print(f"  descargando {nombre}")
            urllib.request.urlretrieve(f"{REPO}/starter_images/{nombre}", destino)
    (CACHE / "seleccion.txt").write_text("\n".join((elegidas + resto)[:cantidad]))
    return CACHE, etiquetas


# ------------------------------------------------------------------ pacientes
def candidatos(cur) -> list[dict]:
    cur.execute("""
        WITH portal AS (
            -- El paciente de la cuenta paciente_demo: así su portal muestra una radiografía.
            SELECT paciente_id, -2 AS orden FROM usuarios WHERE username = 'paciente_demo' AND paciente_id IS NOT NULL
        ), criticos AS (
            -- Pacientes de la demo con valores críticos: los primeros que abre el médico.
            SELECT DISTINCT o.paciente_id, -1 AS orden
            FROM observaciones o JOIN encuentros e ON e.id = o.encuentro_id
            JOIN usuarios u ON u.personal_id = e.medico_responsable_id
            WHERE o.es_critico AND o.activo AND u.username IN ('medico01', 'especialista01')
              AND o.fecha_hora > NOW() - INTERVAL '3 days'
        ), demo AS (
            SELECT DISTINCT e.paciente_id, 0 AS orden
            FROM encuentros e JOIN usuarios u ON u.personal_id IN (e.medico_responsable_id, e.anestesiologo_id)
            WHERE u.username IN ('medico01', 'especialista01') AND e.activo
        ), hosp AS (
            SELECT DISTINCT e.paciente_id, 1 AS orden
            FROM encuentros e WHERE e.activo AND e.tipo IN ('hospitalizacion', 'urgencias')
              AND e.estado = 'in-progress'
        ), todos AS (
            SELECT paciente_id, MIN(orden) AS orden FROM (SELECT * FROM portal UNION ALL SELECT * FROM criticos UNION ALL SELECT * FROM demo UNION ALL SELECT * FROM hosp) x
            GROUP BY paciente_id
        )
        SELECT p.documento_bidx, p.nombre_cifrado, p.apellido_cifrado, p.fecha_nacimiento, p.sexo, t.orden
        FROM todos t JOIN pacientes p ON p.documento_bidx = t.paciente_id
        WHERE p.activo AND p.fecha_nacimiento <= CURRENT_DATE - INTERVAL '12 years'
        ORDER BY t.orden, md5(p.documento_bidx)
    """)
    return cur.fetchall()


def edad(nac) -> int:
    hoy = datetime.now().date()
    return hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day))


def elegir(pacientes: list[dict], info: dict, usados: set) -> dict | None:
    """El primer paciente libre del mismo sexo; si se puede, de una edad parecida."""
    libres = [p for p in pacientes if p["documento_bidx"] not in usados
              and (not info["sexo"] or p["sexo"] == info["sexo"])]
    if not libres:
        return None
    # Los de la demo (portal del paciente y casos críticos) reciben imagen
    # aunque la edad no se parezca tanto.
    urgentes = [p for p in libres if p["orden"] < 0]
    if urgentes:
        return urgentes[0]
    if info["edad"]:
        cercanos = [p for p in libres if abs(edad(p["fecha_nacimiento"]) - info["edad"]) <= 15]
        prioritarios = [p for p in cercanos if p["orden"] <= 0] or cercanos
        if prioritarios:
            return prioritarios[0]
    return libres[0]


# ------------------------------------------------------------------ principal
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--carpeta", type=Path)
    ap.add_argument("--etiquetas", type=Path)
    ap.add_argument("--cantidad", type=int, default=24)
    ap.add_argument("--semilla", type=int, default=7)
    ap.add_argument("--simular", action="store_true", help="Solo muestra la asignación")
    a = ap.parse_args()
    rng = random.Random(a.semilla)

    if a.carpeta:
        if not a.etiquetas:
            sys.exit("Con --carpeta hace falta --etiquetas (Data_Entry_2017.csv)")
        carpeta, ruta_etiquetas = a.carpeta, a.etiquetas
    else:
        carpeta, ruta_etiquetas = descargar_muestra(a.cantidad)
    etiquetas = leer_etiquetas(ruta_etiquetas)
    seleccion = carpeta / "seleccion.txt"
    if seleccion.exists() and not a.carpeta:
        imagenes = [carpeta / n for n in seleccion.read_text().split() if (carpeta / n).exists()]
    else:
        imagenes = sorted(p for p in carpeta.glob("*.png") if p.name in etiquetas)[: a.cantidad]
    if not imagenes:
        sys.exit(f"No hay PNG del dataset con etiqueta en {carpeta}")

    url = os.getenv("DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    pacientes = candidatos(cur)
    conn.close()
    if not pacientes:
        sys.exit("No hay pacientes candidatos. Corre simular_jornada.py y casos_demo.py primero.")

    if not a.simular:
        from app.services import pacs
        if not pacs.is_alive():
            sys.exit("El PACS (Orthanc) no responde. ¿Está arriba 'docker compose up -d'?")

    usados: set[str] = set()
    hechas = 0
    ahora = datetime.now(timezone.utc)
    for ruta in imagenes:
        info = etiquetas[ruta.name]
        p = elegir(pacientes, info, usados)
        if p is None:
            print(f"{ruta.name}: no queda un paciente compatible, se omite")
            continue
        usados.add(p["documento_bidx"])
        hallazgo = ", ".join(info["hallazgos"]) or "Sin hallazgos"
        codigo = ruta.stem
        descripcion = f"Rx tórax {info['vista']} · {hallazgo} · NIH {codigo}"[:64]
        nombre = f"{descifrar(bytes(p['nombre_cifrado']), 'pacientes.nombre')} " \
                 f"{descifrar(bytes(p['apellido_cifrado']), 'pacientes.apellido')}"
        print(f"{codigo} ({info['sexo']}, {info['edad']} a) -> {nombre} "
              f"({p['sexo']}, {edad(p['fecha_nacimiento'])} a){' · portal del paciente' if p['orden'] == -2 else ' · caso crítico de la demo' if p['orden'] == -1 else ' · demo' if p['orden'] == 0 else ''}: {hallazgo}")
        if a.simular:
            continue

        from app.services import pacs
        if any(codigo in (i.get("description") or "") for i in pacs.list_images(p["documento_bidx"])):
            print("   ya estaba cargada")
            continue
        img = Image.open(ruta)
        if img.mode.startswith("I"):
            img = img.point(lambda v: v / 256).convert("L")
        elif img.mode not in ("L", "RGB"):
            img = img.convert("L")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        fecha = ahora - timedelta(days=rng.randint(0, 6), hours=rng.randint(0, 20))
        pacs.dicomize(buf.getvalue(), {
            "documento_bidx": p["documento_bidx"],
            "nombre": descifrar(bytes(p["nombre_cifrado"]), "pacientes.nombre"),
            "apellido": descifrar(bytes(p["apellido_cifrado"]), "pacientes.apellido"),
            "fecha_nacimiento": p["fecha_nacimiento"], "sexo": p["sexo"],
        }, descripcion, modalidad="DX", extra={
            "StudyDate": fecha.strftime("%Y%m%d"), "StudyTime": fecha.strftime("%H%M%S"),
            "BodyPartExamined": "CHEST", "ViewPosition": info["vista"],
            "InstitutionName": "Hospital San Rafael (caso de estudio)",
        })
        hechas += 1
    print(f"\nRadiografías cargadas: {hechas}" if not a.simular else "\n(simulación: no se subió nada)")


if __name__ == "__main__":
    main()
