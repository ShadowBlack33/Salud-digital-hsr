import { useEffect, useState } from "react";
import { CalendarClock, CheckCircle2, ChevronDown, HeartPulse, ShieldAlert, Sparkles } from "lucide-react";
import ChipDemo from "../../components/ChipDemo";
import Anillo from "../../components/Anillo";
import Esqueleto from "../../components/Esqueleto";
import GaleriaImagenes from "../../components/GaleriaImagenes";
import BotonHistoriaPDF from "../../components/BotonHistoriaPDF";
import { api } from "../../api";
import * as S from "../../lib/servicios";
import { useReloj, useUsuario } from "../../lib/hooks";
import { fechaYHora } from "../../lib/format";

const TIPO = { cirugia: "Cirugía", consulta: "Consulta", hospitalizacion: "Hospitalización", urgencias: "Urgencias" };

/** Explica un reporte de IA aprobado en lenguaje sencillo, sin jerga. */
function explicar(r) {
  const pct = Math.round(Number(r.probabilidad || 0) * 100);
  if (r.clase === "requiere_uci" || r.critico) {
    return `Según tus exámenes, es probable (${pct} %) que después de la cirugía necesites unos días en cuidados intensivos. Tu equipo ya lo tuvo en cuenta para tenerte un espacio listo.`;
  }
  return `Según tus exámenes, lo más probable es que después de la cirugía no necesites cuidados intensivos (${pct} % de probabilidad de necesitarlos).`;
}

/** "Faltan 2 días y 3 horas". */
function cuantoFalta(iso, ahora) {
  const m = Math.round((Date.parse(iso) - ahora) / 60000);
  if (m <= 0) return "Es ahora";
  const d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), min = m % 60;
  if (d > 0) return `Faltan ${d} ${d === 1 ? "día" : "días"}${h ? ` y ${h} ${h === 1 ? "hora" : "horas"}` : ""}`;
  if (h > 0) return `Faltan ${h} ${h === 1 ? "hora" : "horas"}${min ? ` y ${min} min` : ""}`;
  return `Faltan ${min} min`;
}

/** Un resultado aprobado, explicado sin jerga, con el detalle desplegable. */
function Resultado({ r }) {
  const pct = Math.round(Number(r.probabilidad || 0) * 100);
  return (
    <li className="rounded-3xl bg-cloud-card p-5">
      <div className="flex items-start gap-4">
        <Anillo valor={pct} tamano={76} grosor={8} color="var(--color-metric-blue)" etiqueta={`${pct} por ciento`}>
          <span className="text-base font-semibold tabular-nums">{pct}%</span>
        </Anillo>
        <div className="min-w-0">
          <p className="text-[15px] leading-relaxed">{explicar(r)}</p>
          {r.observaciones && <p className="mt-2 text-sm text-gray-strong">Nota de tu médico: “{r.observaciones}”</p>}
          <p className="mt-2 text-xs text-gray-strong">{fechaYHora(r.created_at)}</p>
        </div>
      </div>
      <details className="group mt-4 rounded-2xl bg-paper-white px-4 py-3">
        <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-medium">
          ¿Qué significa esto?<ChevronDown size={16} className="transition group-open:rotate-180" aria-hidden="true" />
        </summary>
        <div className="mt-2 space-y-2 text-sm leading-relaxed text-gray-strong">
          <p>Un programa de computador comparó tus exámenes de antes de la cirugía con los de miles de pacientes. El número es qué tan probable es que necesites cuidados intensivos después.</p>
          <p>No es un diagnóstico: tu médico lo revisó y lo aprobó antes de que lo vieras. Sirve para que el hospital tenga tu cama lista con tiempo.</p>
          <p>Si tienes dudas, pregúntale a tu médico en tu próxima cita.</p>
        </div>
      </details>
    </li>
  );
}

/** Portal del paciente (R01: el paciente solo ve su propia información). Pensado primero para celular. */
export default function MiSalud() {
  const usuario = useUsuario();
  const pid = usuario?.paciente_id;
  const ahora = useReloj(60000);
  const [paciente, setPaciente] = useState(null);
  const [historia, setHistoria] = useState({ datos: null, demo: false });
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!pid) return;
    let vivo = true;
    api(`/pacientes/${pid}`).then((p) => vivo && setPaciente(p)).catch((e) => vivo && setError(e));
    S.historia(pid).then((h) => vivo && setHistoria(h)).catch(() => vivo && setHistoria({ datos: { encuentros: [], reportes_ia: [] }, demo: false }));
    return () => { vivo = false; };
  }, [pid]);

  if (!pid) {
    return <p role="alert" className="rounded-[28px] bg-coral-soft p-6 text-sm text-coral-ink">Tu cuenta no está asociada a un paciente. Comunícate con el hospital.</p>;
  }
  if (error) {
    return <p role="alert" className="flex items-center gap-2 rounded-[28px] bg-coral-soft p-6 text-sm text-coral-ink"><ShieldAlert size={18} />{error.message}</p>;
  }
  if (!paciente) return <div className="mx-auto max-w-2xl"><Esqueleto filas={4} alto="h-16" /></div>;

  const encuentros = historia.datos?.encuentros ?? [];
  const proximos = encuentros.filter((e) => e.fecha && Date.parse(e.fecha) >= ahora).sort((a, b) => Date.parse(a.fecha) - Date.parse(b.fecha));
  const proximo = proximos[0];
  const pasados = encuentros.filter((e) => !proximos.includes(e));
  const reportes = historia.datos?.reportes_ia ?? [];
  const nombre = `${paciente.nombre} ${paciente.apellido}`;

  return (
    <div className="mx-auto max-w-2xl space-y-6 pb-16">
      <header className="anim-rise">
        <p className="text-xs font-semibold uppercase tracking-wider text-metric-blue">Mi salud</p>
        <h1 className="mt-1 text-[34px] font-semibold leading-tight tracking-display">Hola, {paciente.nombre}</h1>
        <p className="mt-1 text-[15px] text-gray-strong">Aquí ves tus próximas citas, tus resultados y tus imágenes. Solo tú y tu equipo médico pueden verlos.</p>
        {historia.demo && <div className="mt-2"><ChipDemo visible /></div>}
      </header>

      <section className="anim-rise rounded-[32px] bg-gradient-to-b from-hero-sky to-[#fff9ee] p-6" aria-label="Próxima cita">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-paper-white px-3 py-1 text-xs font-semibold"><CalendarClock size={13} aria-hidden="true" />Lo próximo</span>
        {proximo ? (
          <>
            <h2 className="mt-4 text-2xl font-semibold leading-tight tracking-display">{proximo.descripcion || TIPO[proximo.tipo] || "Cita"}</h2>
            <p className="mt-1 text-sm text-gray-strong">{fechaYHora(proximo.fecha)}{proximo.lugar ? ` · ${proximo.lugar}` : ""}</p>
            <p className="mt-3 text-[15px] font-semibold tabular-nums">{cuantoFalta(proximo.fecha, ahora)}</p>
            <span className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-green-soft px-3 py-1 text-xs font-semibold text-green-ink"><CheckCircle2 size={13} aria-hidden="true" />{proximo.estado === "programado" ? "Confirmada" : proximo.estado}</span>
          </>
        ) : (
          <p className="mt-4 text-[15px]">No tienes citas ni cirugías programadas por ahora.</p>
        )}
      </section>

      <section className="rounded-[28px] bg-paper-white p-6 shadow-lift" aria-label="Resultados">
        <h2 className="flex items-center gap-2 text-lg font-semibold"><Sparkles size={18} className="text-metric-blue" aria-hidden="true" />Tus resultados</h2>
        <p className="mt-1 text-sm text-gray-strong">Solo aparecen los resultados que tu médico ya revisó y aprobó.</p>
        {reportes.length === 0 ? (
          <p className="mt-4 rounded-3xl bg-cloud-card p-5 text-sm">Todavía no tienes resultados aprobados.</p>
        ) : (
          <ul className="mt-4 space-y-3">
            {reportes.map((r) => <Resultado key={r.id} r={r} />)}
          </ul>
        )}
      </section>

      <GaleriaImagenes pacienteId={pid} />

      {pasados.length > 0 && (
        <section className="rounded-[28px] bg-paper-white p-6 shadow-lift" aria-label="Historial">
          <h2 className="flex items-center gap-2 text-lg font-semibold"><HeartPulse size={18} className="text-coral-deep" aria-hidden="true" />Tu historial</h2>
          <ol className="mt-4 space-y-4 border-l-2 border-cloud-card pl-5">
            {pasados.map((e) => (
              <li key={e.id} className="relative">
                <span className="absolute -left-[27px] top-1.5 size-3 rounded-full bg-metric-blue" aria-hidden="true" />
                <p className="text-sm font-medium">{e.descripcion || TIPO[e.tipo] || e.tipo}</p>
                <p className="text-xs text-gray-strong">{fechaYHora(e.fecha)}{e.lugar ? ` · ${e.lugar}` : ""}</p>
              </li>
            ))}
          </ol>
        </section>
      )}

      <BotonHistoriaPDF pacienteId={pid} nombre={nombre} ancho texto="Descargar mi historia clínica (PDF)" />
    </div>
  );
}
