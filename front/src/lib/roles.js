// Qué ve cada perfil (R01, R16). La API es la que autoriza: esto solo decide
// qué pantallas y menús mostrar. Cada perfil recibe lo que necesita para su
// trabajo y nada más: un especialista no necesita el tablero de 13 quirófanos,
// necesita saber si SU paciente está en cirugía.
import { puede } from "../api";

export const esMedico = (u) => u?.rol === "medico";
export const esEspecialista = (u) => u?.rol === "especialista";
export const esClinico = (u) => esMedico(u) || esEspecialista(u);
export const esAdmin = (u) => u?.rol === "admin";
export const esContable = (u) => u?.rol === "contable";
export const esPaciente = (u) => u?.rol === "paciente";
export const esCoordinador = (u) => u?.rol === "coordinador";
export const esJefeEnfermeria = (u) => u?.rol === "enfermero_jefe";
export const programaCirugias = (u) => puede(u, "agenda", "update");

/** Ruta de inicio de cada perfil. */
export function rutaInicio(u) {
  if (esAdmin(u)) return "/app/admin";
  if (esCoordinador(u)) return "/app/hospital";
  if (esMedico(u)) return "/app/turno";
  if (esEspecialista(u)) return "/app/remisiones";
  if (esContable(u)) return "/app/facturacion";
  if (esPaciente(u)) return "/app/mi-salud";
  if (programaCirugias(u)) return "/app/cirugias";
  if (puede(u, "cama", "read")) return "/app/mando";
  if (puede(u, "paciente", "read")) return "/app/pacientes";
  return "/app/sin-pantalla";
}

/** Entradas del menú: [ruta, etiqueta, clave de ícono]. */
export function menu(u) {
  // El admin ve todo el sistema: administración y auditoría, rendimiento, y las
  // pantallas de cada perfil (la API ya le da alcance total).
  if (esAdmin(u)) return [["/app/admin", "Admin", "admin"], ["/app/rendimiento", "Rendimiento", "rendimiento"],
                          ["/app/hospital", "Hospital", "hospital"], ["/app/cirugias", "Cirugías", "cirugias"],
                          ["/app/mando", "Mando", "mando"], ["/app/pacientes", "Pacientes", "pacientes"],
                          ["/app/remisiones", "Remisiones", "remisiones"], ["/app/facturacion", "Facturación", "facturacion"]];
  if (esCoordinador(u)) return [["/app/hospital", "Hospital", "hospital"]];
  if (esMedico(u)) return [["/app/turno", "Mi turno", "turno"], ["/app/mis-pacientes", "Mis pacientes", "pacientes"],
                           ["/app/remisiones", "Remisiones", "remisiones"]];
  if (esEspecialista(u)) return [["/app/remisiones", "Remisiones", "remisiones"], ["/app/mis-pacientes", "Mis pacientes", "pacientes"],
                                 ["/app/mis-cirugias", "Mis cirugías", "cirugias"]];
  if (esContable(u)) return [["/app/facturacion", "Facturación", "facturacion"]];
  if (esPaciente(u)) return [["/app/mi-salud", "Mi salud", "salud"]];
  // Enfermería jefe y los perfiles operativos del Corte 1.
  const items = [];
  if (programaCirugias(u)) items.push(["/app/cirugias", "Cirugías", "cirugias"]);
  if (puede(u, "cama", "read")) items.push(["/app/mando", "Centro de mando", "mando"]);
  if (puede(u, "paciente", "read")) items.push(["/app/pacientes", "Pacientes", "pacientes"]);
  return items;
}
