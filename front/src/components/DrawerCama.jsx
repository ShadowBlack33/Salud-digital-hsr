import { useNavigate } from "react-router-dom";
import { ArrowRight, Stethoscope } from "lucide-react";
import Panel from "./Panel";
import Insignia from "./Insignia";
import Dato from "./Dato";
import AccionesEstado from "./AccionesEstado";
import { useAvisos } from "./Avisos";
import { api, puede } from "../api";
import { CAMA, CAMA_CON_PACIENTE, infoCama } from "../lib/estados";
import { cop, duracion, edadLegible, enmascarar, hora, minutosDesde } from "../lib/format";

const TIPO_ENCUENTRO = { hospitalizacion: "Hospitalización", cirugia: "Cirugía", urgencias: "Urgencias", consulta_externa: "Consulta externa" };
const SEXO = { M: "Masculino", F: "Femenino", O: "Otro" };
const MUEVEN_PACIENTE = ["disponible", "en_limpieza", "bloqueada", "contaminada", "aislamiento"];

/** Panel lateral de una cama: ocupante, tiempos, costo y cambio de estado. */
export default function DrawerCama({ cama, ahora, usuario, onCerrar, onCambio }) {
  const navegar = useNavigate();
  const { avisar } = useAvisos();
  if (!cama) return <Panel abierto={false} />;

  const info = infoCama(cama.estado_cama);
  const min = minutosDesde(cama.estado_cama_desde, ahora);
  const costoHora = Number(cama.costo_dia_cop || 0) / 24;
  const conPaciente = cama.encuentro_activo && cama.paciente_nombre_corto && CAMA_CON_PACIENTE.includes(cama.estado_cama);
  const destinoDeCirugia = cama.encuentro_activo && cama.encuentro_tipo === "cirugia" && !CAMA_CON_PACIENTE.includes(cama.estado_cama);
  const vacia = !CAMA_CON_PACIENTE.includes(cama.estado_cama);
  const puedeCambiar = puede(usuario, "cama", "update");

  const principales = [
    { estado: "disponible", etiqueta: "Marcar disponible" },
    { estado: "en_limpieza", etiqueta: "Iniciar limpieza" },
    { estado: "bloqueada", etiqueta: "Bloquear" },
  ].filter((p) => p.estado !== cama.estado_cama);
  const otros = Object.entries(CAMA)
    .filter(([e]) => e !== cama.estado_cama && !principales.some((p) => p.estado === e))
    .map(([estado, v]) => ({ estado, etiqueta: v.etiqueta }));

  async function cambiar(estado, motivo) {
    try {
      await api(`/camas/${cama.cama_id}/estado`, { method: "PATCH", json: { estado, motivo } });
      avisar(`Cama ${cama.cama_codigo}: ${CAMA[estado].etiqueta.toLowerCase()}`);
      await onCambio();
    } catch (e) {
      avisar(e.status === 403 ? "Tu rol no puede cambiar el estado de las camas" : e.message, "error");
    }
  }

  return (
    <Panel abierto onCerrar={onCerrar} titulo={`Cama ${cama.cama_codigo}`} subtitulo={cama.tipo_nombre}
           pie={puedeCambiar ? (
             <AccionesEstado principales={principales} otros={otros} onCambiar={cambiar}
               advertencia={(e) => conPaciente && MUEVEN_PACIENTE.includes(e)
                 ? `Esta cama tiene un paciente en atención (${cama.paciente_nombre_corto}). Cambiarla a "${CAMA[e].etiqueta.toLowerCase()}" no lo traslada: confirma solo si ya salió.`
                 : null}
               pideMotivo={(e) => e === "bloqueada" || e === "aislamiento"} />
           ) : <p className="text-sm text-gray-strong">Tu rol puede ver esta cama, pero no cambiar su estado.</p>}>
      <div className="flex flex-wrap items-center gap-3">
        <Insignia grupo={info.grupo} etiqueta={info.etiqueta} />
        <span className="text-sm text-gray-strong">desde las {hora(cama.estado_cama_desde)} · hace {duracion(min)}</span>
      </div>

      {conPaciente && (
        <section className="mt-6 rounded-3xl bg-cloud-card p-5" aria-label="Paciente">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-strong">Paciente</p>
          <p className="mt-1 text-xl font-semibold tracking-display">{cama.paciente_nombre_corto}</p>
          <dl className="mt-2 divide-y divide-paper-white">
            <Dato etiqueta="Documento">{cama.paciente_tipo_documento} {enmascarar(cama.paciente_documento)}</Dato>
            <Dato etiqueta="Edad y sexo">{edadLegible(cama.paciente_fecha_nacimiento)} · {SEXO[cama.paciente_sexo] || "—"}</Dato>
            <Dato etiqueta="Atención">{TIPO_ENCUENTRO[cama.encuentro_tipo] || cama.encuentro_tipo}</Dato>
            {cama.diagnostico && <Dato etiqueta="Diagnóstico">{cama.diagnostico}</Dato>}
            {cama.medico_nombre && (
              <Dato etiqueta="Médico">
                {cama.medico_nombre}
                {cama.medico_especialidad && <span className="block text-xs font-normal text-gray-strong">{cama.medico_especialidad}</span>}
              </Dato>
            )}
          </dl>
          {puede(usuario, "paciente", "read") && (
            <button onClick={() => navegar(`/app/pacientes/${cama.paciente_id}`)}
                    className="mt-3 flex w-full items-center justify-center gap-2 rounded-full bg-paper-white px-5 py-3 text-sm font-semibold transition hover:shadow-lift">
              <Stethoscope size={16} aria-hidden="true" />Ver ficha e imágenes<ArrowRight size={16} aria-hidden="true" />
            </button>
          )}
        </section>
      )}

      {!conPaciente && (
        <p className="mt-6 rounded-3xl bg-cloud-card p-5 text-sm text-gray-strong">
          {destinoDeCirugia
            ? `Es la cama de destino de una cirugía en curso (paciente ${cama.paciente_nombre_corto || "en quirófano"}).`
            : "Esta cama no tiene un paciente en atención."}
        </p>
      )}

      <section className="mt-6" aria-label="Costo">
        <p className="text-xs font-semibold uppercase tracking-wider text-gray-strong">Costo</p>
        <dl className="divide-y divide-cloud-card">
          <Dato etiqueta="Por día">{cop(cama.costo_dia_cop)}</Dato>
          <Dato etiqueta="Por hora">≈ {cop(costoHora)}</Dato>
          {vacia && cama.estado_cama !== "bloqueada" && cama.estado_cama !== "aislamiento" && (
            <Dato etiqueta="Sin paciente desde hace">{duracion(min)} · ≈ {cop((min / 60) * costoHora)}</Dato>
          )}
        </dl>
        <p className="mt-2 text-xs text-gray-strong">Estimación con el costo diario del tipo de cama; no es facturación real.</p>
      </section>
    </Panel>
  );
}
