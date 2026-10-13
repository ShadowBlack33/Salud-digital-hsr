// Datos de DEMOSTRACIÓN para las rutas del Corte 2 que aún no existen en la
// API. Respetan exactamente los campos del contrato (tester.yaml), así que al
// llegar la ruta real la pantalla no cambia. Se guardan en memoria: las
// acciones (aprobar, aceptar, pagar) persisten mientras la pestaña esté abierta.
//
// Todo es ficticio: nombres, documentos y valores son inventados.

import { generarMovimientos, repartir, TARIFARIO } from "./facturacion";

const ahora = () => new Date().toISOString();
const haceMin = (m) => new Date(Date.now() - m * 60000).toISOString();
let sec = 2000;   // por encima de los ids sembrados abajo, para no repetirlos
const nuevoId = () => ++sec;

const db = {
  // Arranca vacía: la llenan los eventos del panel de demostración, para no
  // mostrar avisos clínicos a roles que no deben verlos (paciente, contable).
  notificaciones: [],
  alertas: [],
  reportes: [
    { id: 501, paciente_id: "demo-1", estado: "aprobado", probabilidad: 0.82, clase: "requiere_uci", critico: false,
      observaciones: "Coincide con la valoración preanestésica. Se reserva cama UCI.", created_at: haceMin(60 * 26) },
  ],
  remisiones: [
    { id: 301, paciente_id: "demo-1", paciente_nombre: "Juan Fernando Pérez Caicedo", medico: "Dra. Sofía Restrepo",
      especialista: "Dr. Alejandro Caicedo", motivo: "Valoración por cirugía cardiovascular antes del reemplazo valvular.",
      estado: "pendiente", created_at: haceMin(12) },
  ],
  // Un mes de movimientos (~3.300), generados la primera vez que se piden.
  facturas: null,
};

export const especialistas = () => [
  { id: 2, nombre: "Dr. Alejandro Caicedo", especialidad: "Cirugía cardiovascular" },
  { id: 3, nombre: "Dra. Paula Andrea Zúñiga", especialidad: "Neurocirugía" },
  { id: 4, nombre: "Dr. Hernando Paz", especialidad: "Anestesiología" },
];

// --------------------------------------------------------------- bandeja y alertas
export const notificaciones = () => db.notificaciones;
export function marcarLeida(id) {
  const n = db.notificaciones.find((x) => x.id === id);
  if (n) n.leida = true;
  return n;
}
export function agregarNotificacion(evento) {
  const n = { id: nuevoId(), leida: false, fecha: evento.fecha || ahora(), ...evento };
  db.notificaciones = [n, ...db.notificaciones];
  return n;
}
export const pendientes = () => ({
  reportes_por_revisar: db.reportes.filter((r) => r.estado === "pendiente").length,
  remisiones_recibidas: db.remisiones.filter((r) => r.estado === "pendiente").length,
  alertas_activas: db.alertas.filter((a) => a.estado === "activa").length,
});
export const alertas = () => db.alertas;
export function agregarAlerta({ paciente_id = "demo-1", mensaje, nivel = "critico" }) {
  const a = { id: nuevoId(), paciente_id, nivel, estado: "activa", mensaje, created_at: ahora() };
  db.alertas = [a, ...db.alertas];
  return a;
}
export function reconocer(id, nota) {
  const a = db.alertas.find((x) => x.id === id);
  if (a) Object.assign(a, { estado: "reconocida", nota });
  return a;
}

// --------------------------------------------------------------- IA
export const reportesPendientes = () => db.reportes.filter((r) => r.estado === "pendiente");
export const reportesDe = (pacienteId) => db.reportes.filter((r) => r.paciente_id === pacienteId);
export const reporte = (id) => db.reportes.find((r) => r.id === Number(id));
export function analizar(pacienteId) {
  const probabilidad = Math.round((0.35 + Math.random() * 0.6) * 100) / 100;
  const r = {
    id: nuevoId(), paciente_id: pacienteId, estado: "pendiente", probabilidad,
    clase: probabilidad >= 0.5 ? "requiere_uci" : "no_requiere_uci", critico: probabilidad >= 0.9,
    observaciones: null, created_at: ahora(),
    _payload: {
      pseudo_id: `p_${Math.random().toString(16).slice(2, 18)}`,
      variables: { edad: 64, sexo: "F", imc: 31.2, asa: 3, emergencia: 0, glucosa_preop: 142, albumina_preop: 3.4, hemoglobina_preop: 11.8, procedimiento: "cardiovascular" },
    },
  };
  db.reportes = [r, ...db.reportes];
  return { id: r.id, estado: r.estado };
}
export const payload = (id) => ({ payload: reporte(id)?._payload ?? null });
export function decidir(id, decision, observaciones) {
  const r = reporte(id);
  if (r) Object.assign(r, { estado: decision === "aprobar" ? "aprobado" : "rechazado", observaciones });
  // Simula el reactor del backend (R19): aprobar crea sola la factura ligada al reporte.
  if (r && decision === "aprobar" && !db.facturas.some((f) => f.reporte_id === r.id)) crearFacturaConReporte(r.id);
  return r;
}

// --------------------------------------------------------------- remisiones
export const remisiones = () => db.remisiones;
export function remitir({ paciente_id, especialista_id, motivo }) {
  const esp = especialistas().find((e) => e.id === Number(especialista_id));
  const r = { id: nuevoId(), paciente_id, paciente_nombre: "Paciente remitido", medico: "Usted",
              especialista: esp?.nombre ?? "Especialista", motivo, estado: "pendiente", created_at: ahora() };
  db.remisiones = [r, ...db.remisiones];
  return { id: r.id };
}
export function aceptar(id) {
  const r = db.remisiones.find((x) => x.id === id);
  if (r) r.estado = "aceptada";
  return r;
}
// Remisiones que llegan desde el panel de demostración: se muestran junto a
// las reales (id "sim-…") para ensayar el aviso en vivo sin tocar la base.
export const remisionesSimuladas = () => db.remisiones.filter((r) => String(r.id).startsWith("sim-"));
export function agregarRemision(motivo) {
  const r = { id: `sim-${nuevoId()}`, paciente_id: "demo-2", paciente_nombre: "Martha Lucía Gómez Varela", medico: "Dra. Sofía Restrepo",
              especialista: "Usted", motivo, estado: "pendiente", created_at: ahora() };
  db.remisiones = [r, ...db.remisiones];
  return r;
}

// --------------------------------------------------------------- facturación
const listaFacturas = () => (db.facturas ??= generarMovimientos());
export const facturas = () => listaFacturas();
export const tarifario = () => TARIFARIO;
export function crearFactura(datos) {
  const f = { id: `F-${nuevoId()}`, fecha: ahora(), estado_pago: "pendiente", origen: "manual", ...datos, valor: Number(datos.valor) };
  db.facturas = [f, ...listaFacturas()];
  return f;
}
export function agregarFacturaAutomatica() {
  return crearFacturaConReporte(nuevoId());
}
function crearFacturaConReporte(reporteId) {
  const cobertura = { tipo: "eps", entidad: "EPS Alfa", regimen: "contributivo" };
  const f = { id: `F-${nuevoId()}`, paciente_id: "demo-1", paciente_nombre: "Juan Fernando Pérez", paciente_documento: "****4521",
              servicio: "analisis_ia", tipo_cobro: "ia", cups: "IA0001", descripcion: "Análisis de IA aprobado por el clínico",
              cantidad: 1, valor_unitario: 85000, valor: 85000, cobertura, ...repartir(85000, cobertura, "ia"),
              fecha: ahora(), estado_pago: "pendiente", origen: "automatica", reporte_id: reporteId };
  db.facturas = [f, ...listaFacturas()];
  return f;
}
const cambiarEstado = (id, estado) => {
  const f = listaFacturas().find((x) => x.id === id);
  if (f) f.estado_pago = estado;
  return f;
};
export const pagar = (id) => cambiarEstado(id, "pagada");
export const anular = (id) => cambiarEstado(id, "anulada");

// --------------------------------------------------------------- historia
export const historia = (pacienteId) => ({
  paciente_id: pacienteId,
  encuentros: [
    { id: 1, tipo: "cirugia", estado: "programado", descripcion: "Reemplazo valvular aórtico", fecha: new Date(Date.now() + 2 * 864e5).toISOString(), lugar: "Quirófano 4" },
    { id: 2, tipo: "consulta", estado: "finalizado", descripcion: "Consulta preanestésica", fecha: haceMin(60 * 24 * 14), lugar: "Consulta externa" },
  ],
  observaciones: [],
  reportes_ia: db.reportes.filter((r) => r.paciente_id === pacienteId && r.estado === "aprobado"),
});
