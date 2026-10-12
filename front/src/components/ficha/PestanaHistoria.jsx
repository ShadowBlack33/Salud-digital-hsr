import { useEffect, useState } from "react";
import { ClipboardList, Send, Sparkles, Stethoscope } from "lucide-react";
import ChipDemo from "../ChipDemo";
import Esqueleto from "../Esqueleto";
import Insignia from "../Insignia";
import * as S from "../../lib/servicios";
import { useEventos } from "../../lib/tiempoReal";
import { fechaYHora } from "../../lib/format";

const TIPO = { cirugia: "Cirugía", consulta: "Consulta", hospitalizacion: "Hospitalización", urgencias: "Urgencias" };
const ICONO = { encuentro: [Stethoscope, "text-metric-blue"], observacion: [ClipboardList, "text-sleep-lilac"], reporte: [Sparkles, "text-green-deep"], remision: [Send, "text-gold-deep"] };

/** Todo lo que le ha pasado al paciente, en orden: encuentros, observaciones, reportes aprobados y remisiones. */
export default function PestanaHistoria({ pacienteId }) {
  const [estado, setEstado] = useState({ cargando: true, eventos: [], demo: false });

  const cargar = async () => {
    const [h, r] = await Promise.allSettled([S.historia(pacienteId), S.remisiones()]);
    const historia = h.status === "fulfilled" ? h.value.datos : {};
    const remisiones = r.status === "fulfilled" ? r.value.datos.filter((x) => x.paciente_id === pacienteId) : [];
    const eventos = [
      ...(historia.encuentros || []).map((e) => ({ clase: "encuentro", id: `e${e.id}`, fecha: e.fecha || e.hora_real_inicio || e.created_at,
        titulo: e.descripcion || TIPO[e.tipo] || e.tipo, detalle: [e.lugar, e.estado].filter(Boolean).join(" · ") })),
      ...(historia.observaciones || []).map((o) => ({ clase: "observacion", id: `o${o.id}`, fecha: o.fecha || o.created_at,
        titulo: o.descripcion || o.codigo_loinc || "Observación", detalle: o.valor != null ? `${o.valor} ${o.unidad || ""}` : "" })),
      ...(historia.reportes_ia || []).map((x) => ({ clase: "reporte", id: `r${x.id}`, fecha: x.created_at,
        titulo: `Reporte de IA aprobado · ${Math.round(Number(x.probabilidad || 0) * 100)} %`, detalle: x.observaciones || "" })),
      ...remisiones.map((x) => ({ clase: "remision", id: `m${x.id}`, fecha: x.created_at,
        titulo: `Remisión a ${x.especialista}`, detalle: x.motivo, estado: x.estado })),
    ].filter((e) => e.fecha).sort((a, b) => Date.parse(b.fecha) - Date.parse(a.fecha));
    setEstado({ cargando: false, eventos, demo: [h, r].some((x) => x.status === "fulfilled" && x.value.demo) });
  };

  useEffect(() => { cargar(); }, [pacienteId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEventos((ev) => { if (ev.paciente_id === pacienteId) cargar(); });

  return (
    <section className="rounded-[28px] bg-paper-white p-6 shadow-lift" aria-label="Línea de tiempo">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Línea de tiempo</h2>
        <ChipDemo visible={estado.demo} />
      </div>
      {estado.cargando ? <Esqueleto filas={4} /> : estado.eventos.length === 0 ? (
        <p className="text-sm text-gray-strong">Todavía no hay eventos registrados para este paciente.</p>
      ) : (
        <ol className="relative space-y-5 border-l-2 border-cloud-card pl-7">
          {estado.eventos.map((e) => {
            const [Icono, tono] = ICONO[e.clase];
            return (
              <li key={e.id} className="relative">
                <span className="absolute -left-[42px] top-0 grid size-7 place-items-center rounded-full bg-cloud-card"><Icono size={14} className={tono} aria-hidden="true" /></span>
                <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                  {e.titulo}
                  {e.estado && <Insignia grupo={e.estado === "aceptada" ? "libre" : "proceso"} etiqueta={e.estado === "aceptada" ? "Aceptada" : "Pendiente"} tamano="sm" />}
                </p>
                <p className="text-xs text-gray-strong">{fechaYHora(e.fecha)}{e.detalle ? ` · ${e.detalle}` : ""}</p>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
