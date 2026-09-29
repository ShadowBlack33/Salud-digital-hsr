import { CalendarClock } from "lucide-react";
import Panel from "./Panel";
import Insignia from "./Insignia";
import Dato from "./Dato";
import AccionesEstado from "./AccionesEstado";
import { useAvisos } from "./Avisos";
import { api, puede } from "../api";
import { QUIROFANO, infoCama, infoQx } from "../lib/estados";
import { duracion, hora, minutosDesde } from "../lib/format";
import { retrasoCirugia } from "../lib/tablero";

/** Panel lateral de un quirófano: cirugía en curso, retraso, siguientes y cambio de estado. */
export default function DrawerQuirofano({ quirofano: q, ahora, usuario, onCerrar, onCambio }) {
  const { avisar } = useAvisos();
  if (!q) return <Panel abierto={false} />;

  const info = infoQx(q.estado);
  const a = q.actual;
  const retraso = retrasoCirugia(a, ahora);
  const puedeCambiar = puede(usuario, "quirofano", "update");
  const principales = [
    { estado: "disponible", etiqueta: "Marcar disponible" },
    { estado: "en_preparacion", etiqueta: "En preparación" },
    { estado: "en_limpieza", etiqueta: "Iniciar limpieza" },
    { estado: "bloqueado", etiqueta: "Bloquear" },
  ].filter((p) => p.estado !== q.estado);

  async function cambiar(estado, motivo) {
    try {
      await api(`/quirofanos/${q.id}/estado`, { method: "PATCH", json: { estado, motivo } });
      avisar(`${q.codigo}: ${QUIROFANO[estado].etiqueta.toLowerCase()}`);
      await onCambio();
    } catch (e) {
      avisar(e.status === 403 ? "Tu rol no puede cambiar el estado de los quirófanos" : e.message, "error");
    }
  }

  return (
    <Panel abierto onCerrar={onCerrar} titulo={q.nombre || q.codigo}
           subtitulo={q.tiene_circulacion_extracorporea ? "Con circulación extracorpórea" : q.tiene_arco_c ? "Con arco en C" : "Quirófano general"}
           pie={puedeCambiar ? (
             <AccionesEstado principales={principales}
               advertencia={() => a ? `Hay una cirugía en curso (${a.procedimiento}). Cambiar el estado del quirófano no la detiene.` : null}
               pideMotivo={(e) => e === "bloqueado"} onCambiar={cambiar} />
           ) : <p className="text-sm text-gray-strong">Tu rol puede ver este quirófano, pero no cambiar su estado.</p>}>
      <div className="flex flex-wrap items-center gap-3">
        <Insignia grupo={info.grupo} etiqueta={info.etiqueta} />
        <span className="text-sm text-gray-strong">desde las {hora(q.estado_desde)} · hace {duracion(minutosDesde(q.estado_desde, ahora))}</span>
      </div>

      {a ? (
        <section className="mt-6 rounded-3xl bg-cloud-card p-5" aria-label="Cirugía en curso">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-strong">Cirugía en curso</p>
          <p className="mt-1 text-xl font-semibold tracking-display">{a.procedimiento}</p>
          <p className="text-sm text-gray-strong">{a.especialidad}</p>
          <dl className="mt-2 divide-y divide-paper-white">
            <Dato etiqueta="Cirujano">{a.cirujano}</Dato>
            <Dato etiqueta="Paciente">{a.paciente_nombre_corto}</Dato>
            <Dato etiqueta="Programada">{hora(a.hora_programada_inicio)}</Dato>
            <Dato etiqueta="Inició">{hora(a.hora_real_inicio)}{a.retraso_inicio_min > 0 && <span className="text-coral-ink"> (+{a.retraso_inicio_min} min)</span>}</Dato>
            <Dato etiqueta="Duración estimada">{duracion(a.duracion_estimada_min)}</Dato>
            <Dato etiqueta="Retraso acumulado">
              <span className={retraso >= 15 ? "text-coral-ink" : ""}>{retraso > 0 ? `+${retraso} min` : "A tiempo"}</span>
            </Dato>
            {a.cama_destino && (
              <Dato etiqueta="Cama de destino">
                {a.cama_destino} <Insignia grupo={infoCama(a.cama_destino_estado).grupo} etiqueta={infoCama(a.cama_destino_estado).etiqueta} tamano="sm" className="ml-1" />
              </Dato>
            )}
          </dl>
        </section>
      ) : (
        <p className="mt-6 rounded-3xl bg-cloud-card p-5 text-sm text-gray-strong">No hay una cirugía en curso en este quirófano.</p>
      )}

      {q.proximas?.length > 0 && (
        <section className="mt-6" aria-label="Siguientes cirugías">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-strong">Siguientes</p>
          <ul className="mt-2 space-y-2">
            {q.proximas.map((p) => (
              <li key={p.encuentro_id} className="flex items-start gap-3 rounded-2xl bg-cloud-card p-3.5">
                <CalendarClock size={18} className="mt-0.5 shrink-0 text-gray-strong" aria-hidden="true" />
                <span className="min-w-0 text-sm">
                  <span className="block font-medium">{p.procedimiento}</span>
                  <span className="block text-gray-strong">{hora(p.hora_programada_inicio)} a {hora(p.hora_programada_fin)} · {p.cirujano}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Panel>
  );
}
