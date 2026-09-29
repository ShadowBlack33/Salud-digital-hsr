import { memo } from "react";
import { Clock, User } from "lucide-react";
import { CAMA_CON_PACIENTE, GRUPOS, infoCama } from "../lib/estados";
import { duracion, minutosDesde } from "../lib/format";

/** Tarjeta de una cama: código, estado (color + ícono + texto), paciente y tiempo en el estado. */
function BedCard({ cama, ahora, seleccionada, onAbrir }) {
  const info = infoCama(cama.estado_cama);
  const g = GRUPOS[info.grupo];
  const Icono = g.icono;
  const conPaciente = CAMA_CON_PACIENTE.includes(cama.estado_cama) && cama.encuentro_activo && cama.paciente_nombre_corto;
  const min = minutosDesde(cama.estado_cama_desde, ahora);
  const limpiezaLarga = cama.estado_cama === "en_limpieza" && min > 120; // ver punto crítico R2 del AS-IS

  return (
    <button type="button" onClick={() => onAbrir(cama)}
            aria-label={`Cama ${cama.cama_codigo}, ${info.etiqueta}`}
            className={`flex min-h-[124px] flex-col gap-2 rounded-2xl bg-paper-white p-3.5 text-left transition duration-200 hover:-translate-y-0.5 hover:shadow-lift ${seleccionada ? "ring-2 ring-metric-blue" : ""}`}>
      <span className="flex items-center justify-between">
        <span className="font-mono text-[13px] font-semibold">{cama.cama_codigo}</span>
        <span className={`size-2.5 rounded-full ${g.punto}`} aria-hidden="true" />
      </span>
      <span className={`inline-flex w-fit items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${g.badge}`}>
        <Icono size={12} aria-hidden="true" />{info.etiqueta}
      </span>
      <span className="flex min-w-0 items-center gap-1.5 text-xs">
        {conPaciente
          ? <><User size={12} className="shrink-0 text-gray-strong" aria-hidden="true" /><span className="truncate font-medium">{cama.paciente_nombre_corto}</span></>
          : <span className="text-gray-strong">Sin paciente</span>}
      </span>
      <span className={`mt-auto flex items-center gap-1 text-xs ${limpiezaLarga ? "font-semibold text-coral-ink" : "text-gray-strong"}`}>
        <Clock size={12} aria-hidden="true" />{duracion(min)}{limpiezaLarga && " · larga"}
      </span>
    </button>
  );
}

export default memo(BedCard);
