import { ChevronDown } from "lucide-react";

/**
 * Tarjeta Cloud Card con un número grande que cambia en vivo (con un pequeño
 * salto al cambiar). Con `onClick` se vuelve un botón que despliega el detalle.
 */
export default function TarjetaContador({ etiqueta, valor, detalle, icono: Icono, tono = "text-metric-blue", resaltar = false, onClick, abierta = false }) {
  const Contenedor = onClick ? "button" : "div";
  return (
    <Contenedor onClick={onClick} {...(onClick ? { "aria-expanded": abierta, type: "button" } : {})}
                className={`flex flex-col justify-between rounded-[28px] p-6 text-left transition duration-300 ${resaltar ? "bg-coral-soft" : "bg-cloud-card"} ${onClick ? "hover:-translate-y-0.5 hover:shadow-lift" : ""} ${abierta ? "ring-2 ring-charcoal" : ""}`}>
      <span className="flex w-full items-center justify-between gap-3">
        <span className="text-sm font-medium">{etiqueta}</span>
        {Icono && <Icono size={20} className={tono} aria-hidden="true" />}
      </span>
      <span className="mt-5 block w-full">
        <span key={valor} className="anim-pop inline-block text-5xl font-semibold tabular-nums tracking-display" aria-live="polite">{valor}</span>
        <span className="mt-1 flex items-center justify-between gap-2 text-xs text-gray-strong">
          {detalle}
          {onClick && <ChevronDown size={15} className={`shrink-0 transition ${abierta ? "rotate-180" : ""}`} aria-hidden="true" />}
        </span>
      </span>
    </Contenedor>
  );
}
