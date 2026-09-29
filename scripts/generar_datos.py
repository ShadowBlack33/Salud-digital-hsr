#!/usr/bin/env python3
"""
Generador de datos sintéticos para el Hospital San Rafael.

No genera datos "de juguete": las distribuciones están calibradas con
literatura real para que el dataset reproduzca los patrones que sí ocurren
en una institución de alta complejidad.

Calibración
-----------
· Tasa de cancelación 2,7 % - 7,6 %          (Segnini et al., 2022)
· Reparto de causas: 56,7 % paciente,
  40,5 % prestador, 2,7 % asegurador          (Muñoz-Caicedo et al., 2019)
· Duración quirúrgica: log-normal
  (una cirugía casi nunca termina antes de lo previsto, pero se puede
   alargar mucho -> cola derecha larga, no una normal simétrica)
· Llegadas a urgencias: Poisson con tasa
  variable por hora del día y día de semana
· Retraso de médicos: distribución sesgada; la mayoría puntual,
  cola larga                                  (hallazgo de campo, D.F. De la Cruz)
· Ocupación UCI: incluye un período de crisis que simula la saturación
  posterior al terremoto del 10 de agosto de 2026

Uso
---
    python scripts/generar_datos.py --meses 6 --salida db/03_datos.sql
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import datetime, timedelta

import numpy as np
from faker import Faker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.core.crypto import blind_index, cifrar, generar_clave  # noqa: E402
from app.core.security import hash_password  # noqa: E402

fake = Faker("es_CO")
Faker.seed(42)
random.seed(42)
np.random.seed(42)

# ---------------------------------------------------------------------------
# Configuración del hospital (perfil tipo Valle del Lili)
# ---------------------------------------------------------------------------
N_QUIROFANOS = 13
CAMAS_POR_TIPO = {
    "UCI": 60,
    "UCIN": 20,
    "INTERMEDIA": 45,
    "GENERAL": 160,
    "OBSERV_URG": 15,
}
PERSONAL_POR_TIPO = {
    "medico_especialista": 45,
    "medico_general": 22,
    "anestesiologo": 14,
    "enfermero_jefe": 12,
    "enfermero": 85,
    "instrumentador": 18,
    "auxiliar_enfermeria": 60,
    "secretaria": 10,
}

TASA_CANCELACION = 0.052        # punto medio del rango 2,7 %-7,6 %
CIRUGIAS_POR_DIA_HABIL = 34
PCT_URGENCIA = 0.28             # proporción de cirugías de origen urgente

# Terremoto 10 ago 2026 -> saturación de UCI las semanas siguientes
CRISIS_INICIO = datetime(2026, 8, 10)
CRISIS_FIN = datetime(2026, 9, 5)

# Perfil horario de llegadas a urgencias (tasa relativa por hora)
PERFIL_URGENCIAS = [
    0.4, 0.3, 0.25, 0.2, 0.2, 0.3, 0.5, 0.8, 1.1, 1.3, 1.4, 1.5,
    1.4, 1.3, 1.3, 1.4, 1.5, 1.6, 1.7, 1.6, 1.3, 1.0, 0.8, 0.6,
]

# LOINC de signos vitales (perfil oficial de FHIR Vital Signs)
SIGNOS_VITALES = [
    ("8867-4",  "Heart rate",                    "/min",   60, 100, 45, 150),
    ("9279-1",  "Respiratory rate",              "/min",   12,  20,  8,  35),
    ("8310-5",  "Body temperature",              "Cel",    36.1, 37.5, 35.0, 40.0),
    ("8480-6",  "Systolic blood pressure",       "mm[Hg]", 100, 130, 80, 190),
    ("8462-4",  "Diastolic blood pressure",      "mm[Hg]",  60,  85, 45, 115),
    ("59408-5", "Oxygen saturation by pulse ox", "%",       95, 100, 82, 100),
]

sql: list[str] = []


def esc(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, datetime):
        return f"'{v.isoformat()}'"
    if isinstance(v, bytes):
        return "'\\x" + v.hex() + "'::bytea"
    return "'" + str(v).replace("'", "''") + "'"


def insert(tabla: str, columnas: list[str], filas: list[tuple]) -> None:
    if not filas:
        return
    sql.append(f"\n-- {len(filas)} filas en {tabla}")
    for i in range(0, len(filas), 500):
        lote = filas[i:i + 500]
        vals = ",\n  ".join("(" + ", ".join(esc(v) for v in f) + ")" for f in lote)
        sql.append(f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES\n  {vals};")


# ---------------------------------------------------------------------------
def gen_usuarios_y_personal():
    """Personal del hospital con datos identificatorios cifrados."""
    personal_filas, usuario_filas = [], []
    pid = 0
    uid = 0

    # Mapa de tipo de personal -> código de rol
    rol_por_tipo = {t: t for t in PERSONAL_POR_TIPO}

    esp_quirurgicas = list(range(1, 11))   # ids de especialidades quirúrgicas
    pwd_demo = hash_password("Demo#Hospital2026")

    for tipo, cantidad in PERSONAL_POR_TIPO.items():
        for _ in range(cantidad):
            pid += 1
            doc = str(random.randint(1_000_000_00, 1_299_999_999))
            nombre = fake.first_name()
            apellido = fake.last_name()

            if tipo in ("medico_especialista", "anestesiologo"):
                esp_id = 11 if tipo == "anestesiologo" else random.choice(esp_quirurgicas)
            elif tipo == "medico_general":
                esp_id = 13
            else:
                esp_id = None

            # Tiempo de desplazamiento: variable predictiva.
            # NO se almacena la dirección (Ley 1581/2012).
            desplazamiento = int(np.clip(np.random.lognormal(3.1, 0.5), 8, 95))

            personal_filas.append((
                pid,
                cifrar(doc, "personal.documento"),
                blind_index(doc, "personal.documento"),
                cifrar(nombre, "personal.nombre"),
                cifrar(apellido, "personal.apellido"),
                cifrar(fake.phone_number()[:20], "personal.telefono"),
                cifrar(f"{nombre.lower()}.{apellido.lower()}@hsanrafael.co", "personal.email"),
                esp_id,
                tipo,
                desplazamiento,
                random.choice(["manana", "tarde", "noche", "rotativo"]),
            ))

            uid += 1
            usuario_filas.append((
                uid,
                f"{tipo[:4]}{pid:04d}",
                pwd_demo,
                f"(SELECT id FROM roles WHERE codigo = '{rol_por_tipo[tipo]}')",
                pid,
            ))

    insert("personal",
           ["id", "documento_cifrado", "documento_bidx", "nombre_cifrado",
            "apellido_cifrado", "telefono_cifrado", "email_cifrado",
            "especialidad_id", "tipo_personal", "tiempo_desplazamiento_min",
            "turno_habitual"],
           personal_filas)

    # Los usuarios usan subconsulta para el rol -> se insertan uno a uno
    sql.append(f"\n-- {len(usuario_filas)} usuarios del personal")
    for u in usuario_filas:
        sql.append(
            "INSERT INTO usuarios (id, username, password_hash, rol_id, personal_id, "
            "debe_cambiar_password) VALUES "
            f"({u[0]}, {esc(u[1])}, {esc(u[2])}, {u[3]}, {u[4]}, FALSE);"
        )

    # Cuentas especiales para la demo de roles
    especiales = [
        ("admin",                  "admin"),
        ("director",               "director_medico"),
        ("coordinador",            "coordinador_quirurgico"),
        ("integracion_svc",        "servicio_integracion"),
        ("facturacion01",          "facturacion"),
    ]
    for username, rol in especiales:
        uid += 1
        sql.append(
            "INSERT INTO usuarios (id, username, password_hash, rol_id, "
            "debe_cambiar_password) VALUES "
            f"({uid}, {esc(username)}, {esc(pwd_demo)}, "
            f"(SELECT id FROM roles WHERE codigo = '{rol}'), FALSE);"
        )

    return pid, uid


# ---------------------------------------------------------------------------
def gen_recursos():
    """Quirófanos y camas."""
    quirofanos = []
    for i in range(1, N_QUIROFANOS + 1):
        quirofanos.append((
            i, f"QX-{i:02d}", f"Quirófano {i}", 4,           # servicio CIR = 4
            i <= 6,                                          # arco en C
            i in (1, 2),                                     # circulación extracorpórea
            "disponible",
        ))
    insert("quirofanos",
           ["id", "codigo", "nombre", "servicio_id", "tiene_arco_c",
            "tiene_circulacion_extracorporea", "estado"],
           quirofanos)

    servicio_por_tipo = {"UCI": 2, "UCIN": 3, "INTERMEDIA": 5,
                         "GENERAL": 6, "OBSERV_URG": 1}
    # Prefijos explícitos: 'UCI'[:3] y 'UCIN'[:3] colisionarían.
    prefijo_por_tipo = {"UCI": "UCI", "UCIN": "UCN", "INTERMEDIA": "INT",
                        "GENERAL": "GEN", "OBSERV_URG": "OBS"}
    camas, cid = [], 0
    for tipo, n in CAMAS_POR_TIPO.items():
        for k in range(1, n + 1):
            cid += 1
            # Ocupación base realista por tipo
            p_ocupada = {"UCI": .88, "UCIN": .75, "INTERMEDIA": .80,
                         "GENERAL": .72, "OBSERV_URG": .85}[tipo]
            r = random.random()
            estado = ("ocupada" if r < p_ocupada
                      else "en_limpieza" if r < p_ocupada + .06
                      else "en_proceso_alta" if r < p_ocupada + .10
                      else "disponible")
            camas.append((
                cid, f"{prefijo_por_tipo[tipo]}-{k:03d}",
                f"(SELECT id FROM tipos_cama WHERE codigo = '{tipo}')",
                servicio_por_tipo[tipo], estado,
            ))

    sql.append(f"\n-- {len(camas)} camas")
    for c in camas:
        sql.append(
            "INSERT INTO camas (id, codigo, tipo_cama_id, servicio_id, estado) VALUES "
            f"({c[0]}, {esc(c[1])}, {c[2]}, {c[3]}, {esc(c[4])});"
        )
    return cid


# ---------------------------------------------------------------------------
def gen_pacientes(n: int) -> list[str]:
    """
    Genera n pacientes. La llave primaria de `pacientes` ya no es un id
    autoincremental -- es documento_bidx, el índice ciego de la cédula
    (ver la nota en db/01_schema.sql). Por eso esta función YA NO recibe
    ni asigna un id secuencial: cada fila se identifica por su propio
    documento_bidx, calculado aquí mismo.

    Devuelve la lista de esos documento_bidx generados, para que
    gen_encuentros() pueda elegir pacientes reales al azar en vez de
    un rango de enteros que ya no existe.
    """
    filas = []
    bidx_generados = []
    documentos_usados = set()

    while len(filas) < n:
        doc = str(random.randint(1_000_000_00, 1_299_999_999))
        if doc in documentos_usados:
            continue  # evita colisión de documento_bidx (poco probable, pero posible)
        documentos_usados.add(doc)

        bidx = blind_index(doc, "pacientes.documento")
        nombre, apellido = fake.first_name(), fake.last_name()
        edad = int(np.clip(np.random.gamma(7, 7), 0, 98))

        # El tipo de documento depende de la edad, no es independiente:
        # RC es solo para niños hasta ~7 años, TI solo para menores de edad.
        # Antes se elegía al azar sin mirar la edad, y salían imposibles
        # como una TI de alguien nacido en 1957.
        if edad < 7:
            tipo_documento = "RC"
        elif edad < 18:
            tipo_documento = "TI"
        else:
            tipo_documento = random.choices(["CC", "CE"], weights=[93, 7])[0]

        filas.append((
            bidx,
            tipo_documento,
            cifrar(doc, "pacientes.documento"),
            cifrar(nombre, "pacientes.nombre"),
            cifrar(apellido, "pacientes.apellido"),
            cifrar(fake.phone_number()[:20], "pacientes.telefono"),
            cifrar(fake.address().replace("\n", ", ")[:120], "pacientes.direccion"),
            (datetime.now() - timedelta(days=edad * 365 + random.randint(0, 364))).date(),
            random.choice(["M", "F"]),
            random.randint(1, 7),
            edad > 55 and random.random() < .55,
            min(5, max(1, int(np.random.normal(2 + edad / 40, 0.9)))),
            True,
        ))
        bidx_generados.append(bidx)

    insert("pacientes",
           ["documento_bidx", "tipo_documento", "documento_cifrado",
            "nombre_cifrado", "apellido_cifrado", "telefono_cifrado",
            "direccion_cifrada", "fecha_nacimiento", "sexo", "eps_id",
            "tiene_comorbilidades", "riesgo_asa", "consentimiento_datos"],
           filas)
    return bidx_generados


# ---------------------------------------------------------------------------
def duracion_real(estimada: int, desviacion: int, urgencia: bool,
                  hora: int, comorbilidad: bool) -> int:
    """
    Log-normal: la mediana queda cerca de la estimación pero con cola
    derecha larga (una cirugía se alarga mucho más fácil de lo que se acorta).
    """
    sigma = 0.16 + desviacion / 260
    mu = np.log(max(estimada, 1))
    dur = np.random.lognormal(mu, sigma)
    if urgencia:
        dur *= np.random.uniform(1.05, 1.30)   # urgencias son menos predecibles
    if comorbilidad:
        dur *= np.random.uniform(1.02, 1.18)
    if hora >= 16:
        dur *= np.random.uniform(1.0, 1.12)    # fatiga al final de la jornada
    return int(np.clip(dur, estimada * 0.65, estimada * 3.2))


def retraso_medico(desplazamiento_min: int) -> int:
    """Mayoría puntual, cola larga de retrasos (hallazgo de campo)."""
    if random.random() < 0.62:
        return int(np.random.uniform(-5, 5))
    base = np.random.exponential(14) + desplazamiento_min * 0.10
    return int(np.clip(base, 0, 95))


def gen_encuentros(pacientes_bidx: list[str], n_personal, n_camas, meses: int):
    """Cirugías, urgencias y sus observaciones/cancelaciones."""
    encuentros, observaciones, cancelaciones, eventos = [], [], [], []
    eid = oid = cid = evid = 0

    fin = datetime(2026, 9, 7)
    inicio = fin - timedelta(days=meses * 30)

    # ids de personal por tipo (según el orden de creación)
    base = 0
    rango = {}
    for tipo, cant in PERSONAL_POR_TIPO.items():
        rango[tipo] = (base + 1, base + cant)
        base += cant
    esp_ini, esp_fin = rango["medico_especialista"]
    anes_ini, anes_fin = rango["anestesiologo"]
    enf_ini, enf_fin = rango["enfermero"]

    dia = inicio
    while dia <= fin:
        if dia.weekday() < 5:          # días hábiles
            n_cir = int(np.random.normal(CIRUGIAS_POR_DIA_HABIL, 5))
        else:
            n_cir = int(np.random.normal(9, 3))
        n_cir = max(0, n_cir)

        en_crisis = CRISIS_INICIO <= dia <= CRISIS_FIN
        if en_crisis:
            n_cir = int(n_cir * 1.25)   # más trauma, menos electiva

        for _ in range(n_cir):
            eid += 1
            proc_id = random.randint(1, 22)
            paciente_id = random.choice(pacientes_bidx)
            urgencia = random.random() < (PCT_URGENCIA * (1.7 if en_crisis else 1))
            hora_ini = random.choices(range(6, 20),
                                      weights=[3, 8, 10, 10, 9, 8, 7, 8, 8, 7, 6, 4, 3, 2])[0]

            prog_ini = dia.replace(hour=hora_ini,
                                   minute=random.choice([0, 15, 30, 45]))
            # duración estimada del catálogo (aprox por complejidad del id)
            est = [60, 90, 75, 150, 300, 270, 240, 150, 120, 150, 60,
                   180, 90, 90, 45, 120, 180, 240, 30, 45, 60, 90][proc_id - 1]
            desv = [20, 25, 20, 50, 75, 70, 65, 40, 35, 40, 20,
                    45, 25, 30, 15, 35, 50, 70, 10, 15, 20, 30][proc_id - 1]
            prog_fin = prog_ini + timedelta(minutes=est)

            cirujano = random.randint(esp_ini, esp_fin)
            anestesiologo = random.randint(anes_ini, anes_fin)
            comorbilidad = random.random() < .35

            # ¿se cancela?
            p_cancel = TASA_CANCELACION * (1.6 if en_crisis else 1.0)
            cancelada = random.random() < p_cancel

            if cancelada:
                estado = "cancelled"
                real_ini = real_fin = None
            else:
                estado = "finished"
                retraso = retraso_medico(random.randint(10, 70))
                real_ini = prog_ini + timedelta(minutes=max(0, retraso))
                real_fin = real_ini + timedelta(
                    minutes=duracion_real(est, desv, urgencia, hora_ini, comorbilidad))

            encuentros.append((
                eid, paciente_id, "cirugia", estado,
                "urgencia" if urgencia else "electiva",
                1 if urgencia else random.randint(2, 4),
                None, proc_id,
                random.randint(1, N_QUIROFANOS),
                random.randint(1, n_camas),
                cirujano, anestesiologo,
                prog_ini, prog_fin, real_ini, real_fin,
            ))

            if cancelada:
                cid += 1
                # Reparto de causas según Muñoz-Caicedo et al. (2019)
                grupo = random.choices(["paciente", "prestador", "asegurador"],
                                       weights=[56.7, 40.5, 2.7])[0]
                causa = {
                    "paciente":   random.randint(1, 6),
                    "prestador":  random.randint(7, 17),
                    "asegurador": random.randint(18, 20),
                }[grupo]
                cancelaciones.append((
                    cid, eid, causa,
                    int(np.clip(np.random.exponential(180), 5, 2880)),
                    random.random() < .7,
                    round(random.uniform(2_000_000, 9_000_000), 2),
                ))

            # Signos vitales preoperatorios
            for cod, disp, unidad, lo, hi, mn, mx in random.sample(SIGNOS_VITALES, 4):
                oid += 1
                critico = random.random() < .045
                val = (round(random.uniform(mn, lo - .1), 1) if critico and random.random() < .5
                       else round(random.uniform(hi + .1, mx), 1) if critico
                       else round(random.uniform(lo, hi), 1))
                observaciones.append((
                    oid, eid, paciente_id, "vital-signs", cod, disp,
                    val, unidad, "final", critico,
                    prog_ini - timedelta(minutes=random.randint(20, 180)),
                    random.randint(enf_ini, enf_fin),
                ))

        # Eventos de estado de camas (alimentan el cálculo de horas ociosas)
        for _ in range(random.randint(25, 60)):
            evid += 1
            cama = random.randint(1, n_camas)
            anterior, nuevo = random.choice([
                ("ocupada", "en_proceso_alta"), ("en_proceso_alta", "en_limpieza"),
                ("en_limpieza", "disponible"), ("disponible", "reservada"),
                ("reservada", "ocupada"),
            ])
            # En crisis la cama disponible se ocupa más rápido
            if anterior == "disponible":
                dur = int(np.random.exponential(45 if en_crisis else 190))
            elif anterior == "en_limpieza":
                dur = int(np.clip(np.random.normal(48, 18), 15, 180))
            else:
                dur = int(np.clip(np.random.exponential(600), 30, 8000))
            eventos.append((
                evid, "cama", cama, anterior, nuevo, dur,
                dia.replace(hour=random.randint(0, 23), minute=random.randint(0, 59)),
                random.choice(["manual", "manual", "manual", "automatico"]),
            ))

        dia += timedelta(days=1)

    insert("encuentros",
           ["id", "paciente_id", "tipo", "estado", "origen", "prioridad_clinica",
            "nivel_triage", "procedimiento_id", "quirofano_id", "cama_id",
            "medico_responsable_id", "anestesiologo_id",
            "hora_programada_inicio", "hora_programada_fin",
            "hora_real_inicio", "hora_real_fin"],
           encuentros)

    insert("observaciones",
           ["id", "encuentro_id", "paciente_id", "categoria", "codigo_loinc",
            "display_loinc", "valor_numerico", "unidad_ucum", "estado",
            "es_critico", "fecha_hora", "registrado_por"],
           observaciones)

    insert("cancelaciones",
           ["id", "encuentro_id", "causa_id", "minutos_anticipacion",
            "reprogramada", "costo_estimado_cop"],
           cancelaciones)

    insert("eventos_estado",
           ["id", "entidad_tipo", "entidad_id", "estado_anterior", "estado_nuevo",
            "duracion_estado_anterior_min", "timestamp", "origen"],
           eventos)

    return eid, oid, cid, evid


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meses", type=int, default=6)
    ap.add_argument("--pacientes", type=int, default=4000)
    ap.add_argument("--salida", default="db/03_datos_sinteticos.sql")
    args = ap.parse_args()

    # Claves efímeras si no hay entorno configurado (solo para generar)
    os.environ.setdefault("APP_ENCRYPTION_KEY", generar_clave())
    os.environ.setdefault("APP_BLIND_INDEX_KEY", generar_clave())

    sql.append("-- ==========================================================")
    sql.append("-- DATOS SINTÉTICOS - Hospital San Rafael")
    sql.append(f"-- Generado: {datetime.now().isoformat()}")
    sql.append(f"-- Período: {args.meses} meses | Pacientes: {args.pacientes}")
    sql.append("-- Distribuciones calibradas con Segnini et al. (2022) y")
    sql.append("-- Muñoz-Caicedo et al. (2019). Incluye período de crisis")
    sql.append("-- (terremoto 10-ago-2026) para probar saturación de UCI.")
    sql.append("-- ==========================================================")
    sql.append("BEGIN;")

    n_pers, n_users = gen_usuarios_y_personal()
    n_camas = gen_recursos()
    pacientes_bidx = gen_pacientes(args.pacientes)   # lista de documento_bidx, no un conteo
    n_pac = len(pacientes_bidx)

    # Cuenta de demo para el rol 'paciente' -- uno de los 3 roles mínimos que
    # exige la rúbrica. Va aquí, DESPUÉS de gen_pacientes(), porque necesita
    # un documento_bidx real para engancharse; no existía ningún paciente
    # todavía cuando corrían las demás cuentas especiales, arriba.
    # Al estar en el generador, esta cuenta sobrevive cada vez que se
    # regeneran los datos, en vez de haber quedado como un INSERT suelto
    # que hay que acordarse de repetir a mano.
    n_users += 1
    sql.append(
        "INSERT INTO usuarios (id, username, password_hash, rol_id, "
        "paciente_id, debe_cambiar_password) VALUES "
        f"({n_users}, {esc('paciente_demo')}, {esc(hash_password('Demo#Hospital2026'))}, "
        f"(SELECT id FROM roles WHERE codigo = 'paciente'), "
        f"{esc(pacientes_bidx[0])}, FALSE);"
    )

    n_enc, n_obs, n_can, n_evt = gen_encuentros(pacientes_bidx, n_pers, n_camas, args.meses)

    # Resincronizar secuencias
    # OJO: "pacientes" queda fuera de esta lista a propósito -- ya no tiene
    # una columna id SERIAL (su llave es documento_bidx), así que no existe
    # secuencia que resincronizar para esa tabla.
    sql.append("\n-- Ajuste de secuencias")
    for t in ["personal", "usuarios", "quirofanos", "camas",
              "encuentros", "observaciones", "cancelaciones", "eventos_estado"]:
        sql.append(
            f"SELECT setval(pg_get_serial_sequence('{t}','id'), "
            f"COALESCE((SELECT MAX(id) FROM {t}), 1));"
        )
    sql.append("COMMIT;")

    os.makedirs(os.path.dirname(args.salida) or ".", exist_ok=True)
    with open(args.salida, "w", encoding="utf-8") as f:
        f.write("\n".join(sql))

    tam = os.path.getsize(args.salida) / 1_048_576
    print("Datos sintéticos generados")
    print(f"  archivo      : {args.salida} ({tam:.1f} MB)")
    print(f"  personal     : {n_pers}")
    print(f"  usuarios     : {n_users}")
    print(f"  camas        : {n_camas}")
    print(f"  pacientes    : {n_pac}")
    print(f"  encuentros   : {n_enc}")
    print(f"  observaciones: {n_obs}")
    print(f"  cancelaciones: {n_can}  ({100*n_can/max(n_enc,1):.2f} %)")
    print(f"  eventos      : {n_evt}")


if __name__ == "__main__":
    main()
