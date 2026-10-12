/** Tarjeta Cloud Card con un número grande que cambia en vivo (con un pequeño salto al cambiar). */
export default function TarjetaContador({ etiqueta, valor, detalle, icono: Icono, tono = "text-metric-blue", resaltar = false }) {
  return (
    <div className={`flex flex-col justify-between rounded-[28px] p-6 transition-colors duration-500 ${resaltar ? "bg-coral-soft" : "bg-cloud-card"}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium">{etiqueta}</span>
        {Icono && <Icono size={20} className={tono} aria-hidden="true" />}
      </div>
      <div className="mt-5">
        <span key={valor} className="anim-pop inline-block text-5xl font-semibold tabular-nums tracking-display" aria-live="polite">{valor}</span>
        {detalle && <span className="mt-1 block text-xs text-gray-strong">{detalle}</span>}
      </div>
    </div>
  );
}
