import { BellRing, CheckCircle2 } from "lucide-react";
import * as S from "../lib/servicios";
import { useSondeo } from "../lib/hooks";

/**
 * Alertas críticas sin atender, por médico (R20). Para el coordinador y el
 * admin: dice QUIÉN tiene alertas pendientes y desde hace cuánto, sin ningún
 * dato del paciente. Reemplaza el escalamiento al admin, que no atiende
 * pacientes: la alerta vencida se avisa a los otros médicos del paciente.
 */
export default function AlertasSinAtender() {
  const r = useSondeo(S.alertasSinAtender, 30000);
  const d = r.datos;
  if (r.error?.status === 403) return null;
  return (
    <section aria-labelledby="t-alertas-sin-atender" className="rounded-[32px] bg-cloud-card p-6">
      <h2 id="t-alertas-sin-atender" className="flex items-center gap-2 text-lg font-semibold">
        <BellRing size={18} aria-hidden="true" />Alertas críticas sin atender
      </h2>
      <p className="mt-1 text-sm text-gray-strong">
        Por médico responsable. Vencida = más de {d?.minutos_para_vencer ?? 5} min sin reconocer (ya se avisó a los otros médicos del paciente).
      </p>
      {r.error && <p role="alert" className="mt-3 text-sm text-coral-ink">{r.error.message}</p>}
      {d && d.medicos.length === 0 && (
        <p className="mt-4 flex items-center gap-2 text-sm text-green-ink"><CheckCircle2 size={16} aria-hidden="true" />Ninguna alerta pendiente.</p>
      )}
      {d && d.medicos.length > 0 && (
        <>
          <p className="mt-3 text-sm"><strong>{d.total}</strong> sin atender · <strong className={d.vencidas ? "text-coral-deep" : ""}>{d.vencidas}</strong> vencidas</p>
          <ul className="mt-3 space-y-2">
            {d.medicos.map((m) => (
              <li key={m.usuario_id ?? m.usuario} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-paper-white px-4 py-2.5 text-sm">
                <span><span className="font-medium">{m.nombre}</span> <span className="text-gray-strong">· {m.usuario}{m.rol ? ` · ${m.rol}` : ""}</span></span>
                <span className="flex items-center gap-2 tabular-nums">
                  <span>{m.sin_atender} sin atender</span>
                  {m.vencidas > 0 && <span className="rounded-full bg-coral-deep px-2 py-0.5 text-[11px] font-semibold text-white">{m.vencidas} vencida{m.vencidas === 1 ? "" : "s"}</span>}
                  <span className="text-gray-strong">la más antigua hace {m.minutos_mas_antigua} min</span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
