import { Link } from "react-router-dom";
import { Compass, Lock, ServerCrash, WifiOff } from "lucide-react";

const CASOS = {
  403: [Lock, "No tienes permiso para ver esto", "Tu rol no tiene acceso a esta información. Si crees que es un error, pídele acceso al administrador."],
  404: [Compass, "No encontramos lo que buscas", "Puede que el registro se haya eliminado o que el enlace no sea correcto."],
  0: [WifiOff, "Sin conexión con el servidor", "Revisa tu conexión. Reintentaremos en cuanto vuelva."],
};

/** Mensaje de error amable según el código HTTP. */
export default function ErrorEstado({ error, status, titulo, detalle, accion = true }) {
  const codigo = status ?? error?.status;
  const [Icono, t, d] = CASOS[codigo] || [ServerCrash, "Algo salió mal", "Ocurrió un error inesperado. Intenta de nuevo en un momento."];
  return (
    <div role="alert" className="anim-pop flex flex-col items-center gap-3 rounded-[32px] bg-cloud-card px-6 py-14 text-center">
      <span className="grid size-14 place-items-center rounded-full bg-paper-white"><Icono size={24} aria-hidden="true" /></span>
      <h2 className="text-[26px] font-semibold leading-tight tracking-display">{titulo || t}</h2>
      <p className="max-w-md text-[15px] text-gray-strong">{detalle || d}</p>
      {codigo !== undefined && codigo !== 0 && <p className="font-mono text-xs text-gray-strong">Código {codigo}{error?.message && error.message !== t ? ` · ${error.message}` : ""}</p>}
      {accion && <Link to="/app" className="mt-2 rounded-full bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink">Ir a mi inicio</Link>}
    </div>
  );
}
