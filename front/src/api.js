// Cliente de la API.
//
// Sesión: el token de acceso dura 15 minutos y el de renovación 7 días. Cuando
// una petición recibe 401, se renueva el par una sola vez (aunque fallen varias
// peticiones a la vez) y se repite. Si la renovación también falla, la sesión
// se cierra y la pantalla vuelve al login. Sin esto, un tablero en vivo dejaba
// de funcionar a los 15 minutos.

export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const K = { access: "hsr_access", refresh: "hsr_refresh", usuario: "hsr_usuario" };

export class ApiError extends Error {
  constructor(status, data, mensaje) {
    super(mensaje);
    this.status = status;
    this.data = data;
  }
}

// ---- Sesión como un pequeño almacén al que los componentes se suscriben
const oyentes = new Set();
let usuario = (() => {
  try { return JSON.parse(localStorage.getItem(K.usuario)); } catch { return null; }
})();

export const suscribirSesion = (fn) => { oyentes.add(fn); return () => oyentes.delete(fn); };
export const getUsuario = () => usuario;
export const estaAutenticado = () => !!localStorage.getItem(K.access);

function cambiarUsuario(u) {
  usuario = u;
  if (u) localStorage.setItem(K.usuario, JSON.stringify(u));
  else localStorage.removeItem(K.usuario);
  oyentes.forEach((fn) => fn());
}

function guardarTokens(t) {
  localStorage.setItem(K.access, t.access_token);
  if (t.refresh_token) localStorage.setItem(K.refresh, t.refresh_token);
}

function cerrarSesionLocal() {
  localStorage.removeItem(K.access);
  localStorage.removeItem(K.refresh);
  cambiarUsuario(null);
}

/** ¿Tiene el usuario algún permiso 'recurso:accion:*'? (p. ej. puede(u, 'cama', 'update')) */
export const puede = (u, recurso, accion) =>
  !!u?.permisos?.some((p) => p.startsWith(`${recurso}:${accion}:`) || p === `${recurso}:${accion}`);

// ---- Peticiones
async function leerCuerpo(r) {
  if (r.status === 204) return null;
  const tipo = r.headers.get("content-type") || "";
  return tipo.includes("json") ? r.json().catch(() => null) : r.text().catch(() => null);
}

function comoError(r, cuerpo) {
  let detalle = "Error inesperado";
  if (typeof cuerpo === "string" && cuerpo) detalle = cuerpo;
  else if (typeof cuerpo?.detail === "string") detalle = cuerpo.detail;
  else if (Array.isArray(cuerpo?.detail)) detalle = cuerpo.detail.map((d) => d.msg).join("; ");
  return new ApiError(r.status, cuerpo && typeof cuerpo === "object" ? cuerpo : null, detalle);
}

let renovando = null;
function renovar() {
  if (renovando) return renovando;
  const rt = localStorage.getItem(K.refresh);
  if (!rt) return Promise.resolve(false);
  renovando = fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: rt }),
  })
    .then(async (r) => {
      if (!r.ok) return false;
      guardarTokens(await r.json());
      return true;
    })
    .catch(() => false)
    .finally(() => { renovando = null; });
  return renovando;
}

async function pedir(ruta, { json, ...opciones } = {}, reintentar = true) {
  const token = localStorage.getItem(K.access);
  const headers = {
    ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...opciones.headers,
  };
  let r;
  try {
    r = await fetch(API_BASE + ruta, {
      ...opciones,
      headers,
      body: json !== undefined ? JSON.stringify(json) : opciones.body,
    });
  } catch {
    throw new ApiError(0, null, "No se pudo conectar con el servidor");
  }
  if (r.status === 401 && reintentar && token) {
    if (await renovar()) return pedir(ruta, { json, ...opciones }, false);
    cerrarSesionLocal();
  }
  return r;
}

/** Petición JSON autenticada. `json` = cuerpo a enviar. Lanza ApiError si falla. */
export async function api(ruta, opciones) {
  const r = await pedir(ruta, opciones);
  const cuerpo = await leerCuerpo(r);
  if (!r.ok) throw comoError(r, cuerpo);
  return cuerpo;
}

/** Descarga un recurso binario (una imagen). Un <img src> no puede mandar el
 *  header Authorization, por eso se descarga así y se muestra desde un blob. */
export async function apiBlob(ruta) {
  const r = await pedir(ruta);
  if (!r.ok) throw new ApiError(r.status, null, `No se pudo cargar (${r.status})`);
  return r.blob();
}

/** Estado de los servicios (no requiere sesión). */
export async function salud() {
  const r = await fetch(`${API_BASE}/salud`);
  if (!r.ok) throw new ApiError(r.status, null, "sin respuesta");
  return r.json();
}

export async function login(username, password) {
  let r;
  try {
    r = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
  } catch {
    throw new ApiError(0, null, "No se pudo conectar con el servidor");
  }
  const cuerpo = await leerCuerpo(r);
  if (!r.ok) throw comoError(r, cuerpo); // .data trae intentos_restantes y bloqueado_hasta
  guardarTokens(cuerpo);
  const yo = await api("/auth/yo");
  cambiarUsuario(yo);
  return yo;
}

export async function cerrarSesion() {
  const rt = localStorage.getItem(K.refresh);
  if (rt) {
    try { await pedir("/auth/logout", { method: "POST", json: { refresh_token: rt } }, false); } catch { /* da igual */ }
  }
  cerrarSesionLocal();
}
