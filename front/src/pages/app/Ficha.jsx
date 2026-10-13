import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ArrowLeft, Eye, EyeOff, Loader2 } from "lucide-react";
import GaleriaImagenes from "../../components/GaleriaImagenes";
import BotonHistoriaPDF from "../../components/BotonHistoriaPDF";
import ErrorEstado from "../../components/ErrorEstado";
import PestanaIA from "../../components/ficha/PestanaIA";
import PestanaRemitir from "../../components/ficha/PestanaRemitir";
import PestanaHistoria from "../../components/ficha/PestanaHistoria";
import { esClinico, esPaciente } from "../../lib/roles";
import * as S from "../../lib/servicios";
import { ESTADO_CIRUGIA, TIPO_ENCUENTRO, valorClinico } from "../../lib/clinico";
import Dato from "../../components/Dato";
import Insignia from "../../components/Insignia";
import { api, puede } from "../../api";
import { infoCama } from "../../lib/estados";
import { duracion, edadLegible, enmascarar, hora, iniciales, minutosDesde } from "../../lib/format";
import { useReloj, useUsuario } from "../../lib/hooks";

const SEXO = { M: "Masculino", F: "Femenino", O: "Otro" };

export default function Ficha() {
  const { id } = useParams();
  const usuario = useUsuario();
  const ahora = useReloj(60000);
  const [paciente, setPaciente] = useState(null);
  const [error, setError] = useState(null);
  const [estancia, setEstancia] = useState(null);
  const [atencion, setAtencion] = useState(null);    // médico/especialista: su vista del paciente
  const [verDoc, setVerDoc] = useState(false);
  const { state } = useLocation();
  const [pestana, setPestana] = useState(state?.pestana || "historia");

  useEffect(() => {
    let vivo = true;
    setPaciente(null); setError(null); setEstancia(null); setAtencion(null); setVerDoc(false); setPestana(state?.pestana || "historia");
    api(`/pacientes/${id}`).then((p) => vivo && setPaciente(p)).catch((e) => vivo && setError(e));
    if (esClinico(usuario)) {
      S.misPacientes().then((r) => vivo && setAtencion(r.pacientes.find((x) => x.paciente_id === id) || null)).catch(() => {});
    } else if (puede(usuario, "cama", "read")) {
      api("/camas/ocupacion?solo_ocupadas=false")
        .then((l) => vivo && setEstancia(l.find((c) => c.paciente_id === id && c.encuentro_activo && c.encuentro_tipo === "hospitalizacion") || null))
        .catch(() => {});
    }
    return () => { vivo = false; };
  }, [id, usuario]);

  const atras = puede(usuario, "paciente", "read") && (puede(usuario, "cama", "read") || usuario?.rol !== "paciente");

  if (error) {
    return <ErrorEstado error={error} titulo={error.status === 404 ? "Paciente no encontrado" : error.status === 403 ? "No tienes acceso a este paciente" : undefined} />;
  }
  if (!paciente) return <p className="flex items-center gap-2 text-sm text-gray-strong"><Loader2 size={16} className="anim-spin" />Cargando ficha…</p>;

  const nombre = `${paciente.nombre} ${paciente.apellido}`;
  return (
    <div className="space-y-6 pb-16">
      {atras && (
        <Link to={esClinico(usuario) ? "/app/mis-pacientes" : "/app/pacientes"} className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-strong transition hover:text-ink">
          <ArrowLeft size={16} aria-hidden="true" />{esClinico(usuario) ? "Mis pacientes" : "Pacientes"}
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
              <span className="rounded-full bg-paper-white px-3 py-1" title="Quién responde por la atención">
                {paciente.cobertura === "particular" ? "Particular" : `${paciente.eps_nombre || "EPS"}${paciente.regimen ? ` · ${paciente.regimen}` : ""}`}
              </span>
            </div>
          </div>
        </div>

        {esClinico(usuario) ? <AtencionActual a={atencion} /> : (
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
        )}
      </section>

      {(() => {
        // Pestañas según el rol: la API vuelve a validar cada acción.
        const pestanas = [["historia", "Historia"], ["imagenes", "Imágenes"]];
        if (esClinico(usuario)) pestanas.push(["ia", "Análisis de IA"]);
        if (esClinico(usuario)) pestanas.push(["remitir", "Remitir"]);
        const verPDF = esClinico(usuario) || esPaciente(usuario);
        return (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap gap-2" role="tablist" aria-label="Secciones de la ficha">
                {pestanas.map(([clave, texto]) => (
                  <button key={clave} role="tab" aria-selected={pestana === clave} onClick={() => setPestana(clave)}
                          className={`rounded-full px-4 py-2 text-sm font-medium transition ${pestana === clave ? "bg-charcoal text-white" : "bg-cloud-card text-ink hover:bg-hero-sky"}`}>
                    {texto}
                  </button>
                ))}
              </div>
              {verPDF && <BotonHistoriaPDF pacienteId={id} nombre={nombre} />}
            </div>
            {pestana === "historia" && <PestanaHistoria pacienteId={id} />}
            {pestana === "imagenes" && <GaleriaImagenes pacienteId={id} />}
            {pestana === "ia" && <PestanaIA pacienteId={id} />}
            {pestana === "remitir" && <PestanaRemitir pacienteId={id} />}
          </>
        );
      })()}
    </div>
  );
}

/** Lo que el médico necesita ver arriba: dónde está, críticos y cirugía. */
function AtencionActual({ a }) {
  const e = a?.encuentro, cx = a?.cirugia;
  return (
    <div className="rounded-3xl bg-paper-white p-5">
      <p className="text-xs font-semibold uppercase tracking-wider text-gray-strong">Atención actual</p>
      {!a ? <p className="mt-2 text-sm text-gray-strong">Sin atención activa a tu cargo.</p> : (
        <dl className="mt-1 divide-y divide-cloud-card">
          {e ? (
            <>
              <Dato etiqueta="Dónde">{TIPO_ENCUENTRO[e.tipo]}{e.triage ? ` · triage ${e.triage}` : ""}{e.cama ? ` · ${e.cama}` : ""}</Dato>
              {e.diagnostico && <Dato etiqueta="Diagnóstico">{e.dx_codigo} · {e.diagnostico}</Dato>}
              {e.medico && <Dato etiqueta="Responsable">{e.soy_responsable ? "Usted" : e.medico}</Dato>}
            </>
          ) : <Dato etiqueta="Dónde">Sin encuentro activo</Dato>}
          {cx && (
            <Dato etiqueta="Cirugía">
              {ESTADO_CIRUGIA[cx.estado]} · {cx.procedimiento}{cx.quirofano ? ` · ${cx.quirofano}` : ""}
              {cx.estado === "planned" && cx.hora_programada_inicio ? ` · ${hora(cx.hora_programada_inicio)}` : ""}
              {" · "}{cx.mi_papel === "cirujano" ? "usted opera" : cx.mi_papel === "anestesiologo" ? "usted anestesia" : `cirujano: ${cx.cirujano || "sin asignar"}`}
            </Dato>
          )}
          {a.criticos.length > 0 && (
            <Dato etiqueta="Críticos">
              <span className="flex flex-wrap justify-end gap-1">{a.criticos.slice(0, 3).map((c, i) => <span key={i} className="rounded-full bg-coral-deep px-2 py-0.5 text-xs font-semibold text-white">{valorClinico(c)}</span>)}</span>
            </Dato>
          )}
        </dl>
      )}
    </div>
  );
}
