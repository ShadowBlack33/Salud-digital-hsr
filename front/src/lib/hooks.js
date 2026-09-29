import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { getUsuario, suscribirSesion } from "../api";

/** Usuario de la sesión actual (se actualiza al iniciar y cerrar sesión). */
export const useUsuario = () => useSyncExternalStore(suscribirSesion, getUsuario);

/** Reloj compartido: devuelve Date.now() y se actualiza cada `ms`. */
export function useReloj(ms = 30000) {
  const [t, setT] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setT(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return t;
}

/** Ejecuta `cargar` de inmediato y luego cada `ms`. Se pausa con la pestaña oculta. */
export function useSondeo(cargar, ms = 15000) {
  const [estado, setEstado] = useState({ datos: null, error: null, cargando: true, actualizado: null });
  const cargarRef = useRef(cargar);
  useEffect(() => { cargarRef.current = cargar; });
  const montado = useRef(true);

  const recargar = useCallback(async () => {
    try {
      const datos = await cargarRef.current();
      if (montado.current) setEstado({ datos, error: null, cargando: false, actualizado: Date.now() });
    } catch (error) {
      if (montado.current) setEstado((e) => ({ ...e, error, cargando: false }));
    }
  }, []);

  useEffect(() => {
    montado.current = true;
    const tick = () => { if (!document.hidden) recargar(); };
    tick();
    const id = setInterval(tick, ms);
    document.addEventListener("visibilitychange", tick);
    return () => {
      montado.current = false;
      clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [ms, recargar]);

  return { ...estado, recargar };
}

/** Marca `visible` la primera vez que el elemento entra en pantalla. */
export function useAparicion(umbral = 0.15) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!("IntersectionObserver" in window)) { setVisible(true); return; }
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { setVisible(true); io.disconnect(); }
    }, { threshold: umbral });
    io.observe(el);
    return () => io.disconnect();
  }, [umbral]);
  return [ref, visible];
}

/** Número que sube de 0 a `meta` cuando `activo` pasa a true. */
export function useContador(meta, activo, ms = 1400) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (!activo) return;
    const reducido = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reducido) { setV(meta); return; }
    let raf;
    const t0 = performance.now();
    const paso = (ahora) => {
      const p = Math.min(1, (ahora - t0) / ms);
      setV(meta * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(paso);
    };
    raf = requestAnimationFrame(paso);
    return () => cancelAnimationFrame(raf);
  }, [meta, activo, ms]);
  return v;
}
