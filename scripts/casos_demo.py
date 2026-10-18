#!/usr/bin/env python3
"""
Casos clínicos de demostración para las cuentas medico01 y especialista01.

Sin esto, al entrar como médico la pantalla queda vacía: nadie tiene
pacientes "a su cargo" y no hay valores críticos. Este script les arma un
turno creíble sobre la jornada que deja scripts/simular_jornada.py:

  medico01 (medicina general)
    · 3 pacientes en urgencias, triage 1-2, con valores críticos recientes
      (saturación baja, hipotensión, lactato, potasio, glucosa).
    · 2 hospitalizados de la jornada pasan a su cargo; uno con un crítico.
    · 2 controles de consulta externa ya atendidos (pacientes estables).
    · 1 paciente suyo tiene una cirugía programada con otro cirujano.

  especialista01 (cirugía general)
    · Es el cirujano de 1 cirugía en curso y de 1 programada para hoy.
    · 1 paciente suyo (lo vio en consulta) está programado con OTRO cirujano:
      la pantalla muestra que no está asignado.
    · 1 hospitalizado posoperatorio a su cargo, con hemoglobina crítica.

Todo lo que crea queda marcado con observaciones_texto = 'CASOS_DEMO' y se
borra al volver a correrlo. Correr DESPUÉS de simular_jornada.py (el
contenedor 'jornada' lo hace solo).

Uso:
    python scripts/casos_demo.py
    python scripts/casos_demo.py --limpiar
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

MARCA = "CASOS_DEMO"
JORNADA = "SIMULACION_JORNADA"

# (LOINC, nombre, unidad, valor crítico, valor normal)
CRITICOS = [
    ("59408-5", "Oxygen saturation by pulse ox", "%", 84, 97),
    ("8480-6", "Systolic blood pressure", "mm[Hg]", 76, 122),
    ("2524-7", "Lactate [Moles/volume] in Blood", "mmol/L", 4.9, 1.2),
    ("2823-3", "Potassium [Moles/volume] in Serum", "mmol/L", 6.6, 4.1),
    ("2339-0", "Glucose [Mass/volume] in Blood", "mg/dL", 42, 96),
    ("8867-4", "Heart rate", "/min", 148, 82),
]
HEMOGLOBINA = ("718-7", "Hemoglobin [Mass/volume] in Blood", "g/dL", 6.8, 12.9)
DX_URGENCIAS = ["A41", "I21", "S06", "K35", "N20"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limpiar", action="store_true")
    ap.add_argument("--semilla", type=int, default=11)
    args = ap.parse_args()
    rng = random.Random(args.semilla)

    url = os.getenv("DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
    if not url:
        sys.exit("Falta DATABASE_URL en el .env")
    conn = psycopg2.connect(url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ahora = datetime.now(timezone.utc)

    sub = "SELECT id FROM encuentros WHERE observaciones_texto = %s"
    # Las observaciones de demostración llevan la marca en valor_texto (algunas
    # cuelgan de hospitalizaciones de la jornada, no de encuentros propios).
    cur.execute(f"DELETE FROM observaciones WHERE valor_texto = %s OR encuentro_id IN ({sub})", (MARCA, MARCA))
    cur.execute(f"DELETE FROM traslados WHERE encuentro_origen_id IN ({sub})", (MARCA,))
    cur.execute(f"DELETE FROM cancelaciones WHERE encuentro_id IN ({sub}) OR encuentro_nuevo_id IN ({sub})",
                (MARCA, MARCA))
    cur.execute("DELETE FROM encuentros WHERE observaciones_texto = %s", (MARCA,))
    print(f"Casos de demostración anteriores borrados: {cur.rowcount}")
    if args.limpiar:
        conn.commit()
        return

    cur.execute("""SELECT u.username, u.id AS usuario_id, u.personal_id, p.especialidad_id
                   FROM usuarios u JOIN personal p ON p.id = u.personal_id
                   WHERE u.username IN ('medico01', 'especialista01')""")
    cuentas = {r["username"]: r for r in cur.fetchall()}
    if len(cuentas) < 2:
        sys.exit("Faltan medico01 o especialista01 con personal asignado (db/08_roles_corte2.sql).")
    med, esp = cuentas["medico01"], cuentas["especialista01"]

    cur.execute("SELECT id, codigo FROM diagnosticos_cie10")
    dx = {r["codigo"]: r["id"] for r in cur.fetchall()}

    # Pacientes adultos sin nada en curso: para urgencias y consultas.
    cur.execute("""
        SELECT documento_bidx FROM pacientes p
        WHERE p.activo AND p.fecha_nacimiento <= CURRENT_DATE - INTERVAL '18 years'
          AND NOT EXISTS (SELECT 1 FROM encuentros e WHERE e.paciente_id = p.documento_bidx
                          AND e.activo AND e.estado IN ('planned','arrived','triaged','in-progress'))
        ORDER BY md5(documento_bidx || %s) LIMIT 12
    """, (str(args.semilla),))
    libres = [r["documento_bidx"] for r in cur.fetchall()]
    if len(libres) < 8:
        # Base de pruebas pequeña: se completan con adultos que no están en cirugía.
        cur.execute("""
            SELECT documento_bidx FROM pacientes p
            WHERE p.activo AND p.fecha_nacimiento <= CURRENT_DATE - INTERVAL '18 years'
              AND NOT EXISTS (SELECT 1 FROM encuentros e WHERE e.paciente_id = p.documento_bidx
                              AND e.activo AND e.tipo = 'cirugia' AND e.estado IN ('planned','in-progress'))
              AND NOT (p.documento_bidx = ANY(%s))
            ORDER BY md5(documento_bidx) LIMIT %s
        """, (libres, 12 - len(libres)))
        libres += [r["documento_bidx"] for r in cur.fetchall()]
    if len(libres) < 8:
        sys.exit("No hay suficientes pacientes para armar los casos.")

    def encuentro(**f) -> int:
        f.setdefault("observaciones_texto", MARCA)
        cols = ", ".join(f)
        cur.execute(f"INSERT INTO encuentros ({cols}) VALUES ({', '.join(['%s'] * len(f))}) RETURNING id",
                    list(f.values()))
        return cur.fetchone()["id"]

    def observacion(enc_id: int, paciente: str, loinc, critico: bool, hace_min: int, registro=None):
        codigo, nombre, unidad, v_crit, v_norm = loinc
        cur.execute("""
            INSERT INTO observaciones (encuentro_id, paciente_id, categoria, codigo_loinc, display_loinc,
                valor_numerico, valor_texto, unidad_ucum, es_critico, fecha_hora, registrado_por, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (enc_id, paciente, "laboratory" if unidad in ("mmol/L", "mg/dL", "g/dL") else "vital-signs",
              codigo, nombre, v_crit if critico else v_norm, MARCA, unidad, critico,
              ahora - timedelta(minutes=hace_min), registro, None))

    resumen = []
    # ---------------------------------------------------------------- médico general
    for i, (pac, triage, codigo_dx) in enumerate(zip(libres[:3], (1, 2, 2), rng.sample(DX_URGENCIAS, 3))):
        llegada = ahora - timedelta(minutes=rng.randint(35, 160))
        enc = encuentro(paciente_id=pac, tipo="urgencias", estado="in-progress", origen="urgencia",
                        prioridad_clinica=triage, nivel_triage=triage, diagnostico_cie10_id=dx.get(codigo_dx),
                        medico_responsable_id=med["personal_id"], hora_real_inicio=llegada,
                        hora_programada_inicio=llegada)
        criticos = rng.sample(CRITICOS, 2 if i == 0 else 1)
        for j, c in enumerate(criticos):
            observacion(enc, pac, c, True, rng.randint(4, 25) + j * 7, med["personal_id"])
        for c in rng.sample([x for x in CRITICOS if x not in criticos], 2):
            observacion(enc, pac, c, False, rng.randint(30, 60), med["personal_id"])
        resumen.append(f"medico01 · urgencias triage {triage} ({codigo_dx}) con {len(criticos)} crítico(s)")

    for pac in libres[3:5]:
        cuando = ahora - timedelta(days=rng.randint(2, 20), hours=rng.randint(0, 6))
        encuentro(paciente_id=pac, tipo="consulta_externa", estado="finished", origen="electiva",
                  prioridad_clinica=4, medico_responsable_id=med["personal_id"],
                  hora_programada_inicio=cuando, hora_real_inicio=cuando,
                  hora_real_fin=cuando + timedelta(minutes=20))
    resumen.append("medico01 · 2 controles de consulta externa")

    # Hospitalizados de la jornada que pasan a su cargo.
    cur.execute("""SELECT id, paciente_id FROM encuentros
                   WHERE observaciones_texto = %s AND tipo = 'hospitalizacion' AND estado = 'in-progress'
                   ORDER BY id LIMIT 4""", (JORNADA,))
    hosp = cur.fetchall()
    for k, h in enumerate(hosp[:2]):
        cur.execute("UPDATE encuentros SET medico_responsable_id = %s WHERE id = %s", (med["personal_id"], h["id"]))
        if k == 0:
            observacion(h["id"], h["paciente_id"], CRITICOS[0], True, 12, med["personal_id"])
    resumen.append(f"medico01 · {min(len(hosp), 2)} hospitalizados a su cargo")

    # Paciente suyo con cirugía programada por otro cirujano.
    cur.execute("""SELECT id, paciente_id FROM encuentros
                   WHERE observaciones_texto = %s AND tipo = 'cirugia' AND estado = 'planned'
                     AND medico_responsable_id IS DISTINCT FROM %s
                   ORDER BY hora_programada_inicio DESC LIMIT 1""", (JORNADA, esp["personal_id"]))
    cx_med = cur.fetchone()
    if cx_med:
        cuando = ahora - timedelta(days=6)
        encuentro(paciente_id=cx_med["paciente_id"], tipo="consulta_externa", estado="finished",
                  origen="electiva", prioridad_clinica=3, medico_responsable_id=med["personal_id"],
                  hora_programada_inicio=cuando, hora_real_inicio=cuando, hora_real_fin=cuando + timedelta(minutes=25))
        resumen.append("medico01 · 1 paciente suyo con cirugía programada (otro cirujano)")

    # ---------------------------------------------------------------- especialista
    cur.execute("""SELECT id, paciente_id, estado FROM encuentros
                   WHERE observaciones_texto = %s AND tipo = 'cirugia' AND estado IN ('in-progress', 'planned')
                     AND id IS DISTINCT FROM %s
                   ORDER BY estado DESC, hora_programada_inicio""",
                (JORNADA, cx_med["id"] if cx_med else None))
    cirugias = cur.fetchall()
    en_curso = next((c for c in cirugias if c["estado"] == "in-progress"), None)
    programadas = [c for c in cirugias if c["estado"] == "planned"]
    # Un cirujano general no opera cataratas: sus cirugías pasan a un
    # procedimiento de su especialidad que la sala pueda hacer.
    cur.execute("""SELECT cp.id, cp.duracion_estimada_min AS dur, cp.requiere_arco_c FROM catalogo_procedimientos cp
                   WHERE cp.activo AND cp.especialidad_id = %s ORDER BY cp.id""", (esp["especialidad_id"],))
    propios = cur.fetchall()
    for c in filter(None, [en_curso, programadas[0] if programadas else None]):
        cur.execute("""SELECT q.tiene_arco_c, cp.especialidad_id FROM encuentros e JOIN quirofanos q ON q.id = e.quirofano_id
                       JOIN catalogo_procedimientos cp ON cp.id = e.procedimiento_id WHERE e.id = %s""", (c["id"],))
        sala = cur.fetchone()
        aptos = [p for p in propios if sala and (sala["tiene_arco_c"] or not p["requiere_arco_c"])]
        if sala and sala["especialidad_id"] != esp["especialidad_id"] and aptos:
            p = rng.choice(aptos)
            cur.execute("""UPDATE encuentros SET procedimiento_id = %s,
                               hora_programada_fin = hora_programada_inicio + make_interval(mins => %s)
                           WHERE id = %s""", (p["id"], p["dur"], c["id"]))
        cur.execute("UPDATE encuentros SET medico_responsable_id = %s WHERE id = %s", (esp["personal_id"], c["id"]))
    resumen.append("especialista01 · cirujano de 1 cirugía en curso y 1 programada")

    # Paciente suyo, programado con otro cirujano.
    otra = programadas[1] if len(programadas) > 1 else None
    if otra:
        cuando = ahora - timedelta(days=9)
        encuentro(paciente_id=otra["paciente_id"], tipo="consulta_externa", estado="finished",
                  origen="electiva", prioridad_clinica=3, medico_responsable_id=esp["personal_id"],
                  hora_programada_inicio=cuando, hora_real_inicio=cuando, hora_real_fin=cuando + timedelta(minutes=30))
        resumen.append("especialista01 · paciente suyo programado con otro cirujano (no asignado)")

    # Posoperatorio a su cargo con hemoglobina crítica.
    if len(hosp) > 2:
        h = hosp[2]
        cur.execute("UPDATE encuentros SET medico_responsable_id = %s WHERE id = %s", (esp["personal_id"], h["id"]))
        observacion(h["id"], h["paciente_id"], HEMOGLOBINA, True, 18, esp["personal_id"])
        resumen.append("especialista01 · posoperatorio con hemoglobina crítica")

    # Consulta con un paciente libre (estable).
    cuando = ahora - timedelta(days=3)
    encuentro(paciente_id=libres[5], tipo="consulta_externa", estado="finished", origen="electiva",
              prioridad_clinica=4, medico_responsable_id=esp["personal_id"],
              hora_programada_inicio=cuando, hora_real_inicio=cuando, hora_real_fin=cuando + timedelta(minutes=30))

    # ---------------------------------------------------------------- portal del paciente
    # paciente_demo: lo vio medico01 en consulta, tuvo valoración preanestésica
    # (con signos vitales) y tiene una colecistectomía mañana con especialista01.
    cur.execute("SELECT paciente_id FROM usuarios WHERE username = 'paciente_demo'")
    fila = cur.fetchone()
    if fila and fila["paciente_id"]:
        pd_ = fila["paciente_id"]
        cur.execute("SELECT id FROM personal WHERE tipo_personal = 'anestesiologo' AND activo ORDER BY id LIMIT 1")
        anest = cur.fetchone()["id"]
        cur.execute("""SELECT cp.id, cp.duracion_estimada_min AS dur FROM catalogo_procedimientos cp
                       WHERE cp.especialidad_id = %s AND NOT cp.requiere_arco_c ORDER BY (cp.nombre ILIKE 'Colecist%%') DESC, cp.id LIMIT 1""",
                    (esp["especialidad_id"],))
        proc = cur.fetchone()
        cuando = ahora - timedelta(days=12)
        encuentro(paciente_id=pd_, tipo="consulta_externa", estado="finished", origen="electiva", prioridad_clinica=4,
                  medico_responsable_id=med["personal_id"], hora_programada_inicio=cuando, hora_real_inicio=cuando,
                  hora_real_fin=cuando + timedelta(minutes=20), diagnostico_cie10_id=dx.get("K80"))
        cuando = ahora - timedelta(days=2)
        pre = encuentro(paciente_id=pd_, tipo="consulta_externa", estado="finished", origen="electiva", prioridad_clinica=3,
                        medico_responsable_id=anest, hora_programada_inicio=cuando, hora_real_inicio=cuando,
                        hora_real_fin=cuando + timedelta(minutes=30), diagnostico_cie10_id=dx.get("K80"))
        for c, v in (("8867-4", 76), ("8480-6", 128), ("8462-4", 79), ("59408-5", 97), ("8310-5", 36.6), ("9279-1", 16)):
            cur.execute("""INSERT INTO observaciones (encuentro_id, paciente_id, categoria, codigo_loinc, display_loinc,
                               valor_numerico, valor_texto, unidad_ucum, es_critico, fecha_hora, registrado_por)
                           VALUES (%s, %s, 'vital-signs', %s, %s, %s, %s, %s, FALSE, %s, %s)""",
                        (pre, pd_, c, c, v, MARCA, {"8867-4": "/min", "8480-6": "mm[Hg]", "8462-4": "mm[Hg]",
                                                    "59408-5": "%", "8310-5": "Cel", "9279-1": "/min"}[c], cuando, anest))
        if proc:
            local = datetime.now(timezone(timedelta(hours=-5)))   # Colombia, sin horario de verano
            manana = (local + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
            cur.execute("SELECT id FROM quirofanos WHERE codigo = 'QX-09'")
            qx = cur.fetchone()
            encuentro(paciente_id=pd_, tipo="cirugia", estado="planned", origen="electiva", prioridad_clinica=3,
                      procedimiento_id=proc["id"], quirofano_id=qx["id"] if qx else None,
                      medico_responsable_id=esp["personal_id"], anestesiologo_id=anest,
                      hora_programada_inicio=manana, hora_programada_fin=manana + timedelta(minutes=proc["dur"]),
                      diagnostico_cie10_id=dx.get("K80"))
        resumen.append("paciente_demo · consulta, valoración preanestésica y cirugía programada para mañana")

    conn.commit()
    conn.close()
    print("Casos de demostración creados:")
    for r in resumen:
        print(f"  · {r}")


if __name__ == "__main__":
    main()
