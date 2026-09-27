#!/usr/bin/env python3
"""
Aplica un archivo .sql contra la base de datos configurada en .env,
sin necesitar el cliente psql instalado (útil en Windows).

Antes de aplicar el esquema, los catálogos o los datos sintéticos,
verifica si ya existen en la base y pide confirmación explícita si
volver a aplicarlos podría chocar con lo que ya está cargado
(tablas duplicadas, filas repetidas, error de llave única, etc.).

Uso:
    python scripts/aplicar_sql.py db/01_schema.sql
    python scripts/aplicar_sql.py db/02_seed_catalogos.sql
    python scripts/aplicar_sql.py db/03_datos_sinteticos.sql
    python scripts/aplicar_sql.py db/00_reset_datos.sql

Para saltar la confirmación (por ejemplo, en un script automatizado):
    python scripts/aplicar_sql.py db/01_schema.sql --forzar
"""
import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def existe_tabla(cur, nombre_tabla: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{nombre_tabla}",))
    return bool(cur.fetchone()[0])


def contar_filas(cur, nombre_tabla: str) -> int:
    if not existe_tabla(cur, nombre_tabla):
        return 0
    cur.execute(f"SELECT COUNT(*) FROM {nombre_tabla}")
    return cur.fetchone()[0]


def verificar_estado(cur, archivo: str):
    """
    Devuelve un mensaje de advertencia si aplicar este archivo podría chocar
    con lo que ya existe en la base, o None si es seguro continuar sin preguntar.
    """
    nombre = os.path.basename(archivo).lower()

    if "01_schema" in nombre:
        if existe_tabla(cur, "roles"):
            return ("El esquema ya está creado (la tabla 'roles' ya existe). "
                    "Volver a crearlo va a fallar en cada tabla que ya exista, "
                    "o puede dejar la base en un estado inconsistente.")

    elif "02_seed_catalogos" in nombre:
        n = contar_filas(cur, "especialidades")
        if n > 0:
            return (f"Los catálogos ya están cargados ({n} especialidades ya existen). "
                    "Volver a insertarlos va a duplicar filas o fallar por llave única.")

    elif "00_reset_datos" in nombre:
        n = contar_filas(cur, "pacientes")
        if n > 0:
            return (f"Esto va a BORRAR los {n} pacientes y todos los datos generados "
                    "(encuentros, observaciones, camas, personal, etc.) de la base "
                    "compartida del equipo. Los catálogos y roles NO se tocan.")

    elif "datos_sinteticos" in nombre:
        n = contar_filas(cur, "pacientes")
        if n > 0:
            return (f"Ya hay {n} pacientes cargados en la base. "
                    "Volver a cargar datos sintéticos va a duplicarlos o fallar por "
                    "documento repetido. Si quieres regenerarlos, corre primero "
                    "'db/00_reset_datos.sql'.")

    elif "cedula_como_llave" in nombre:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'pacientes' AND column_name = 'id')"
        )
        ya_migrado = not cur.fetchone()[0]
        if ya_migrado:
            return ("Esta migración ya se aplicó antes: 'pacientes' ya no tiene "
                    "columna 'id' (documento_bidx ya es la llave primaria). "
                    "Volver a correrla va a fallar al intentar borrar columnas "
                    "que ya no existen.")

    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    forzar = "--forzar" in sys.argv

    if len(args) != 1:
        print("Uso: python scripts/aplicar_sql.py <archivo.sql> [--forzar]")
        sys.exit(1)

    archivo = args[0]
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Falta DATABASE_URL en el .env")
        sys.exit(1)

    # psycopg2 no entiende el prefijo 'postgresql+psycopg2://' de SQLAlchemy
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://")

    if not os.path.exists(archivo):
        print(f"No se encontró el archivo: {archivo}")
        sys.exit(1)

    with open(archivo, encoding="utf-8") as f:
        sql = f.read()

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            advertencia = verificar_estado(cur, archivo)

            if advertencia and not forzar:
                print("\n" + "=" * 60)
                print("ADVERTENCIA")
                print("=" * 60)
                print(advertencia)
                print("=" * 60)
                respuesta = input(
                    "\n¿Seguro que quieres hacer esto? Escribe SI (mayúsculas) "
                    "para continuar, cualquier otra cosa para cancelar: "
                )
                if respuesta.strip() != "SI":
                    print("Cancelado. No se modificó la base de datos.")
                    sys.exit(0)

            print(f"\nAplicando {archivo} ...")
            cur.execute(sql)
        print("Listo.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()