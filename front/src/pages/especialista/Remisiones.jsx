import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Check, Clock, Inbox, Loader2, Send, UserCheck } from "lucide-react";
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
              <h2 className="text-lg font-semibold leading-snug">
                <Link to={`/app/pacientes/${r.paciente_id}`} className="hover:underline">{r.paciente_nombre || "Paciente"}</Link>
              </h2>
              <p className="mt-1 flex-1 text-sm text-gray-strong">{r.motivo}</p>
              <div className="mt-5 flex items-center justify-between">
                <Insignia grupo="proceso" etiqueta="Pendiente" tamano="sm" />
                {recibe && (
                  <button onClick={() => aceptar(r)} disabled={aceptando === r.id}
                          className="flex items-center gap-1.5 rounded-full bg-charcoal px-4 py-2 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50">
                    {aceptando === r.id ? <Loader2 size={15} className="anim-spin" /> : <Check size={15} />}Aceptar
                  </button>
                )}
              </div>
            </article>
          ))}
        </section>
      )}

      {resueltas.length > 0 && (
        <section aria-label="Atendidas" className="rounded-[28px] bg-paper-white p-6 shadow-lift">
          <h2 className="mb-2 text-lg font-semibold">Atendidas</h2>
          <ul className="divide-y divide-cloud-card">
            {resueltas.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                <span>
                  <span className="font-medium">{r.paciente_nombre || "Paciente"}</span>
                  <span className="block text-xs text-gray-strong">{recibe ? r.medico : r.especialista} · {haceCuanto(r.created_at)}</span>
                </span>
                <Insignia grupo="libre" etiqueta="Aceptada" tamano="sm" />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
