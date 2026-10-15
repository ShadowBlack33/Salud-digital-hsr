import { useState } from "react";
import { FileDown, Loader2 } from "lucide-react";
import { useAvisos } from "./Avisos";
import { descargarHistoriaPDF } from "../lib/servicios";
import { useTiempoReal } from "../lib/tiempoReal";

/** Descarga la historia clínica en PDF (R11). Solo incluye reportes de IA aprobados (lo filtra la API). */
export default function BotonHistoriaPDF({ pacienteId, nombre, ancho = false, texto = "Descargar historia clínica (PDF)" }) {
  const { avisar } = useAvisos();
  const [bajando, setBajando] = useState(false);
  const tr = useTiempoReal();
  const bajar = async () => {
    setBajando(true);
    try {
      const archivo = `historia_${(nombre || "paciente").toLowerCase().replace(/\s+/g, "_")}.pdf`;
      await descargarHistoriaPDF(pacienteId, archivo);
      tr?.marcarHito("pdf_descargado");
    } catch (err) {
      avisar(err.status === 404 ? "La descarga del PDF todavía no está disponible en la API." : err.message, "error");
    } finally { setBajando(false); }
  };
  return (
    <button onClick={bajar} disabled={bajando}
            className={`flex items-center justify-center gap-2 rounded-full bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50 ${ancho ? "w-full py-3" : ""}`}>
      {bajando ? <Loader2 size={16} className="anim-spin" /> : <FileDown size={16} aria-hidden="true" />}{texto}
    </button>
  );
}
