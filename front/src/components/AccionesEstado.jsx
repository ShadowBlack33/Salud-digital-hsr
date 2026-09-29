import { useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

/** Botones para cambiar el estado de un recurso, con un paso de confirmación
 *  cuando el cambio es delicado (hay un paciente o una cirugía en curso) o
 *  cuando se bloquea (para dejar el motivo). */
export default function AccionesEstado({ principales, otros, advertencia, pideMotivo, onCambiar }) {
  const [pendiente, setPendiente] = useState(null);
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function ejecutar(estado, m) {
    setEnviando(true);
    try { await onCambiar(estado, m || null); } finally { setEnviando(false); setPendiente(null); setMotivo(""); }
  }
  function elegir(estado) {
    if (advertencia?.(estado) || pideMotivo?.(estado)) setPendiente(estado);
    else ejecutar(estado);
  }

  const aviso = pendiente && advertencia?.(pendiente);
  const conMotivo = pendiente && pideMotivo?.(pendiente);

  if (pendiente) {
    return (
      <div className="anim-pop space-y-3">
        {aviso && (
          <p className="flex gap-2.5 rounded-2xl bg-gold-soft p-3.5 text-sm text-gold-ink">
            <AlertTriangle size={18} className="mt-0.5 shrink-0" aria-hidden="true" />{aviso}
          </p>
        )}
        {conMotivo && (
          <label className="block text-sm">
            <span className="mb-1.5 block font-medium">Motivo (opcional)</span>
            <input value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={120} autoFocus
                   placeholder="Ej.: mantenimiento del aire acondicionado"
                   className="w-full rounded-2xl bg-cloud-card px-4 py-3 text-sm outline-none placeholder:text-gray-strong focus:ring-2 focus:ring-metric-blue" />
          </label>
        )}
        <div className="flex gap-2">
          <button onClick={() => ejecutar(pendiente, motivo)} disabled={enviando}
                  className="flex flex-1 items-center justify-center gap-2 rounded-full bg-charcoal px-5 py-3 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-60">
            {enviando && <Loader2 size={16} className="anim-spin" />}Confirmar
          </button>
          <button onClick={() => setPendiente(null)} disabled={enviando}
                  className="rounded-full bg-cloud-card px-5 py-3 text-sm font-semibold transition hover:bg-hero-sky">Cancelar</button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {principales.map((p, i) => (
          <button key={p.estado} onClick={() => elegir(p.estado)} disabled={enviando}
                  className={`rounded-full px-4 py-2.5 text-sm font-semibold transition disabled:opacity-60 ${i === 0 ? "bg-charcoal text-white hover:bg-ink" : "bg-cloud-card text-ink hover:bg-hero-sky"}`}>
            {p.etiqueta}
          </button>
        ))}
      </div>
      {otros?.length > 0 && (
        <label className="block text-xs text-gray-strong">
          <span className="sr-only">Otro estado</span>
          <select value="" onChange={(e) => e.target.value && elegir(e.target.value)} disabled={enviando}
                  className="w-full rounded-full bg-cloud-card px-4 py-2.5 text-sm text-ink outline-none focus:ring-2 focus:ring-metric-blue">
            <option value="">Otro estado…</option>
            {otros.map((o) => <option key={o.estado} value={o.estado}>{o.etiqueta}</option>)}
          </select>
        </label>
      )}
    </div>
  );
}
