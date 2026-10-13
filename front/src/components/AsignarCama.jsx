import { useEffect, useState } from "react";
import { BedDouble, Loader2, Scissors, Siren, UserPlus } from "lucide-react";
import { SolicitarTraslado } from "./Traslados";
import BuscarPaciente from "./BuscarPaciente";
import { api } from "../api";
import { useAvisos } from "./Avisos";
import { duracion } from "../lib/format";

/**
 * Quién espera cama y cómo asignarla. La API valida (cama disponible, tipo de
 * cama que exige la cirugía, un paciente = una cama) y bloquea la fila: si dos
 * personas asignan la misma cama a la vez, la segunda recibe 409.
 */
const ORIGEN = {
  urgencia: { texto: "Urgencias", icono: Siren, clase: "bg-coral-soft text-coral-ink" },
  posquirurgico: { texto: "Salió de quirófano", icono: Scissors, clase: "bg-hero-sky text-ink" },
  en_quirofano: { texto: "En quirófano (reserva)", icono: Scissors, clase: "bg-cloud-card text-ink" },
};

export function usePendientesCama(activo) {
  const [estado, setEstado] = useState({ lista: [], cargando: activo });
  const cargar = () => api("/camas/pendientes").then((d) => setEstado({ lista: d.pendientes, miArea: d.mi_area, cargando: false }))
    .catch(() => setEstado({ lista: [], cargando: false }));
  useEffect(() => { if (activo) cargar(); }, [activo]);   // eslint-disable-line react-hooks/exhaustive-deps
  return { ...estado, recargar: cargar };
}

function Origen({ p }) {
  const o = ORIGEN[p.origen] || ORIGEN.urgencia;
  const Icono = o.icono;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${o.clase}`}>
      <Icono size={11} aria-hidden="true" />{o.texto}{p.triage ? ` · triage ${p.triage}` : ""}
    </span>
  );
}

/** Lista compacta para el Centro de mando: quién espera y qué tipo de cama necesita. */
export function EsperandoCama({ pendientes, miArea, soloLectura = false }) {
  if (!pendientes.lista.length) return null;
  return (
    <section aria-labelledby="t-espera" className="rounded-[28px] bg-cloud-card p-5">
      <h2 id="t-espera" className="flex items-center gap-2 font-semibold"><BedDouble size={17} aria-hidden="true" />
        {pendientes.lista.length === 1 ? "1 paciente espera cama" : `${pendientes.lista.length} pacientes esperan cama`}
      </h2>
      <p className="mt-0.5 text-xs text-gray-strong">Toca una cama disponible de tu área para asignarla, o pide a otra área que lo reciba.</p>
      <ul className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {pendientes.lista.slice(0, 12).map((p) => (
          <li key={p.encuentro_id} className="rounded-2xl bg-paper-white px-3 py-2 text-sm">
            <span className="flex flex-wrap items-center gap-2"><b>{p.paciente || "Paciente"}</b><Origen p={p} />
              <span className="text-xs text-gray-strong">{p.tipo_cama_requerida_nombre || "cualquier cama"} · {duracion(p.esperando_min || 0)}</span></span>
            {p.origen === "urgencia" && !soloLectura && (p.traslado_pendiente
              ? <p className="mt-1 text-xs font-medium text-metric-blue">Traslado solicitado: esperando respuesta</p>
              : <SolicitarTraslado pacienteId={p.paciente_id} areaActual={miArea} onListo={pendientes.recargar} />)}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Dentro del panel de una cama disponible: elegir a quién se le asigna. */
export function AsignarAqui({ cama, onCambio }) {
  const { avisar } = useAvisos();
  const pend = usePendientesCama(true);
  const [ingreso, setIngreso] = useState(null);
  const [enviando, setEnviando] = useState(null);
  const compatibles = pend.lista.filter((p) => !p.tipo_cama_requerida || p.tipo_cama_requerida === cama.tipo_cama);
  const otros = pend.lista.length - compatibles.length;

  const asignar = async (cuerpo, clave) => {
    setEnviando(clave);
    try {
      const r = await api(`/camas/${cama.cama_id}/asignar`, { method: "POST", json: cuerpo });
      avisar(r.estado === "reservada" ? `Cama ${r.cama} reservada: el paciente sigue en quirófano` : `Cama ${r.cama} asignada`);
      setIngreso(null);
      await onCambio();
    } catch (e) { avisar(e.message, "error"); pend.recargar(); await onCambio(); }
    finally { setEnviando(null); }
  };

  return (
    <section className="mt-6 rounded-3xl bg-cloud-card p-5" aria-label="Asignar paciente">
      <p className="text-xs font-semibold uppercase tracking-wider text-gray-strong">Asignar esta cama</p>
      {pend.cargando ? <p className="mt-2 text-sm text-gray-strong">Buscando pacientes que esperan cama…</p> : compatibles.length === 0 ? (
        <p className="mt-2 text-sm text-gray-strong">Nadie espera una cama de este tipo{otros ? ` (${otros} esperan otro tipo de cama)` : ""}.</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {compatibles.map((p) => (
            <li key={p.encuentro_id} className="flex items-center justify-between gap-3 rounded-2xl bg-paper-white p-3">
              <div className="min-w-0">
                <p className="text-sm font-semibold">{p.paciente || "Paciente"} <span className="font-normal text-gray-strong">{p.edad ? `· ${p.edad}` : ""}</span></p>
                <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-gray-strong"><Origen p={p} />{p.procedimiento && <span className="truncate">{p.procedimiento}</span>}<span>· espera {duracion(p.esperando_min || 0)}</span></p>
              </div>
              <button onClick={() => asignar({ encuentro_id: p.encuentro_id }, p.encuentro_id)} disabled={!!enviando}
                      className="flex shrink-0 items-center gap-1.5 rounded-full bg-charcoal px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">
                {enviando === p.encuentro_id ? <Loader2 size={13} className="anim-spin" /> : <UserPlus size={13} />}Asignar
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-4 space-y-2">
        <BuscarPaciente valor={ingreso} onElegir={setIngreso} id={`ingreso-${cama.cama_id}`} etiqueta="Ingreso directo (paciente que no viene de urgencias ni de cirugía)" />
        {ingreso && (
          <button onClick={() => asignar({ paciente_id: ingreso.paciente_id, motivo: "Ingreso directo" }, "doc")} disabled={!!enviando}
                  className="flex w-full items-center justify-center gap-1.5 rounded-full bg-charcoal px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
            {enviando === "doc" ? <Loader2 size={14} className="anim-spin" /> : <UserPlus size={14} />}Asignar a {ingreso.nombre.split(" ")[0]}
          </button>
        )}
      </div>
    </section>
  );
}

