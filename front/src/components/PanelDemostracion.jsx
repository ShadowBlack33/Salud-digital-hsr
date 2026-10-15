import { useEffect, useState } from "react";
import { Activity, AlertTriangle, Check, CheckCircle2, FlaskConical, Receipt, RotateCcw, Send, UserX, X } from "lucide-react";
import { useEventos, useTiempoReal } from "../lib/tiempoReal";

const EVENTOS = [
  ["remision_nueva", "Llega una remisión", Send, "text-metric-blue"],
  ["remision_aceptada", "El especialista acepta", CheckCircle2, "text-green-deep"],
  ["alerta_critica", "Alerta crítica", AlertTriangle, "text-coral-deep"],
  ["factura_creada", "Factura automática", Receipt, "text-green-deep"],
  ["cuenta_bloqueada", "Cuenta bloqueada", UserX, "text-gold-deep"],
  ["fhir_observation", "Glucosa desde FHIR", Activity, "text-sleep-lilac"],
];

// Guion de la sustentación (REQUISITOS.md, sección 6). Cada paso se marca solo
// cuando en ESTA ventana ocurre el evento o la acción que lo demuestra.
const GUION = [
  ["Paciente crítico: llega la alerta y sube el contador", ["alerta_critica", "reporte_pendiente"]],
  ["Se reconoce la alerta y se aprueba el reporte → factura", ["reporte_aprobado", "factura_creada", "alerta_reconocida"]],
  ["Remisión al especialista y aviso de aceptación", ["remision_nueva", "remision_aceptada"]],
  ["Observation desde FHIR → aviso al médico", ["fhir_observation"]],
  ["Tres intentos fallidos → aviso al admin y desbloqueo", ["cuenta_bloqueada", "cuenta_desbloqueada"]],
  ["Historia clínica en PDF y auditoría", ["pdf_descargado", "auditoria_vista"]],
];
const CLAVE = "hsr_guion_demo";
const leer = () => { try { return JSON.parse(sessionStorage.getItem(CLAVE)) || GUION.map(() => false); } catch { return GUION.map(() => false); } };

/**
 * Panel para ensayar la sustentación: guion con los 6 pasos y eventos simulados.
 * No cambia de rol ni da permisos. Se abre y se cierra con Ctrl + Shift + D.
 */
export default function PanelDemostracion() {
  const tr = useTiempoReal();
  const [abierto, setAbierto] = useState(false);
  const [hechos, setHechos] = useState(leer);

  const guardar = (nuevos) => {
    setHechos(nuevos);
    try { sessionStorage.setItem(CLAVE, JSON.stringify(nuevos)); } catch { /* sin almacenamiento */ }
  };

  useEventos((ev) => {
    const i = GUION.findIndex(([, tipos]) => tipos.includes(ev.tipo));
    if (i >= 0 && !hechos[i]) guardar(hechos.map((h, j) => (j === i ? true : h)));
  });

  useEffect(() => {
    const tecla = (e) => {
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "d") { e.preventDefault(); setAbierto((v) => !v); }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, []);

  if (!abierto || !tr) return null;
  const listos = hechos.filter(Boolean).length;
  return (
    <aside aria-label="Panel de demostración" className="anim-pop fixed bottom-4 right-4 z-[55] max-h-[calc(100dvh-2rem)] w-80 overflow-y-auto rounded-[28px] bg-paper-white p-5 shadow-drawer">
      <div className="mb-1 flex items-center justify-between">
        <span className="flex items-center gap-2 text-sm font-semibold"><FlaskConical size={15} className="text-gold-deep" />Demostración</span>
        <button onClick={() => setAbierto(false)} aria-label="Cerrar panel de demostración" className="grid size-8 place-items-center rounded-full hover:bg-cloud-card"><X size={15} /></button>
      </div>
      <p className="mb-3 text-xs text-gray-strong">Ctrl + Shift + D para ocultar. Canal real: {tr.conectado ? "conectado" : "sin conexión"}.</p>

      <div className="mb-4 rounded-3xl bg-cloud-card p-3">
        <div className="mb-2 flex items-center justify-between px-1">
          <span className="text-xs font-semibold">Guion · {listos}/{GUION.length}</span>
          <button onClick={() => guardar(GUION.map(() => false))} className="flex items-center gap-1 text-xs text-gray-strong hover:text-ink"><RotateCcw size={12} />Reiniciar</button>
        </div>
        <ol className="space-y-1">
          {GUION.map(([texto], i) => (
            <li key={texto}>
              <button onClick={() => guardar(hechos.map((h, j) => (j === i ? !h : h)))} aria-pressed={hechos[i]}
                      className="flex w-full items-start gap-2 rounded-2xl px-1.5 py-1 text-left text-xs transition hover:bg-paper-white">
                <span className={`mt-0.5 grid size-4 shrink-0 place-items-center rounded-full ${hechos[i] ? "bg-green-deep text-white" : "bg-paper-white text-gray-strong"}`}>
                  {hechos[i] ? <Check size={11} /> : <span className="text-[9px] font-semibold">{i + 1}</span>}
                </span>
                <span className={hechos[i] ? "text-green-ink" : ""}>{texto}</span>
              </button>
            </li>
          ))}
        </ol>
      </div>

      <p className="mb-2 text-xs font-medium text-gray-strong">Simular un evento</p>
      <div className="space-y-1.5">
        {EVENTOS.map(([tipo, texto, Icono, tono]) => (
          <button key={tipo} onClick={() => tr.simularEvento(tipo)}
                  className="flex w-full items-center gap-2.5 rounded-2xl bg-cloud-card px-3 py-2 text-left text-sm transition hover:bg-hero-sky">
            <Icono size={15} className={tono} aria-hidden="true" />{texto}
          </button>
        ))}
      </div>
    </aside>
  );
}
