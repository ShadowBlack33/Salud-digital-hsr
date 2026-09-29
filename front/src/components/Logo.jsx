import { Cross } from "lucide-react";

export default function Logo({ compacto = false, className = "" }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <span className="grid size-9 place-items-center rounded-xl bg-charcoal text-cloud-card">
        <Cross size={18} strokeWidth={2.6} aria-hidden="true" />
      </span>
      {!compacto && (
        <span className="leading-tight">
          <span className="block text-[17px] font-medium tracking-[0.01em] text-ink">San Rafael OS</span>
          <span className="block text-xs text-gray-strong">Centro de mando</span>
        </span>
      )}
    </span>
  );
}
