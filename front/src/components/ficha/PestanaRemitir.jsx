import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, Send } from "lucide-react";
import ChipDemo from "../ChipDemo";
import { useAvisos } from "../Avisos";
import * as S from "../../lib/servicios";

/** Remitir el paciente a un especialista (R08). */
export default function PestanaRemitir({ pacienteId }) {
  const { avisar } = useAvisos();
  const [especialistas, setEspecialistas] = useState({ lista: [], demo: false });
  const [datos, setDatos] = useState({ especialista_id: "", motivo: "" });
  const [enviando, setEnviando] = useState(false);
  const [hecha, setHecha] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    S.especialistas().then(({ datos, demo }) => setEspecialistas({ lista: Array.isArray(datos) ? datos : [], demo })).catch((e) => setError(e.message));
  }, []);

  const enviar = async (e) => {
    e.preventDefault();
    setEnviando(true); setError(null);
    try {
      const { datos: r } = await S.remitir({ paciente_id: pacienteId, especialista_id: Number(datos.especialista_id), motivo: datos.motivo.trim() });
      setHecha(r.id);
      setDatos({ especialista_id: "", motivo: "" });
      avisar("Remisión enviada. El especialista ya recibió el aviso.");
    } catch (err) { setError(err.message); }
    finally { setEnviando(false); }
  };

  const entrada = "mt-1 w-full rounded-2xl bg-cloud-card px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-metric-blue/40";
  return (
    <form onSubmit={enviar} className="max-w-2xl space-y-4 rounded-[28px] bg-paper-white p-6 shadow-lift">
      <div>
        <h2 className="text-lg font-semibold">Remitir a especialista</h2>
        <p className="mt-1 text-sm text-gray-strong">El especialista recibe el aviso al instante y, cuando acepte, te llega la confirmación.</p>
        {especialistas.demo && <div className="mt-2"><ChipDemo visible /></div>}
      </div>
      {hecha && (
        <p className="anim-pop flex items-center gap-2 rounded-3xl bg-green-soft p-4 text-sm text-green-ink">
          <CheckCircle2 size={17} aria-hidden="true" />Remisión {hecha} enviada. Puedes seguirla en Remisiones.
        </p>
      )}
      <label className="block text-sm font-medium">Especialista
        <select required value={datos.especialista_id} onChange={(e) => setDatos((d) => ({ ...d, especialista_id: e.target.value }))} className={entrada}>
          <option value="" disabled>Elige un especialista</option>
          {especialistas.lista.map((e) => <option key={e.id} value={e.id}>{e.nombre}{e.especialidad ? ` · ${e.especialidad}` : ""}</option>)}
        </select>
      </label>
      <label className="block text-sm font-medium">Motivo
        <textarea required minLength={10} rows={3} value={datos.motivo} onChange={(e) => setDatos((d) => ({ ...d, motivo: e.target.value }))}
                  placeholder="Ej.: valoración por cirugía cardiovascular antes del reemplazo valvular." className={`${entrada} resize-y`} />
      </label>
      {error && <p role="alert" className="text-sm text-coral-ink">{error}</p>}
      <button type="submit" disabled={enviando} className="flex items-center gap-2 rounded-full bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50">
        {enviando ? <Loader2 size={15} className="anim-spin" /> : <Send size={15} />}Remitir
      </button>
    </form>
  );
}
