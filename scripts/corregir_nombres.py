#!/usr/bin/env python3
"""
Corrige pacientes cuyo nombre no corresponde al sexo registrado
("Juan Gutiérrez, femenino"). El generador de datos elegía el nombre y el
sexo por separado; desde ahora los elige juntos, y este script arregla la
base que ya existe sin regenerarla.

Solo cambia el nombre (cifrado). Documento, sexo, fechas y todo lo clínico
quedan igual. El nombre nuevo sale de la misma lista de nombres colombianos
de Faker y es siempre el mismo para un paciente (depende de su llave), así
que correrlo dos veces no cambia nada.

Uso:
    python scripts/corregir_nombres.py --simular   # cuenta cuántos cambiaría
    python scripts/corregir_nombres.py
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from faker.providers.person.es_CO import Provider

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

from app.core.crypto import cifrar, descifrar  # noqa: E402

MASCULINOS = sorted(Provider.first_names_male)
FEMENINOS = sorted(Provider.first_names_female)
SET_M, SET_F = set(MASCULINOS), set(FEMENINOS)


def nombre_para(sexo: str, semilla: str) -> str:
    lista = MASCULINOS if sexo == "M" else FEMENINOS
    return lista[int(hashlib.sha256(semilla.encode()).hexdigest(), 16) % len(lista)]


def no_coincide(nombre: str, sexo: str) -> bool:
    primero = (nombre or "").split(" ")[0]
    if sexo == "M":
        return primero in SET_F
    if sexo == "F":
        return primero in SET_M
    return False


def corregir(cur, tabla: str, llave: str, aad: str, simular: bool) -> int:
    cur.execute(f"SELECT {llave} AS k, nombre_cifrado, sexo FROM {tabla}")
    filas = cur.fetchall()
    cambios = []
    for f in filas:
        nombre = descifrar(bytes(f["nombre_cifrado"]), f"{aad}.nombre")
        if no_coincide(nombre, f["sexo"]):
            cambios.append((psycopg2.Binary(cifrar(nombre_para(f["sexo"], str(f["k"])), f"{aad}.nombre")), f["k"]))
    if cambios and not simular:
        psycopg2.extras.execute_batch(cur, f"UPDATE {tabla} SET nombre_cifrado = %s WHERE {llave} = %s", cambios)
    return len(cambios)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simular", action="store_true")
    a = ap.parse_args()
    url = os.getenv("DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    n = corregir(cur, "pacientes", "documento_bidx", "pacientes", a.simular)
    if a.simular:
        conn.rollback()
        print(f"Pacientes con nombre que no corresponde al sexo: {n} (no se cambió nada)")
    else:
        conn.commit()
        print(f"Pacientes corregidos: {n}")
    conn.close()


if __name__ == "__main__":
    main()
