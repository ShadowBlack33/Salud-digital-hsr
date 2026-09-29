import { GRUPOS } from "../lib/estados";

/** Badge de estado: color + ícono + texto (nunca solo color). */
export default function Insignia({ grupo, etiqueta, tamano = "md", className = "" }) {
  const g = GRUPOS[grupo];
  const Icono = g.icono;
  const medidas = tamano === "sm" ? "gap-1 px-2 py-0.5 text-[11px]" : "gap-1.5 px-2.5 py-1 text-xs";
  return (
    <span className={`inline-flex w-fit items-center rounded-full font-semibold ${medidas} ${g.badge} ${className}`}>
      <Icono size={tamano === "sm" ? 12 : 14} aria-hidden="true" />
      {etiqueta || g.etiqueta}
    </span>
  );
}
