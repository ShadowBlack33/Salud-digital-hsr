#!/usr/bin/env python3
"""
Simula una jornada hospitalaria EN CURSO, tomando la hora actual como "ahora".

Por qué hace falta: el generador de datos produce historia (cirugías ya
terminadas, hasta el 7 de septiembre) y estados de cama y quirófano sin un
"ahora" que los sostenga. Con eso, un tablero en tiempo real muestra todos los
quirófanos disponibles, ninguna cirugía en curso y camas "en limpieza desde
hace 3 semanas". Este script agrega lo que falta, sin tocar la historia:

  · Hospitalizaciones activas: un encuentro en curso por cada cama ocupada,
    con paciente, médico responsable y diagnóstico.
  · Cirugías en curso en los quirófanos, con la hora programada frente a la
    real (el retraso) y una cama de destino.
  · Cirugías programadas para las próximas horas.
  · Los tiempos "en este estado" de camas y quirófanos, refrescados a la
    hora actual.
  · 24 recién nacidos (RC) para la UCI neonatal: el generador casi no crea
    niños, y un adulto en neonatos no sería creíble.

Se puede correr todas las veces que haga falta (antes de una demo, por
ejemplo): borra primero lo que creó la vez anterior. Todo lo que crea queda
marcado en encuentros.observaciones_texto = 'SIMULACION_JORNADA'.

Uso:
    python scripts/simular_jornada.py            # crea o refresca la jornada
    python scripts/simular_jornada.py --limpiar  # borra solo los encuentros simulados
    python scripts/simular_jornada.py --semilla 7   # resultado repetible
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

from app.core.crypto import blind_index, cifrar  # noqa: E402

MARCA = "SIMULACION_JORNADA"
APELLIDOS_RN = ["Gómez", "Rojas", "Mosquera", "Cárdenas", "Quintero", "Valencia",
                "Zapata", "Salazar", "Ibarra", "Lozano", "Caicedo", "Mejía",
                "Bolaños", "Rengifo", "Trujillo", "Vásquez", "Perea", "Cuéllar",
                "Riascos", "Mina", "Benítez", "Palacios", "Sinisterra", "Ospina"]

# Estado de cada quirófano, en orden QX-01..QX-13. QX-01 y QX-02 tienen
# circulación extracorpórea; QX-03 a QX-06, arco en C.
PLAN_QX = ["en_cirugia", "en_preparacion", "en_cirugia", "en_cirugia", "en_limpieza",
           "en_cirugia", "en_cirugia", "en_cirugia", "disponible", "en_cirugia",
           "en_limpieza", "bloqueado", "en_cirugia"]

# Minutos que lleva una cama en su estado actual, según estado y tipo.
def minutos_en_estado(rng: random.Random, estado: str, tipo: str) -> int:
    if estado in ("ocupada", "reservada"):
        rangos = {"UCI": (720, 14 * 1440), "UCIN": (2 * 1440, 20 * 1440),
                  "INTERMEDIA": (1440, 6 * 1440), "GENERAL": (180, 8 * 1440),
                  "OBSERV_URG": (40, 14 * 60)}
        return rng.randint(*rangos.get(tipo, (180, 2 * 1440)))
    if estado == "en_limpieza":
        return int(rng.triangular(5, 190, 30))
    if estado == "en_proceso_alta":
        return rng.randint(20, 240)
    if estado == "disponible":
        return rng.randint(5, 420)
    return rng.randint(30, 600)


def _dx_todos(cur):
    cur.execute("SELECT id, codigo FROM diagnosticos_cie10")
    return cur.fetchall()


def insertar(cur, tabla: str, filas: list[dict]) -> list[int]:
    ids = []
    for f in filas:
        cols = ", ".join(f)
        marcas = ", ".join(["%s"] * len(f))
        cur.execute(f"INSERT INTO {tabla} ({cols}) VALUES ({marcas}) RETURNING id",
                    list(f.values()))
        ids.append(cur.fetchone()["id"])
    return ids


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limpiar", action="store_true",
                    help="Solo borra los encuentros de la simulación anterior")
    ap.add_argument("--semilla", type=int, default=None)
    args = ap.parse_args()
    rng = random.Random(args.semilla)

    db_url = os.getenv("DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
    if not db_url:
        print("Falta DATABASE_URL en el .env")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ahora = datetime.now(timezone.utc)

    cur.execute("DELETE FROM encuentros WHERE observaciones_texto = %s", (MARCA,))
    print(f"Encuentros simulados anteriores borrados: {cur.rowcount}")
    if args.limpiar:
        conn.commit()
        return

    # ------------------------------------------------------------ pacientes
    cur.execute("""SELECT documento_bidx FROM pacientes
                   WHERE activo AND fecha_nacimiento <= CURRENT_DATE - INTERVAL '18 years'
                   ORDER BY random() LIMIT 800""")
    adultos = [r["documento_bidx"] for r in cur.fetchall()]

    recien_nacidos = []
    for i, apellido in enumerate(APELLIDOS_RN):
        doc = str(1_099_000_001 + i)
        bidx = blind_index(doc, "pacientes.documento")
        nacimiento = (ahora - timedelta(days=rng.randint(1, 25))).date()
        cur.execute("""
            INSERT INTO pacientes (documento_bidx, tipo_documento, documento_cifrado,
                nombre_cifrado, apellido_cifrado, fecha_nacimiento, sexo, eps_id,
                tiene_comorbilidades, riesgo_asa, consentimiento_datos)
            VALUES (%s, 'RC', %s, %s, %s, %s, %s, 1, FALSE, 2, TRUE)
            ON CONFLICT (documento_bidx) DO UPDATE SET fecha_nacimiento = EXCLUDED.fecha_nacimiento
        """, (bidx,
              psycopg2.Binary(cifrar(doc, "pacientes.documento")),
              psycopg2.Binary(cifrar("Bebé", "pacientes.nombre")),
              psycopg2.Binary(cifrar(apellido, "pacientes.apellido")),
              nacimiento, rng.choice(["M", "F"])))
        recien_nacidos.append(bidx)

    iter_adultos, iter_rn = iter(adultos), iter(recien_nacidos)

    def paciente_para(tipo_cama: str) -> str:
        return next(iter_rn if tipo_cama == "UCIN" else iter_adultos)

    # ------------------------------------------------------------- personal
    cur.execute("""SELECT id, tipo_personal, especialidad_id FROM personal
                   WHERE activo AND tipo_personal IN
                   ('medico_especialista', 'medico_general', 'anestesiologo')""")
    personal = cur.fetchall()
    generales = [p["id"] for p in personal if p["tipo_personal"] == "medico_general"]
    especialistas = [p for p in personal if p["tipo_personal"] == "medico_especialista"]
    anestesiologos = [p["id"] for p in personal if p["tipo_personal"] == "anestesiologo"]

    cur.execute("SELECT id, codigo FROM diagnosticos_cie10")
    diagnosticos = [r["id"] for r in cur.fetchall()]
    por_codigo = {r["codigo"]: r["id"] for r in _dx_todos(cur)}

    # Un diagnóstico al azar sería absurdo (una catarata en la UCI, una fractura de
    # fémur en un recién nacido). Cada tipo de cama recibe los que tienen sentido.
    # El catálogo no trae diagnósticos neonatales (capítulo P de la CIE-10): en la
    # UCI neonatal el diagnóstico queda vacío en vez de inventar códigos.
    DX_POR_CAMA = {
        "UCI": ["I21", "S06", "A41", "S72", "I70"],
        "INTERMEDIA": ["I21", "I25", "I70", "N20", "K35", "S72"],
        "GENERAL": ["K35", "K80", "K40", "N20", "S72", "H25", "I25"],  # sin O82: no se asigna por sexo
        "OBSERV_URG": ["K35", "I21", "N20", "S72", "A41", "S06"],
        "UCIN": [],
    }

    def diagnostico_para(tipo_cama: str):
        codigos = DX_POR_CAMA.get(tipo_cama, [])
        ids = [por_codigo[c] for c in codigos if c in por_codigo]
        return rng.choice(ids) if ids else None

    # ---------------------------------------------------------------- camas
    cur.execute("""SELECT c.id, c.codigo, c.estado, tc.codigo AS tipo
                   FROM camas c JOIN tipos_cama tc ON tc.id = c.tipo_cama_id
                   WHERE c.activo ORDER BY c.id""")
    camas = cur.fetchall()

    tiempos_cama, hospitalizaciones = [], []
    for c in camas:
        minutos = minutos_en_estado(rng, c["estado"], c["tipo"])
        desde = ahora - timedelta(minutes=minutos)
        tiempos_cama.append((c["id"], desde))
        if c["estado"] in ("ocupada", "en_proceso_alta"):
            # En el catálogo no hay intensivistas ni pediatras: los pacientes
            # hospitalizados quedan a cargo de medicina general, en vez de que un
            # oftalmólogo aparezca como médico de un paciente de UCI.
            medicos = generales
            prioridad = {"UCI": (1, 2), "UCIN": (1, 2), "INTERMEDIA": (2, 3),
                         "GENERAL": (3, 4), "OBSERV_URG": (2, 3)}[c["tipo"]]
            hospitalizaciones.append({
                "paciente_id": paciente_para(c["tipo"]), "tipo": "hospitalizacion",
                "estado": "in-progress",
                "origen": "urgencia" if (c["tipo"] == "OBSERV_URG" or rng.random() < .45)
                          else "electiva",
                "prioridad_clinica": rng.randint(*prioridad),
                "diagnostico_cie10_id": diagnostico_para(c["tipo"]),
                "cama_id": c["id"], "medico_responsable_id": rng.choice(medicos),
                "hora_programada_inicio": desde, "hora_real_inicio": desde,
                "observaciones_texto": MARCA,
            })
    insertar(cur, "encuentros", hospitalizaciones)

    psycopg2.extras.execute_values(
        cur, "UPDATE camas SET estado_desde = v.t FROM (VALUES %s) AS v(id, t) "
             "WHERE camas.id = v.id",
        tiempos_cama, template="(%s::int, %s::timestamptz)")

    # ----------------------------------------------------------- quirófanos
    cur.execute("""SELECT id, codigo, tiene_arco_c, tiene_circulacion_extracorporea AS cec
                   FROM quirofanos WHERE activo ORDER BY id""")
    quirofanos = cur.fetchall()
    cur.execute("""SELECT cp.id, cp.nombre, cp.duracion_estimada_min AS dur,
                          cp.requiere_arco_c AS arco, cp.especialidad_id,
                          cp.tipo_cama_requerida_id, tc.codigo AS cama_tipo,
                          esp.nombre AS esp
                   FROM catalogo_procedimientos cp
                   JOIN tipos_cama tc ON tc.id = cp.tipo_cama_requerida_id
                   JOIN especialidades esp ON esp.id = cp.especialidad_id
                   WHERE cp.activo""")
    procs = cur.fetchall()

    def procedimiento_para(qx):
        if qx["cec"]:
            pool = [p for p in procs if p["esp"] in ("Cirugía cardiovascular", "Cirugía vascular")]
        elif qx["tiene_arco_c"]:
            # Las cirugías cardíacas necesitan circulación extracorpórea: solo QX-01 y QX-02.
            pool = [p for p in procs if p["arco"] and p["esp"] != "Cirugía cardiovascular"]
        else:
            pool = [p for p in procs if not p["arco"] and p["dur"] <= 180]
        return rng.choice(pool or procs)

    ocupacion_personal: dict[int, list[tuple]] = {}

    def elegir(candidatos, ini, fin):
        """Elige a alguien que no tenga otra cirugía que se cruce con [ini, fin]."""
        libres_ = [c for c in candidatos
                   if all(fin <= a or ini >= b for a, b in ocupacion_personal.get(c, []))]
        elegido = rng.choice(libres_ or candidatos)
        ocupacion_personal.setdefault(elegido, []).append((ini, fin))
        return elegido

    def cirujano_para(proc, ini, fin):
        aptos = [p["id"] for p in especialistas if p["especialidad_id"] == proc["especialidad_id"]]
        return elegir(aptos or [p["id"] for p in especialistas], ini, fin)

    def anestesiologo_para(ini, fin):
        return elegir(anestesiologos, ini, fin)

    # Camas de destino: de las que aún no están ocupadas, del tipo que pide el procedimiento.
    libres = {}
    for c in camas:
        if c["estado"] in ("en_limpieza", "disponible"):
            libres.setdefault(c["tipo"], []).append(c["id"])
    for lista in libres.values():
        rng.shuffle(lista)

    def cama_destino(proc):
        lista = libres.get(proc["cama_tipo"]) or []
        return lista.pop() if lista else None

    estados_qx, resumen_qx = [], []
    for qx, plan in zip(quirofanos, PLAN_QX):
        fin_actual = None
        if plan == "en_cirugia":
            proc = procedimiento_para(qx)
            transcurrido = int(proc["dur"] * rng.uniform(0.15, 1.10))
            # La mayoría arranca a tiempo; unas pocas se atrasan (así se ve un día real).
            retraso = rng.choice([0, 0, 0, 0, 5, 5, 10, 15, 25, 40])
            real_inicio = ahora - timedelta(minutes=transcurrido)
            prog_inicio = real_inicio - timedelta(minutes=retraso)
            urgencia = rng.random() < .25
            insertar(cur, "encuentros", [{
                "paciente_id": next(iter_adultos), "tipo": "cirugia", "estado": "in-progress",
                "origen": "urgencia" if urgencia else "electiva",
                "prioridad_clinica": 1 if urgencia else 3,
                "diagnostico_cie10_id": rng.choice(diagnosticos),
                "procedimiento_id": proc["id"], "quirofano_id": qx["id"],
                "cama_id": cama_destino(proc),
                "medico_responsable_id": cirujano_para(proc, real_inicio, real_inicio + timedelta(minutes=proc["dur"])),
                "anestesiologo_id": anestesiologo_para(real_inicio, real_inicio + timedelta(minutes=proc["dur"])),
                "hora_programada_inicio": prog_inicio,
                "hora_programada_fin": prog_inicio + timedelta(minutes=proc["dur"]),
                "hora_real_inicio": real_inicio, "observaciones_texto": MARCA,
            }])
            estados_qx.append((qx["id"], "en_cirugia", real_inicio))
            fin_actual = prog_inicio + timedelta(minutes=proc["dur"])
            resumen_qx.append(f"{qx['codigo']}: {proc['nombre']} (+{retraso} min)")
        else:
            minutos = {"en_preparacion": rng.randint(8, 25), "en_limpieza": rng.randint(5, 30),
                       "disponible": rng.randint(10, 120), "bloqueado": 130}[plan]
            estados_qx.append((qx["id"], plan, ahora - timedelta(minutes=minutos)))
            resumen_qx.append(f"{qx['codigo']}: {plan}")

        if plan == "bloqueado":
            continue
        # Cirugías programadas a continuación (1 o 2), con 30 min de recambio.
        base = (fin_actual or ahora + timedelta(minutes=rng.randint(10, 40))) + timedelta(minutes=30)
        for _ in range(rng.choice([1, 2])):
            proc = procedimiento_para(qx)
            insertar(cur, "encuentros", [{
                "paciente_id": next(iter_adultos), "tipo": "cirugia", "estado": "planned",
                "origen": "electiva", "prioridad_clinica": 3,
                "diagnostico_cie10_id": rng.choice(diagnosticos),
                "procedimiento_id": proc["id"], "quirofano_id": qx["id"],
                "medico_responsable_id": cirujano_para(proc, base, base + timedelta(minutes=proc["dur"])),
                "anestesiologo_id": anestesiologo_para(base, base + timedelta(minutes=proc["dur"])),
                "hora_programada_inicio": base,
                "hora_programada_fin": base + timedelta(minutes=proc["dur"]),
                "observaciones_texto": MARCA,
            }])
            base += timedelta(minutes=proc["dur"] + 30)

    psycopg2.extras.execute_values(
        cur, "UPDATE quirofanos SET estado = v.e, estado_desde = v.t "
             "FROM (VALUES %s) AS v(id, e, t) WHERE quirofanos.id = v.id",
        estados_qx, template="(%s::int, %s::varchar, %s::timestamptz)")

    conn.commit()
    conn.close()

    print(f"\nJornada simulada, con la hora actual ({ahora:%Y-%m-%d %H:%M} UTC) como referencia")
    print(f"  hospitalizaciones activas : {len(hospitalizaciones)}")
    print("  quirófanos:")
    for linea in resumen_qx:
        print(f"    {linea}")


if __name__ == "__main__":
    main()
