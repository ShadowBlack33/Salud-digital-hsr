import { useEffect, useState } from "react";
import { BedDouble, CalendarClock, CheckCircle2, ChevronDown, ClipboardCheck, HeartPulse, ShieldAlert, ShieldCheck,
  Sparkles, Stethoscope, UserRound } from "lucide-react";
import ChipDemo from "../../components/ChipDemo";
import Anillo from "../../components/Anillo";
import Esqueleto from "../../components/Esqueleto";
import GaleriaImagenes from "../../components/GaleriaImagenes";
import BotonHistoriaPDF from "../../components/BotonHistoriaPDF";
import MisCobros from "../../components/MisCobros";
import MisDatos from "../../components/MisDatos";
import * as S from "../../lib/servicios";
import { useReloj, useUsuario } from "../../lib/hooks";
import { duracion, fechaYHora, iniciales, minutosDesde } from "../../lib/format";

const TIPO = { cirugia: "Cirugía", consulta_externa: "Consulta", hospitalizacion: "Hospitalización", urgencias: "Urgencias" };
const SECCIONES = [["resumen", "Resumen"], ["resultados", "Resultados"], ["imagenes", "Imágenes"], ["cobros", "Cobros"], ["historial", "Historial"], ["datos", "Mis datos"]];

/** Explica un reporte de IA aprobado en lenguaje sencillo, sin jerga. */
function explicar(r) {
  const pct = Math.round(Number(r.probabilidad || 0) * 100);
  if (r.clase === "riesgo_uci" || r.clase === "requiere_uci" || r.critico) {
    return `Según tus exámenes, es probable (${pct} %) que después de la cirugía necesites unos días en cuidados intensivos. Tu equipo ya lo tuvo en cuenta para tenerte un espacio listo.`;
  }
  return `Según tus exámenes, lo más probable es que después de la cirugía no necesites cuidados intensivos (${pct} % de probabilidad de necesitarlos).`;
}

/** "Mañana a las 10:00 a. m." / "Faltan 2 días y 3 horas". */
function cuantoFalta(iso, ahora) {
  const m = Math.round((Date.parse(iso) - ahora) / 60000);
  if (m <= 0) return "Es ahora";
  const d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), min = m % 60;
  if (d > 0) return `Faltan ${d} ${d === 1 ? "día" : "días"}${h ? ` y ${h} ${h === 1 ? "hora" : "horas"}` : ""}`;
  if (h > 0) return `Faltan ${h} ${h === 1 ? "hora" : "horas"}${min ? ` y ${min} min` : ""}`;
  return `Faltan ${min} min`;
}

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
        </div>
      </details>
    </li>
  );
}

/**
 * Portal del paciente (R01: solo su propia información). Pensado primero para
 * el celular: arriba lo que más le importa (dónde está, qué sigue y cuándo),
 * luego quién lo atiende, sus resultados, imágenes y lo que se le cobra.
 */
export default function MiSalud() {
  const usuario = useUsuario();
  const pid = usuario?.paciente_id;
  const ahora = useReloj(30000);
  const [r, setR] = useState(null);
  const [reportes, setReportes] = useState({ lista: [], demo: false });
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!pid) return;
    let vivo = true;
    S.miResumen().then((d) => vivo && setR(d)).catch((e) => vivo && setError(e));
    S.historia(pid).then((h) => vivo && setReportes({ lista: h.datos?.reportes_ia ?? [], demo: h.demo })).catch(() => {});
    return () => { vivo = false; };
  }, [pid]);

  if (!pid) return <p role="alert" className="rounded-[28px] bg-coral-soft p-6 text-sm text-coral-ink">Tu cuenta no está asociada a un paciente. Comunícate con el hospital.</p>;
  if (error) return <p role="alert" className="flex items-center gap-2 rounded-[28px] bg-coral-soft p-6 text-sm text-coral-ink"><ShieldAlert size={18} />{error.message}</p>;
  if (!r) return <div className="mx-auto max-w-3xl"><Esqueleto filas={4} alto="h-24" /></div>;

  const { paciente: p, ahora: actual, proxima_cirugia: cx } = r;
  const a = p.sexo === "F" ? "a" : "o";
  const nombre = `${p.nombre} ${p.apellido}`;
  const hora = new Date().getHours();
  const saludo = hora < 12 ? "Buenos días" : hora < 19 ? "Buenas tardes" : "Buenas noches";

  return (
    <div className="mx-auto max-w-3xl space-y-5 pb-16">
      <header className="anim-rise">
        <p className="text-xs font-semibold uppercase tracking-wider text-metric-blue">Mi salud</p>
        <h1 className="mt-1 text-[34px] font-semibold leading-tight tracking-display">{saludo}, {p.nombre}</h1>
        <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-gray-strong">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-cloud-card px-3 py-1 font-medium text-ink">
            <ShieldCheck size={13} aria-hidden="true" />{p.cobertura.tipo === "particular" ? "Particular" : p.cobertura.entidad}
          </span>
          Solo tú y tu equipo médico pueden ver esta información.
        </p>
      </header>

      <nav aria-label="Secciones" className="sticky top-24 z-30 -mx-1 flex gap-1.5 overflow-x-auto rounded-full bg-paper-white/85 p-1 backdrop-blur">
        {SECCIONES.map(([id, t]) => (
          <a key={id} href={`#${id}`} className="shrink-0 rounded-full bg-cloud-card px-4 py-2 text-sm font-medium transition hover:bg-hero-sky">{t}</a>
        ))}
      </nav>

      <section id="resumen" className="grid scroll-mt-40 gap-4 md:grid-cols-2" aria-label="Resumen">
        {/* Dónde estoy */}
        <div className={`anim-rise rounded-[32px] p-6 ${actual ? "bg-gradient-to-b from-hero-sky to-[#f3f8ff]" : "bg-cloud-card"} ${cx ? "" : "md:col-span-2"}`}>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-paper-white px-3 py-1 text-xs font-semibold"><BedDouble size={13} aria-hidden="true" />Ahora</span>
          {actual ? (
            <>
              <h2 className="mt-4 text-2xl font-semibold leading-tight tracking-display">{!actual.lugar || actual.lugar === "Hospitalización" ? `Estás hospitalizad${a}` : `Estás en ${actual.lugar.toLowerCase()}`}</h2>
              <p className="mt-1 text-sm text-gray-strong">Cama {actual.cama} · {actual.servicio}</p>
              <p className="mt-3 text-[15px]">Llevas <b className="tabular-nums">{duracion(minutosDesde(actual.desde, ahora))}</b> con nosotros.</p>
              {actual.medico && <p className="mt-1 text-sm text-gray-strong">Te atiende {actual.medico}.</p>}
            </>
          ) : (
            <p className="mt-4 text-[15px]">No estás hospitalizad{a}. Aquí verás tu cama y tu médico si te internan.</p>
          )}
        </div>

        {/* Lo que sigue */}
        {cx && (
          <div className="anim-rise rounded-[32px] bg-gradient-to-b from-[#fff4cc] to-[#fffaf0] p-6">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-paper-white px-3 py-1 text-xs font-semibold"><CalendarClock size={13} aria-hidden="true" />Tu cirugía</span>
            <h2 className="mt-4 text-2xl font-semibold leading-tight tracking-display">{cx.procedimiento}</h2>
            <p className="mt-1 text-sm text-gray-strong">{fechaYHora(cx.fecha)}{cx.quirofano ? ` · Quirófano ${cx.quirofano.replace("QX-", "")}` : ""}</p>
            <p className="mt-3 text-[15px] font-semibold tabular-nums">{cx.estado === "in-progress" ? "En curso ahora" : cuantoFalta(cx.fecha, ahora)}</p>
            <ul className="mt-3 space-y-1 text-sm">
              {cx.cirujano && <li>Te opera: <b>{cx.cirujano}</b></li>}
              {cx.anestesiologo && <li>Anestesia: <b>{cx.anestesiologo}</b></li>}
              {cx.duracion_min && <li>Dura alrededor de {duracion(cx.duracion_min)}</li>}
              {cx.recuperacion && <li>Después te recuperas en: <b>{cx.recuperacion.toLowerCase()}</b></li>}
            </ul>
            <span className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-green-soft px-3 py-1 text-xs font-semibold text-green-ink"><CheckCircle2 size={13} aria-hidden="true" />Confirmada</span>
          </div>
        )}
      </section>

      {cx && cx.estado === "planned" && (
        <details className="group rounded-[28px] bg-paper-white p-6 shadow-lift" open>
          <summary className="flex cursor-pointer list-none items-center justify-between text-lg font-semibold">
            <span className="flex items-center gap-2"><ClipboardCheck size={18} className="text-green-deep" aria-hidden="true" />Antes de tu cirugía</span>
            <ChevronDown size={18} className="transition group-open:rotate-180" aria-hidden="true" />
          </summary>
          <ul className="mt-3 space-y-2 text-[15px]">
            {["No comas ni tomes nada desde 8 horas antes (salvo lo que te indique tu anestesiólogo).",
              "Llega 2 horas antes con tu documento de identidad y la orden de la cirugía.",
              "Ven con un acompañante adulto que pueda llevarte a casa.",
              "Si tienes fiebre, gripa o tos en estos días, avísale al hospital: es mejor reprogramar."].map((t) => (
              <li key={t} className="flex gap-2"><CheckCircle2 size={17} className="mt-0.5 shrink-0 text-green-deep" aria-hidden="true" />{t}</li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-gray-strong">Recomendaciones generales. Sigue siempre las indicaciones de tu equipo médico.</p>
        </details>
      )}

      {r.signos.length > 0 && (
        <section aria-labelledby="t-signos" className="rounded-[28px] bg-paper-white p-6 shadow-lift">
          <h2 id="t-signos" className="flex items-center gap-2 text-lg font-semibold"><HeartPulse size={18} className="text-coral-deep" aria-hidden="true" />Tus últimos signos vitales</h2>
          <p className="mt-1 text-sm text-gray-strong">Tomados el {fechaYHora(r.signos[0].fecha)}</p>
          <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {r.signos.map((s) => (
              <div key={s.nombre} className="rounded-2xl bg-cloud-card px-4 py-3">
                <dt className="text-xs text-gray-strong">{s.nombre}</dt>
                <dd className="text-xl font-semibold tabular-nums">{Number.isInteger(s.valor) ? s.valor : s.valor.toFixed(1)} <span className="text-xs font-normal text-gray-strong">{s.unidad}</span></dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {r.equipo.length > 0 && (
        <section aria-labelledby="t-equipo" className="rounded-[28px] bg-paper-white p-6 shadow-lift">
          <h2 id="t-equipo" className="flex items-center gap-2 text-lg font-semibold"><Stethoscope size={18} className="text-metric-blue" aria-hidden="true" />Tu equipo de atención</h2>
          <ul className="mt-4 grid gap-2 sm:grid-cols-2">
            {r.equipo.map((m, i) => (
              <li key={i} className="flex items-center gap-3 rounded-2xl bg-cloud-card px-4 py-3">
                <span className="grid size-10 shrink-0 place-items-center rounded-full bg-charcoal text-sm font-semibold text-white" aria-hidden="true">{iniciales(m.nombre)}</span>
                <span className="min-w-0">
                  <span className="block truncate font-medium">{m.nombre}</span>
                  <span className="block text-xs text-gray-strong">{m.funcion[0].toUpperCase() + m.funcion.slice(1)}{m.especialidad ? ` · ${m.especialidad}` : ""}</span>
                </span>
              </li>
            ))}
          </ul>
          {r.remisiones.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm">
              {r.remisiones.map((x, i) => (
                <li key={i} className="flex items-center gap-2 text-gray-strong">
                  <UserRound size={14} aria-hidden="true" />Te remitieron a {x.especialidad || "un especialista"} ({x.especialista}) · {x.estado === "pendiente" ? "esperando respuesta" : x.estado}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section id="resultados" className="scroll-mt-40 rounded-[28px] bg-paper-white p-6 shadow-lift" aria-label="Resultados">
        <h2 className="flex items-center gap-2 text-lg font-semibold"><Sparkles size={18} className="text-metric-blue" aria-hidden="true" />Tus resultados</h2>
        <p className="mt-1 text-sm text-gray-strong">Solo aparecen los resultados que tu médico ya revisó y aprobó.</p>
        {reportes.demo && <div className="mt-2"><ChipDemo visible /></div>}
        {reportes.lista.length === 0 ? (
          <p className="mt-4 rounded-3xl bg-cloud-card p-5 text-sm">Todavía no tienes resultados aprobados.</p>
        ) : (
          <ul className="mt-4 space-y-3">{reportes.lista.map((x) => <Resultado key={x.id} r={x} />)}</ul>
        )}
      </section>

      <div id="imagenes" className="scroll-mt-40"><GaleriaImagenes pacienteId={pid} /></div>
      <div id="cobros" className="scroll-mt-40"><MisCobros /></div>

      {r.historial.length > 0 && (
        <section id="historial" className="scroll-mt-40 rounded-[28px] bg-paper-white p-6 shadow-lift" aria-label="Historial">
          <h2 className="flex items-center gap-2 text-lg font-semibold"><HeartPulse size={18} className="text-coral-deep" aria-hidden="true" />Tu historial</h2>
          <ol className="mt-4 space-y-4 border-l-2 border-cloud-card pl-5">
            {r.historial.map((e, i) => (
              <li key={i} className="relative">
                <span className={`absolute -left-[27px] top-1.5 size-3 rounded-full ${e.estado === "finished" ? "bg-metric-blue" : "bg-gold-deep"}`} aria-hidden="true" />
                <p className="text-sm font-medium">{TIPO[e.tipo] || e.tipo}{e.detalle ? ` · ${e.detalle}` : ""}{e.estado !== "finished" ? " · en curso" : ""}</p>
                <p className="text-xs text-gray-strong">{fechaYHora(e.fecha)}{e.profesional ? ` · ${e.profesional}` : ""}</p>
              </li>
            ))}
          </ol>
        </section>
      )}

      <div id="datos" className="scroll-mt-40"><MisDatos /></div>

      <BotonHistoriaPDF pacienteId={pid} nombre={nombre} ancho texto="Descargar mi historia clínica (PDF)" />
    </div>
  );
}
