// Cliente de la API. La URL viene de una variable de entorno de Vite, así
// que el mismo build sirve en local, en Docker o en producción sin tocar código.
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

let token = localStorage.getItem("hsr_token") || null;
let usuario = JSON.parse(localStorage.getItem("hsr_usuario") || "null");

export function getUsuario() {
  return usuario;
}

export function estaAutenticado() {
  return !!token;
}

export function cerrarSesion() {
  token = null;
  usuario = null;
  localStorage.removeItem("hsr_token");
  localStorage.removeItem("hsr_usuario");
}

async function manejarRespuesta(r) {
  if (r.status === 204) return null;
  const contentType = r.headers.get("content-type") || "";
  const cuerpo = contentType.includes("application/json") ? await r.json() : await r.text();
  if (!r.ok) {
    const detalle = typeof cuerpo === "string" ? cuerpo : cuerpo.detail || JSON.stringify(cuerpo);
    const error = new Error(detalle);
    error.status = r.status;
    throw error;
  }
  return cuerpo;
}

// Login. Devuelve el error del backend tal cual (incluye el 423 de bloqueo,
// con la fecha/hora hasta la que la cuenta queda bloqueada).
export async function login(username, password) {
  const r = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const datos = await manejarRespuesta(r);
  token = datos.access_token;
  localStorage.setItem("hsr_token", token);

  const yo = await api("/auth/yo");
  usuario = yo;
  localStorage.setItem("hsr_usuario", JSON.stringify(yo));
  return yo;
}

// Fetch autenticado genérico para JSON.
export async function api(ruta, opciones = {}) {
  const r = await fetch(`${API_BASE}${ruta}`, {
    ...opciones,
    headers: {
      ...(opciones.body && !(opciones.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...opciones.headers,
    },
  });
  return manejarRespuesta(r);
}

// Descarga un recurso binario (una imagen) autenticado y lo devuelve como
// blob. Un <img src="..."> normal no puede mandar el header Authorization,
// por eso se descarga así y se muestra desde una URL temporal.
export async function apiBlob(ruta) {
  const r = await fetch(`${API_BASE}${ruta}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!r.ok) {
    const error = new Error(`No se pudo cargar la imagen (${r.status})`);
    error.status = r.status;
    throw error;
  }
  return r.blob();
}

export { API_BASE };
