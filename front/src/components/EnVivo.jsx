import { useTiempoReal } from "../lib/tiempoReal";

/** Indicador del canal en vivo: verde y latiendo si está conectado. */
export default function EnVivo() {
  const tr = useTiempoReal();
  if (!tr) return null;
  const ok = tr.conectado;
  return (
    <span role="status" title={ok ? "Recibiendo eventos en tiempo real" : "Reconectando el canal en vivo (los avisos llegarán al volver)"}
          className={`hidden items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold sm:flex ${ok ? "bg-green-soft text-green-ink" : "bg-cloud-card text-slate-ink"}`}>
      <span className={`size-2 rounded-full ${ok ? "anim-pulse-dot bg-green-deep" : "bg-body-gray"}`} aria-hidden="true" />
      {ok ? "En vivo" : "Reconectando"}
    </span>
  );
}
