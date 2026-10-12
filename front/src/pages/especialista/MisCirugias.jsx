import { Link } from "react-router-dom";
import { BedDouble, CheckCircle2, Clock, Scissors, UserCheck, UserX } from "lucide-react";
import Encabezado from "../../components/Encabezado";
import Esqueleto from "../../components/Esqueleto";
import ErrorEstado from "../../components/ErrorEstado";
import * as S from "../../lib/servicios";
import { useReloj, useSondeo } from "../../lib/hooks";
import { duracion, hora, minutosDesde } from "../../lib/format";

/**
 * Lo único quirúrgico que le importa a un especialista: si un paciente SUYO
 * está en cirugía, cuándo entra y si él está asignado. Sin el tablero de los
 * 13 quirófanos ni cirugías ajenas.
 */
export default function MisCirugias() {
  const ahora = useReloj(30000);
  const r = useSondeo(() => S.misCirugias(7), 30000);
  if (r.error && !r.datos) return <ErrorEstado status={r.error.status} detalle={r.error.message} />;
  const lista = r.datos?.cirugias;
  const enCurso = (lista || []).filter((c) => c.estado === "in-progress");
  const proximas = (lista || []).filter((c) => c.estado === "planned");
  const hechas = (lista || []).filter((c) => c.estado === "finished");
  const asignadas = (lista || []).filter((c) => c.mi_papel && c.estado !== "finished").length;

  return (
    <div className="space-y-8 pb-16">
      <Encabezado titulo="Mis cirugías"
                  subtitulo="Cirugías de tus pacientes y las que tienes asignadas, de hoy a 7 días." />
      <div className="grid gap-3 sm:grid-cols-3">
        <Dato etiqueta="En quirófano ahora" valor={enCurso.length} tono={enCurso.length ? "bg-gold-soft" : "bg-cloud-card"} />
        <Dato etiqueta="Programadas" valor={proximas.length} />
        <Dato etiqueta="Donde usted es el cirujano o anestesiólogo" valor={asignadas} />
      </div>
      {!lista ? <Esqueleto filas={4} alto="h-24" /> : lista.length === 0 ? (
        <p className="rounded-[28px] bg-cloud-card p-6 text-sm text-gray-strong">Ningún paciente tuyo tiene cirugía en los próximos 7 días.</p>
      ) : (
        <>
          <Grupo titulo="En quirófano ahora" cirugias={enCurso} ahora={ahora} />
          <Grupo titulo="Programadas" cirugias={proximas} ahora={ahora} />
          <Grupo titulo="Terminadas hoy" cirugias={hechas} ahora={ahora} />
        </>
      )}
    </div>
  );
}

function Dato({ etiqueta, valor, tono = "bg-cloud-card" }) {
  return (
    <div className={`rounded-[28px] p-5 ${tono}`}>
      <p className="text-sm font-medium">{etiqueta}</p>
      <p className="mt-2 text-4xl font-semibold tabular-nums tracking-display">{valor}</p>
    </div>
  );
}

function Grupo({ titulo, cirugias, ahora }) {
  if (!cirugias.length) return null;
  return (
    <section aria-label={titulo}>
      <h2 className="mb-3 text-lg font-semibold">{titulo}</h2>
      <ul className="space-y-2">{cirugias.map((c) => <Fila key={c.id} c={c} ahora={ahora} />)}</ul>
    </section>
  );
}

function Fila({ c, ahora }) {
  const enCurso = c.estado === "in-progress";
  const transcurrido = enCurso ? minutosDesde(c.hora_real_inicio, ahora) : 0;
  const avance = enCurso && c.duracion_estimada_min ? Math.min(100, (transcurrido / c.duracion_estimada_min) * 100) : 0;
  const papel = c.mi_papel === "cirujano" ? "Usted es el cirujano" : c.mi_papel === "anestesiologo" ? "Usted es el anestesiólogo" : null;
  return (
    <li className={`grid gap-3 rounded-[24px] p-4 sm:grid-cols-[120px_1fr_auto] sm:items-center ${enCurso ? "bg-gold-soft" : "bg-cloud-card"}`}>
      <div>
        <p className="font-mono text-lg font-semibold">{c.quirofano || "—"}</p>
        <p className="flex items-center gap-1 text-xs text-gray-strong"><Clock size={12} aria-hidden="true" />
          {enCurso ? `desde ${hora(c.hora_real_inicio)}` : c.estado === "finished" ? `terminó ${hora(c.hora_real_fin)}` : hora(c.hora_programada_inicio)}
        </p>
      </div>
      <div className="min-w-0">
        <p className="truncate font-semibold">
          {c.es_mi_paciente ? <Link to={`/app/pacientes/${c.paciente_id}`} className="hover:underline">{c.paciente}</Link> : c.paciente}
          <span className="font-normal text-gray-strong"> · {c.procedimiento}</span>
        </p>
        <p className="text-xs text-gray-strong">
          Cirujano: {c.cirujano || "sin asignar"}{c.anestesiologo ? ` · Anestesia: ${c.anestesiologo}` : ""}
          {c.cama_destino ? <> · <BedDouble size={12} className="inline" aria-hidden="true" /> Cama de destino {c.cama_destino}</> : null}
        </p>
        {enCurso && (
          <div className="mt-2 flex items-center gap-2">
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-paper-white"><span className="block h-full rounded-full bg-gold-deep" style={{ width: `${avance}%` }} /></span>
            <span className="text-xs tabular-nums text-gold-ink">{duracion(transcurrido)} de {duracion(c.duracion_estimada_min)}</span>
          </div>
        )}
        {c.retraso_inicio_min > 10 && <p className="mt-1 text-xs text-coral-ink">Empezó {c.retraso_inicio_min} min tarde</p>}
      </div>
      <div className="flex flex-wrap gap-1.5 sm:justify-end">
        {papel ? (
          <span className="flex items-center gap-1 rounded-full bg-charcoal px-3 py-1 text-xs font-semibold text-white"><UserCheck size={13} aria-hidden="true" />{papel}</span>
        ) : (
          <span className="flex items-center gap-1 rounded-full bg-paper-white px-3 py-1 text-xs font-semibold text-slate-ink"><UserX size={13} aria-hidden="true" />No está asignado</span>
        )}
        {c.es_mi_paciente && <span className="flex items-center gap-1 rounded-full bg-paper-white px-3 py-1 text-xs font-semibold text-green-ink"><CheckCircle2 size={13} aria-hidden="true" />Su paciente</span>}
        {c.origen === "urgencia" && <span className="flex items-center gap-1 rounded-full bg-coral-deep px-3 py-1 text-xs font-semibold text-white"><Scissors size={13} aria-hidden="true" />Urgencia</span>}
      </div>
    </li>
  );
}
