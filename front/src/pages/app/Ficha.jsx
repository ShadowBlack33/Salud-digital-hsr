import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Eye, EyeOff, Loader2, ShieldAlert } from "lucide-react";
import GaleriaImagenes from "../../components/GaleriaImagenes";
import Dato from "../../components/Dato";
import Insignia from "../../components/Insignia";
import { api, puede } from "../../api";
import { infoCama } from "../../lib/estados";
import { duracion, edadLegible, enmascarar, iniciales, minutosDesde } from "../../lib/format";
import { useReloj, useUsuario } from "../../lib/hooks";

const SEXO = { M: "Masculino", F: "Femenino", O: "Otro" };

export default function Ficha() {
  const { id } = useParams();
  const usuario = useUsuario();
  const ahora = useReloj(60000);
  const [paciente, setPaciente] = useState(null);
  const [error, setError] = useState(null);
  const [estancia, setEstancia] = useState(null);
  const [verDoc, setVerDoc] = useState(false);

  useEffect(() => {
    let vivo = true;
    setPaciente(null); setError(null); setEstancia(null); setVerDoc(false);
    api(`/pacientes/${id}`).then((p) => vivo && setPaciente(p)).catch((e) => vivo && setError(e));
    if (puede(usuario, "cama", "read")) {
      api("/camas/ocupacion?solo_ocupadas=false")
        .then((l) => vivo && setEstancia(l.find((c) => c.paciente_id === id && c.encuentro_activo && c.encuentro_tipo === "hospitalizacion") || null))
        .catch(() => {});
    }
    return () => { vivo = false; };
  }, [id, usuario]);

  const atras = puede(usuario, "paciente", "read") && (puede(usuario, "cama", "read") || usuario?.rol !== "paciente");

  if (error) {
    return (
      <div role="alert" className="flex items-start gap-3 rounded-[28px] bg-coral-soft p-6 text-coral-ink">
        <ShieldAlert className="mt-0.5 shrink-0" aria-hidden="true" />
        <div>
          <p className="font-semibold">{error.status === 404 ? "Paciente no encontrado" : error.status === 403 ? "No tienes acceso a este paciente" : "No se pudo cargar la ficha"}</p>
          <p className="mt-1 text-sm">{error.message}</p>
          <Link to="/app/pacientes" className="mt-3 inline-block rounded-full bg-coral-ink px-4 py-2 text-sm font-semibold text-white">Volver a pacientes</Link>
        </div>
      </div>
    );
  }
  if (!paciente) return <p className="flex items-center gap-2 text-sm text-gray-strong"><Loader2 size={16} className="anim-spin" />Cargando ficha…</p>;

  const nombre = `${paciente.nombre} ${paciente.apellido}`;
  return (
    <div className="space-y-6 pb-16">
      {atras && (
        <Link to="/app/pacientes" className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-strong transition hover:text-ink">
          <ArrowLeft size={16} aria-hidden="true" />Pacientes
        </Link>
      )}

      <section className="grid gap-6 rounded-[28px] bg-cloud-card p-6 sm:p-7 lg:grid-cols-[1.1fr_1fr]" aria-label="Datos del paciente">
        <div className="flex items-start gap-4">
          <span className="grid size-16 shrink-0 place-items-center rounded-full bg-charcoal text-xl font-semibold text-white" aria-hidden="true">{iniciales(nombre)}</span>
          <div className="min-w-0">
            <h1 className="text-[30px] font-semibold leading-tight tracking-display">{nombre}</h1>
            <p className="mt-1 flex items-center gap-2 text-sm text-gray-strong">
              {paciente.tipo_documento}
              <span className="font-mono">{verDoc ? paciente.documento : enmascarar(paciente.documento)}</span>
              <button onClick={() => setVerDoc((v) => !v)} aria-label={verDoc ? "Ocultar documento" : "Mostrar documento"}
                      className="grid size-7 place-items-center rounded-full bg-paper-white text-ink transition hover:shadow-lift">
                {verDoc ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs font-semibold">
              <span className="rounded-full bg-paper-white px-3 py-1">{edadLegible(paciente.fecha_nacimiento)}</span>
              <span className="rounded-full bg-paper-white px-3 py-1">{SEXO[paciente.sexo] || paciente.sexo}</span>
              {paciente.riesgo_asa && <span className="rounded-full bg-paper-white px-3 py-1">ASA {paciente.riesgo_asa}</span>}
              {paciente.tiene_comorbilidades && <span className="rounded-full bg-gold-soft px-3 py-1 text-gold-ink">Con comorbilidades</span>}
            </div>
          </div>
        </div>

        <div className="rounded-3xl bg-paper-white p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-strong">Estancia actual</p>
          {estancia ? (
            <dl className="mt-1 divide-y divide-cloud-card">
              <Dato etiqueta="Cama">{estancia.cama_codigo} <Insignia grupo={infoCama(estancia.estado_cama).grupo} etiqueta={infoCama(estancia.estado_cama).etiqueta} tamano="sm" className="ml-1" /></Dato>
              <Dato etiqueta="Hospitalizado hace">{duracion(minutosDesde(estancia.hora_real_inicio, ahora))}</Dato>
              {estancia.diagnostico && <Dato etiqueta="Diagnóstico">{estancia.diagnostico}</Dato>}
              {estancia.medico_nombre && <Dato etiqueta="Médico">{estancia.medico_nombre}</Dato>}
            </dl>
          ) : (
            <p className="mt-2 text-sm text-gray-strong">No está hospitalizado en este momento.</p>
          )}
        </div>
      </section>

      <GaleriaImagenes pacienteId={id} />
    </div>
  );
}
