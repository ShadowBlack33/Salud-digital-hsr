import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, BedDouble, Clock, LogIn, LogOut, ShieldCheck, Siren, UserCog } from "lucide-react";
import Encabezado from "../../components/Encabezado";
import Esqueleto from "../../components/Esqueleto";
import ErrorEstado from "../../components/ErrorEstado";
import Insignia from "../../components/Insignia";
import DrawerCama from "../../components/DrawerCama";
import { EsperandoCama, usePendientesCama } from "../../components/AsignarCama";
import { PanelTraslados, useAreas } from "../../components/Traslados";
import { useAvisos } from "../../components/Avisos";
import { api } from "../../api";
import { infoCama } from "../../lib/estados";
import { duracion, hora } from "../../lib/format";
import { useReloj, useUsuario } from "../../lib/hooks";
import { esAdmin } from "../../lib/roles";

/**
 * Tablero del área para el enfermero(a) jefe: sus camas con cada paciente,
 * lo que requiere atención, quién está de turno y la programación. Solo el
 * jefe de turno opera el área; los demás la ven en solo lectura.
 */
const TURNO = { manana: "Mañana · 6 h", tarde: "Tarde · 6 h", noche: "Noche · 12 h", cobertura: "Cobertura" };
const NIVEL = { alta: "bg-coral-soft text-coral-ink", media: "bg-gold-soft text-gold-ink", baja: "bg-cloud-card text-ink" };
const FILTROS = [["todas", "Todas"], ["con_paciente", "Con paciente"], ["libres", "Libres"], ["atencion", "Requieren atención"]];

function Kpi({ icono: Icono, etiqueta, valor, detalle, alerta }) {
  return (
    <div className={`rounded-[24px] p-5 ${alerta ? "bg-coral-soft" : "bg-cloud-card"}`}>
      <p className="flex items-center justify-between text-sm font-medium">{etiqueta}<Icono size={17} className={alerta ? "text-coral-deep" : "text-metric-blue"} aria-hidden="true" /></p>
      <p className="mt-3 text-3xl font-semibold tabular-nums tracking-display">{valor}</p>
      {detalle && <p className="mt-1 text-xs text-gray-strong">{detalle}</p>}
    </div>
  );
}

function Turno({ t, onCubierto }) {
  const { avisar } = useAvisos();
  const [motivo, setMotivo] = useState("");
  const [abierto, setAbierto] = useState(false);
  const actual = t.actual;
  const cubrir = async (e) => {
    e.preventDefault();
    try { await api("/areas/turno/cubrir", { method: "POST", json: { motivo } }); avisar("Ahora estás de turno en esta área"); setAbierto(false); onCubierto(); }
    catch (err) { avisar(err.message, "error"); }
  };
  return (
    <section className={`rounded-[28px] p-5 ${t.soy_yo ? "bg-green-soft" : t.puedo_operar ? "bg-cloud-card" : "bg-gold-soft"}`} aria-label="Turno">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2 font-semibold">
          {t.soy_yo ? <ShieldCheck size={18} aria-hidden="true" /> : <UserCog size={18} aria-hidden="true" />}
          {t.soy_yo ? `Estás de turno hasta las ${hora(actual.fin)}`
            : actual ? `De turno: ${actual.username} hasta las ${hora(actual.fin)}${t.puedo_operar ? "" : " · tú ves el área en solo lectura"}`
            : "Sin turno programado ahora"}
        </p>
        {!t.soy_yo && !t.puedo_operar && !abierto && (
          <button onClick={() => setAbierto(true)} className="rounded-full bg-charcoal px-4 py-2 text-sm font-semibold text-white">Cubrir el turno</button>
        )}
      </div>
      {abierto && (
        <form onSubmit={cubrir} className="mt-3 flex flex-wrap gap-2">
          <label htmlFor="motivo-cobertura" className="sr-only">Motivo</label>
          <input id="motivo-cobertura" required minLength={5} value={motivo} onChange={(e) => setMotivo(e.target.value)}
                 placeholder="Motivo (p. ej. incapacidad de la jefe de turno)" className="min-w-0 flex-1 rounded-full border border-paper-white bg-paper-white px-4 py-2 text-sm" />
          <button type="submit" className="rounded-full bg-charcoal px-4 py-2 text-sm font-semibold text-white">Confirmar</button>
          <button type="button" onClick={() => setAbierto(false)} className="rounded-full px-3 py-2 text-sm">Cancelar</button>
        </form>
      )}
      {t.programacion.length > 0 && (
        <ol className="mt-4 flex gap-2 overflow-x-auto pb-1" aria-label="Programación de turnos">
          {t.programacion.map((p) => {
            const ahora = actual && p.id === actual.id;
            return (
              <li key={p.id} className={`min-w-[150px] rounded-2xl px-3 py-2 text-xs ${ahora ? "bg-charcoal text-white" : "bg-paper-white"}`}>
                <p className="font-semibold">{TURNO[p.tipo] || p.tipo}</p>
                <p className={ahora ? "text-white/80" : "text-gray-strong"}>{hora(p.inicio)} – {hora(p.fin)}</p>
                <p className="mt-0.5 font-medium">{p.username}</p>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

function TarjetaCama({ c, onAbrir }) {
  const info = infoCama(c.estado_cama);
  const conPaciente = c.encuentro_activo && c.paciente_nombre_corto && ["ocupada", "reservada", "en_proceso_alta"].includes(c.estado_cama);
  return (
    <li>
      <button onClick={() => onAbrir(c.cama_id)} className="flex h-full w-full flex-col rounded-2xl bg-paper-white p-4 text-left transition hover:-translate-y-0.5 hover:shadow-lift">
        <span className="flex items-center justify-between gap-2">
          <span className="font-mono text-sm font-semibold">{c.cama_codigo}</span>
          {c.criticos_24h > 0 && <span className="rounded-full bg-coral-deep px-2 py-0.5 text-[11px] font-semibold text-white">{c.criticos_24h} crítico{c.criticos_24h > 1 ? "s" : ""}</span>}
        </span>
        <span className="mt-1.5"><Insignia grupo={info.grupo} etiqueta={info.etiqueta} tamano="sm" /></span>
        {conPaciente ? (
          <>
            <span className="mt-2 text-sm font-semibold">{c.paciente_nombre_corto}</span>
            {c.diagnostico && <span className="line-clamp-2 text-xs text-gray-strong">{c.diagnostico}</span>}
            <span className="mt-auto pt-2 text-xs text-gray-strong">
              {c.dias_estancia != null ? `${c.dias_estancia} d de estancia` : ""}{c.medico_nombre ? ` · ${c.medico_nombre.split(" ").slice(0, 2).join(" ")}` : ""}
            </span>
          </>
        ) : (
          <span className="mt-2 flex items-center gap-1 text-xs text-gray-strong"><Clock size={12} aria-hidden="true" />{duracion(c.minutos_en_estado || 0)} así</span>
        )}
      </button>
    </li>
  );
}

export default function MiArea() {
  const usuario = useUsuario();
  const admin = esAdmin(usuario);
  const { areas } = useAreas();
  const [servicio, setServicio] = useState(null);
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  const [filtro, setFiltro] = useState("todas");
  const [camaId, setCamaId] = useState(null);
  const reloj = useReloj(30000);
  const pendientes = usePendientesCama(true);

  const cargar = useCallback(() => {
    const q = admin && servicio ? `?servicio_id=${servicio}` : "";
    return api(`/areas/tablero${q}`).then((r) => { setD(r); setError(null); }).catch(setError);
  }, [admin, servicio]);
  useEffect(() => { cargar(); const t = setInterval(cargar, 20000); return () => clearInterval(t); }, [cargar]);
  const recargar = () => Promise.all([cargar(), pendientes.recargar()]);

  const atencion = useMemo(() => new Set((d?.alertas || []).map((a) => a.cama)), [d]);
  const camas = (d?.camas || []).filter((c) => filtro === "todas" ? true
    : filtro === "con_paciente" ? c.encuentro_activo && c.paciente_nombre_corto && ["ocupada", "reservada", "en_proceso_alta"].includes(c.estado_cama)
    : filtro === "libres" ? c.estado_cama === "disponible" : atencion.has(c.cama_codigo));

  if (error) return <ErrorEstado status={error.status} detalle={error.message} />;
  if (!d) return <Esqueleto filas={4} alto="h-24" />;
  const r = d.resumen, pe = r.por_estado || {};
  const camaSel = d.camas.find((c) => c.cama_id === camaId);

  return (
    <div className="space-y-6 pb-16">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <Encabezado titulo={d.area.nombre} subtitulo={`Tablero del área · ${r.total} camas · se actualiza solo`} />
        {admin && (
          <label className="text-sm font-medium" htmlFor="sel-area">Área
            <select id="sel-area" value={servicio || d.area.id} onChange={(e) => setServicio(Number(e.target.value))}
                    className="ml-2 rounded-full border border-cloud-card bg-paper-white px-3 py-2 text-sm">
              {areas.map((a) => <option key={a.id} value={a.id}>{a.nombre}</option>)}
            </select>
          </label>
        )}
      </div>

      <Turno t={d.turno} onCubierto={recargar} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi icono={BedDouble} etiqueta="Ocupación" valor={`${r.pct_ocupacion} %`} detalle={`${r.ocupadas} de ${r.utiles} camas útiles`} alerta={r.pct_ocupacion >= 90} />
        <Kpi icono={BedDouble} etiqueta="Camas libres" valor={pe.disponible || 0} detalle={`${pe.en_limpieza || 0} en limpieza · ${(pe.bloqueada || 0) + (pe.contaminada || 0)} fuera de servicio`} alerta={(pe.disponible || 0) === 0} />
        <Kpi icono={LogOut} etiqueta="Altas por salir" valor={pe.en_proceso_alta || 0} detalle={`${r.egresos_hoy} egresos hoy · estancia promedio ${r.estancia_promedio_dias ?? "—"} d`} />
        <Kpi icono={LogIn} etiqueta="Ingresos hoy" valor={r.ingresos_hoy} detalle={`${r.traslados_entrantes} traslados por recibir · ${r.traslados_salientes} enviados`} alerta={r.traslados_entrantes > 0} />
      </div>

      {d.alertas.length > 0 && (
        <section aria-labelledby="t-alertas" className="rounded-[28px] bg-paper-white p-5 shadow-lift">
          <h2 id="t-alertas" className="flex items-center gap-2 font-semibold"><AlertTriangle size={17} aria-hidden="true" />Requiere atención</h2>
          <ul className="mt-3 grid gap-2 md:grid-cols-2">
            {d.alertas.slice(0, 10).map((a, i) => (
              <li key={i}>
                <button onClick={() => setCamaId(d.camas.find((c) => c.cama_codigo === a.cama)?.cama_id)}
                        className={`flex w-full items-center gap-2 rounded-2xl px-3 py-2 text-left text-sm ${NIVEL[a.nivel]}`}>
                  {a.nivel === "alta" ? <Siren size={14} aria-hidden="true" /> : <Clock size={14} aria-hidden="true" />}
                  <b className="font-mono">{a.cama}</b><span>{a.texto}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {d.es_mia && <PanelTraslados onCambio={recargar} soloLectura={!d.turno.puedo_operar} />}
      {d.es_mia && <EsperandoCama pendientes={pendientes} miArea={d.area.id} soloLectura={!d.turno.puedo_operar} />}

      <section aria-labelledby="t-camas" className="rounded-[32px] bg-cloud-card p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="t-camas" className="text-lg font-semibold">Camas y pacientes</h2>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrar camas">
            {FILTROS.map(([v, t]) => (
              <button key={v} onClick={() => setFiltro(v)} aria-pressed={filtro === v}
                      className={`rounded-full px-3 py-1.5 text-sm ${filtro === v ? "bg-charcoal text-white" : "bg-paper-white"}`}>{t}</button>
            ))}
          </div>
        </div>
        {camas.length === 0 ? <p className="mt-4 text-sm text-gray-strong">No hay camas con ese filtro.</p> : (
          <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {camas.map((c) => <TarjetaCama key={c.cama_id} c={c} onAbrir={setCamaId} />)}
          </ul>
        )}
      </section>

      <DrawerCama cama={camaSel} ahora={reloj} usuario={usuario} onCerrar={() => setCamaId(null)} onCambio={recargar}
                  deMiArea={(d.es_mia || admin) && d.turno.puedo_operar} areaCama={d.area.id} />
    </div>
  );
}
