import { useState } from "react";
import { Loader2, LogOut } from "lucide-react";
import { api } from "../../api";
import { useAvisos } from "../Avisos";

/** Alta médica: solo el médico tratante, con tipo de egreso y motivo. La cama queda en proceso de alta. */
const EGRESOS = [["mejoria", "Mejoría"], ["remision_externa", "Remisión a otra institución"], ["voluntaria", "Alta voluntaria"],
                 ["fallecimiento", "Fallecimiento"], ["otro", "Otro"]];

export default function AltaMedica({ pacienteId, onListo }) {
  const { avisar } = useAvisos();
  const [abierto, setAbierto] = useState(false);
  const [f, setF] = useState({ tipo_egreso: "mejoria", motivo: "" });
  const [enviando, setEnviando] = useState(false);

  const enviar = async (e) => {
    e.preventDefault();
    setEnviando(true);
    try {
      const r = await api(`/pacientes/${pacienteId}/alta`, { method: "POST", json: f });
      avisar(r.cama ? `Alta registrada. La cama ${r.cama} queda en proceso de alta hasta que enfermería confirme la salida.` : "Alta registrada.");
      setAbierto(false);
      onListo?.();
    } catch (err) { avisar(err.message, "error"); }
    finally { setEnviando(false); }
  };

  if (!abierto) {
    return (
      <button onClick={() => setAbierto(true)} className="mt-3 flex w-full items-center justify-center gap-2 rounded-full bg-cloud-card px-4 py-2.5 text-sm font-semibold transition hover:bg-hero-sky">
        <LogOut size={15} aria-hidden="true" />Dar de alta
      </button>
    );
  }
  return (
    <form onSubmit={enviar} className="mt-3 space-y-3 rounded-2xl bg-cloud-card p-4">
      <label className="block text-sm font-medium" htmlFor="tipo-egreso">Tipo de egreso
        <select id="tipo-egreso" value={f.tipo_egreso} onChange={(e) => setF({ ...f, tipo_egreso: e.target.value })}
                className="mt-1 w-full rounded-2xl border border-paper-white bg-paper-white px-3 py-2 text-sm">
          {EGRESOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
        </select>
      </label>
      <label className="block text-sm font-medium" htmlFor="motivo-alta">Por qué se da el alta
        <textarea id="motivo-alta" required minLength={10} rows={3} value={f.motivo} onChange={(e) => setF({ ...f, motivo: e.target.value })}
                  placeholder="p. ej. estable 48 h, tolera vía oral, sin requerimiento de oxígeno"
                  className="mt-1 w-full rounded-2xl border border-paper-white bg-paper-white px-3 py-2 text-sm" />
      </label>
      <p className="text-xs text-gray-strong">Queda en la historia y en la auditoría. La cama no se libera hasta que enfermería confirme que el paciente salió.</p>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={() => setAbierto(false)} className="rounded-full px-3 py-2 text-sm">Cancelar</button>
        <button type="submit" disabled={enviando || f.motivo.trim().length < 10}
                className="flex items-center gap-1.5 rounded-full bg-charcoal px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
          {enviando && <Loader2 size={14} className="anim-spin" />}Confirmar alta
        </button>
      </div>
    </form>
  );
}
