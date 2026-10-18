import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, BedDouble, ChevronRight, HeartPulse, ScanLine, Scissors, SearchX, Send, ShieldCheck, Siren, Stethoscope } from "lucide-react";
import Encabezado from "../../components/Encabezado";
import NuevoPaciente from "../../components/NuevoPaciente";
import { puede } from "../../api";
import { useUsuario } from "../../lib/hooks";
import Esqueleto from "../../components/Esqueleto";
import ErrorEstado from "../../components/ErrorEstado";
import * as S from "../../lib/servicios";
import { useSondeo } from "../../lib/hooks";
import { haceCuanto, hora } from "../../lib/format";
import { ESTADO_CIRUGIA, TIPO_ENCUENTRO, textoCobertura, valorClinico } from "../../lib/clinico";
import { useEventos } from "../../lib/tiempoReal";

const FILTROS = [
  ["todos", "Todos"],
  ["criticos", "Con críticos"],
  ["urgencias", "Urgencias"],
  ["hospitalizados", "Hospitalizados"],
  ["cirugia", "En cirugía o programados"],
  ["remitidos", "Remitidos"],
  ["imagenes", "Con radiografías"],
  ["estables", "Sin atención activa"],
];

const cumple = (p, f) => ({
  todos: true,
  criticos: p.criticos.length > 0,
  urgencias: p.encuentro?.tipo === "urgencias",
  hospitalizados: p.encuentro?.tipo === "hospitalizacion",
  cirugia: !!p.cirugia,
  remitidos: !!p.remision,
  imagenes: !!p.tiene_imagenes,
  estables: !p.encuentro && !p.cirugia,
}[f]);

const normalizar = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/**
 * Los pacientes del médico o especialista: los que registró, los que tiene a
 * cargo y los que le remitieron. Nada más: la API no le deja ver a los demás.
 * Arriba los que tienen valores críticos, luego los que están en cirugía.
 */
export default function MisPacientes() {
  const datos = useSondeo(S.misPacientes, 30000);
  useEventos((ev) => { if (!ev.local) datos.recargar?.(); });
  const [filtro, setFiltro] = useState("todos");
  const [texto, setTexto] = useState("");
  const lista = datos.datos?.pacientes;
  const usuario = useUsuario();

  const conteo = useMemo(() => Object.fromEntries(FILTROS.map(([k]) => [k, (lista || []).filter((p) => cumple(p, k)).length])), [lista]);
  const visibles = useMemo(() => {
    const t = normalizar(texto.trim());
    return (lista || []).filter((p) => cumple(p, filtro) &&
      (!t || normalizar(`${p.nombre} ${p.apellido} ${p.documento} ${p.encuentro?.cama || ""}`).includes(t)));
  }, [lista, filtro, texto]);

  if (datos.error && !lista) return <ErrorEstado status={datos.error.status} detalle={datos.error.message} />;

  return (
    <div className="space-y-6 pb-16">
      <Encabezado titulo="Mis pacientes"
                  subtitulo="Solo los pacientes a tu cargo: los que registraste, los que atiendes y los que te remitieron.">
        {puede(usuario, "paciente", "create") && <NuevoPaciente />}
      </Encabezado>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div role="tablist" aria-label="Filtrar pacientes" className="flex gap-1.5 overflow-x-auto pb-1">
          {FILTROS.map(([k, t]) => (
            <button key={k} role="tab" aria-selected={filtro === k} onClick={() => setFiltro(k)}
                    className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-4 py-2 text-sm font-medium transition ${filtro === k ? "bg-charcoal text-white" : "bg-cloud-card text-ink hover:bg-hero-sky"}`}>
              {t}<span className={`rounded-full px-1.5 text-xs tabular-nums ${filtro === k ? "bg-white/20" : k === "criticos" && conteo[k] ? "bg-coral-deep text-white" : "bg-paper-white"}`}>{conteo[k] ?? 0}</span>
            </button>
          ))}
        </div>
        <input type="search" value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Nombre, documento o cama"
               aria-label="Buscar entre mis pacientes"
               className="w-full rounded-full bg-cloud-card px-5 py-2.5 text-sm outline-none placeholder:text-gray-strong focus:ring-2 focus:ring-metric-blue lg:w-72" />
      </div>

      {!lista ? <Esqueleto filas={6} alto="h-24" /> : visibles.length === 0 ? (
        <p className="flex items-center gap-3 rounded-[28px] bg-cloud-card p-6 text-sm text-gray-strong">
          <SearchX size={20} aria-hidden="true" />
          {lista.length === 0 ? "No tienes pacientes a tu cargo en este momento." : "Ningún paciente coincide con el filtro."}
        </p>
      ) : (
        <ul className="grid gap-3 xl:grid-cols-2">
          {visibles.map((p) => <TarjetaPaciente key={p.paciente_id} p={p} />)}
        </ul>
      )}
    </div>
  );
}

function TarjetaPaciente({ p }) {
  const e = p.encuentro, cx = p.cirugia;
  const critico = p.criticos.length > 0;
  return (
    <li>
      <Link to={`/app/pacientes/${p.paciente_id}`}
            className={`group flex h-full flex-col gap-3 rounded-[28px] p-5 transition hover:-translate-y-0.5 hover:shadow-lift ${critico ? "bg-coral-soft" : "bg-cloud-card"}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-[17px] font-semibold">{p.nombre} {p.apellido}</p>
            <p className="text-xs text-gray-strong">
              {p.tipo_documento} {p.documento} · {p.edad != null ? `${p.edad} años` : "—"} · {p.sexo === "F" ? "Mujer" : p.sexo === "M" ? "Hombre" : "Otro"}
            </p>
          </div>
          <span className="flex shrink-0 items-center gap-1 rounded-full bg-paper-white px-2.5 py-1 text-[11px] font-semibold text-slate-ink" title="Quién responde por la atención">
            <ShieldCheck size={12} aria-hidden="true" />{textoCobertura(p.cobertura)}
          </span>
        </div>

        {p.equipo?.length > 1 && (
          <p className="rounded-2xl bg-paper-white/80 px-3 py-2 text-xs">
            <b className="font-semibold">Lo atienden {p.equipo.length} especialistas:</b> {p.equipo.map((x) => x.especialista).join(", ")}
          </p>
        )}
        {p.remision && (
          <p className={`flex flex-wrap items-center gap-1.5 rounded-2xl px-3 py-2 text-xs ${p.remision.recibida && p.remision.estado === "pendiente" ? "bg-hero-sky" : "bg-paper-white/80"}`}>
            <Send size={13} className="text-metric-blue" aria-hidden="true" />
            <b className="font-semibold">{p.remision.recibida ? `Remitido por ${p.remision.de}` : `Remitido a ${p.remision.para}`}</b>
            · {p.remision.estado}{p.remision.prioridad === "urgente" ? " · urgente" : ""} · {haceCuanto(p.remision.fecha)}
            <span className="w-full text-gray-strong">{p.remision.motivo}</span>
          </p>
        )}
        {critico && (
          <div className="rounded-2xl bg-paper-white/80 px-3 py-2">
            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-coral-ink"><AlertTriangle size={13} aria-hidden="true" />Valores críticos</p>
            <ul className="mt-1 flex flex-wrap gap-1.5">
              {p.criticos.slice(0, 3).map((c, i) => (
                <li key={i} className="rounded-full bg-coral-deep px-2.5 py-0.5 text-xs font-semibold text-white">{valorClinico(c)} <span className="font-normal opacity-90">· {haceCuanto(c.fecha)}</span></li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex flex-wrap gap-2 text-sm">
          {e ? (
            <span className="flex items-center gap-1.5 rounded-full bg-paper-white px-3 py-1">
              {e.tipo === "urgencias" ? <Siren size={14} className="text-coral-deep" aria-hidden="true" /> : <BedDouble size={14} className="text-metric-blue" aria-hidden="true" />}
              {TIPO_ENCUENTRO[e.tipo]}{e.triage ? ` · triage ${e.triage}` : ""}{e.cama ? ` · ${e.cama}` : ""}
              <span className="text-gray-strong">· {haceCuanto(e.desde)}</span>
            </span>
          ) : (
            <span className="flex items-center gap-1.5 rounded-full bg-paper-white px-3 py-1 text-gray-strong">
              <Stethoscope size={14} aria-hidden="true" />Última atención {p.ultima_atencion ? haceCuanto(p.ultima_atencion) : "—"}
            </span>
          )}
          {cx && (
            <span className={`flex items-center gap-1.5 rounded-full px-3 py-1 ${cx.estado === "in-progress" ? "bg-gold-soft text-gold-ink" : "bg-paper-white"}`}>
              <Scissors size={14} aria-hidden="true" />
              {ESTADO_CIRUGIA[cx.estado]}{cx.quirofano ? ` · ${cx.quirofano}` : ""}
              {cx.estado === "planned" && cx.hora_programada_inicio ? ` · ${hora(cx.hora_programada_inicio)}` : ""}
              <b className="font-semibold">{cx.mi_papel === "cirujano" ? " · usted opera" : cx.mi_papel === "anestesiologo" ? " · usted anestesia" : " · otro cirujano"}</b>
            </span>
          )}
        </div>
        {p.tiene_imagenes && (
          <span className="flex w-fit items-center gap-1.5 rounded-full bg-paper-white px-3 py-1 text-xs font-semibold text-metric-blue"><ScanLine size={13} aria-hidden="true" />Tiene radiografías en el PACS</span>
        )}
        {e?.diagnostico && <p className="flex items-center gap-1.5 text-xs text-gray-strong"><HeartPulse size={13} aria-hidden="true" />{e.dx_codigo} · {e.diagnostico}</p>}
        <span className="mt-auto flex items-center justify-end text-xs font-medium text-metric-blue">Abrir ficha<ChevronRight size={14} className="transition group-hover:translate-x-0.5" aria-hidden="true" /></span>
      </Link>
    </li>
  );
}
