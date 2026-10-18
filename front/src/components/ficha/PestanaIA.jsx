import { useCallback, useEffect, useState } from "react";
import { Braces, Check, Info, Loader2, Play, ShieldCheck, X } from "lucide-react";
import Anillo from "../Anillo";
import Panel from "../Panel";
import Insignia from "../Insignia";
import ChipDemo from "../ChipDemo";
import Esqueleto from "../Esqueleto";
import { useAvisos } from "../Avisos";
import * as S from "../../lib/servicios";
import { useEventos, useTiempoReal } from "../../lib/tiempoReal";
import { fechaYHora } from "../../lib/format";

const ESTADO = { pendiente: ["proceso", "Pendiente"], aprobado: ["libre", "Aprobado"], rechazado: ["bloqueado", "Rechazado"] };
const CLASE = { requiere_uci: "Requerirá cama de UCI tras la cirugía", no_requiere_uci: "No requerirá UCI tras la cirugía" };
const textoClase = (r) => CLASE[r.clase] || r.clase || "Resultado del modelo";

/** Análisis de IA con aprobación clínica (R10) y vista del payload seudonimizado (R12). */
export default function PestanaIA({ pacienteId }) {
  const { avisar } = useAvisos();
  const [estado, setEstado] = useState({ cargando: true, lista: [], demo: false, error: null });
  const [analizando, setAnalizando] = useState(false);
  const [payload, setPayload] = useState(null);
  const [labs, setLabs] = useState({ glucosa: "", potasio: "", hemoglobina: "" });

  const cargar = useCallback(async () => {
    try {
      const { datos, demo } = await S.reportesDePaciente(pacienteId);
      const ordenados = [...datos].sort((a, b) => Date.parse(b.created_at || 0) - Date.parse(a.created_at || 0));
      setEstado({ cargando: false, lista: ordenados, demo, error: null });
    } catch (err) { setEstado((e) => ({ ...e, cargando: false, error: err })); }
  }, [pacienteId]);

  useEffect(() => { cargar(); }, [cargar]);
  useEventos((ev) => { if (ev.paciente_id === pacienteId) cargar(); });

  const analizar = async () => {
    setAnalizando(true);
    try {
      const variables = Object.fromEntries(Object.entries(labs).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)]));
      const { datos } = await S.analizar(pacienteId, Object.keys(variables).length ? variables : undefined);
      avisar(`Análisis listo (reporte ${datos.id}). Queda pendiente hasta que un clínico lo apruebe.`);
      await cargar();
    } catch (err) { avisar(err.message, "error"); }
    finally { setAnalizando(false); }
  };

  const verPayload = async (r) => {
    setPayload({ id: r.id, cargando: true });
    try { const { datos } = await S.payloadReporte(r.id); setPayload({ id: r.id, datos }); }
    catch (err) { setPayload({ id: r.id, error: err.message }); }
  };

  const pendientes = estado.lista.filter((r) => r.estado === "pendiente");
  const historial = estado.lista.filter((r) => r.estado !== "pendiente");

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 rounded-[28px] bg-cloud-card p-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Predicción de cama UCI postquirúrgica</h2>
          <p className="mt-1 max-w-xl text-sm text-gray-strong">El modelo recibe solo variables clínicas y un identificador seudónimo. El resultado no entra a la historia clínica hasta que un clínico lo apruebe.</p>
          {estado.demo && <div className="mt-2"><ChipDemo visible /></div>}
        </div>
        <button onClick={analizar} disabled={analizando}
                className="flex shrink-0 items-center justify-center gap-2 rounded-full bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50">
          {analizando ? <Loader2 size={16} className="anim-spin" /> : <Play size={16} />}Ejecutar análisis
        </button>
      </div>

      <div className="rounded-[28px] bg-cloud-card p-6">
        <h3 className="text-sm font-semibold">Laboratorios para el análisis (opcional)</h3>
        <p className="mt-1 text-xs text-gray-strong">Si los dejas vacíos, el modelo usa los últimos laboratorios registrados del paciente.</p>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[["glucosa", "Glucosa", "mg/dL"], ["potasio", "Potasio", "mmol/L"], ["hemoglobina", "Hemoglobina", "g/dL"]].map(([k, t, u]) => (
            <label key={k} className="text-xs font-medium text-gray-strong">{t} <span className="font-normal">({u})</span>
              <input type="number" step="any" min="0" inputMode="decimal" value={labs[k]}
                     onChange={(e) => setLabs((v) => ({ ...v, [k]: e.target.value }))}
                     className="mt-1 w-full rounded-2xl bg-paper-white px-4 py-2.5 text-sm text-ink outline-none focus:ring-2 focus:ring-metric-blue" />
            </label>
          ))}
        </div>
      </div>

      {estado.cargando && <Esqueleto filas={2} alto="h-16" />}
      {estado.error && <p role="alert" className="text-sm text-coral-ink">{estado.error.message}</p>}

      {pendientes.map((r) => <ReportePendiente key={r.id} reporte={r} onVerPayload={() => verPayload(r)} onDecidido={cargar} />)}

      {historial.length > 0 && (
        <section className="rounded-[28px] bg-paper-white p-6 shadow-lift" aria-label="Reportes anteriores">
          <h3 className="mb-2 font-semibold">Reportes anteriores</h3>
          <ul className="divide-y divide-cloud-card">
            {historial.map((r) => {
              const [grupo, etiqueta] = ESTADO[r.estado] || ["bloqueado", r.estado];
              return (
                <li key={r.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <span>
                    <span className="block text-sm font-medium">{textoClase(r)} · {Math.round(Number(r.probabilidad || 0) * 100)} %</span>
                    <span className="block text-xs text-gray-strong">Reporte {r.id} · {fechaYHora(r.created_at)}{r.observaciones ? ` · “${r.observaciones}”` : ""}</span>
                  </span>
                  <span className="flex items-center gap-2">
                    <button onClick={() => verPayload(r)} className="text-xs font-medium text-metric-blue hover:underline">Datos enviados</button>
                    <Insignia grupo={grupo} etiqueta={etiqueta} tamano="sm" />
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 flex items-center gap-1.5 text-xs text-gray-strong"><Info size={13} aria-hidden="true" />Los rechazados no se borran: quedan como evidencia y en la auditoría.</p>
        </section>
      )}

      {!estado.cargando && estado.lista.length === 0 && <p className="text-sm text-gray-strong">Este paciente aún no tiene análisis de IA.</p>}

      <Panel abierto={!!payload} onCerrar={() => setPayload(null)} titulo="Datos enviados al modelo" subtitulo={payload ? `Reporte ${payload.id}` : ""}>
        <p className="mb-3 flex items-start gap-2 rounded-3xl bg-green-soft p-4 text-sm text-green-ink">
          <ShieldCheck size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
          Esto es exactamente lo que recibió el modelo: variables clínicas y un seudónimo. Nunca viajan el nombre, el documento, el teléfono, el correo ni la dirección (Ley 1581 de 2012).
        </p>
        {payload?.cargando && <p className="flex items-center gap-2 text-sm text-gray-strong"><Loader2 size={16} className="anim-spin" />Cargando…</p>}
        {payload?.error && <p className="text-sm text-coral-ink">{payload.error}</p>}
        {payload?.datos && (
          <pre className="overflow-x-auto rounded-3xl bg-charcoal p-5 font-mono text-xs leading-relaxed text-cloud-card">{JSON.stringify(payload.datos, null, 2)}</pre>
        )}
      </Panel>
    </div>
  );
}

function ReportePendiente({ reporte: r, onVerPayload, onDecidido }) {
  const { avisar } = useAvisos();
  const tr = useTiempoReal();
  const [observaciones, setObservaciones] = useState("");
  const [enviando, setEnviando] = useState(null);
  const pct = Math.round(Number(r.probabilidad || 0) * 100);
  const color = r.critico ? "var(--color-coral-deep)" : pct >= 50 ? "var(--color-gold-deep)" : "var(--color-green-deep)";

  const decidir = async (decision) => {
    setEnviando(decision);
    try {
      await S.decidirReporte(r.id, decision, observaciones.trim() || null);
      avisar(decision === "aprobar" ? "Reporte aprobado: ya forma parte de la historia clínica." : "Reporte rechazado. Queda como evidencia.");
      if (decision === "aprobar") tr?.marcarHito("reporte_aprobado");
      onDecidido();
    } catch (err) { avisar(err.message, "error"); setEnviando(null); }
  };

  return (
    <article className="anim-pop rounded-[28px] bg-paper-white p-6 shadow-lift" aria-label={`Reporte ${r.id} pendiente`}>
      <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
        <Anillo valor={pct} tamano={120} grosor={12} color={color} pista="var(--color-cloud-card)" etiqueta={`Probabilidad ${pct} %`}>
          <span><span className="block text-2xl font-semibold tabular-nums">{pct} %</span><span className="text-[11px] text-gray-strong">probabilidad</span></span>
        </Anillo>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Insignia grupo="proceso" etiqueta="Pendiente de revisión" tamano="sm" />
            {r.critico && <Insignia grupo="ocupado" etiqueta="Caso crítico" tamano="sm" />}
          </div>
          <h3 className="mt-2 text-xl font-semibold leading-snug">{textoClase(r)}</h3>
          <p className="mt-1 text-xs text-gray-strong">Reporte {r.id} · {fechaYHora(r.created_at)}</p>
          <button onClick={onVerPayload} className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-metric-blue hover:underline">
            <Braces size={14} aria-hidden="true" />Ver datos enviados al modelo
          </button>
        </div>
      </div>
      <p className="mt-5 flex items-start gap-2 rounded-3xl bg-gold-soft p-4 text-sm text-gold-ink">
        <Info size={17} className="mt-0.5 shrink-0" aria-hidden="true" />Este resultado no entra a la historia clínica hasta que un clínico lo apruebe.
      </p>
      <label className="mt-4 block text-sm font-medium" htmlFor={`obs-${r.id}`}>Observaciones del clínico</label>
      <textarea id={`obs-${r.id}`} rows={2} value={observaciones} onChange={(e) => setObservaciones(e.target.value)}
                placeholder="Opcional: por qué lo apruebas o lo rechazas"
                className="mt-1 w-full resize-y rounded-2xl bg-cloud-card px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-metric-blue/40" />
      <div className="mt-4 flex flex-wrap gap-2">
        <button onClick={() => decidir("aprobar")} disabled={!!enviando}
                className="flex items-center gap-2 rounded-full bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50">
          {enviando === "aprobar" ? <Loader2 size={15} className="anim-spin" /> : <Check size={15} />}Aprobar
        </button>
        <button onClick={() => decidir("rechazar")} disabled={!!enviando}
                className="flex items-center gap-2 rounded-full bg-cloud-card px-5 py-2.5 text-sm font-semibold transition hover:bg-coral-soft hover:text-coral-ink disabled:opacity-50">
          {enviando === "rechazar" ? <Loader2 size={15} className="anim-spin" /> : <X size={15} />}Rechazar
        </button>
      </div>
    </article>
  );
}
