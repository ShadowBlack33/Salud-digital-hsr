import { useEffect, useState } from "react";
import { ArrowRight, Check, Loader2, Send, X } from "lucide-react";
import { api } from "../api";
import { useAvisos } from "./Avisos";
import { haceCuanto } from "../lib/format";

/**
 * Traslados entre áreas. El jefe de origen revisa la disponibilidad del área
 * destino y le envía la solicitud; el jefe de destino la acepta eligiendo una
 * cama libre de su área, o la rechaza con motivo. La API valida cada paso.
 */
const PRIORIDAD = { urgente: "bg-coral-deep text-white", prioritaria: "bg-gold-soft text-gold-ink", rutinaria: "bg-cloud-card text-ink" };

export function useAreas() {
  const [d, setD] = useState({ mi_area: null, areas: [] });
  useEffect(() => { api("/areas").then(setD).catch(() => {}); }, []);
  return d;
}

/** Formulario para pedir a otra área que reciba al paciente. */
export function SolicitarTraslado({ pacienteId, areaActual, onListo }) {
  const { avisar } = useAvisos();
  const { areas } = useAreas();
  const [abierto, setAbierto] = useState(false);
  const [f, setF] = useState({ servicio_destino_id: "", prioridad: "prioritaria", motivo: "" });
  const [enviando, setEnviando] = useState(false);
  const destinos = areas.filter((a) => a.id !== areaActual);

  const enviar = async (e) => {
    e.preventDefault();
    setEnviando(true);
    try {
      const r = await api("/traslados", { method: "POST", json: { paciente_id: pacienteId, ...f, servicio_destino_id: Number(f.servicio_destino_id) } });
      avisar(`Solicitud enviada a ${r.destino}. Te avisamos cuando la acepten.`);
      setAbierto(false); setF({ servicio_destino_id: "", prioridad: "prioritaria", motivo: "" });
      onListo?.();
    } catch (err) { avisar(err.message, "error"); }
    finally { setEnviando(false); }
  };

  if (!abierto) {
    return (
      <button onClick={() => setAbierto(true)} className="mt-3 flex w-full items-center justify-center gap-2 rounded-full bg-paper-white px-5 py-3 text-sm font-semibold transition hover:shadow-lift">
        <Send size={15} aria-hidden="true" />Solicitar traslado a otra área
      </button>
    );
  }
  return (
    <form onSubmit={enviar} className="mt-3 space-y-3 rounded-2xl bg-paper-white p-4">
      <label className="block text-sm font-medium" htmlFor={`dest-${pacienteId}`}>Área destino
        <select id={`dest-${pacienteId}`} required value={f.servicio_destino_id} onChange={(e) => setF({ ...f, servicio_destino_id: e.target.value })}
                className="mt-1 w-full rounded-2xl border border-cloud-card bg-paper-white px-3 py-2 text-sm">
          <option value="" disabled>Elige el área</option>
          {destinos.map((a) => <option key={a.id} value={a.id}>{a.nombre} — {a.disponibles} libres de {a.total}</option>)}
        </select>
      </label>
      <div className="flex flex-wrap gap-2 text-sm">
        {["rutinaria", "prioritaria", "urgente"].map((p) => (
          <label key={p} className={`cursor-pointer rounded-full px-3 py-1.5 capitalize ${f.prioridad === p ? PRIORIDAD[p] : "bg-cloud-card"}`}>
            <input type="radio" name={`prio-${pacienteId}`} value={p} checked={f.prioridad === p} onChange={() => setF({ ...f, prioridad: p })} className="sr-only" />{p}
          </label>
        ))}
      </div>
      <label className="block text-sm font-medium" htmlFor={`mot-${pacienteId}`}>Motivo
        <textarea id={`mot-${pacienteId}`} required minLength={5} rows={2} value={f.motivo} onChange={(e) => setF({ ...f, motivo: e.target.value })}
                  placeholder="p. ej. deterioro respiratorio, requiere ventilación" className="mt-1 w-full rounded-2xl border border-cloud-card px-3 py-2 text-sm" />
      </label>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={() => setAbierto(false)} className="rounded-full px-3 py-2 text-sm">Cancelar</button>
        <button type="submit" disabled={enviando} className="flex items-center gap-1.5 rounded-full bg-charcoal px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
          {enviando ? <Loader2 size={14} className="anim-spin" /> : <Send size={14} />}Enviar solicitud
        </button>
      </div>
    </form>
  );
}

/** Panel del Centro de mando: solicitudes que llegan a mi área y las que envié. */
export function PanelTraslados({ onCambio, soloLectura = false }) {
  const { avisar } = useAvisos();
  const [lista, setLista] = useState([]);
  const [libres, setLibres] = useState([]);
  const [eleccion, setEleccion] = useState({});      // traslado -> cama elegida
  const [rechazo, setRechazo] = useState({ id: null, motivo: "" });
  const [enviando, setEnviando] = useState(null);

  const cargar = () => api("/traslados").then((d) => setLista(d.traslados)).catch(() => {});
  useEffect(() => { cargar(); const t = setInterval(cargar, 15000); return () => clearInterval(t); }, []);
  useEffect(() => { api("/camas?estado=disponible&limite=400").then(setLibres).catch(() => {}); }, [lista.length]);

  const accion = async (id, ruta, cuerpo, mensaje) => {
    setEnviando(id);
    try { await api(`/traslados/${id}/${ruta}`, { method: "POST", json: cuerpo }); avisar(mensaje); setRechazo({ id: null, motivo: "" }); await cargar(); await onCambio?.(); }
    catch (e) { avisar(e.message, "error"); await cargar(); }
    finally { setEnviando(null); }
  };

  const pendientesEntrantes = lista.filter((t) => t.entrante && t.estado === "pendiente");
  // Historial corto: lo que envié (con su estado) y lo que mi área ya resolvió.
  const salientes = lista.filter((t) => !(t.entrante && t.estado === "pendiente")).slice(0, 6);
  if (pendientesEntrantes.length === 0 && salientes.length === 0) return null;
  return (
    <section aria-labelledby="t-traslados" className="rounded-[28px] bg-cloud-card p-5">
      <h2 id="t-traslados" className="font-semibold">Traslados entre áreas</h2>
      {pendientesEntrantes.length > 0 && (
        <ul className="mt-3 grid gap-3 lg:grid-cols-2">
          {pendientesEntrantes.map((t) => {
            const opciones = libres.filter((c) => c.servicio === t.destino);
            return (
              <li key={t.id} className="rounded-2xl bg-paper-white p-4">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm"><b>{t.paciente || "Paciente"}</b> <span className="text-gray-strong">{t.origen} <ArrowRight size={12} className="inline" aria-hidden="true" /> {t.destino}</span></p>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ${PRIORIDAD[t.prioridad]}`}>{t.prioridad}</span>
                </div>
                <p className="mt-1 text-sm text-gray-strong">{t.motivo}</p>
                <p className="mt-1 text-xs text-gray-strong">Solicitado {haceCuanto(t.created_at)}</p>
                {soloLectura ? (
                  <p className="mt-3 text-xs font-medium text-gray-strong">Solo el jefe de turno puede aceptarla o rechazarla.</p>
                ) : rechazo.id === t.id ? (
                  <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); accion(t.id, "rechazar", { motivo: rechazo.motivo }, "Traslado rechazado"); }}>
                    <label htmlFor={`rz-${t.id}`} className="sr-only">Motivo del rechazo</label>
                    <input id={`rz-${t.id}`} autoFocus minLength={5} required value={rechazo.motivo} onChange={(e) => setRechazo({ id: t.id, motivo: e.target.value })}
                           placeholder="Motivo del rechazo" className="min-w-0 flex-1 rounded-full border border-cloud-card px-3 py-2 text-sm" />
                    <button type="submit" className="rounded-full bg-coral-deep px-3 py-2 text-sm font-semibold text-white">Rechazar</button>
                    <button type="button" onClick={() => setRechazo({ id: null, motivo: "" })} aria-label="Cancelar" className="rounded-full px-2"><X size={15} /></button>
                  </form>
                ) : (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <label htmlFor={`cama-${t.id}`} className="sr-only">Cama</label>
                    <select id={`cama-${t.id}`} value={eleccion[t.id] || ""} onChange={(e) => setEleccion({ ...eleccion, [t.id]: e.target.value })}
                            className="min-w-0 flex-1 rounded-full border border-cloud-card bg-paper-white px-3 py-2 text-sm">
                      <option value="">{opciones.length ? "Elige la cama" : "No hay camas libres en tu área"}</option>
                      {opciones.map((c) => <option key={c.id} value={c.id}>{c.codigo}</option>)}
                    </select>
                    <button disabled={!eleccion[t.id] || enviando === t.id} onClick={() => accion(t.id, "aceptar", { cama_id: Number(eleccion[t.id]) }, "Traslado aceptado: el paciente ya tiene cama en tu área")}
                            className="flex items-center gap-1 rounded-full bg-charcoal px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">
                      {enviando === t.id ? <Loader2 size={14} className="anim-spin" /> : <Check size={14} />}Aceptar
                    </button>
                    <button onClick={() => setRechazo({ id: t.id, motivo: "" })} className="rounded-full px-3 py-2 text-sm font-medium text-coral-ink hover:bg-coral-soft">Rechazar</button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {salientes.length > 0 && (
        <ul className="mt-3 divide-y divide-paper-white text-sm">
          {salientes.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span><b>{t.paciente}</b> <span className="text-gray-strong">{t.saliente && !t.entrante ? "" : `${t.origen} `}→ {t.destino}{t.cama_destino ? ` · cama ${t.cama_destino}` : ""}{t.respuesta ? ` · ${t.respuesta}` : ""}</span></span>
              <span className="flex items-center gap-2">
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${t.estado === "aceptado" ? "bg-green-soft text-green-ink" : t.estado === "rechazado" ? "bg-coral-soft text-coral-ink" : "bg-paper-white"}`}>{t.estado}</span>
                {t.estado === "pendiente" && t.saliente && !soloLectura && <button onClick={() => accion(t.id, "cancelar", {}, "Solicitud retirada")} className="text-xs font-medium text-gray-strong underline">Retirar</button>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
