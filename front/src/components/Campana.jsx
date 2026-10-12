import { useState } from "react";
import { Activity, AlertTriangle, Bell, CheckCircle2, FileText, Receipt, Send, UserX } from "lucide-react";
import Panel from "./Panel";
import ChipDemo from "./ChipDemo";
import { useTiempoReal } from "../lib/tiempoReal";
import { haceCuanto } from "../lib/format";

const ICONOS = {
  remision_nueva: [Send, "text-metric-blue"],
  remision_aceptada: [CheckCircle2, "text-green-deep"],
  factura_creada: [Receipt, "text-green-deep"],
  cuenta_bloqueada: [UserX, "text-gold-deep"],
  alerta_critica: [AlertTriangle, "text-coral-deep"],
  alerta_escalada: [AlertTriangle, "text-coral-deep"],
  reporte_pendiente: [FileText, "text-metric-blue"],
  fhir_observation: [Activity, "text-sleep-lilac"],
};

/** Campana con el contador de no leídas y la bandeja (R18). Se actualiza sola con el canal en vivo. */
export default function Campana() {
  const tr = useTiempoReal();
  const [abierta, setAbierta] = useState(false);
  if (!tr) return null;
  const { notificaciones, noLeidas, marcarLeida, conectado, demo } = tr;

  return (
    <>
      <button onClick={() => setAbierta(true)} aria-label={`Bandeja de avisos: ${noLeidas} sin leer`} title="Bandeja de avisos"
              className="relative grid size-10 place-items-center rounded-full text-ink transition hover:bg-cloud-card">
        <Bell size={18} />
        {noLeidas > 0 && (
          <span key={noLeidas} className="anim-pop absolute -right-0.5 -top-0.5 grid min-w-5 place-items-center rounded-full bg-coral-deep px-1 text-[11px] font-semibold text-white">
            {noLeidas > 99 ? "99+" : noLeidas}
          </span>
        )}
      </button>

      <Panel abierto={abierta} onCerrar={() => setAbierta(false)} titulo="Bandeja"
             subtitulo={`${noLeidas} sin leer · ${conectado ? "en vivo" : "reconectando el canal…"}`}>
        {demo && <div className="mb-3"><ChipDemo visible /></div>}
        {notificaciones.length === 0 ? (
          <p className="py-10 text-center text-sm text-gray-strong">No tienes avisos.</p>
        ) : (
          <ul className="space-y-2">
            {notificaciones.map((n) => {
              const [Icono, tono] = ICONOS[n.tipo] || [Bell, "text-gray-strong"];
              return (
                <li key={n.id}>
                  <button onClick={() => !n.leida && marcarLeida(n.id)}
                          className={`flex w-full items-start gap-3 rounded-3xl p-4 text-left transition ${n.leida ? "bg-paper-white hover:bg-cloud-card/60" : "bg-cloud-card hover:bg-hero-sky"}`}>
                    <span className="grid size-9 shrink-0 place-items-center rounded-full bg-paper-white"><Icono size={17} className={tono} aria-hidden="true" /></span>
                    <span className="min-w-0 flex-1">
                      <span className={`block text-sm ${n.leida ? "text-gray-strong" : "font-medium"}`}>{n.mensaje}</span>
                      <span className="mt-0.5 block text-xs text-gray-strong">{haceCuanto(n.fecha)}</span>
                    </span>
                    {!n.leida && <span className="mt-1.5 size-2.5 shrink-0 rounded-full bg-metric-blue" aria-label="Sin leer" />}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </>
  );
}
