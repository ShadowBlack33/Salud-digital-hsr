// Acceso a los módulos del Corte 2 (IA, remisiones, facturación, bandeja,
// alertas). Varias de estas rutas todavía las está construyendo el equipo: si
// la API responde que la ruta NO EXISTE, se usan datos de demostración y la
// pantalla lo indica. Cuando la ruta real aparece, se usa sola, sin tocar nada.
//
// Solo cuenta como "ruta inexistente" el 404/405 genérico de FastAPI ("Not
// Found" / "Method Not Allowed"), y solo si VITE_DATOS_DEMO no es "false"
// (ver lib/demo.js). Un 404 propio de un endpoint real (por
// ejemplo "Reporte no encontrado") se muestra como error normal.

import { api, apiBlob } from "../api";
import * as M from "./mocks";
import { normalizarFactura } from "./facturacion";
import { DATOS_DEMO } from "./demo";

const rutaInexistente = (e) => DATOS_DEMO && (
  (e?.status === 404 && e.message === "Not Found") || (e?.status === 405 && e.message === "Method Not Allowed"));

/** GET con respaldo: devuelve { datos, demo }. */
async function leer(ruta, respaldo) {
  try {
    return { datos: await api(ruta), demo: false };
  } catch (e) {
    if (rutaInexistente(e)) return { datos: typeof respaldo === "function" ? respaldo() : respaldo, demo: true };
    throw e;
  }
}

/** POST/PATCH con respaldo: si la ruta no existe, ejecuta `simular` sobre los datos locales. */
async function escribir(ruta, opciones, simular) {
  try {
    return { datos: await api(ruta, opciones), demo: false };
  } catch (e) {
    if (rutaInexistente(e)) return { datos: simular(), demo: true };
    throw e;
  }
}

// La API devuelve listas sueltas o envueltas ({imagenes: [...]}); el contrato
// admite las dos formas.
const lista = (x, clave) => (Array.isArray(x) ? x : x?.[clave] ?? []);

// ------------------------------------------------------------------ bandeja y alertas (R18, R20)
export const notificaciones = async () => {
  const r = await leer("/notificaciones", M.notificaciones);
  return { ...r, datos: lista(r.datos, "notificaciones") };
};
export const leerNotificacion = (id) =>
  escribir(`/notificaciones/${id}/leer`, { method: "POST" }, () => M.marcarLeida(id));
export const pendientes = () => leer("/pendientes", M.pendientes);
export const alertas = async () => {
  const r = await leer("/alertas", M.alertas);
  return { ...r, datos: lista(r.datos, "alertas") };
};
export const reconocerAlerta = (id, nota) =>
  escribir(`/alertas/${id}/reconocer`, { method: "POST", json: { nota } }, () => M.reconocer(id, nota));

// ------------------------------------------------------------------ IA (R10, R12)
export const reportesDePaciente = async (pacienteId) => {
  const r = await leer(`/ia/reportes?paciente_id=${encodeURIComponent(pacienteId)}`, () => M.reportesDe(pacienteId));
  return { ...r, datos: lista(r.datos, "reportes") };
};
export const analizar = (pacienteId, variables) =>
  escribir("/ia/analizar", { method: "POST", json: { paciente_id: pacienteId, ...(variables ? { variables } : {}) } },
    () => M.analizar(pacienteId));
export const reportesPendientes = async () => {
  const r = await leer("/ia/reportes?estado=pendiente", M.reportesPendientes);
  return { ...r, datos: lista(r.datos, "reportes") };
};
export const reporte = (id) => leer(`/ia/reportes/${id}`, () => M.reporte(id));
export const payloadReporte = async (id) => {
  const r = await leer(`/ia/reportes/${id}/payload`, () => M.payload(id));
  return { ...r, datos: r.datos?.payload ?? r.datos };
};
export const decidirReporte = (id, decision, observaciones) =>
  escribir(`/ia/reportes/${id}/${decision}`, { method: "POST", json: { observaciones } },
           () => M.decidir(id, decision, observaciones));

// ------------------------------------------------------------------ remisiones (R08)
export const especialistas = () => leer("/especialistas", M.especialistas);
export const remisiones = async () => {
  const r = await leer("/remisiones", M.remisiones);
  const datos = lista(r.datos, "remisiones");
  return { ...r, datos: r.demo || !DATOS_DEMO ? datos : [...M.remisionesSimuladas(), ...datos] };
};
export const remitir = (datos) =>
  escribir("/remisiones", { method: "POST", json: datos }, () => M.remitir(datos));
export const aceptarRemision = (id) => (String(id).startsWith("sim-")
  ? Promise.resolve({ datos: M.aceptar(id), demo: true })
  : escribir(`/remisiones/${id}/aceptar`, { method: "POST" }, () => M.aceptar(id)));
// Rechazar (con motivo) y cerrar como atendida: solo existen en la API real.
export const rechazarRemision = (id, motivo) => api(`/remisiones/${id}/rechazar`, { method: "POST", json: { motivo } });
export const atenderRemision = (id, motivo) => api(`/remisiones/${id}/atender`, { method: "POST", json: { motivo } });

// ------------------------------------------------------------------ contabilidad (R09)
// La lista puede venir completa (y se filtra aquí) o ya filtrada y paginada
// por la API ({facturas, total}); ver docs/CONTRATO_FACTURACION.md.
export const facturas = async (filtros = {}) => {
  const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v !== "" && v != null));
  const r = await leer(`/contabilidad/facturas${q.size ? `?${q}` : ""}`, M.facturas);
  return { ...r, datos: lista(r.datos, "facturas").map(normalizarFactura), total: r.datos?.total, paginada: !Array.isArray(r.datos) && r.datos?.total != null };
};
export const tarifario = async () => {
  const r = await leer("/contabilidad/tarifario", M.tarifario);
  return { ...r, datos: lista(r.datos, "servicios") };
};
export const crearFactura = (datos) =>
  escribir("/contabilidad/facturas", { method: "POST", json: datos }, () => M.crearFactura(datos));
export const pagarFactura = (id) =>
  escribir(`/contabilidad/facturas/${id}/pagar`, { method: "PATCH" }, () => M.pagar(id));
export const anularFactura = (id, motivo) =>
  escribir(`/contabilidad/facturas/${id}/anular`, { method: "PATCH", json: { motivo } }, () => M.anular(id));

// ------------------------------------------------------------------ historia clínica (R11)
export const historia = (pacienteId) => leer(`/pacientes/${pacienteId}/historia`, () => M.historia(pacienteId));

/** Descarga el PDF con el token (un enlace normal no lo enviaría). */
export async function descargarHistoriaPDF(pacienteId, nombreArchivo = "historia_clinica.pdf") {
  const blob = await apiBlob(`/pacientes/${pacienteId}/historia/pdf`);
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: nombreArchivo });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

// ------------------------------------------------------------------ admin (rutas reales, Corte 2)
export const usuarios = (soloBloqueadas = false) => api(`/usuarios${soloBloqueadas ? "?bloqueadas=true" : ""}`);
export const rolesDisponibles = () => api("/usuarios/roles");
export const crearUsuario = (datos) => api("/usuarios", { method: "POST", json: datos });
export const desbloquear = (id) => api(`/usuarios/${id}/desbloquear`, { method: "POST" });
export const auditoria = ({ operacion, entidad, limite = 100 } = {}) => {
  const q = new URLSearchParams({ limite: String(limite) });
  if (operacion) q.set("operacion", operacion);
  if (entidad) q.set("entidad_tipo", entidad);
  return api(`/auditoria?${q}`);
};

// ------------------------------------------------------------------ vistas por perfil (rutas reales)
export const misPacientes = () => api("/mis-pacientes");
export const misCirugias = (dias = 7) => api(`/mis-cirugias?dias=${dias}`);
export const tableroHospital = () => api("/analitica/hospital");
export const miCuenta = () => api("/mi-cuenta");

// ------------------------------------------------------------------ coordinación quirúrgica
export const cirugiasDia = (fecha) => api(`/cirugias/dia${fecha ? `?fecha=${fecha}` : ""}`);
export const cirugiasCatalogos = () => api("/cirugias/catalogos");
export const programarCirugia = (datos) => api("/cirugias", { method: "POST", json: datos });
export const reprogramarCirugia = (id, datos) => api(`/cirugias/${id}/reprogramar`, { method: "PATCH", json: datos });
export const cancelarCirugia = (id, datos) => api(`/cirugias/${id}/cancelar`, { method: "POST", json: datos });
export const miResumen = () => api("/mi-resumen");
