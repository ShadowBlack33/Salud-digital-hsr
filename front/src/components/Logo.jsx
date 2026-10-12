import { Activity } from "lucide-react";

/** Marca de la aplicación: Pulso, coordinación hospitalaria en tiempo real. */
export default function Logo({ compacto = false, className = "" }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <span className="grid size-9 place-items-center rounded-xl bg-charcoal text-cloud-card">
        <Activity size={19} strokeWidth={2.6} aria-hidden="true" />
      </span>
      {!compacto && (
        <span className="leading-tight">
          <span className="block text-[17px] font-semibold tracking-[0.01em] text-ink">Pulso</span>
          <span className="block text-xs text-gray-strong">Coordinación hospitalaria</span>
        </span>
      )}
    </span>
  );
}
