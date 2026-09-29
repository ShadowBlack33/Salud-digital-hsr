import { infoCama } from "./estados";
import { minutosDesde } from "./format";

/** Cuenta camas por tipo y grupo del semáforo, y el costo de las que esperan limpieza. */
export function resumenCamas(camas, ahora) {
  const porTipo = {};
  const limpieza = { n: 0, costo: 0 };
  for (const c of camas) {
    const t = (porTipo[c.tipo_cama] ||= { total: 0, libre: 0, ocupado: 0, proceso: 0, bloqueado: 0, nombre: c.tipo_nombre });
    t.total++;
    t[infoCama(c.estado_cama).grupo]++;
    if (c.estado_cama === "en_limpieza") {
      limpieza.n++;
      // horas que lleva vacía la cama x lo que cuesta una hora de esa cama
      limpieza.costo += (minutosDesde(c.estado_cama_desde, ahora) / 60) * (Number(c.costo_dia_cop || 0) / 24);
    }
  }
  const suma = (g) => Object.values(porTipo).reduce((s, t) => s + t[g], 0);
  return { porTipo, limpieza, total: camas.length, libres: suma("libre") };
}

/** Minutos de retraso de una cirugía en curso: lo que tardó en empezar
 *  más lo que ya se pasó del tiempo estimado (ese retraso se propaga a la agenda). */
export function retrasoCirugia(actual, ahora) {
  if (!actual) return 0;
  const transcurrido = minutosDesde(actual.hora_real_inicio, ahora);
  const sobretiempo = Math.max(0, transcurrido - (actual.duracion_estimada_min || 0));
  return Math.round(Math.max(0, actual.retraso_inicio_min || 0) + sobretiempo);
}

export const UMBRAL_RETRASO_MIN = 15;
