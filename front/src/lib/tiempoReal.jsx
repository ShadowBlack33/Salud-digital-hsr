// Canal en vivo del front (R16, R17, R18, R20).
//
// Abre el canal SSE de la API (`/eventos/stream?token=...`). El navegador no
// puede mandar el header Authorization en un EventSource, por eso el token
// viaja en la URL, como permite el enunciado. Cada evento que llega:
//   1. se avisa en pantalla,
//   2. vuelve a pedir bandeja, contadores y alertas (la API es la fuente de
//      verdad: el evento solo dice "algo cambió"),
//   3. se reparte a las pantallas suscritas (por ejemplo, Facturación recarga
//      su tabla cuando llega `factura_creada`).
//
// Nada de esto usa sondeo: sin eventos, no hay peticiones.
//
// simularEvento() es el respaldo de demostración: modifica los datos locales
// (lib/mocks.js) y dispara el mismo flujo, para ensayar mientras el canal real
// no exista.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE, tokenActual } from "../api";
import { useAvisos } from "../components/Avisos";
import * as S from "./servicios";
import * as M from "./mocks";
import { notificarEscritorio, sonarAlerta } from "./sonido";

const Contexto = createContext(null);
export const useTiempoReal = () => useContext(Contexto);

/** Suscribe una pantalla a los eventos en vivo mientras esté montada. */
export function useEventos(alRecibir) {
  const ctx = useTiempoReal();
  const ref = useRef(alRecibir);
  useEffect(() => { ref.current = alRecibir; });
  useEffect(() => ctx?.suscribir((ev) => ref.current(ev)), [ctx]);
}

export function ProveedorTiempoReal({ children }) {
  const { avisar } = useAvisos();
  const [estado, setEstado] = useState({
    notificaciones: [], pendientes: { reportes_por_revisar: 0, remisiones_recibidas: 0, alertas_activas: 0 },
    alertas: [], demo: false,
  });
  const [conectado, setConectado] = useState(false);
  const oyentes = useRef(new Set());

  const refrescar = useCallback(async () => {
    const [n, p, a] = await Promise.allSettled([S.notificaciones(), S.pendientes(), S.alertas()]);
    setEstado((e) => ({
      notificaciones: n.status === "fulfilled" ? n.value.datos : e.notificaciones,
      pendientes: p.status === "fulfilled" ? p.value.datos : e.pendientes,
      // Un 403 (roles sin alertas, como paciente o contable) deja la lista vacía.
      alertas: a.status === "fulfilled" ? a.value.datos : [],
      demo: [n, p, a].some((r) => r.status === "fulfilled" && r.value.demo),
    }));
  }, []);

  const despachar = useCallback((ev) => {
    const urgente = /alerta|critic/i.test(ev?.tipo || "");
    if (ev?.mensaje) avisar(ev.mensaje, urgente || /bloque/i.test(ev.tipo) ? "alerta" : "ok");
    if (urgente) {
      sonarAlerta();
      notificarEscritorio("Alerta crítica · Pulso", ev.mensaje || "Hay un caso crítico por revisar.");
    }
    refrescar();
    oyentes.current.forEach((fn) => fn(ev));
  }, [avisar, refrescar]);

  // Hitos del guion de demostración (acciones locales que no llegan como evento).
  const marcarHito = useCallback((tipo) => oyentes.current.forEach((fn) => fn({ tipo, local: true })), []);

  // Conexión SSE con reconexión progresiva (5 s, 10 s, ... hasta 30 s).
  useEffect(() => {
    let es = null, espera = 5000, temporizador = null, vivo = true;
    const abrir = () => {
      const token = tokenActual();
      if (!token || !vivo) return;
      es = new EventSource(`${API_BASE}/eventos/stream?token=${encodeURIComponent(token)}`);
      es.onopen = () => { setConectado(true); espera = 5000; };
      es.onmessage = (m) => {
        try { despachar(JSON.parse(m.data)); } catch { /* evento mal formado: se ignora */ }
      };
      es.onerror = () => {
        // Token vencido o ruta aún inexistente: se cierra y se reintenta con el
        // token que tenga la sesión en ese momento (api.js lo renueva solo).
        setConectado(false);
        es.close();
        if (vivo) temporizador = setTimeout(abrir, espera);
        espera = Math.min(espera * 2, 30000);
      };
    };
    refrescar();
    abrir();
    return () => { vivo = false; clearTimeout(temporizador); es?.close(); };
  }, [despachar, refrescar]);

  const suscribir = useCallback((fn) => { oyentes.current.add(fn); return () => oyentes.current.delete(fn); }, []);

  const marcarLeida = useCallback(async (id) => {
    setEstado((e) => ({ ...e, notificaciones: e.notificaciones.map((n) => (n.id === id ? { ...n, leida: true } : n)) }));
    try { await S.leerNotificacion(id); } catch { refrescar(); }
  }, [refrescar]);

  const reconocer = useCallback(async (id, nota) => {
    await S.reconocerAlerta(id, nota);
    await refrescar();
  }, [refrescar]);

  /** Solo para el panel de demostración: imita lo que haría el backend. */
  const simularEvento = useCallback((tipo) => {
    const f = new Date().toISOString();
    const eventos = {
      remision_nueva: () => {
        const r = M.agregarRemision("Paciente con estenosis aórtica severa: valoración para reemplazo valvular.");
        return { mensaje: `Nueva remisión de ${r.medico}: ${r.paciente_nombre}.`, paciente_id: r.paciente_id };
      },
      remision_aceptada: () => ({ mensaje: "El especialista aceptó su remisión.", paciente_id: "demo-2" }),
      factura_creada: () => {
        const fac = M.agregarFacturaAutomatica();
        return { mensaje: `Factura automática ${fac.id} creada al aprobar un reporte de IA.`, paciente_id: fac.paciente_id };
      },
      cuenta_bloqueada: () => ({ mensaje: "La cuenta bloqueo_prueba quedó bloqueada tras 3 intentos fallidos." }),
      alerta_critica: () => {
        const a = M.agregarAlerta({ mensaje: "Riesgo crítico de requerir UCI: probabilidad 94 %. Revise al paciente." });
        return { mensaje: a.mensaje, paciente_id: a.paciente_id };
      },
      fhir_observation: () => ({ mensaje: "Llegó una glucosa desde FHIR (LOINC 2339-0): 238 mg/dL.", paciente_id: "demo-1" }),
    };
    const datos = eventos[tipo]?.();
    if (!datos) return;
    const ev = { tipo, fecha: f, ...datos };
    M.agregarNotificacion(ev);
    despachar(ev);
  }, [despachar]);

  const noLeidas = estado.notificaciones.filter((n) => !n.leida).length;

  // Contador en el título de la pestaña: con varias ventanas abiertas se ve
  // cuál recibió el aviso sin entrar a ella.
  useEffect(() => {
    const base = "Pulso · Coordinación hospitalaria";
    document.title = noLeidas > 0 ? `(${noLeidas}) ${base}` : base;
    return () => { document.title = base; };
  }, [noLeidas]);

  const valor = useMemo(() => ({
    ...estado,
    noLeidas,
    alertasActivas: estado.alertas.filter((a) => a.estado === "activa"),
    conectado, suscribir, marcarLeida, reconocer, refrescar, simularEvento, marcarHito,
  }), [estado, noLeidas, conectado, suscribir, marcarLeida, reconocer, refrescar, simularEvento, marcarHito]);

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}
