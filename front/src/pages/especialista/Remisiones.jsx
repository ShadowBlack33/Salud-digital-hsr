import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Check, CheckCheck, Clock, Inbox, Loader2, Send, UserCheck, X } from "lucide-react";
import Encabezado from "../../components/Encabezado";
import Insignia from "../../components/Insignia";
import Esqueleto from "../../components/Esqueleto";
import { useAvisos } from "../../components/Avisos";
import * as S from "../../lib/servicios";
import { useEventos } from "../../lib/tiempoReal";
import { useUsuario } from "../../lib/hooks";
import { esEspecialista } from "../../lib/roles";
import { haceCuanto } from "../../lib/format";

/** Remisiones (R08): el especialista ve las recibidas y las acepta; el médico ve las que envió. */
export default function Remisiones() {
  const usuario = useUsuario();
  const { avisar } = useAvisos();
  const recibe = esEspecialista(usuario);
  const [estado, setEstado] = useState({ cargando: true, lista: [], demo: false, error: null });
  const [nuevas, setNuevas] = useState(new Set());
  const [aceptando, setAceptando] = useState(null);
  const [rechazo, setRechazo] = useState({ id: null, motivo: "" });   // formulario de rechazo abierto

  const vistas = useRef(null);   // ids ya mostrados: lo que no esté aquí es nuevo

  const cargar = useCallback(async () => {
    try {
      const { datos, demo } = await S.remisiones();
      if (vistas.current) setNuevas(new Set(datos.filter((r) => !vistas.current.has(r.id)).map((r) => r.id)));
      vistas.current = new Set(datos.map((r) => r.id));
      setEstado({ cargando: false, lista: datos, demo, error: null });
    } catch (err) {
      setEstado((e) => ({ ...e, cargando: false, error: err }));
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);
  useEventos((ev) => { if (ev.tipo?.startsWith("remision")) cargar(); });

  const aceptar = async (r) => {
    setAceptando(r.id);
    try {
      await S.aceptarRemision(r.id);
      avisar("Remisión aceptada. El médico remitente ya fue avisado.");
      await cargar();
    } catch (err) { avisar(err.message, "error"); }
    finally { setAceptando(null); }
  };

  const accion = async (r, fn, mensaje) => {
    setAceptando(r.id);
    try {
      await fn();
      avisar(mensaje);
      setRechazo({ id: null, motivo: "" });
      await cargar();
    } catch (err) { avisar(err.message, "error"); await cargar(); }
    finally { setAceptando(null); }
  };
  const rechazar = (r) => accion(r, () => S.rechazarRemision(r.id, rechazo.motivo.trim()),
    "Remisión rechazada. Ya no tienes acceso a la ficha de este paciente.");
  const atender = (r) => accion(r, () => S.atenderRemision(r.id),
    "Remisión cerrada como atendida. Conservas el acceso a la ficha unos días más.");
  const simulada = (r) => String(r.id).startsWith("sim-");

  const pendientes = estado.lista.filter((r) => r.estado === "pendiente");
  const resueltas = estado.lista.filter((r) => r.estado !== "pendiente");

  return (
    <div className="space-y-8 pb-16">
      <Encabezado titulo={recibe ? "Remisiones recibidas" : "Remisiones"}
                  subtitulo={recibe ? "Pacientes que otros médicos te remitieron para valoración." : "Pacientes que remitiste a un especialista. Para remitir, abre la ficha del paciente."}
                  demo={estado.demo} />

      {estado.cargando && <Esqueleto filas={3} alto="h-20" />}
      {estado.error && <p role="alert" className="rounded-3xl bg-coral-soft p-5 text-sm text-coral-ink">{estado.error.message}</p>}

      {!estado.cargando && !estado.error && estado.lista.length === 0 && (
        <div className="flex flex-col items-center gap-2 rounded-[28px] bg-cloud-card py-14 text-center">
          <Inbox size={28} className="text-gray-strong" aria-hidden="true" />
          <p className="font-medium">No hay remisiones</p>
          <p className="text-sm text-gray-strong">Cuando llegue una, aparecerá aquí sin recargar.</p>
        </div>
      )}

      {pendientes.length > 0 && (
        <section aria-label="Pendientes" className="grid gap-4 md:grid-cols-2">
          {pendientes.map((r) => (
            <article key={r.id} className={`flex flex-col rounded-[28px] bg-cloud-card p-6 ${nuevas.has(r.id) ? "anim-pop ring-2 ring-metric-blue" : ""}`}>
              <div className="mb-3 flex items-center justify-between gap-3 text-xs">
                <span className="flex items-center gap-1.5 font-semibold text-metric-blue">
                  {recibe ? <><UserCheck size={14} aria-hidden="true" />{r.medico}</> : <><Send size={14} aria-hidden="true" />Para {r.especialista}</>}
                </span>
                <span className="flex items-center gap-1 text-gray-strong"><Clock size={12} aria-hidden="true" />{haceCuanto(r.created_at)}</span>
              </div>
              <h2 className="flex flex-wrap items-center gap-2 text-lg font-semibold leading-snug">
                <Link to={`/app/pacientes/${r.paciente_id}`} className="hover:underline">{r.paciente_nombre || "Paciente"}</Link>
                {r.prioridad === "urgente" && <span className="rounded-full bg-coral-deep px-2 py-0.5 text-[11px] font-semibold text-white">Urgente</span>}
              </h2>
              {!recibe && r.especialidad && <p className="text-xs text-gray-strong">{r.especialidad}</p>}
              <p className="mt-1 flex-1 text-sm text-gray-strong">{r.motivo}</p>
              <div className="mt-5 flex items-center justify-between gap-2">
                <Insignia grupo="proceso" etiqueta="Pendiente" tamano="sm" />
                {recibe && <Link to={`/app/pacientes/${r.paciente_id}`} className="ml-auto rounded-full px-3 py-2 text-sm font-medium text-metric-blue hover:bg-paper-white">Revisar ficha</Link>}
                {recibe && !simulada(r) && rechazo.id !== r.id && (
                  <button onClick={() => setRechazo({ id: r.id, motivo: "" })} disabled={aceptando === r.id}
                          className="rounded-full px-3 py-2 text-sm font-medium text-coral-ink hover:bg-coral-soft">Rechazar</button>
                )}
                {recibe && (
                  <button onClick={() => aceptar(r)} disabled={aceptando === r.id}
                          className="flex items-center gap-1.5 rounded-full bg-charcoal px-4 py-2 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50">
                    {aceptando === r.id ? <Loader2 size={15} className="anim-spin" /> : <Check size={15} />}Aceptar
                  </button>
                )}
              </div>
              {rechazo.id === r.id && (
                <form className="mt-4 space-y-2" onSubmit={(e) => { e.preventDefault(); rechazar(r); }}>
                  <label htmlFor={`rechazo-${r.id}`} className="text-xs font-medium">Motivo del rechazo (lo verá el médico remitente)</label>
                  <textarea id={`rechazo-${r.id}`} rows={2} value={rechazo.motivo} autoFocus
                            onChange={(e) => setRechazo({ id: r.id, motivo: e.target.value })}
                            className="w-full rounded-2xl border border-cloud-card bg-paper-white p-3 text-sm" />
                  <div className="flex justify-end gap-2">
                    <button type="button" onClick={() => setRechazo({ id: null, motivo: "" })} className="flex items-center gap-1 rounded-full px-3 py-2 text-sm"><X size={14} />Cancelar</button>
                    <button type="submit" disabled={rechazo.motivo.trim().length < 5 || aceptando === r.id}
                            className="rounded-full bg-coral-deep px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Confirmar rechazo</button>
                  </div>
                </form>
              )}
            </article>
          ))}
        </section>
      )}

      {resueltas.length > 0 && (
        <section aria-label="Atendidas" className="rounded-[28px] bg-paper-white p-6 shadow-lift">
          <h2 className="mb-2 text-lg font-semibold">Resueltas</h2>
          <ul className="divide-y divide-cloud-card">
            {resueltas.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                <span>
                  <Link to={`/app/pacientes/${r.paciente_id}`} className="font-medium hover:underline">{r.paciente_nombre || "Paciente"}</Link>
                  <span className="block text-xs text-gray-strong">{recibe ? `De ${r.medico}` : `Para ${r.especialista}`} · {r.motivo} · {haceCuanto(r.created_at)}</span>
                  {r.estado === "rechazada" && r.respuesta && <span className="block text-xs text-coral-ink">Motivo del rechazo: {r.respuesta}</span>}
                </span>
                {recibe && r.estado === "aceptada" && !simulada(r) && (
                  <button onClick={() => atender(r)} disabled={aceptando === r.id}
                          className="ml-auto flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold text-metric-blue hover:bg-cloud-card disabled:opacity-50">
                    {aceptando === r.id ? <Loader2 size={13} className="anim-spin" /> : <CheckCheck size={13} />}Marcar atendida
                  </button>
                )}
                <Insignia grupo={r.estado === "rechazada" ? "bloqueado" : "libre"} etiqueta={r.estado === "rechazada" ? "Rechazada" : r.estado === "atendida" ? "Atendida" : "Aceptada"} tamano="sm" />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
