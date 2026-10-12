import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowRightLeft, CalendarPlus, ChevronLeft, ChevronRight, Loader2, Siren, XCircle } from "lucide-react";
import Encabezado from "../../components/Encabezado";
import Esqueleto from "../../components/Esqueleto";
import ErrorEstado from "../../components/ErrorEstado";
import Insignia from "../../components/Insignia";
import Panel from "../../components/Panel";
import { useAvisos } from "../../components/Avisos";
import * as S from "../../lib/servicios";
import { useSondeo } from "../../lib/hooks";
import { hora } from "../../lib/format";
import { infoQx } from "../../lib/estados";
import { ESTADO_CIRUGIA } from "../../lib/clinico";

const entrada = "w-full rounded-2xl bg-cloud-card px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-metric-blue/40";
const hoyISO = () => new Date().toLocaleDateString("en-CA");          // AAAA-MM-DD local
const sumarDias = (iso, n) => { const d = new Date(`${iso}T12:00:00`); d.setDate(d.getDate() + n); return d.toLocaleDateString("en-CA"); };
// <input type="datetime-local"> trabaja en hora local sin zona; la API recibe ISO con zona.
const aLocal = (iso) => { const d = new Date(iso); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); };
const enMediaHora = () => { const d = new Date(Date.now() + 30 * 60000); d.setMinutes(Math.ceil(d.getMinutes() / 5) * 5, 0, 0); return aLocal(d.toISOString()); };

/**
 * Programación quirúrgica del día, sala por sala. El enfermero(a) jefe
 * programa, mueve y cancela; si llega una urgencia puede meterla y correr
 * las cirugías siguientes de esa sala. Cada cambio pide un motivo y queda en
 * la auditoría.
 */
export default function CoordinacionQuirurgica() {
  const [fecha, setFecha] = useState(hoyISO());
  const agenda = useSondeo(() => S.cirugiasDia(fecha), 30000);
  const [catalogos, setCatalogos] = useState(null);
  const [accion, setAccion] = useState(null);     // {tipo: "programar"|"mover"|"cancelar", cirugia?, urgencia?}
  useEffect(() => { S.cirugiasCatalogos().then(setCatalogos).catch(() => setCatalogos(null)); }, []);
  useEffect(() => { agenda.recargar(); }, [fecha]); // eslint-disable-line react-hooks/exhaustive-deps

  const d = agenda.datos;
  const resumen = useMemo(() => {
    const todas = (d?.salas || []).flatMap((s) => s.cirugias);
    return {
      programadas: todas.filter((c) => c.estado === "planned").length,
      enCurso: todas.filter((c) => c.estado === "in-progress").length,
      urgencias: todas.filter((c) => c.origen === "urgencia" && c.estado !== "cancelled").length,
      canceladas: todas.filter((c) => c.estado === "cancelled").length,
    };
  }, [d]);
  const cerrar = useCallback(() => setAccion(null), []);
  const hecho = useCallback(() => { setAccion(null); agenda.recargar(); }, [agenda]);

  if (agenda.error && !d) return <ErrorEstado status={agenda.error.status} detalle={agenda.error.message} />;

  return (
    <div className="space-y-6 pb-16">
      <Encabezado titulo="Coordinación quirúrgica" subtitulo="Programa, mueve o cancela cirugías. Cada cambio pide un motivo y queda auditado.">
        <button onClick={() => setAccion({ tipo: "programar", urgencia: true })}
                className="flex items-center gap-2 rounded-full bg-coral-deep px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-coral-ink">
          <Siren size={16} aria-hidden="true" />Urgencia
        </button>
        <button onClick={() => setAccion({ tipo: "programar" })}
                className="flex items-center gap-2 rounded-full bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink">
          <CalendarPlus size={16} aria-hidden="true" />Programar cirugía
        </button>
      </Encabezado>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1 rounded-full bg-cloud-card p-1">
          <button onClick={() => setFecha((f) => sumarDias(f, -1))} aria-label="Día anterior" className="grid size-9 place-items-center rounded-full hover:bg-paper-white"><ChevronLeft size={16} /></button>
          <input type="date" value={fecha} onChange={(e) => e.target.value && setFecha(e.target.value)} aria-label="Fecha"
                 className="rounded-full bg-transparent px-2 text-sm font-medium outline-none" />
          <button onClick={() => setFecha((f) => sumarDias(f, 1))} aria-label="Día siguiente" className="grid size-9 place-items-center rounded-full hover:bg-paper-white"><ChevronRight size={16} /></button>
          {fecha !== hoyISO() && <button onClick={() => setFecha(hoyISO())} className="rounded-full px-3 py-1.5 text-sm font-medium hover:bg-paper-white">Hoy</button>}
        </div>
        <p className="text-sm text-gray-strong">
          <b className="text-ink">{resumen.enCurso}</b> en curso · <b className="text-ink">{resumen.programadas}</b> programadas ·{" "}
          <b className="text-ink">{resumen.urgencias}</b> urgencias · <b className="text-ink">{resumen.canceladas}</b> canceladas
          {d && <> · rotación entre cirugías {d.rotacion_min} min</>}
        </p>
      </div>

      {d?.conflictos?.length > 0 && (
        <p role="alert" className="flex items-start gap-2 rounded-2xl bg-gold-soft px-4 py-3 text-sm text-gold-ink">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          {d.conflictos.length === 1 ? "Hay una cirugía que ya no cabe" : `Hay ${d.conflictos.length} cirugías que ya no caben`} por
          retrasos de la anterior ({d.conflictos.map((c) => c.quirofano).join(", ")}). Muévelas o córrelas.
        </p>
      )}

      {!d ? <Esqueleto filas={4} alto="h-40" /> : (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {d.salas.map((s) => (
            <Sala key={s.id} sala={s} conflictos={d.conflictos}
                  onMover={(c) => setAccion({ tipo: "mover", cirugia: c })}
                  onCancelar={(c) => setAccion({ tipo: "cancelar", cirugia: c })} />
          ))}
        </div>
      )}

      {accion?.tipo === "programar" && <Programar catalogos={catalogos} urgencia={!!accion.urgencia} onCerrar={cerrar} onListo={hecho} />}
      {accion?.tipo === "mover" && <Mover catalogos={catalogos} cirugia={accion.cirugia} onCerrar={cerrar} onListo={hecho} />}
      {accion?.tipo === "cancelar" && <Cancelar catalogos={catalogos} cirugia={accion.cirugia} onCerrar={cerrar} onListo={hecho} />}
    </div>
  );
}

function Sala({ sala, conflictos, onMover, onCancelar }) {
  const info = infoQx(sala.estado);
  const conConflicto = new Set(conflictos.filter((c) => c.quirofano === sala.codigo).map((c) => c.cirugia_id));
  return (
    <section aria-label={`Sala ${sala.codigo}`} className="flex flex-col rounded-[28px] bg-cloud-card p-5">
      <header className="mb-3 flex items-center justify-between gap-2">
        <div>
          <h2 className="font-mono text-lg font-semibold">{sala.codigo}</h2>
          <p className="text-xs text-gray-strong">{sala.nombre}{sala.tiene_arco_c ? " · arco en C" : ""}</p>
        </div>
        <Insignia grupo={info.grupo} etiqueta={info.etiqueta} tamano="sm" />
      </header>
      {sala.cirugias.length === 0 ? (
        <p className="rounded-2xl bg-paper-white/70 px-4 py-6 text-center text-sm text-gray-strong">Sin cirugías este día</p>
      ) : (
        <ol className="space-y-2">
          {sala.cirugias.map((c) => {
            const tachada = c.estado === "cancelled";
            return (
              <li key={c.id} className={`rounded-2xl bg-paper-white p-3 ${conConflicto.has(c.id) ? "ring-2 ring-gold-deep" : ""} ${tachada ? "opacity-60" : ""}`}>
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-semibold tabular-nums">
                    {hora(c.hora_real_inicio || c.hora_programada_inicio)}{c.hora_programada_fin && !c.hora_real_fin ? `–${hora(c.hora_programada_fin)}` : ""}
                  </p>
                  <span className="flex flex-wrap justify-end gap-1">
                    {c.origen === "urgencia" && <span className="rounded-full bg-coral-deep px-2 py-0.5 text-[11px] font-semibold text-white">Urgencia</span>}
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${c.estado === "in-progress" ? "bg-gold-soft text-gold-ink" : tachada ? "bg-cloud-card text-slate-ink" : "bg-hero-sky text-ink"}`}>{ESTADO_CIRUGIA[c.estado] || c.estado}</span>
                  </span>
                </div>
                <p className={`mt-1 text-sm ${tachada ? "line-through" : ""}`}>{c.procedimiento}</p>
                <p className="text-xs text-gray-strong">{c.paciente} · {c.cirujano || "cirujano sin asignar"}</p>
                {c.estado === "planned" && (
                  <div className="mt-2 flex gap-1.5">
                    <button onClick={() => onMover(c)} className="flex items-center gap-1 rounded-full bg-cloud-card px-3 py-1.5 text-xs font-semibold transition hover:bg-hero-sky">
                      <ArrowRightLeft size={13} aria-hidden="true" />Mover
                    </button>
                    <button onClick={() => onCancelar(c)} className="flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-semibold text-coral-ink transition hover:bg-coral-soft">
                      <XCircle size={13} aria-hidden="true" />Cancelar
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

/** Lista de choques que devuelve la API (409) y la opción de correr las siguientes. */
function Choques({ choques, onCorrer, enviando }) {
  const hayEnCurso = choques.some((c) => c.estado === "in-progress");
  return (
    <div role="alert" className="anim-pop rounded-2xl bg-gold-soft p-4 text-sm text-gold-ink">
      <p className="flex items-center gap-2 font-semibold"><AlertTriangle size={15} aria-hidden="true" />La sala está ocupada en ese horario</p>
      <ul className="mt-2 space-y-1">
        {choques.map((c) => (
          <li key={c.id}>· {hora(c.hora_real_inicio || c.hora_programada_inicio)} {c.procedimiento} ({c.paciente}) — {ESTADO_CIRUGIA[c.estado]}</li>
        ))}
      </ul>
      {hayEnCurso ? (
        <p className="mt-2">Hay una cirugía en curso a esa hora: elige otra sala o una hora posterior.</p>
      ) : (
        <button type="button" onClick={onCorrer} disabled={enviando}
                className="mt-3 flex items-center gap-2 rounded-full bg-charcoal px-4 py-2 text-xs font-semibold text-white transition hover:bg-ink disabled:opacity-50">
          {enviando && <Loader2 size={13} className="anim-spin" />}Hacerlo y correr las siguientes de la sala
        </button>
      )}
    </div>
  );
}

function useEnvio(onListo) {
  const { avisar } = useAvisos();
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);
  const [choques, setChoques] = useState(null);
  const enviar = async (fn, mensaje) => {
    setEnviando(true); setError(null);
    try {
      const r = await fn();
      const corridas = r?.corridas?.length || 0;
      avisar(corridas ? `${mensaje}. Se corrieron ${corridas} cirugía(s) de la sala.` : mensaje);
      onListo();
    } catch (e) {
      if (e.status === 409 && e.data?.detail?.choques) setChoques(e.data.detail.choques);
      else setError(e.message);
    } finally { setEnviando(false); }
  };
  return { enviando, error, choques, setChoques, enviar };
}

function Programar({ catalogos, urgencia, onCerrar, onListo }) {
  const [f, setF] = useState({ documento: "", procedimiento_id: "", quirofano_id: "", hora: enMediaHora(), cirujano_id: "", anestesiologo_id: "", origen: urgencia ? "urgencia" : "electiva", motivo: "" });
  const { enviando, error, choques, setChoques, enviar } = useEnvio(onListo);
  const campo = (k) => (e) => { setF((x) => ({ ...x, [k]: e.target.value })); setChoques(null); };
  const proc = catalogos?.procedimientos.find((p) => String(p.id) === String(f.procedimiento_id));
  const salas = (catalogos?.quirofanos || []).filter((q) => q.estado !== "bloqueado" && (!proc?.requiere_arco_c || q.tiene_arco_c));
  const cirujanos = (catalogos?.cirujanos || []).filter((c) => !proc || c.especialidad_id === proc.especialidad_id);
  const porEspecialidad = useMemo(() => {
    const g = {};
    (catalogos?.procedimientos || []).forEach((p) => { (g[p.especialidad] ||= []).push(p); });
    return Object.entries(g);
  }, [catalogos]);

  const mandar = (desplazar) => enviar(() => S.programarCirugia({
    documento: f.documento.trim(), procedimiento_id: Number(f.procedimiento_id), quirofano_id: Number(f.quirofano_id),
    hora_inicio: new Date(f.hora).toISOString(), cirujano_id: f.cirujano_id ? Number(f.cirujano_id) : null,
    anestesiologo_id: f.anestesiologo_id ? Number(f.anestesiologo_id) : null, origen: f.origen,
    prioridad: f.origen === "urgencia" ? 1 : 3, desplazar, motivo: f.motivo || null,
  }), f.origen === "urgencia" ? "Urgencia programada" : "Cirugía programada");

  return (
    <Panel abierto titulo={urgencia ? "Urgencia quirúrgica" : "Programar cirugía"} onCerrar={onCerrar}
           subtitulo={urgencia ? "Busca la primera sala apta; si está ocupada, puedes correr las siguientes." : "La sala debe tener el equipo que pide el procedimiento."}>
      {!catalogos ? <Esqueleto filas={5} /> : (
        <form id="f-programar" onSubmit={(e) => { e.preventDefault(); mandar(false); }} className="space-y-4">
          <label className="block text-sm">Documento del paciente
            <input required inputMode="numeric" value={f.documento} onChange={(e) => setF((x) => ({ ...x, documento: e.target.value.replace(/\D/g, "") }))} className={`${entrada} mt-1`} placeholder="Se busca cifrado (índice ciego)" />
          </label>
          <label className="block text-sm">Procedimiento
            <select required value={f.procedimiento_id} onChange={campo("procedimiento_id")} className={`${entrada} mt-1`}>
              <option value="">Elige…</option>
              {porEspecialidad.map(([esp, ps]) => (
                <optgroup key={esp} label={esp}>{ps.map((p) => <option key={p.id} value={p.id}>{p.nombre} · {p.duracion_estimada_min} min{p.requiere_arco_c ? " · arco en C" : ""}</option>)}</optgroup>
              ))}
            </select>
            {proc && <span className="mt-1 block text-xs text-gray-strong">Recuperación en {proc.cama_requerida}.</span>}
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm">Sala
              <select required value={f.quirofano_id} onChange={campo("quirofano_id")} className={`${entrada} mt-1`}>
                <option value="">Elige…</option>
                {salas.map((q) => <option key={q.id} value={q.id}>{q.codigo}{q.tiene_arco_c ? " · arco C" : ""}</option>)}
              </select>
            </label>
            <label className="block text-sm">Inicio
              <input required type="datetime-local" value={f.hora} onChange={campo("hora")} className={`${entrada} mt-1`} />
            </label>
          </div>
          <label className="block text-sm">Cirujano
            <select value={f.cirujano_id} onChange={campo("cirujano_id")} className={`${entrada} mt-1`}>
              <option value="">Sin asignar todavía</option>
              {cirujanos.map((c) => <option key={c.id} value={c.id}>{c.nombre} · {c.especialidad}</option>)}
            </select>
          </label>
          <label className="block text-sm">Anestesiólogo
            <select value={f.anestesiologo_id} onChange={campo("anestesiologo_id")} className={`${entrada} mt-1`}>
              <option value="">Sin asignar todavía</option>
              {catalogos.anestesiologos.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
          </label>
          <fieldset className="text-sm">
            <legend>Tipo</legend>
            <div className="mt-1 flex gap-2">
              {[["electiva", "Electiva"], ["urgencia", "Urgencia"]].map(([v, t]) => (
                <label key={v} className={`cursor-pointer rounded-full px-4 py-2 font-medium ${f.origen === v ? (v === "urgencia" ? "bg-coral-deep text-white" : "bg-charcoal text-white") : "bg-cloud-card"}`}>
                  <input type="radio" name="origen" value={v} checked={f.origen === v} onChange={campo("origen")} className="sr-only" />{t}
                </label>
              ))}
            </div>
          </fieldset>
          <label className="block text-sm">Motivo o nota (opcional)
            <input value={f.motivo} onChange={campo("motivo")} maxLength={200} className={`${entrada} mt-1`} placeholder="Ej.: apendicitis perforada, remitida de urgencias" />
          </label>
          {choques && <Choques choques={choques} enviando={enviando} onCorrer={() => mandar(true)} />}
          {error && <p role="alert" className="text-sm text-coral-ink">{error}</p>}
          <button type="submit" disabled={enviando}
                  className="flex w-full items-center justify-center gap-2 rounded-full bg-charcoal px-5 py-3 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50">
            {enviando && <Loader2 size={15} className="anim-spin" />}Programar
          </button>
        </form>
      )}
    </Panel>
  );
}

function Mover({ catalogos, cirugia, onCerrar, onListo }) {
  const [f, setF] = useState({ quirofano_id: String(cirugia.quirofano_id || ""), hora: aLocal(cirugia.hora_programada_inicio), motivo: "" });
  const { enviando, error, choques, setChoques, enviar } = useEnvio(onListo);
  const campo = (k) => (e) => { setF((x) => ({ ...x, [k]: e.target.value })); setChoques(null); };
  const mandar = (desplazar) => enviar(() => S.reprogramarCirugia(cirugia.id, {
    quirofano_id: Number(f.quirofano_id), hora_inicio: new Date(f.hora).toISOString(), motivo: f.motivo.trim(), desplazar,
  }), "Cirugía movida");
  return (
    <Panel abierto titulo="Mover cirugía" onCerrar={onCerrar} subtitulo={`${cirugia.procedimiento} · ${cirugia.paciente}`}>
      <form onSubmit={(e) => { e.preventDefault(); mandar(false); }} className="space-y-4">
        <p className="rounded-2xl bg-cloud-card px-4 py-3 text-sm">Ahora: <b>{hora(cirugia.hora_programada_inicio)}</b> · {cirugia.cirujano || "sin cirujano"}</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">Nueva sala
            <select value={f.quirofano_id} onChange={campo("quirofano_id")} className={`${entrada} mt-1`}>
              {(catalogos?.quirofanos || []).filter((q) => q.estado !== "bloqueado").map((q) => <option key={q.id} value={q.id}>{q.codigo}{q.tiene_arco_c ? " · arco C" : ""}</option>)}
            </select>
          </label>
          <label className="block text-sm">Nueva hora
            <input required type="datetime-local" value={f.hora} onChange={campo("hora")} className={`${entrada} mt-1`} />
          </label>
        </div>
        <label className="block text-sm">Motivo (obligatorio, queda en la auditoría)
          <input required minLength={3} value={f.motivo} onChange={campo("motivo")} maxLength={200} className={`${entrada} mt-1`} placeholder="Ej.: liberar QX-04 para una urgencia" />
        </label>
        {choques && <Choques choques={choques} enviando={enviando} onCorrer={() => mandar(true)} />}
        {error && <p role="alert" className="text-sm text-coral-ink">{error}</p>}
        <button type="submit" disabled={enviando}
                className="flex w-full items-center justify-center gap-2 rounded-full bg-charcoal px-5 py-3 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50">
          {enviando && <Loader2 size={15} className="anim-spin" />}Mover
        </button>
      </form>
    </Panel>
  );
}

function Cancelar({ catalogos, cirugia, onCerrar, onListo }) {
  const [f, setF] = useState({ causa_id: "", detalle: "" });
  const { enviando, error, enviar } = useEnvio(onListo);
  const grupos = useMemo(() => {
    const g = {};
    (catalogos?.causas_cancelacion || []).forEach((c) => { (g[c.responsable] ||= []).push(c); });
    return Object.entries(g);
  }, [catalogos]);
  const NOMBRE = { paciente: "Atribuible al paciente", prestador: "Atribuible al hospital", asegurador: "Atribuible a la EPS" };
  return (
    <Panel abierto titulo="Cancelar cirugía" onCerrar={onCerrar} subtitulo={`${cirugia.procedimiento} · ${cirugia.paciente} · ${hora(cirugia.hora_programada_inicio)}`}>
      <form onSubmit={(e) => { e.preventDefault(); enviar(() => S.cancelarCirugia(cirugia.id, { causa_id: Number(f.causa_id), detalle: f.detalle || null }), "Cirugía cancelada"); }} className="space-y-4">
        <p className="text-sm text-gray-strong">La causa alimenta el indicador de cancelación (Res. 256 de 2016). Si la cirugía solo cambia de hora o de sala, usa <b>Mover</b>.</p>
        <label className="block text-sm">Causa
          <select required value={f.causa_id} onChange={(e) => setF((x) => ({ ...x, causa_id: e.target.value }))} className={`${entrada} mt-1`}>
            <option value="">Elige…</option>
            {grupos.map(([r, cs]) => <optgroup key={r} label={NOMBRE[r] || r}>{cs.map((c) => <option key={c.id} value={c.id}>{c.descripcion}</option>)}</optgroup>)}
          </select>
        </label>
        <label className="block text-sm">Detalle
          <textarea value={f.detalle} onChange={(e) => setF((x) => ({ ...x, detalle: e.target.value }))} maxLength={500} rows={3} className={`${entrada} mt-1`} />
        </label>
        {error && <p role="alert" className="text-sm text-coral-ink">{error}</p>}
        <button type="submit" disabled={enviando}
                className="flex w-full items-center justify-center gap-2 rounded-full bg-coral-deep px-5 py-3 text-sm font-semibold text-white transition hover:bg-coral-ink disabled:opacity-50">
          {enviando && <Loader2 size={15} className="anim-spin" />}Cancelar cirugía
        </button>
      </form>
    </Panel>
  );
}
