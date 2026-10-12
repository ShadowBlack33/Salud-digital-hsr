import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, ChevronRight, FileCheck, Loader2, Send, Users } from "lucide-react";
import Encabezado from "../../components/Encabezado";
import TarjetaContador from "../../components/TarjetaContador";
import { api } from "../../api";
import { useTiempoReal } from "../../lib/tiempoReal";
import { useUsuario } from "../../lib/hooks";
import { edadLegible } from "../../lib/format";

/** Inicio del médico: trabajo pendiente en vivo (R18) y sus pacientes. */
export default function MiTurno() {
  const usuario = useUsuario();
  const { pendientes, demo } = useTiempoReal();
  const [pacientes, setPacientes] = useState(null);

  useEffect(() => {
    let vivo = true;
    api("/pacientes?limite=8").then((l) => vivo && setPacientes(l)).catch(() => vivo && setPacientes([]));
    return () => { vivo = false; };
  }, []);

  return (
    <div className="space-y-8 pb-16">
      <Encabezado titulo="Mi turno" subtitulo={`Hola, ${usuario?.username}. Esto es lo que necesita tu atención ahora.`} demo={demo} />

      <div className="grid gap-4 md:grid-cols-3">
        <TarjetaContador etiqueta="Reportes de IA por revisar" valor={pendientes.reportes_por_revisar} icono={FileCheck}
                         detalle="Esperan tu aprobación antes de entrar a la historia" />
        <TarjetaContador etiqueta="Remisiones" valor={pendientes.remisiones_recibidas} icono={Send} tono="text-green-deep"
                         detalle="Pendientes de respuesta" />
        <TarjetaContador etiqueta="Alertas activas" valor={pendientes.alertas_activas} icono={AlertCircle}
                         tono={pendientes.alertas_activas ? "text-coral-deep" : "text-gray-strong"}
                         resaltar={pendientes.alertas_activas > 0} detalle="Casos críticos sin reconocer" />
      </div>

      <section className="rounded-[28px] bg-paper-white p-6 shadow-lift" aria-label="Pacientes">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-semibold"><Users size={18} aria-hidden="true" />Pacientes</h2>
          <Link to="/app/pacientes" className="text-sm font-medium text-metric-blue hover:underline">Ver todos</Link>
        </div>
        {!pacientes ? (
          <p className="flex items-center gap-2 py-4 text-sm text-gray-strong"><Loader2 size={16} className="anim-spin" />Cargando…</p>
        ) : pacientes.length === 0 ? (
          <p className="py-4 text-sm text-gray-strong">No hay pacientes para mostrar.</p>
        ) : (
          <ul className="divide-y divide-cloud-card">
            {pacientes.map((p) => (
              <li key={p.paciente_id}>
                <Link to={`/app/pacientes/${p.paciente_id}`} className="flex items-center justify-between gap-3 rounded-2xl px-3 py-3 transition hover:bg-cloud-card/60">
                  <span>
                    <span className="block text-sm font-medium">{p.nombre} {p.apellido}</span>
                    <span className="block text-xs text-gray-strong">{p.tipo_documento} {p.documento} · {edadLegible(p.fecha_nacimiento)}{p.riesgo_asa ? ` · ASA ${p.riesgo_asa}` : ""}</span>
                  </span>
                  <ChevronRight size={18} className="text-gray-strong" aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
