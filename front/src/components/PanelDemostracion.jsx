import { useEffect, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, FlaskConical, Receipt, Send, UserX, X } from "lucide-react";
import { useTiempoReal } from "../lib/tiempoReal";

const EVENTOS = [
  ["remision_nueva", "Llega una remisión", Send, "text-metric-blue"],
  ["remision_aceptada", "El especialista acepta", CheckCircle2, "text-green-deep"],
  ["alerta_critica", "Alerta crítica", AlertTriangle, "text-coral-deep"],
  ["factura_creada", "Factura automática", Receipt, "text-green-deep"],
  ["cuenta_bloqueada", "Cuenta bloqueada", UserX, "text-gold-deep"],
  ["fhir_observation", "Glucosa desde FHIR", Activity, "text-sleep-lilac"],
];

/**
 * Panel para ensayar la sustentación: dispara eventos simulados sin backend.
 * No cambia de rol ni da permisos: solo imita lo que el canal en vivo enviaría.
 * Está oculto; se abre y se cierra con Ctrl + Shift + D.
 */
export default function PanelDemostracion() {
  const tr = useTiempoReal();
  const [abierto, setAbierto] = useState(false);

  useEffect(() => {
    const tecla = (e) => {
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "d") { e.preventDefault(); setAbierto((v) => !v); }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, []);

  if (!abierto || !tr) return null;
  return (
    <aside aria-label="Panel de demostración" className="anim-pop fixed bottom-4 right-4 z-[55] w-72 rounded-[28px] bg-paper-white p-5 shadow-drawer">
      <div className="mb-1 flex items-center justify-between">
        <span className="flex items-center gap-2 text-sm font-semibold"><FlaskConical size={15} className="text-gold-deep" />Demostración</span>
        <button onClick={() => setAbierto(false)} aria-label="Cerrar panel de demostración" className="grid size-8 place-items-center rounded-full hover:bg-cloud-card"><X size={15} /></button>
      </div>
      <p className="mb-3 text-xs text-gray-strong">Simula eventos del canal en vivo. Ctrl + Shift + D para ocultar.</p>
      <div className="space-y-1.5">
        {EVENTOS.map(([tipo, texto, Icono, tono]) => (
          <button key={tipo} onClick={() => tr.simularEvento(tipo)}
                  className="flex w-full items-center gap-2.5 rounded-2xl bg-cloud-card px-3 py-2 text-left text-sm transition hover:bg-hero-sky">
            <Icono size={15} className={tono} aria-hidden="true" />{texto}
          </button>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-gray-strong">Canal real: {tr.conectado ? "conectado" : "sin conexión (usa la simulación)"}</p>
    </aside>
  );
}
