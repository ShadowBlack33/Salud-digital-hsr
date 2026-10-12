// Nombres en español de lo clínico que llega con códigos estándar.

const LOINC = {
  "59408-5": "SpO₂", "2708-6": "SpO₂", "8480-6": "Presión sistólica", "8462-4": "Presión diastólica",
  "8867-4": "Frecuencia cardiaca", "9279-1": "Frecuencia respiratoria", "8310-5": "Temperatura",
  "2524-7": "Lactato", "2823-3": "Potasio", "2339-0": "Glucosa", "718-7": "Hemoglobina",
  "2160-0": "Creatinina", "6598-7": "Troponina",
};
const UNIDAD = { "mm[Hg]": "mmHg", Cel: "°C", "/min": "/min" };

/** "SpO₂ 84 %" a partir de una observación {codigo_loinc, nombre, valor, unidad}. */
export function valorClinico(o) {
  const nombre = LOINC[o.codigo_loinc] || o.nombre || o.codigo_loinc;
  const v = typeof o.valor === "number" ? (Number.isInteger(o.valor) ? o.valor : o.valor.toFixed(1)) : o.valor;
  return `${nombre} ${v}${o.unidad ? ` ${UNIDAD[o.unidad] || o.unidad}` : ""}`.replace(" %", " %");
}

export const TIPO_ENCUENTRO = {
  urgencias: "Urgencias", hospitalizacion: "Hospitalizado", cirugia: "Cirugía", consulta_externa: "Consulta externa",
};
export const ESTADO_CIRUGIA = {
  planned: "Programada", "in-progress": "En cirugía", finished: "Terminada", cancelled: "Cancelada",
};

/** Etiqueta de cobertura: "Particular", "EPS Alfa · contributivo". */
export function textoCobertura(c) {
  if (!c) return "—";
  if (c.tipo === "particular") return "Particular";
  return c.regimen ? `${c.entidad} · ${c.regimen}` : c.entidad;
}
