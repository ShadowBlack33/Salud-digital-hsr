// Qué ve cada rol (R01, R16). La API es la que autoriza: esto solo decide qué
// pantallas y menús mostrar para no ofrecer botones que van a responder 403.
import { puede } from "../api";

export const MEDICOS = ["medico", "medico_general"];
export const ESPECIALISTAS = ["especialista", "medico_especialista"];
export const CLINICOS = [...MEDICOS, ...ESPECIALISTAS];

export const esMedico = (u) => MEDICOS.includes(u?.rol);
export const esEspecialista = (u) => ESPECIALISTAS.includes(u?.rol);
export const esClinico = (u) => CLINICOS.includes(u?.rol);
export const esAdmin = (u) => u?.rol === "admin";
export const esContable = (u) => u?.rol === "contable";
export const esPaciente = (u) => u?.rol === "paciente";

/** Ruta de inicio de cada rol. */
export function rutaInicio(u) {
  if (esAdmin(u)) return "/app/admin";
  if (esMedico(u)) return "/app/turno";
  if (esEspecialista(u)) return "/app/remisiones";
  if (esContable(u)) return "/app/facturacion";
  if (esPaciente(u)) return "/app/mi-salud";
  if (puede(u, "cama", "read")) return "/app/mando";
  if (puede(u, "paciente", "read")) return "/app/pacientes";
  return "/app/sin-pantalla";
}

/** Entradas del menú: [ruta, etiqueta, clave de ícono]. */
export function menu(u) {
  const items = [];
  if (esAdmin(u)) items.push(["/app/admin", "Administración", "admin"]);
  if (esMedico(u)) items.push(["/app/turno", "Mi turno", "turno"]);
  if (esClinico(u)) items.push(["/app/remisiones", "Remisiones", "remisiones"]);
  if (esContable(u)) items.push(["/app/facturacion", "Facturación", "facturacion"]);
  if (esPaciente(u)) items.push(["/app/mi-salud", "Mi salud", "salud"]);
  if (puede(u, "cama", "read")) items.push(["/app/mando", "Centro de mando", "mando"]);
  if (puede(u, "paciente", "read") && !esPaciente(u)) items.push(["/app/pacientes", "Pacientes", "pacientes"]);
  return items;
}
