#!/usr/bin/env python3
"""
Crea imágenes SINTÉTICAS de práctica (no son clínicas) y las sube al PACS
(Orthanc), enganchadas a pacientes reales que ya existen en la base.

Adaptado del notebook de la Semana 8: genera una imagen de aspecto
"fondo de ojo" con poco contraste a propósito -- así, al subir el contraste
en el visor, los vasos aparecen. Se puede correr varias veces: si el
paciente ya tiene imágenes, se lo salta.

Requiere Orthanc arriba (`docker compose up -d`) y las variables ORTHANC_*
en el .env (ya vienen con valores por defecto que funcionan en local).

Uso:
    python scripts/seed_images.py --pacientes 5
"""
from __future__ import annotations

import argparse
import io
import math
import os
import random
import sys

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

load_dotenv()

from app.core.crypto import descifrar  # noqa: E402
from app.services import pacs  # noqa: E402


def make_phantom(seed: int, size: int = 512) -> Image.Image:
    """Imagen sintética tipo 'fondo de ojo' -- no es una imagen clínica real."""
    rng = random.Random(seed)
    img = Image.new("RGB", (size, size), (6, 6, 6))
    draw = ImageDraw.Draw(img)
    c, radius = size // 2, int(size * 0.46)

    # 1. Retina: disco con degradado radial
    for r in range(radius, 0, -2):
        t = 1 - r / radius
        draw.ellipse([c - r, c - r, c + r, c + r],
                    fill=(int(70 + 90 * t), int(30 + 50 * t), int(14 + 22 * t)))

    # 2. Disco óptico
    ox, oy = c + int(size * 0.13), c - int(size * 0.03)
    draw.ellipse([ox - 26, oy - 26, ox + 26, oy + 26], fill=(190, 150, 80))

    # 3. Vasos: caminatas aleatorias que parten del disco óptico
    for _ in range(10):
        x, y, angle = ox, oy, rng.uniform(0, 2 * math.pi)
        for step in range(70):
            angle += rng.uniform(-0.22, 0.22)
            nx, ny = x + math.cos(angle) * 6, y + math.sin(angle) * 6
            if (nx - c) ** 2 + (ny - c) ** 2 > (radius - 6) ** 2:
                break
            draw.line([x, y, nx, ny], fill=(105, 22, 16), width=max(1, 4 - step // 18))
            x, y = nx, ny

    img = img.filter(ImageFilter.GaussianBlur(1.1))
    img = ImageEnhance.Contrast(img).enhance(0.45)
    return ImageEnhance.Brightness(img).enhance(1.9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pacientes", type=int, default=5,
                    help="A cuántos pacientes reales ponerles imágenes")
    args = ap.parse_args()

    db_url = os.getenv("DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
    if not db_url:
        print("Falta DATABASE_URL en el .env")
        sys.exit(1)

    if not pacs.is_alive():
        print("El PACS (Orthanc) no responde. ¿Corriste 'docker compose up -d'?")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT documento_bidx, documento_cifrado, nombre_cifrado, apellido_cifrado,
               fecha_nacimiento, sexo
        FROM pacientes WHERE activo LIMIT %s
    """, (args.pacientes,))
    pacientes = cur.fetchall()
    conn.close()

    if not pacientes:
        print("No hay pacientes en la base todavía. Corre generar_datos.py primero.")
        sys.exit(1)

    for i, p in enumerate(pacientes):
        if pacs.list_images(p["documento_bidx"]):
            documento = descifrar(bytes(p["documento_cifrado"]), "pacientes.documento")
            print(f"documento {documento}: ya tiene imágenes, se omite")
            continue

        paciente_dicom = {
            "documento_bidx": p["documento_bidx"],
            "nombre": descifrar(bytes(p["nombre_cifrado"]), "pacientes.nombre"),
            "apellido": descifrar(bytes(p["apellido_cifrado"]), "pacientes.apellido"),
            "fecha_nacimiento": p["fecha_nacimiento"],
            "sexo": p["sexo"],
        }

        buf = io.BytesIO()
        make_phantom(seed=100 + i).save(buf, format="PNG")
        instance_id = pacs.dicomize(buf.getvalue(), paciente_dicom,
                                    "Imagen sintética de práctica")
        documento = descifrar(bytes(p["documento_cifrado"]), "pacientes.documento")
        print(f"documento {documento}: {paciente_dicom['nombre']} "
              f"{paciente_dicom['apellido']} -> imagen creada ({instance_id})")
    print("\nPara encontrarlos en el front: pega el número de documento de "
          "arriba en el buscador de la lista de pacientes y dale Enter.")


if __name__ == "__main__":
    main()
