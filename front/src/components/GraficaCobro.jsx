import { useState } from "react";
import { cop } from "../lib/format";
import { TIPOS_COBRO } from "../lib/facturacion";

const NOMBRES = { ...TIPOS_COBRO, analisis_ia: "Análisis de IA" };
// "Por cobrar" usa rayas además del color: verde y dorado se confunden con
// daltonismo rojo-verde, así que el patrón y la diferencia de luz los separan.
const RAYAS = "repeating-linear-gradient(135deg, var(--color-gold-soft) 0 5px, color-mix(in srgb, var(--color-gold-deep) 55%, transparent) 5px 7px)";

/** Cobrado frente a por cobrar, por tipo de servicio (barras horizontales apiladas). */
export default function GraficaCobro({ facturas }) {
  const [foco, setFoco] = useState(null);
  const grupos = Object.values(facturas.filter((f) => f.estado_pago !== "anulada").reduce((acc, f) => {
    const clave = f.tipo_cobro || f.servicio;
    const g = (acc[clave] ??= { servicio: clave, pagado: 0, pendiente: 0 });
    g[f.estado_pago === "pagada" ? "pagado" : "pendiente"] += Number(f.valor || 0);
    return acc;
  }, {})).sort((a, b) => (b.pagado + b.pendiente) - (a.pagado + a.pendiente));
  const maximo = Math.max(1, ...grupos.map((g) => g.pagado + g.pendiente));
  if (grupos.length === 0) return null;

  return (
    <figure className="rounded-[28px] bg-paper-white p-6 shadow-lift" aria-label="Cobrado frente a por cobrar por servicio">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <figcaption className="text-lg font-semibold">Cobro por tipo de servicio <span className="text-sm font-normal text-gray-strong">(según los filtros)</span></figcaption>
        <ul className="flex gap-4 text-xs text-gray-strong" aria-label="Leyenda">
          <li className="flex items-center gap-1.5"><span className="h-3 w-5 rounded-[4px] bg-green-deep" aria-hidden="true" />Cobrado</li>
          <li className="flex items-center gap-1.5"><span className="h-3 w-5 rounded-[4px]" style={{ background: RAYAS }} aria-hidden="true" />Por cobrar</li>
        </ul>
      </div>
      <div className="space-y-4">
        {grupos.map((g) => {
          const total = g.pagado + g.pendiente;
          return (
            <div key={g.servicio}>
              <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
                <span className="font-medium">{NOMBRES[g.servicio] || g.servicio}</span>
                <span className="tabular-nums text-gray-strong">{cop(g.pagado)} de {cop(total)}</span>
              </div>
              <div className="relative flex h-5 gap-[2px]" style={{ width: `${(total / maximo) * 100}%` }}>
                {[["pagado", "Cobrado", "bg-green-deep"], ["pendiente", "Por cobrar", ""]].map(([clave, texto, clase]) => g[clave] > 0 && (
                  <span key={clave} tabIndex={0} aria-label={`${NOMBRES[g.servicio] || g.servicio}, ${texto}: ${cop(g[clave])}`}
                        onMouseEnter={() => setFoco(`${g.servicio}-${clave}`)} onMouseLeave={() => setFoco(null)}
                        onFocus={() => setFoco(`${g.servicio}-${clave}`)} onBlur={() => setFoco(null)}
                        className={`relative h-full first:rounded-l-[4px] last:rounded-r-[4px] outline-none ${clase}`}
                        style={{ flexGrow: g[clave], flexBasis: 0, background: clase ? undefined : RAYAS }}>
                    {foco === `${g.servicio}-${clave}` && (
                      <span role="tooltip" className="anim-fade absolute bottom-full left-1/2 z-10 mb-2 -translate-x-1/2 whitespace-nowrap rounded-xl bg-charcoal px-3 py-1.5 text-xs text-cloud-card shadow-lift">
                        {texto}: <b className="tabular-nums">{cop(g[clave])}</b> · {Math.round((g[clave] / total) * 100)} %
                      </span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </figure>
  );
}
