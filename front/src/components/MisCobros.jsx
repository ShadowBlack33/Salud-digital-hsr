import { useEffect, useState } from "react";
import { ChevronDown, Receipt, ShieldCheck } from "lucide-react";
import Esqueleto from "./Esqueleto";
import * as S from "../lib/servicios";
import { cop, fechaYHora } from "../lib/format";

/**
 * Qué se le está cobrando al paciente: cada servicio, cuánto cubre su entidad
 * y cuánto le toca pagar a él (copago, cuota moderadora o el total si es
 * particular). Explicado sin jerga, para leerlo en el celular.
 */
export default function MisCobros() {
  const [cuenta, setCuenta] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { S.miCuenta().then(setCuenta).catch(setError); }, []);

  if (error) return null;   // si el módulo no responde, el resto del portal sigue
  if (!cuenta) return <section className="rounded-[28px] bg-paper-white p-6 shadow-lift"><Esqueleto filas={3} /></section>;
  const { cobertura, totales, servicios } = cuenta;
  const particular = cobertura.tipo === "particular";

  return (
    <section className="rounded-[28px] bg-paper-white p-6 shadow-lift" aria-labelledby="t-cobros">
      <h2 id="t-cobros" className="flex items-center gap-2 text-lg font-semibold"><Receipt size={18} className="text-metric-blue" aria-hidden="true" />Lo que se está cobrando</h2>
      <p className="mt-1 flex flex-wrap items-center gap-1.5 text-sm text-gray-strong">
        <ShieldCheck size={14} aria-hidden="true" />
        {particular ? "Te atiendes como particular: tú pagas el valor completo." : <>Te cubre <b className="text-ink">{cobertura.entidad}</b>{cobertura.regimen ? ` (régimen ${cobertura.regimen})` : ""}. Tú pagas solo una parte: {cuenta.regla.nombre.split(" (")[0].toLowerCase()}.</>}
      </p>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <div className="rounded-3xl bg-gold-soft p-4 text-gold-ink">
          <p className="text-xs font-semibold">Te toca pagar</p>
          <p className="mt-1 break-words text-xl font-semibold tabular-nums sm:text-2xl">{cop(totales.a_cargo_paciente)}</p>
        </div>
        <div className="rounded-3xl bg-cloud-card p-4">
          <p className="text-xs font-semibold">{particular ? "Total de tus servicios" : `Paga ${cobertura.entidad}`}</p>
          <p className="mt-1 break-words text-xl font-semibold tabular-nums sm:text-2xl">{cop(particular ? totales.valor_total : totales.a_cargo_entidad)}</p>
        </div>
      </div>

      {servicios.length === 0 ? <p className="mt-4 rounded-3xl bg-cloud-card p-5 text-sm">No hay servicios cobrados todavía.</p> : (
        <ul className="mt-4 space-y-2">
          {servicios.map((s) => (
            <li key={s.encuentro_id}>
              <details className="group rounded-3xl bg-cloud-card px-5 py-4">
                <summary className="flex cursor-pointer list-none items-start justify-between gap-3">
                  <span>
                    <span className="block text-[15px] font-medium">{s.nombre}<span className="font-normal text-gray-strong"> · {s.estado}</span></span>
                    <span className="block text-xs text-gray-strong">{fechaYHora(s.fecha)}</span>
                  </span>
                  <span className="flex items-center gap-2 text-right">
                    <span>
                      <span className="block text-sm font-semibold tabular-nums">{cop(s.a_cargo_paciente)}</span>
                      <span className="block text-[11px] text-gray-strong">{s.a_cargo_paciente === 0 && !particular ? "cubierto" : "tú pagas"}</span>
                    </span>
                    <ChevronDown size={16} className="transition group-open:rotate-180" aria-hidden="true" />
                  </span>
                </summary>
                <ul className="mt-3 space-y-1.5 border-t border-paper-white pt-3 text-sm">
                  {s.items.map((it, i) => (
                    <li key={i} className="flex justify-between gap-3">
                      <span>{it.concepto}{it.cantidad > 1 ? ` × ${it.cantidad} días` : ""}{it.codigo ? <span className="text-xs text-gray-strong"> · {it.codigo}</span> : null}</span>
                      <span className="tabular-nums">{cop(it.valor)}</span>
                    </li>
                  ))}
                  <li className="flex justify-between gap-3 pt-1 text-gray-strong"><span>{particular ? "Pagas tú (particular)" : `Cubre ${cobertura.entidad}`}</span><span className="tabular-nums">{cop(particular ? s.a_cargo_paciente : s.a_cargo_entidad)}</span></li>
                  {!particular && <li className="flex justify-between gap-3 font-semibold"><span>{s.concepto_paciente}</span><span className="tabular-nums">{cop(s.a_cargo_paciente)}</span></li>}
                </ul>
              </details>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-gray-strong">{cuenta.nota}</p>
    </section>
  );
}
