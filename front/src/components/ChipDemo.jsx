import { FlaskConical } from "lucide-react";

/** Indica que la pantalla usa datos de demostración porque la ruta de la API aún no existe. */
export default function ChipDemo({ visible }) {
  if (!visible) return null;
  return (
    <span title="La API todavía no tiene esta ruta: se muestran datos de demostración. Se cambia sola a los datos reales cuando exista."
          className="inline-flex items-center gap-1.5 rounded-full bg-gold-soft px-3 py-1 text-xs font-semibold text-gold-ink">
      <FlaskConical size={13} aria-hidden="true" />Datos de demostración
    </span>
  );
}
