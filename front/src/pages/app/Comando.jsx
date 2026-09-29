import { useMemo, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import Anillo from "../../components/Anillo";
import DrawerCama from "../../components/DrawerCama";
import DrawerQuirofano from "../../components/DrawerQuirofano";
import PanelCamas from "../../components/PanelCamas";
import PanelQuirofanos from "../../components/PanelQuirofanos";
import { api } from "../../api";
import { useReloj, useSondeo, useUsuario } from "../../lib/hooks";
import { cop, horaConSegundos } from "../../lib/format";
import { cortoTipo, TIPOS_CAMA } from "../../lib/estados";
import { resumenCamas, retrasoCirugia, UMBRAL_RETRASO_MIN } from "../../lib/tablero";

const SONDEO_MS = 15000;

async function cargarAgenda() {
  try {
    return { ...(await api("/quirofanos/agenda")), conAgenda: true };
  } catch (e) {
    if (e.status !== 404) throw e; // servidor sin la agenda: se cae al listado simple
    const lista = await api("/quirofanos");
    return { ahora: null, conAgenda: false, quirofanos: lista.map((q) => ({ ...q, actual: null, proximas: [] })) };
  }
}

function Kpi({ titulo, children, pie }) {
  return (
    <article className="flex flex-col rounded-[28px] bg-cloud-card p-6">
      <h3 className="text-sm font-medium text-gray-strong">{titulo}</h3>
      <div className="mt-3 flex-1">{children}</div>
      {pie && <div className="mt-4 text-sm">{pie}</div>}
    </article>
  );
}

const Cifra = ({ children, sub }) => (
  <p className="flex items-baseline gap-2">
    <span className="text-[44px] font-semibold leading-none tracking-tight tabular-nums">{children}</span>
    {sub && <span className="text-lg text-gray-strong">{sub}</span>}
  </p>
);

function Esqueleto() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Cargando el tablero">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <div key={i} className="h-44 animate-pulse rounded-[28px] bg-cloud-card" />)}
      </div>
      <div className="h-96 animate-pulse rounded-[28px] bg-cloud-card" />
    </div>
  );
}

export default function Comando() {
  const usuario = useUsuario();
  const camas = useSondeo(() => api("/camas/ocupacion?solo_ocupadas=false"), SONDEO_MS);
  const agenda = useSondeo(cargarAgenda, SONDEO_MS);
  const reloj = useReloj(30000);
  const [camaId, setCamaId] = useState(null);
  const [qxId, setQxId] = useState(null);

  // Los tiempos vienen del servidor: se corrige la diferencia con el reloj del navegador.
  const desfase = agenda.datos?.ahora && agenda.actualizado ? Date.parse(agenda.datos.ahora) - agenda.actualizado : 0;
  const ahora = reloj + desfase;

  const lista = camas.datos;
  const qx = agenda.datos?.quirofanos;
  const res = useMemo(() => (lista ? resumenCamas(lista, ahora) : null), [lista, ahora]);

  const recargarTodo = () => Promise.all([camas.recargar(), agenda.recargar()]);
  const cargando = camas.cargando || agenda.cargando;

  if (!lista && camas.cargando) return <Esqueleto />;
  if (!lista) {
    return (
      <div role="alert" className="flex items-start gap-3 rounded-[28px] bg-coral-soft p-6 text-coral-ink">
        <AlertTriangle className="mt-0.5 shrink-0" aria-hidden="true" />
        <div>
          <p className="font-semibold">No se pudo cargar el tablero</p>
          <p className="mt-1 text-sm">{camas.error?.message} {camas.error?.status === 403 && "Tu rol no tiene permiso para ver las camas."}</p>
          <button onClick={recargarTodo} className="mt-3 rounded-full bg-coral-ink px-4 py-2 text-sm font-semibold text-white">Reintentar</button>
        </div>
      </div>
    );
  }

  const uci = res.porTipo.UCI;
  const pctUci = uci ? (uci.ocupado / uci.total) * 100 : 0;
  const enCirugia = (qx || []).filter((q) => q.estado === "en_cirugia").length;
  const retrasadas = (qx || []).map((q) => retrasoCirugia(q.actual, ahora)).filter((r) => r >= UMBRAL_RETRASO_MIN);
  const peor = Math.max(0, ...retrasadas);
  const camaSel = lista.find((c) => c.cama_id === camaId);
  const qxSel = qx?.find((q) => q.id === qxId);

  return (
    <div className="space-y-6 pb-16">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[34px] font-semibold leading-tight tracking-display">Centro de mando</h1>
          <p className="mt-1 text-sm text-gray-strong">
            {res.total} camas · {qx?.length ?? 13} quirófanos · actualizado a las {horaConSegundos(camas.actualizado)}
            {camas.error && <span className="ml-2 font-semibold text-coral-ink">Sin conexión: se muestran los últimos datos</span>}
          </p>
        </div>
        <button onClick={recargarTodo} disabled={cargando}
                className="inline-flex items-center gap-2 rounded-full bg-cloud-card px-4 py-2.5 text-sm font-semibold transition hover:bg-hero-sky disabled:opacity-60">
          <RefreshCw size={15} className={cargando ? "anim-spin" : ""} aria-hidden="true" />Actualizar
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi titulo="Ocupación UCI adultos"
             pie={uci && <span className="text-gray-strong">{uci.proceso} en proceso · {uci.libre} disponibles</span>}>
          <div className="flex items-center gap-4">
            <Anillo valor={pctUci} color={pctUci >= 85 ? "var(--color-coral-deep)" : "var(--color-metric-blue)"} etiqueta={`Ocupación UCI ${Math.round(pctUci)} por ciento`}>
              <span className="text-xl font-semibold tabular-nums">{Math.round(pctUci)}%</span>
            </Anillo>
            {uci && <p className="text-sm text-gray-strong"><span className="block text-2xl font-semibold tabular-nums text-ink">{uci.ocupado}/{uci.total}</span>camas ocupadas</p>}
          </div>
        </Kpi>

        <Kpi titulo="Camas disponibles"
             pie={<span className="flex flex-wrap gap-1.5">
               {TIPOS_CAMA.map((t) => {
                 const n = res.porTipo[t.codigo]?.libre ?? 0;
                 return <span key={t.codigo} className={`rounded-full px-2 py-0.5 text-xs font-semibold ${n === 0 ? "bg-coral-soft text-coral-ink" : "bg-paper-white text-ink"}`}>{cortoTipo(t.codigo)} {n}</span>;
               })}
             </span>}>
          <Cifra sub={`de ${res.total}`}>{res.libres}</Cifra>
        </Kpi>

        <Kpi titulo="Quirófanos en cirugía"
             pie={!agenda.datos?.conAgenda
               ? <span className="text-gray-strong">Sin agenda de cirugías</span>
               : retrasadas.length > 0
                 ? <span className="inline-flex items-center gap-1.5 rounded-full bg-coral-soft px-2.5 py-1 text-xs font-semibold text-coral-ink"><AlertTriangle size={13} aria-hidden="true" />{retrasadas.length} con retraso · hasta +{peor} min</span>
                 : <span className="inline-flex rounded-full bg-green-soft px-2.5 py-1 text-xs font-semibold text-green-ink">Sin retrasos</span>}>
          <Cifra sub={`de ${qx?.length ?? 13}`}>{enCirugia}</Cifra>
        </Kpi>

        <Kpi titulo="Camas en limpieza"
             pie={<span className="text-gray-strong">≈ {cop(res.limpieza.costo)} de espera acumulada</span>}>
          <Cifra sub="camas">{res.limpieza.n}</Cifra>
        </Kpi>
      </div>

      <PanelCamas camas={lista} ahora={ahora} seleccionadaId={camaId} onAbrir={(c) => setCamaId(c.cama_id)} />

      {qx && agenda.error?.status !== 403 && (
        <PanelQuirofanos quirofanos={qx} ahora={ahora} conAgenda={!!agenda.datos?.conAgenda} onAbrir={(q) => setQxId(q.id)} />
      )}

      <DrawerCama cama={camaSel} ahora={ahora} usuario={usuario} onCerrar={() => setCamaId(null)} onCambio={recargarTodo} />
      <DrawerQuirofano quirofano={qxSel} ahora={ahora} usuario={usuario} onCerrar={() => setQxId(null)} onCambio={recargarTodo} />
    </div>
  );
}
