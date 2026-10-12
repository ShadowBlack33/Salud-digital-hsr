import { WifiOff } from "lucide-react";
import { salud } from "../api";
import { useSondeo } from "../lib/hooks";

/** Franja fija si la API deja de responder (por ejemplo, si se cae el túnel en plena demo). */
export default function ConexionCaida() {
  const { error } = useSondeo(salud, 15000);   // un acierto limpia el error
  if (!error) return null;
  return (
    <div role="alert" className="anim-pop sticky top-24 z-30 mb-4 flex items-center gap-3 rounded-full bg-charcoal px-5 py-3 text-sm text-cloud-card shadow-lift">
      <WifiOff size={16} className="text-signal-gold" aria-hidden="true" />
      Se perdió la conexión con el servidor. Reintentando cada 15 segundos…
    </div>
  );
}
