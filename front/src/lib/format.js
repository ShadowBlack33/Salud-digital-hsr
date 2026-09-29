const pesos = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });
export const cop = (n) => pesos.format(Math.round(Number(n) || 0));

/** 47 -> "47 min", 130 -> "2 h 10 min", 3000 -> "2 d 2 h" */
export function duracion(min) {
  min = Math.max(0, Math.round(min));
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} h ${String(min % 60).padStart(2, "0")} min`;
  return `${Math.floor(h / 24)} d ${h % 24} h`;
}

/** Minutos transcurridos desde una fecha ISO hasta `ahora` (ms). */
export const minutosDesde = (iso, ahora) => (iso ? Math.max(0, (ahora - Date.parse(iso)) / 60000) : 0);

const hora12 = new Intl.DateTimeFormat("es-CO", { hour: "numeric", minute: "2-digit" });
const hora12s = new Intl.DateTimeFormat("es-CO", { hour: "numeric", minute: "2-digit", second: "2-digit" });
export const hora = (isoOMs) => hora12.format(new Date(isoOMs));
export const horaConSegundos = (isoOMs) => hora12s.format(new Date(isoOMs));

/** "****4567": en los listados el documento nunca aparece completo. */
export const enmascarar = (doc) => (doc ? `****${String(doc).slice(-4)}` : "—");

export function edad(fechaNacimiento) {
  if (!fechaNacimiento) return null;
  const n = new Date(fechaNacimiento), hoy = new Date();
  let e = hoy.getFullYear() - n.getFullYear();
  if (hoy.getMonth() < n.getMonth() || (hoy.getMonth() === n.getMonth() && hoy.getDate() < n.getDate())) e--;
  return e;
}

/** Edad legible: los recién nacidos se cuentan en días, no en "0 años". */
export function edadLegible(fechaNacimiento) {
  if (!fechaNacimiento) return "—";
  const dias = Math.floor((Date.now() - new Date(fechaNacimiento).getTime()) / 86400000);
  if (dias < 60) return `${dias} días`;
  const e = edad(fechaNacimiento);
  return e < 2 ? `${Math.floor(dias / 30)} meses` : `${e} años`;
}

export const iniciales = (texto = "") =>
  texto.trim().split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() || "").join("");
