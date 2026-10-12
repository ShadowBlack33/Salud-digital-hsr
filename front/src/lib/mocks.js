// Datos de DEMOSTRACIÓN para las rutas del Corte 2 que aún no existen en la
// API. Respetan exactamente los campos del contrato (tester.yaml), así que al
// llegar la ruta real la pantalla no cambia. Se guardan en memoria: las
// acciones (aprobar, aceptar, pagar) persisten mientras la pestaña esté abierta.
//
// Todo es ficticio: nombres, documentos y valores son inventados.

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
  facturas: [
    { id: "F-1001", paciente_id: "demo-1", servicio: "analisis_ia", descripcion: "Análisis de IA: predicción de cama UCI", valor: 85000, fecha: haceMin(60 * 26), estado_pago: "pagada", reporte_id: 501 },
    { id: "F-1002", paciente_id: "demo-2", servicio: "consulta", descripcion: "Consulta de urgencias", valor: 145000, fecha: haceMin(90), estado_pago: "pendiente" },
    { id: "F-1003", paciente_id: "demo-3", servicio: "remision", descripcion: "Interconsulta con cirugía cardiovascular", valor: 210000, fecha: haceMin(60 * 20), estado_pago: "pendiente" },
  ],
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
export function agregarRemision(motivo) {
  const r = { id: nuevoId(), paciente_id: "demo-2", paciente_nombre: "Martha Lucía Gómez Varela", medico: "Dra. Sofía Restrepo",
              especialista: "Usted", motivo, estado: "pendiente", created_at: ahora() };
  db.remisiones = [r, ...db.remisiones];
  return r;
}

// --------------------------------------------------------------- facturación
export const facturas = () => db.facturas;
export function crearFactura({ paciente_id, servicio, valor, descripcion }) {
  const f = { id: `F-${nuevoId()}`, paciente_id, servicio, descripcion, valor: Number(valor), fecha: ahora(), estado_pago: "pendiente" };
  db.facturas = [f, ...db.facturas];
  return f;
}
export function agregarFacturaAutomatica() {
  return crearFacturaConReporte(nuevoId());
}
function crearFacturaConReporte(reporteId) {
  const f = { id: `F-${nuevoId()}`, paciente_id: "demo-1", servicio: "analisis_ia", descripcion: "Análisis de IA aprobado por el clínico",
              valor: 85000, fecha: ahora(), estado_pago: "pendiente", reporte_id: reporteId };
  db.facturas = [f, ...db.facturas];
  return f;
}
export function pagar(id) {
  const f = db.facturas.find((x) => x.id === id);
  if (f) f.estado_pago = "pagada";
  return f;
}

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
