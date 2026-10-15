import { useTiempoReal } from "../lib/tiempoReal";

/** Punto verde discreto cuando el canal en vivo está conectado. Si no lo está
 *  no muestra nada: el aviso de conexión caída ya lo da <ConexionCaida/>, y un
 *  "Reconectando" permanente en la barra solo distrae. */
export default function EnVivo() {
  const tr = useTiempoReal();
  if (!tr?.conectado) return null;
  return (
    <span role="status" title="En vivo: los avisos llegan sin recargar" className="hidden size-10 place-items-center sm:grid">
      <span className="anim-pulse-dot size-2.5 rounded-full bg-green-deep" aria-hidden="true" />
      <span className="sr-only">En vivo</span>
    </span>
  );
}
