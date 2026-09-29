import { useEffect, useState } from "react";

/** Anillo de métrica al estilo Bevel: un arco de color sobre una pista suave. */
export default function Anillo({ valor = 0, tamano = 96, grosor = 10, color = "var(--color-metric-blue)", pista = "var(--color-paper-white)", children, etiqueta }) {
  const [v, setV] = useState(0);
  useEffect(() => { const id = requestAnimationFrame(() => setV(valor)); return () => cancelAnimationFrame(id); }, [valor]);
  const r = (tamano - grosor) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative grid shrink-0 place-items-center" style={{ width: tamano, height: tamano }}
         role="img" aria-label={etiqueta || `${Math.round(valor)} %`}>
      <svg width={tamano} height={tamano} className="-rotate-90">
        <circle cx={tamano / 2} cy={tamano / 2} r={r} fill="none" stroke={pista} strokeWidth={grosor} />
        <circle cx={tamano / 2} cy={tamano / 2} r={r} fill="none" stroke={color} strokeWidth={grosor}
                strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - Math.min(100, v) / 100)}
                style={{ transition: "stroke-dashoffset 1.1s cubic-bezier(.22,1,.36,1), stroke .4s" }} />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">{children}</div>
    </div>
  );
}
