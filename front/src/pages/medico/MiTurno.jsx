import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, AlertTriangle, ChevronRight, FileCheck, Send, Users } from "lucide-react";
import Esqueleto from "../../components/Esqueleto";
import * as S from "../../lib/servicios";
import { useEventos } from "../../lib/tiempoReal";
import { haceCuanto } from "../../lib/format";
import Encabezado from "../../components/Encabezado";
import TarjetaContador from "../../components/TarjetaContador";
import { useTiempoReal } from "../../lib/tiempoReal";
import { useUsuario } from "../../lib/hooks";
import { ESTADO_CIRUGIA, TIPO_ENCUENTRO, textoCobertura, valorClinico } from "../../lib/clinico";

/** Inicio del médico: trabajo pendiente en vivo (R18) y sus pacientes. */
export default function MiTurno() {
  const usuario = useUsuario();
  const { pendientes, demo, alertasActivas } = useTiempoReal();
  const [pacientes, setPacientes] = useState(null);
  const [detalle, setDetalle] = useState(null);       // "reportes" | "remisiones" | "alertas"
  const [items, setItems] = useState(null);

  // El detalle se carga al abrirlo y se refresca con cada evento.
  const cargarDetalle = useCallback(async (cual) => {
    if (!cual) return;
    setItems(null);
    try {
      if (cual === "reportes") setItems((await S.reportesPendientes()).datos);
      if (cual === "remisiones") setItems((await S.remisiones()).datos.filter((r) => r.estado === "pendiente"));
    } catch { setItems([]); }
  }, []);
  useEffect(() => { cargarDetalle(detalle); }, [detalle, cargarDetalle]);
  useEventos((ev) => { if (!ev.local) cargarDetalle(detalle); });
  const alternar = (cual) => setDetalle((d) => (d === cual ? null : cual));

  // Sus pacientes con lo que importa en el turno: críticos, urgencias, cirugía.
  const cargarPacientes = useCallback(() => S.misPacientes().then((r) => setPacientes(r.pacientes)).catch(() => setPacientes([])), []);
  useEffect(() => { cargarPacientes(); const id = setInterval(cargarPacientes, 30000); return () => clearInterval(id); }, [cargarPacientes]);
  useEventos((ev) => { if (!ev.local) cargarPacientes(); });
  const criticos = (pacientes || []).filter((p) => p.criticos.length > 0);
  const enUrgencias = (pacientes || []).filter((p) => p.encuentro?.tipo === "urgencias").length;
  const hospitalizados = (pacientes || []).filter((p) => p.encuentro?.tipo === "hospitalizacion").length;

  return (
    <div className="space-y-8 pb-16">
      <Encabezado titulo="Mi turno" subtitulo={`Hola, ${usuario?.username}. Esto es lo que necesita tu atención ahora.`} demo={demo} />

      <div className="grid gap-4 md:grid-cols-3">
        <TarjetaContador etiqueta="Reportes de IA por revisar" valor={pendientes.reportes_por_revisar} icono={FileCheck}
                         detalle="Esperan tu aprobación antes de entrar a la historia"
                         onClick={() => alternar("reportes")} abierta={detalle === "reportes"} />
        <TarjetaContador etiqueta="Remisiones" valor={pendientes.remisiones_recibidas} icono={Send} tono="text-green-deep"
                         detalle="Pendientes de respuesta" onClick={() => alternar("remisiones")} abierta={detalle === "remisiones"} />
        <TarjetaContador etiqueta="Alertas activas" valor={pendientes.alertas_activas} icono={AlertCircle}
                         tono={pendientes.alertas_activas ? "text-coral-deep" : "text-gray-strong"}
                         resaltar={pendientes.alertas_activas > 0} detalle="Casos críticos sin reconocer"
                         onClick={() => alternar("alertas")} abierta={detalle === "alertas"} />
      </div>

      {detalle && (
        <section className="anim-pop rounded-[28px] bg-paper-white p-6 shadow-lift" aria-label="Detalle">
          {detalle === "alertas" ? (
            alertasActivas.length === 0 ? <p className="text-sm text-gray-strong">No hay alertas activas.</p> : (
              <ul className="divide-y divide-cloud-card">
                {alertasActivas.map((a) => (
                  <li key={a.id}>
                    <Link to={`/app/pacientes/${a.paciente_id}`} state={{ pestana: "ia" }} className="flex items-center justify-between gap-3 rounded-2xl px-3 py-3 transition hover:bg-cloud-card/60">
                      <span><span className="block text-sm font-medium">{a.mensaje}</span><span className="text-xs text-gray-strong">{haceCuanto(a.created_at)} · reconócela en el aviso de arriba</span></span>
                      <ChevronRight size={18} className="text-gray-strong" aria-hidden="true" />
                    </Link>
                  </li>
                ))}
              </ul>
            )
          ) : !items ? <Esqueleto filas={2} /> : items.length === 0 ? (
            <p className="text-sm text-gray-strong">{detalle === "reportes" ? "No hay reportes esperando revisión." : "No hay remisiones pendientes."}</p>
          ) : (
            <ul className="divide-y divide-cloud-card">
              {items.map((x) => (
                <li key={x.id}>
                  <Link to={detalle === "reportes" ? `/app/pacientes/${x.paciente_id}` : "/app/remisiones"} state={detalle === "reportes" ? { pestana: "ia" } : undefined}
                        className="flex items-center justify-between gap-3 rounded-2xl px-3 py-3 transition hover:bg-cloud-card/60">
                    <span>
                      <span className="block text-sm font-medium">
                        {detalle === "reportes" ? `Reporte ${x.id} · ${Math.round(Number(x.probabilidad || 0) * 100)} % de requerir UCI` : `${x.paciente_nombre || "Paciente"} · ${x.especialista || x.medico}`}
                      </span>
                      <span className="text-xs text-gray-strong">{haceCuanto(x.created_at)}{detalle === "reportes" ? " · abrir para aprobar o rechazar" : ` · ${x.motivo}`}</span>
                    </span>
                    <ChevronRight size={18} className="text-gray-strong" aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section className={`rounded-[28px] p-6 ${criticos.length ? "bg-coral-soft" : "bg-cloud-card"}`} aria-labelledby="t-criticos">
        <h2 id="t-criticos" className="flex items-center gap-2 text-lg font-semibold">
          <AlertTriangle size={18} className={criticos.length ? "text-coral-deep" : "text-gray-strong"} aria-hidden="true" />
          Casos críticos de tus pacientes
          {pacientes && <span className={`rounded-full px-2 text-sm tabular-nums ${criticos.length ? "bg-coral-deep text-white" : "bg-paper-white"}`}>{criticos.length}</span>}
        </h2>
        <p className="mt-0.5 text-sm text-gray-strong">Valores críticos de las últimas 72 horas. Ábrelos para revisar y decidir la conducta.</p>
        {!pacientes ? <div className="mt-4"><Esqueleto filas={3} /></div> : criticos.length === 0 ? (
          <p className="mt-4 rounded-2xl bg-paper-white px-4 py-4 text-sm text-gray-strong">Ningún paciente tuyo tiene valores críticos recientes.</p>
        ) : (
          <ul className="mt-4 space-y-2">
            {criticos.map((p) => (
              <li key={p.paciente_id}>
                <Link to={`/app/pacientes/${p.paciente_id}`} className="flex items-center justify-between gap-3 rounded-2xl bg-paper-white px-4 py-3 transition hover:shadow-lift">
                  <span className="min-w-0">
                    <span className="block font-semibold">{p.nombre} {p.apellido}
                      <span className="font-normal text-gray-strong"> · {p.edad} años{p.encuentro ? ` · ${TIPO_ENCUENTRO[p.encuentro.tipo]}${p.encuentro.triage ? ` triage ${p.encuentro.triage}` : ""}${p.encuentro.cama ? ` · ${p.encuentro.cama}` : ""}` : ""}</span>
                    </span>
                    <span className="mt-1 flex flex-wrap gap-1.5">
                      {p.criticos.slice(0, 3).map((c, i) => <span key={i} className="rounded-full bg-coral-deep px-2.5 py-0.5 text-xs font-semibold text-white">{valorClinico(c)} · {haceCuanto(c.fecha)}</span>)}
                    </span>
                  </span>
                  <ChevronRight size={18} className="shrink-0 text-gray-strong" aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-[28px] bg-paper-white p-6 shadow-lift" aria-label="Mis pacientes">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-semibold"><Users size={18} aria-hidden="true" />Mis pacientes</h2>
          <Link to="/app/mis-pacientes" className="text-sm font-medium text-metric-blue hover:underline">Ver todos ({pacientes?.length ?? "…"})</Link>
        </div>
        {pacientes && (
          <p className="mb-2 text-sm text-gray-strong">{enUrgencias} en urgencias · {hospitalizados} hospitalizados · {pacientes.filter((p) => p.cirugia).length} con cirugía</p>
        )}
        {!pacientes ? (
          <Esqueleto filas={5} />
        ) : pacientes.length === 0 ? (
          <p className="py-4 text-sm text-gray-strong">No tienes pacientes a tu cargo en este momento.</p>
        ) : (
          <ul className="divide-y divide-cloud-card">
            {pacientes.filter((p) => !p.criticos.length).slice(0, 6).map((p) => (
              <li key={p.paciente_id}>
                <Link to={`/app/pacientes/${p.paciente_id}`} className="flex items-center justify-between gap-3 rounded-2xl px-3 py-3 transition hover:bg-cloud-card/60">
                  <span>
                    <span className="block text-sm font-medium">{p.nombre} {p.apellido}</span>
                    <span className="block text-xs text-gray-strong">
                      {p.tipo_documento} {p.documento} · {p.edad} años · {textoCobertura(p.cobertura)}
                      {p.encuentro ? ` · ${TIPO_ENCUENTRO[p.encuentro.tipo]}${p.encuentro.cama ? ` ${p.encuentro.cama}` : ""}` : ""}
                      {p.cirugia ? ` · cirugía ${ESTADO_CIRUGIA[p.cirugia.estado].toLowerCase()}` : ""}
                    </span>
                  </span>
                  <ChevronRight size={18} className="text-gray-strong" aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
