import { Activity, AlertTriangle, BedDouble, Brain, Clock, HeartPulse, Scissors, Siren, TrendingDown, TrendingUp, Wallet } from "lucide-react";
import Encabezado from "../../components/Encabezado";
import Esqueleto from "../../components/Esqueleto";
import ErrorEstado from "../../components/ErrorEstado";
import * as S from "../../lib/servicios";
import { useSondeo } from "../../lib/hooks";
import { cop, haceCuanto } from "../../lib/format";

const RIESGO = {
  colapso: { texto: "Colapso", fondo: "bg-coral-deep text-white", barra: "bg-coral-deep" },
  alto: { texto: "Riesgo alto", fondo: "bg-coral-soft text-coral-ink", barra: "bg-coral-deep" },
  medio: { texto: "Vigilar", fondo: "bg-gold-soft text-gold-ink", barra: "bg-gold-deep" },
  bajo: { texto: "Estable", fondo: "bg-green-soft text-green-ink", barra: "bg-green-deep" },
};
const ORDEN = { colapso: 0, alto: 1, medio: 2, bajo: 3 };
const millones = (n) => (Math.abs(n) >= 1e6 ? `$${(n / 1e6).toLocaleString("es-CO", { maximumFractionDigits: 1 })} M` : cop(n));

/**
 * El hospital de un vistazo, para el coordinador. Todo es agregado: ningún
 * paciente aparece aquí. La pregunta que responde es "¿qué área está por
 * colapsar, cuánto estamos perdiendo y cómo va la operación?".
 */
export default function Hospital() {
  const r = useSondeo(S.tableroHospital, 30000);
  const d = r.datos;
  if (r.error && !d) return <ErrorEstado status={r.error.status} detalle={r.error.message} />;
  if (!d) return <div className="space-y-6"><Esqueleto filas={2} alto="h-32" /><Esqueleto filas={5} alto="h-14" /></div>;

  const areas = [...d.areas].sort((a, b) => ORDEN[a.riesgo] - ORDEN[b.riesgo] || b.pct_proyectado_12h - a.pct_proyectado_12h);
  const enRiesgo = areas.filter((a) => a.riesgo === "alto" || a.riesgo === "colapso");
  const perdidaHoy = d.dinero.perdida_ociosa_hoy_cop;
  const qx = d.quirofanos, cx = d.cirugias_hoy;
  const usoQx = qx.total ? Math.round((100 * qx.en_cirugia) / (qx.total - qx.bloqueados || 1)) : 0;

  return (
    <div className="space-y-8 pb-16">
      <Encabezado titulo="Así va el hospital" subtitulo={`Capacidad, riesgo de colapso, dinero y operación · actualizado ${haceCuanto(d.ahora)}`} />

      {enRiesgo.length > 0 && (
        <div role="alert" className="flex items-start gap-3 rounded-[28px] bg-coral-soft p-5">
          <AlertTriangle size={22} className="mt-0.5 shrink-0 text-coral-deep" aria-hidden="true" />
          <div>
            <p className="font-semibold text-coral-ink">{enRiesgo.length === 1 ? "Un área está cerca del colapso" : `${enRiesgo.length} áreas están cerca del colapso`}</p>
            <p className="mt-0.5 text-sm text-coral-ink">
              {enRiesgo.map((a) => `${a.area} (${a.tipo_nombre}): ${a.pct_ocupacion} % hoy, ${a.pct_proyectado_12h} % en 12 h`).join(" · ")}.
              {" "}Considera habilitar camas, acelerar altas o diferir cirugías electivas que necesiten ese tipo de cama.
            </p>
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi icono={BedDouble} etiqueta="Ocupación de camas" valor={`${d.resumen.pct_ocupacion} %`}
             detalle={`${d.resumen.camas_ocupadas} de ${d.resumen.camas_utiles} camas útiles`} alerta={d.resumen.pct_ocupacion >= 90} />
        <Kpi icono={Scissors} etiqueta="Quirófanos en uso" valor={`${usoQx} %`}
             detalle={`${qx.en_cirugia} operando · ${qx.disponibles} libres · ${qx.en_rotacion} en rotación · ${qx.bloqueados} bloqueados`} />
        <Kpi icono={Siren} etiqueta="Urgencias en espera" valor={d.urgencias.en_espera ?? 0}
             detalle={`${d.urgencias.triage_1_2 ?? 0} en triage 1-2 · espera promedio ${d.urgencias.espera_promedio_min ?? 0} min`}
             alerta={(d.urgencias.triage_1_2 ?? 0) > 0} />
        <Kpi icono={TrendingDown} etiqueta="Pérdida por camas ociosas hoy" valor={millones(perdidaHoy)}
             detalle="Horas de cama disponible × costo día" tono="text-coral-deep" />
      </div>

      <section aria-labelledby="t-areas" className="rounded-[32px] bg-cloud-card p-6 sm:p-7">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 id="t-areas" className="text-2xl font-semibold tracking-display">Capacidad por área</h2>
            <p className="text-sm text-gray-strong">La proyección suma las cirugías de las próximas 12 h que necesitarán ese tipo de cama y resta las altas en proceso.</p>
          </div>
          <Leyenda />
        </div>
        <ul className="space-y-3">
          {areas.map((a) => <FilaArea key={`${a.codigo}-${a.tipo_cama}`} a={a} />)}
        </ul>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-labelledby="t-op" className="rounded-[32px] bg-cloud-card p-6">
          <h2 id="t-op" className="flex items-center gap-2 text-lg font-semibold"><Activity size={18} aria-hidden="true" />Operación quirúrgica de hoy</h2>
          <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Cifra etiqueta="En curso" valor={cx.en_curso} />
            <Cifra etiqueta="Pendientes" valor={cx.pendientes} />
            <Cifra etiqueta="Terminadas" valor={cx.terminadas} />
            <Cifra etiqueta="Urgencias" valor={cx.urgencias} />
            <Cifra etiqueta="Canceladas" valor={cx.canceladas} alerta={cx.canceladas > 0} />
            <Cifra etiqueta="Retraso promedio" valor={`${cx.retraso_promedio_min ?? 0} min`} alerta={(cx.retraso_promedio_min ?? 0) > 20} />
          </dl>
        </section>

        <section aria-labelledby="t-dinero" className="rounded-[32px] bg-cloud-card p-6">
          <h2 id="t-dinero" className="flex items-center gap-2 text-lg font-semibold"><Wallet size={18} aria-hidden="true" />Dinero</h2>
          <ul className="mt-4 space-y-2.5 text-sm">
            <Linea icono={TrendingUp} texto="Estancia que se causa hoy (camas ocupadas)" valor={d.dinero.estancia_dia_actual_cop} bueno />
            <Linea icono={TrendingUp} texto="Cirugías iniciadas hoy (tarifa de referencia)" valor={d.dinero.cirugias_hoy_cop} bueno />
            <Linea icono={TrendingUp} texto="Procedimientos terminados este mes" valor={d.dinero.producido_procedimientos_cop} bueno />
            <Linea icono={TrendingDown} texto={`Cancelaciones del mes (${d.dinero.cancelaciones_mes})`} valor={d.dinero.perdida_cancelaciones_cop} />
            <Linea icono={TrendingDown} texto="Camas ociosas este mes" valor={d.dinero.perdida_camas_ociosas_cop} />
          </ul>
          <p className="mt-3 text-xs text-gray-strong">Tarifas y costos de referencia del caso de estudio. La facturación real está en el módulo contable.</p>
        </section>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-labelledby="t-ia" className="rounded-[32px] bg-cloud-card p-6">
          <h2 id="t-ia" className="flex items-center gap-2 text-lg font-semibold"><Brain size={18} aria-hidden="true" />Inteligencia artificial</h2>
          {d.ia.reportes ? (
            <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Cifra etiqueta="Reportes (30 d)" valor={d.ia.reportes.total} />
              <Cifra etiqueta="Pendientes" valor={d.ia.reportes.pendientes} alerta={d.ia.reportes.pendientes > 0} />
              <Cifra etiqueta="Aprobados" valor={d.ia.reportes.aprobados} />
              <Cifra etiqueta="Rechazados" valor={d.ia.reportes.rechazados} />
            </dl>
          ) : (
            <p className="mt-3 text-sm text-gray-strong">El módulo de IA aún no ha publicado reportes. Cuando lo haga, aquí verás cuántos se generan, cuántos aprueban los médicos y cuántos rechazan (una señal de qué tan útil es el modelo).</p>
          )}
          {d.ia.modelos.length > 0 && (
            <ul className="mt-4 space-y-1 text-sm">
              {d.ia.modelos.map((m) => <li key={m.modelo}>· {m.modelo}: {m.n} predicciones, error medio {m.error_medio ?? "—"}</li>)}
            </ul>
          )}
        </section>

        <section aria-labelledby="t-alertas" className="rounded-[32px] bg-cloud-card p-6">
          <h2 id="t-alertas" className="flex items-center gap-2 text-lg font-semibold"><HeartPulse size={18} aria-hidden="true" />Alertas abiertas</h2>
          {d.alertas_abiertas.length === 0 ? <p className="mt-3 text-sm text-gray-strong">No hay alertas del sistema sin resolver.</p> : (
            <ul className="mt-3 space-y-2">
              {d.alertas_abiertas.map((a) => (
                <li key={`${a.tipo}-${a.severidad}`} className="flex items-center justify-between rounded-2xl bg-paper-white px-4 py-2.5 text-sm">
                  <span>{a.tipo.replaceAll("_", " ")} · <span className="text-gray-strong">{a.severidad}</span></span>
                  <b className="tabular-nums">{a.n}</b>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function Kpi({ icono: Icono, etiqueta, valor, detalle, alerta = false, tono = "text-metric-blue" }) {
  return (
    <div className={`rounded-[28px] p-6 ${alerta ? "bg-coral-soft" : "bg-cloud-card"}`}>
      <p className="flex items-center justify-between gap-2 text-sm font-medium">{etiqueta}<Icono size={19} className={alerta ? "text-coral-deep" : tono} aria-hidden="true" /></p>
      <p className="mt-4 text-4xl font-semibold tabular-nums tracking-display">{valor}</p>
      <p className="mt-1 text-xs text-gray-strong">{detalle}</p>
    </div>
  );
}

function FilaArea({ a }) {
  const r = RIESGO[a.riesgo];
  return (
    <li className="grid gap-3 rounded-2xl bg-paper-white p-4 md:grid-cols-[minmax(0,1.3fr)_minmax(0,2fr)_7rem] md:items-center">
      <div>
        <p className="font-semibold">{a.area}</p>
        <p className="text-xs text-gray-strong">{a.tipo_nombre} · {a.total} camas{a.fuera_servicio ? ` (${a.fuera_servicio} fuera de servicio)` : ""}</p>
      </div>
      <div>
        <div className="relative h-3 overflow-hidden rounded-full bg-cloud-card" role="img" aria-label={`Ocupación ${a.pct_ocupacion} %, proyectada ${a.pct_proyectado_12h} %`}>
          <span className="absolute inset-y-0 left-0 rounded-full bg-slate-ink/25" style={{ width: `${Math.min(100, a.pct_proyectado_12h)}%` }} />
          <span className={`absolute inset-y-0 left-0 rounded-full ${r.barra}`} style={{ width: `${Math.min(100, a.pct_ocupacion)}%` }} />
          <span className="absolute inset-y-0 w-px bg-ink/40" style={{ left: "90%" }} aria-hidden="true" />
        </div>
        <p className="mt-1.5 flex flex-wrap gap-x-3 text-xs text-gray-strong">
          <span><b className="text-ink">{a.pct_ocupacion} %</b> hoy</span>
          <span><b className="text-ink">{a.pct_proyectado_12h} %</b> en 12 h</span>
          <span>{a.disponibles} libres · {a.en_limpieza} en limpieza · {a.en_alta} en alta</span>
          {a.demanda_12h > 0 && <span>{a.demanda_12h} cirugías la necesitarán</span>}
          {a.costo_ocioso_hoy_cop > 0 && <span className="flex items-center gap-1"><Clock size={11} aria-hidden="true" />{millones(a.costo_ocioso_hoy_cop)} en camas sin usar</span>}
        </p>
      </div>
      <span className={`w-fit rounded-full px-3 py-1 text-xs font-semibold md:justify-self-end ${r.fondo}`}>{r.texto}</span>
    </li>
  );
}

function Leyenda() {
  return (
    <p className="flex flex-wrap items-center gap-3 text-xs text-gray-strong">
      <span className="flex items-center gap-1.5"><span className="h-2 w-5 rounded-full bg-green-deep" />ocupación hoy</span>
      <span className="flex items-center gap-1.5"><span className="h-2 w-5 rounded-full bg-slate-ink/25" />proyección a 12 h</span>
      <span className="flex items-center gap-1.5"><span className="h-3 w-px bg-ink/40" />umbral 90 %</span>
    </p>
  );
}

function Cifra({ etiqueta, valor, alerta = false }) {
  return (
    <div className={`rounded-2xl px-4 py-3 ${alerta ? "bg-coral-soft" : "bg-paper-white"}`}>
      <dt className="text-xs text-gray-strong">{etiqueta}</dt>
      <dd className="text-2xl font-semibold tabular-nums">{valor ?? 0}</dd>
    </div>
  );
}

function Linea({ icono: Icono, texto, valor, bueno = false }) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-2xl bg-paper-white px-4 py-2.5">
      <span className="flex items-center gap-2"><Icono size={15} className={bueno ? "text-green-deep" : "text-coral-deep"} aria-hidden="true" />{texto}</span>
      <b className="tabular-nums">{millones(valor)}</b>
    </li>
  );
}
