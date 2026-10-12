import { useState } from "react";
import { AlertTriangle, Check, Loader2 } from "lucide-react";
import { useTiempoReal } from "../lib/tiempoReal";
import { useAvisos } from "./Avisos";
import { haceCuanto } from "../lib/format";

function Alerta({ alerta, onReconocer }) {
  const [nota, setNota] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState(null);

  const enviar = async (e) => {
    e.preventDefault();
    if (!nota.trim()) return;
    setGuardando(true); setError(null);
    try { await onReconocer(alerta.id, nota.trim()); }
    catch (err) { setError(err.message); setGuardando(false); }
  };

  return (
    <form onSubmit={enviar} role="alert"
          className="anim-pop flex flex-col gap-3 rounded-[28px] bg-coral-soft p-4 shadow-lift sm:flex-row sm:items-center sm:justify-between sm:pl-5">
      <div className="flex items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-coral-signal text-coral-ink">
          <AlertTriangle size={20} aria-hidden="true" />
        </span>
        <div>
          <p className="text-sm font-semibold text-coral-ink">Alerta crítica · {haceCuanto(alerta.created_at)}</p>
          <p className="text-sm">{alerta.mensaje || "El modelo marcó un caso crítico."}</p>
          {error && <p className="mt-1 text-xs text-coral-ink">{error}</p>}
        </div>
      </div>
      <div className="flex w-full items-center gap-2 sm:w-auto">
        <label className="sr-only" htmlFor={`nota-${alerta.id}`}>Nota de reconocimiento</label>
        <input id={`nota-${alerta.id}`} value={nota} onChange={(e) => setNota(e.target.value)} placeholder="Conducta tomada (obligatoria)"
               className="w-full rounded-full bg-paper-white px-4 py-2 text-sm outline-none ring-coral-deep/40 focus:ring-2 sm:w-72" />
        <button type="submit" disabled={!nota.trim() || guardando}
                className="flex shrink-0 items-center gap-1.5 rounded-full bg-coral-ink px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-40">
          {guardando ? <Loader2 size={15} className="anim-spin" /> : <Check size={15} />}Reconocer
        </button>
      </div>
    </form>
  );
}

/** Alertas críticas activas (R20): quedan fijas arriba hasta que el clínico las reconoce con una nota. */
export default function BannerAlertas() {
  const tr = useTiempoReal();
  const { avisar } = useAvisos();
  if (!tr || tr.alertasActivas.length === 0) return null;
  const reconocer = async (id, nota) => { await tr.reconocer(id, nota); avisar("Alerta reconocida. Quedó en la auditoría."); };
  return (
    <div className="sticky top-24 z-30 mb-6 space-y-2" aria-label="Alertas críticas activas">
      {tr.alertasActivas.map((a) => <Alerta key={a.id} alerta={a} onReconocer={reconocer} />)}
    </div>
  );
}
