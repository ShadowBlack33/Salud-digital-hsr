// Aviso sonoro breve para alertas críticas (dos tonos, sin archivos de audio).
// Los navegadores solo permiten sonar después de que la persona interactuó con
// la página; antes de eso, falla en silencio.
let contexto = null;

export function sonarAlerta() {
  try {
    contexto ??= new (window.AudioContext || window.webkitAudioContext)();
    const t = contexto.currentTime;
    [[880, 0], [660, 0.18]].forEach(([frecuencia, inicio]) => {
      const osc = contexto.createOscillator();
      const vol = contexto.createGain();
      osc.type = "sine";
      osc.frequency.value = frecuencia;
      vol.gain.setValueAtTime(0.0001, t + inicio);
      vol.gain.exponentialRampToValueAtTime(0.18, t + inicio + 0.02);
      vol.gain.exponentialRampToValueAtTime(0.0001, t + inicio + 0.16);
      osc.connect(vol).connect(contexto.destination);
      osc.start(t + inicio);
      osc.stop(t + inicio + 0.18);
    });
  } catch { /* sin audio disponible */ }
}

/** Notificación del sistema operativo si la pestaña no está a la vista. */
export function notificarEscritorio(titulo, cuerpo) {
  try {
    if (!("Notification" in window) || Notification.permission !== "granted" || !document.hidden) return;
    new Notification(titulo, { body: cuerpo, tag: "hsr-alerta", icon: "/favicon.svg" });
  } catch { /* algunos navegadores no la permiten fuera de un service worker */ }
}

export const permisoEscritorio = () => ("Notification" in window ? Notification.permission : "no-soportado");
export const pedirPermisoEscritorio = async () => ("Notification" in window ? Notification.requestPermission() : "no-soportado");
