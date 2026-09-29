import { useMemo } from "react";
import Insignia from "./Insignia";
import { GRUPOS, ORDEN_GRUPOS, infoQx } from "../lib/estados";
import { duracion, hora, minutosDesde } from "../lib/format";
import { retrasoCirugia, UMBRAL_RETRASO_MIN } from "../lib/tablero";

const ATRAS = 3 * 3600e3;     // la línea de tiempo muestra 3 h hacia atrás...
const ADELANTE = 8 * 3600e3;  // ...y 8 h hacia adelante
const soloHora = new Intl.DateTimeFormat("es-CO", { hour: "numeric" });

function Equipos({ q }) {
  return (
    <span className="flex flex-wrap gap-1">
      {q.tiene_circulacion_extracorporea && <span className="rounded-md bg-cloud-card px-1.5 py-0.5 text-[10px] font-semibold text-slate-ink">Circ. extracorp.</span>}
      {q.tiene_arco_c && !q.tiene_circulacion_extracorporea && <span className="rounded-md bg-cloud-card px-1.5 py-0.5 text-[10px] font-semibold text-slate-ink">Arco en C</span>}
    </span>
  );
}

function Leyenda() {
  const item = "flex items-center gap-1.5";
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-strong" aria-label="Leyenda del cronograma">
      <li className={item}><span className="h-2 w-5 rounded-full bg-metric-blue" />Avance</li>
      <li className={item}><span className="h-2 w-5 rounded-full bg-coral-deep" />Pasó del tiempo estimado</li>
      <li className={item}><span className="h-1 w-5 rounded-full bg-signal-gold" />Empezó tarde</li>
      <li className={item}><span className="h-2 w-5 rounded-full bg-cloud-card ring-1 ring-body-gray/30" />Programada</li>
    </ul>
  );
}

/** Cronograma de los quirófanos: cirugía en curso, retraso y las que siguen. */
export default function PanelQuirofanos({ quirofanos, ahora, onAbrir, conAgenda }) {
  const ini = ahora - ATRAS;
  const span = ATRAS + ADELANTE;
  const pct = (t) => Math.max(0, Math.min(100, ((t - ini) / span) * 100));

  const marcas = useMemo(() => {
    const d = new Date(ini); d.setMinutes(0, 0, 0);
    const r = [];
    for (let t = d.getTime() + 3600e3; t < ini + span; t += 3600e3) r.push(t);
    return r;
  }, [ini, span]);

  const conteo = useMemo(() => {
    const r = { libre: 0, ocupado: 0, proceso: 0, bloqueado: 0 };
    quirofanos.forEach((q) => { r[infoQx(q.estado).grupo]++; });
    return r;
  }, [quirofanos]);

  const ahoraPct = pct(ahora);

  return (
    <section aria-labelledby="t-qx" className="rounded-[28px] bg-cloud-card p-6 sm:p-7">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 id="t-qx" className="text-2xl font-semibold tracking-display">Quirófanos</h2>
          <p className="mt-1 text-sm text-gray-strong">{quirofanos.length} quirófanos · jornada de hoy</p>
        </div>
        <ul className="flex flex-wrap gap-2" aria-label="Resumen por estado">
          {ORDEN_GRUPOS.map((g) => (
            <li key={g}><Insignia grupo={g} etiqueta={`${conteo[g]} ${GRUPOS[g].etiqueta.toLowerCase()}`} /></li>
          ))}
        </ul>
      </div>

      {!conAgenda && (
        <p className="mt-4 rounded-2xl bg-gold-soft px-4 py-3 text-sm text-gold-ink">
          El servidor todavía no ofrece la agenda de cirugías; se muestra solo el estado de cada quirófano.
        </p>
      )}

      <div className="mt-5 overflow-x-auto">
        <div className="min-w-[760px]">
          {conAgenda && (
            <div className="grid grid-cols-[150px_1fr] gap-4 px-3 pb-2">
              <span />
              <div className="relative h-7 text-[11px] text-gray-strong">
                {marcas.filter((t) => pct(t) < 96 && Math.abs(pct(t) - ahoraPct) > 4).map((t) => (
                  <span key={t} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${pct(t)}%` }}>{soloHora.format(t)}</span>
                ))}
                <span className="absolute -translate-x-1/2 rounded-full bg-metric-blue px-2 py-0.5 text-[10px] font-semibold text-white" style={{ left: `${ahoraPct}%`, top: -2 }}>Ahora</span>
              </div>
            </div>
          )}

          <ul className="space-y-2">
            {quirofanos.map((q) => {
              const info = infoQx(q.estado);
              const a = q.actual;
              const retraso = retrasoCirugia(a, ahora);
              const siguiente = q.proximas?.[0];
              const desde = minutosDesde(q.estado_desde, ahora);

              let leyenda;
              if (a) leyenda = `${a.procedimiento} · ${a.cirujano || "sin cirujano"}`;
              else if (q.estado === "bloqueado") leyenda = `Bloqueado hace ${duracion(desde)}`;
              else leyenda = `${info.etiqueta} hace ${duracion(desde)}`;

              return (
                <li key={q.id}>
                  <button type="button" onClick={() => onAbrir(q)}
                          aria-label={`${q.codigo}, ${info.etiqueta}${a ? `, ${a.procedimiento}` : ""}`}
                          className="grid w-full grid-cols-[150px_1fr] items-start gap-4 rounded-2xl bg-paper-white p-3 text-left transition hover:shadow-lift">
                    <span className="flex flex-col items-start gap-1.5">
                      <span className="font-mono text-[13px] font-semibold">{q.codigo}</span>
                      <Insignia grupo={info.grupo} etiqueta={info.etiqueta} tamano="sm" />
                      <Equipos q={q} />
                    </span>

                    <span className="min-w-0">
                      {conAgenda && (
                        <span className="relative block h-9">
                          <span className="absolute inset-x-0 top-1/2 h-px bg-cloud-card" />
                          <span className="absolute inset-y-0 w-px bg-metric-blue/60" style={{ left: `${ahoraPct}%` }} />

                          {a && (() => {
                            const t0 = Date.parse(a.hora_real_inicio);
                            const previsto = t0 + a.duracion_estimada_min * 60000;
                            const fin = Math.max(previsto, ahora);
                            const total = fin - t0 || 1;
                            const prog0 = a.hora_programada_inicio ? Date.parse(a.hora_programada_inicio) : t0;
                            return (
                              <>
                                {t0 > prog0 && (
                                  <span className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-signal-gold"
                                        style={{ left: `${pct(prog0)}%`, width: `${pct(t0) - pct(prog0)}%` }} />
                                )}
                                <span className="absolute top-1/2 flex h-7 -translate-y-1/2 overflow-hidden rounded-full bg-metric-blue/15"
                                      style={{ left: `${pct(t0)}%`, width: `${Math.max(1.5, pct(fin) - pct(t0))}%` }}>
                                  <span className="h-full bg-metric-blue" style={{ width: `${(Math.min(ahora, previsto) - t0) / total * 100}%` }} />
                                  {ahora > previsto && <span className="h-full bg-coral-deep" style={{ width: `${(ahora - previsto) / total * 100}%` }} />}
                                </span>
                              </>
                            );
                          })()}

                          {q.proximas?.map((p) => {
                            const s = Date.parse(p.hora_programada_inicio), e = Date.parse(p.hora_programada_fin);
                            if (pct(s) >= 100) return null;
                            return (
                              <span key={p.encuentro_id} title={`${p.procedimiento} · ${hora(s)}`}
                                    className="absolute top-1/2 flex h-7 -translate-y-1/2 items-center overflow-hidden rounded-full bg-cloud-card px-2.5 text-[11px] font-medium text-slate-ink ring-1 ring-body-gray/25"
                                    style={{ left: `${pct(s)}%`, width: `${Math.max(2, pct(e) - pct(s))}%` }}>
                                <span className="truncate">{p.procedimiento}</span>
                              </span>
                            );
                          })}
                        </span>
                      )}

                      <span className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-xs ${conAgenda ? "mt-1.5" : ""}`}>
                        <span className="truncate text-gray-strong">{leyenda}</span>
                        {a && retraso >= UMBRAL_RETRASO_MIN && (
                          <span className="rounded-full bg-coral-soft px-2 py-0.5 font-semibold text-coral-ink">
                            Retraso +{retraso} min{a.cama_destino && ` · cama ${a.cama_destino} ${a.cama_destino_estado === "disponible" ? "lista" : "en espera"}`}
                          </span>
                        )}
                        {!a && siguiente && (
                          <span className="text-gray-strong">Siguiente: {siguiente.procedimiento} a las {hora(siguiente.hora_programada_inicio)}</span>
                        )}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      {conAgenda && <div className="mt-5"><Leyenda /></div>}
    </section>
  );
}
