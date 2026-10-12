// Modelo de facturación del front: tarifario, coberturas, reparto entre el
// paciente y su entidad, y movimientos de demostración a escala real.
//
// El contrato que el módulo de contabilidad (MongoDB, R09) debe cumplir está
// en docs/CONTRATO_FACTURACION.md. Los campos nuevos son opcionales: si la
// API devuelve solo los mínimos del enunciado (paciente_id, servicio, valor,
// fecha, estado_pago), la pantalla sigue funcionando.

export const TIPOS_COBRO = {
  consulta: "Consultas",
  urgencias: "Urgencias",
  hospitalizacion: "Estancia hospitalaria",
  cirugia: "Cirugía y sala",
  imagenologia: "Imagenología",
  laboratorio: "Laboratorio clínico",
  medicamentos: "Medicamentos",
  insumos: "Insumos y dispositivos",
  terapia: "Terapias",
  ia: "Análisis de IA",
  remision: "Remisiones e interconsultas",
  otros: "Otros",
};

export const ESTADOS_PAGO = {
  pendiente: ["proceso", "Pendiente"],
  radicada: ["proceso", "Radicada a la entidad"],
  glosada: ["bloqueado", "Glosada"],
  pagada: ["libre", "Pagada"],
  anulada: ["bloqueado", "Anulada"],
};

// Tarifario de referencia (valores ilustrativos del caso de estudio, en COP).
export const TARIFARIO = [
  ["890201", "Consulta de medicina general", "consulta", 68000],
  ["890202", "Consulta de medicina especializada", "consulta", 115000],
  ["890203", "Consulta de anestesiología (preanestésica)", "consulta", 98000],
  ["890701", "Consulta de urgencias", "urgencias", 145000],
  ["890702", "Observación en urgencias (hasta 6 h)", "urgencias", 210000],
  ["890703", "Reanimación (triage 1)", "urgencias", 620000],
  ["S12101", "Día cama hospitalización general", "hospitalizacion", 420000],
  ["S12201", "Día cama cuidados intermedios", "hospitalizacion", 950000],
  ["S12301", "Día cama UCI adultos", "hospitalizacion", 1800000],
  ["S12302", "Día cama UCI neonatal", "hospitalizacion", 1900000],
  ["471101", "Apendicectomía", "cirugia", 3200000],
  ["512100", "Colecistectomía laparoscópica", "cirugia", 4800000],
  ["791200", "Osteosíntesis de fémur", "cirugia", 7600000],
  ["361100", "Revascularización miocárdica", "cirugia", 32000000],
  ["S40100", "Derechos de sala de cirugía (hora)", "cirugia", 520000],
  ["S40200", "Derechos de sala de recuperación", "cirugia", 260000],
  ["871121", "Radiografía de tórax (PA y lateral)", "imagenologia", 62000],
  ["879111", "Tomografía de cráneo simple", "imagenologia", 310000],
  ["881302", "Ecografía abdominal total", "imagenologia", 135000],
  ["883210", "Resonancia de columna lumbar", "imagenologia", 720000],
  ["902210", "Hemograma completo", "laboratorio", 28000],
  ["903895", "Creatinina en suero", "laboratorio", 14000],
  ["903864", "Electrolitos (Na, K, Cl)", "laboratorio", 42000],
  ["903825", "Lactato en sangre", "laboratorio", 39000],
  ["903437", "Troponina I ultrasensible", "laboratorio", 96000],
  ["904902", "Gases arteriales", "laboratorio", 88000],
  ["MED001", "Ceftriaxona 1 g ampolla", "medicamentos", 18500],
  ["MED002", "Enoxaparina 40 mg jeringa", "medicamentos", 27400],
  ["MED003", "Noradrenalina 4 mg ampolla", "medicamentos", 41200],
  ["MED004", "Omeprazol 40 mg vial", "medicamentos", 12800],
  ["MED005", "Paracetamol 1 g IV", "medicamentos", 21600],
  ["INS001", "Kit de vía central", "insumos", 312000],
  ["INS002", "Sutura absorbible 3-0", "insumos", 24500],
  ["INS003", "Malla de polipropileno", "insumos", 680000],
  ["931000", "Terapia física (sesión)", "terapia", 54000],
  ["939403", "Terapia respiratoria (sesión)", "terapia", 47000],
  ["IA0001", "Análisis de IA: predicción de cama UCI", "ia", 85000],
  ["890402", "Interconsulta por especialista", "remision", 210000],
  ["890403", "Remisión a especialista (gestión)", "remision", 45000],
  ["S99001", "Certificado e historia clínica", "otros", 18000],
].map(([codigo, nombre, tipo_cobro, valor]) => ({ codigo, nombre, tipo_cobro, valor }));

export const ENTIDADES = [
  { tipo: "particular", entidad: "Particular", regimen: null },
  { tipo: "eps", entidad: "EPS Alfa", regimen: "contributivo" },
  { tipo: "eps", entidad: "EPS Beta", regimen: "contributivo" },
  { tipo: "eps", entidad: "EPS Delta", regimen: "contributivo" },
  { tipo: "eps", entidad: "EPS Gamma", regimen: "subsidiado" },
  { tipo: "eps", entidad: "EPS Epsilon", regimen: "subsidiado" },
  { tipo: "especial", entidad: "Régimen especial", regimen: "especial" },
  { tipo: "soat", entidad: "SOAT (accidente de tránsito)", regimen: null },
  { tipo: "prepagada", entidad: "Medicina prepagada", regimen: null },
];

/** Cuánto paga el paciente y cuánto su entidad (reglas de referencia). */
export function repartir(valor, cobertura, tipoCobro) {
  const v = Number(valor) || 0;
  const t = cobertura?.tipo;
  let paciente;
  if (!t || t === "particular") paciente = v;
  else if (t === "soat" || t === "especial") paciente = 0;
  else if (t === "prepagada") paciente = Math.min(v, 35000);                         // bono
  else if (["consulta", "urgencias"].includes(tipoCobro)) paciente = cobertura.regimen === "subsidiado" ? 0 : 4700; // cuota moderadora
  else paciente = Math.round(v * (cobertura.regimen === "subsidiado" ? 0.10 : 0.115)); // copago
  paciente = Math.min(paciente, v);
  return { valor_paciente: paciente, valor_entidad: v - paciente };
}

export const textoEntidad = (c) => (!c || c.tipo === "particular" ? "Particular" : c.regimen && c.tipo === "eps" ? `${c.entidad} · ${c.regimen}` : c.entidad);

/** Completa una factura que trae solo los campos mínimos del enunciado. */
export function normalizarFactura(f) {
  const tarifa = TARIFARIO.find((t) => t.codigo === f.cups || t.tipo_cobro === f.servicio);
  const tipo_cobro = f.tipo_cobro || (f.servicio === "analisis_ia" ? "ia" : TIPOS_COBRO[f.servicio] ? f.servicio : tarifa?.tipo_cobro || "otros");
  const cobertura = f.cobertura || { tipo: "particular", entidad: "Particular", regimen: null };
  const reparto = f.valor_paciente != null ? { valor_paciente: f.valor_paciente, valor_entidad: f.valor_entidad ?? (f.valor - f.valor_paciente) }
                                           : repartir(f.valor, cobertura, tipo_cobro);
  return { ...f, tipo_cobro, cobertura, ...reparto };
}

// ------------------------------------------------------------- movimientos de demostración
// Un mes de un hospital mediano: ~110 movimientos por día. Determinista (la
// misma semilla siempre da los mismos datos) para que la demo sea repetible.
const NOMBRES = ["María", "José", "Luz", "Carlos", "Ana", "Jorge", "Diana", "Andrés", "Paola", "Luis", "Sandra", "Óscar",
  "Claudia", "Fernando", "Gloria", "Julián", "Martha", "Diego", "Patricia", "Héctor", "Valentina", "Camilo", "Rosa", "Iván"];
const APELLIDOS = ["Gómez", "Rodríguez", "Martínez", "Caicedo", "Valencia", "Mosquera", "Rojas", "Zapata", "Ospina", "Cárdenas",
  "Quintero", "Salazar", "Benítez", "Lozano", "Mina", "Trujillo", "Palacios", "Vásquez", "Ibarra", "Restrepo"];
const PESO_TIPO = [["laboratorio", 26], ["medicamentos", 22], ["consulta", 12], ["urgencias", 8], ["imagenologia", 8],
  ["insumos", 7], ["hospitalizacion", 6], ["terapia", 4], ["cirugia", 3], ["remision", 2], ["ia", 1], ["otros", 1]];
const PESO_ENTIDAD = [[0, 12], [1, 20], [2, 14], [3, 12], [4, 18], [5, 10], [6, 6], [7, 4], [8, 4]];

function azar(semilla) {
  let s = semilla >>> 0;
  return () => { s = (s + 0x6d2b79f5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const ponderado = (r, pares) => { const total = pares.reduce((s, [, p]) => s + p, 0); let x = r() * total; for (const [v, p] of pares) { if ((x -= p) < 0) return v; } return pares[0][0]; };

export function generarMovimientos(dias = 30, porDia = 110, semilla = 2026) {
  const r = azar(semilla);
  const pacientes = Array.from({ length: 900 }, (_, i) => {
    const doc = String(10_000_000 + Math.floor(r() * 89_999_999));
    return { paciente_id: `demo-${i + 1}`, paciente_nombre: `${NOMBRES[Math.floor(r() * NOMBRES.length)]} ${APELLIDOS[Math.floor(r() * APELLIDOS.length)]}`,
             paciente_documento: `****${doc.slice(-4)}`, cobertura: ENTIDADES[ponderado(r, PESO_ENTIDAD)] };
  });
  const lista = [];
  const ahora = Date.now();
  let n = 0;
  for (let d = 0; d < dias; d++) {
    const cuantos = Math.round(porDia * (0.8 + r() * 0.4));
    for (let k = 0; k < cuantos; k++) {
      const p = pacientes[Math.floor(r() * pacientes.length)];
      const tipo = ponderado(r, PESO_TIPO);
      const opciones = TARIFARIO.filter((t) => t.tipo_cobro === tipo);
      const t = opciones[Math.floor(r() * opciones.length)];
      const cantidad = ["medicamentos", "insumos", "hospitalizacion", "terapia"].includes(tipo) ? 1 + Math.floor(r() * 4) : 1;
      const valor = t.valor * cantidad;
      const fecha = new Date(ahora - d * 864e5 - Math.floor(r() * 864e5 * (d === 0 ? 0.6 : 1)));
      const viejo = d > 3;
      let estado = "pendiente";
      const x = r();
      if (p.cobertura.tipo === "particular") estado = x < (viejo ? 0.88 : 0.55) ? "pagada" : x < 0.95 ? "pendiente" : "anulada";
      else estado = viejo ? (x < 0.52 ? "pagada" : x < 0.86 ? "radicada" : x < 0.95 ? "glosada" : "anulada") : (x < 0.7 ? "pendiente" : x < 0.96 ? "radicada" : "anulada");
      lista.push({
        id: `F-${String(250000 + ++n)}`, ...p, servicio: tipo, tipo_cobro: tipo, cups: t.codigo, descripcion: t.nombre,
        cantidad, valor_unitario: t.valor, valor, fecha: fecha.toISOString(), estado_pago: estado,
        origen: tipo === "ia" ? "automatica" : "manual", ...(tipo === "ia" ? { reporte_id: 400 + n } : {}),
        ...repartir(valor, p.cobertura, tipo),
      });
    }
  }
  return lista.sort((a, b) => (a.fecha < b.fecha ? 1 : -1));
}
