import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { ArrowUp, BookOpen, ChevronDown, Maximize2, Minimize2, RotateCcw, Sparkles, X } from "lucide-react";
import * as S from "../lib/servicios";
import { useUsuario } from "../lib/hooks";
import Markdown from "./Markdown";

// Lo que cada perfil puede preguntar (la API filtra de verdad; esto solo orienta).
const AYUDA = {
  paciente: "Pregúntame por tu historia aprobada o por lo que puedo hacer.",
  contable: "Pregúntame por facturación: estados, copagos, cuotas moderadoras, anulaciones.",
  coordinador: "Pregúntame por los protocolos de Pulso o por el estado del hospital.",
};
const AYUDA_CLINICA = "Pregúntame por las guías clínicas, tus pacientes o lo que necesites del hospital.";

// Sugerencias para arrancar: un clic las envía.
const EJEMPLOS = {
  paciente: ["¿Qué puedes hacer?", "¿Qué dijo mi último reporte de IA aprobado?"],
  contable: ["¿Qué puedes hacer?", "¿Se puede anular una factura que ya está pagada?",
             "¿Cuánto paga de cuota moderadora un contributivo en urgencias?"],
  coordinador: ["¿Qué puedes hacer?", "¿Hay alertas sin atender?", "¿Cuántas camas libres hay?",
                "¿Qué pasa si nadie reconoce una alerta crítica en 5 minutos?"],
};
const EJEMPLOS_CLINICOS = ["¿Qué puedes hacer?", "¿Tengo alertas?",
                           "¿Desde qué cifra de potasio la hiperpotasemia es grave?",
                           "¿Con qué hemoglobina se transfunde a un paciente estable?"];

const TURNOS_HISTORIAL = 8;   // mensajes previos que se mandan como contexto

/** Quién produjo la respuesta, en una línea discreta (útil para explicar el RAG). */
function origen(m) {
  const g = m.generador;
  if (!g) return null;
  if (g === "sistema") return "Datos en vivo de Pulso";
  if (g === "extractivo") return "Texto tomado de la fuente (sin modelo)";
  if (g === "ninguno") return null;
  return `Redactado por ${g.split(":").pop()}`;
}

/** Numerito de cita: [F3] → ² si F3 es la segunda fuente citada. */
function Cita({ n, onClick }) {
  return (
    <button type="button" data-cita onClick={onClick} title={`Ver la fuente ${n}`}
            className="mx-0.5 inline-grid size-[1.15rem] -translate-y-1 place-items-center rounded-full bg-hero-sky align-baseline text-[10px] font-semibold text-metric-blue hover:bg-metric-blue hover:text-white">
      {n}
    </button>
  );
}

/** Fuentes de una respuesta: plegadas por defecto, para no ensuciar la conversación. */
function Fuentes({ citas, abierta, onToggle }) {
  if (!citas?.length) return null;
  const sistema = citas.every((c) => c.tipo === "sistema");
  return (
    <div className="mt-2">
      <button type="button" onClick={onToggle} aria-expanded={abierta}
              className="flex items-center gap-1 text-[11px] font-medium text-gray-strong hover:text-ink">
        <BookOpen size={12} aria-hidden="true" />
        {sistema ? "Datos en vivo de Pulso" : `Basado en ${citas.length} ${citas.length === 1 ? "fuente" : "fuentes"}`}
        {!sistema && <ChevronDown size={12} className={`transition ${abierta ? "rotate-180" : ""}`} aria-hidden="true" />}
      </button>
      {abierta && !sistema && (
        <ol className="anim-pop mt-2 space-y-2">
          {citas.map((c, i) => (
            <li key={c.id} id={`cita-${c.fragmento_id}`} className="rounded-xl bg-cloud-card/60 px-3 py-2 text-xs">
              <p className="flex gap-2 font-medium">
                <span className="grid size-4 shrink-0 place-items-center rounded-full bg-hero-sky text-[10px] text-metric-blue">{i + 1}</span>
                <span>{c.titulo}{c.seccion ? <span className="font-normal text-gray-strong"> · {c.seccion}</span> : null}
                  {c.paciente ? <span className="font-normal text-gray-strong"> · paciente {c.paciente}</span> : null}</span>
              </p>
              {c.extracto && <p className="mt-1 line-clamp-4 pl-6 text-gray-strong">{c.extracto.replace(/^[^.]+\.\s[^.]+\.\s/, "")}</p>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function Escribiendo() {
  return (
    <div className="flex items-center gap-1 px-1 py-2" role="status" aria-label="Lati está escribiendo">
      {[0, 150, 300].map((d) => (
        <span key={d} className="size-2 rounded-full bg-gray-strong/60 motion-safe:animate-bounce" style={{ animationDelay: `${d}ms` }} />
      ))}
    </div>
  );
}

/**
 * Asistente de Pulso: conversación con memoria sobre las fuentes que el perfil puede ver
 * (guías, historia aprobada) y datos en vivo. La API decide qué se recupera; aquí solo se
 * conversa, se muestra el Markdown de la respuesta y las citas como numeritos.
 */
export default function Asistente() {
  const usuario = useUsuario();
  const { pathname } = useLocation();
  const [abierto, setAbierto] = useState(false);
  const [grande, setGrande] = useState(false);
  const [pregunta, setPregunta] = useState("");
  const [conversacion, setConversacion] = useState([]);
  const [enviando, setEnviando] = useState(false);
  const [soloPaciente, setSoloPaciente] = useState(true);
  const [fuentes, setFuentes] = useState(null);
  const [desplegadas, setDesplegadas] = useState({});
  const fin = useRef(null);
  const entrada = useRef(null);

  // Qué puede consultar este perfil: se pide una vez, al abrir el asistente.
  useEffect(() => {
    if (abierto && fuentes === null) S.fuentesAsistente().then((r) => setFuentes(r.fuentes || [])).catch(() => setFuentes([]));
  }, [abierto, fuentes]);

  const enFicha = pathname.match(/^\/app\/pacientes\/([^/]+)/);
  const pacienteId = enFicha && usuario?.rol !== "paciente" ? decodeURIComponent(enFicha[1]) : null;

  useEffect(() => { fin.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [conversacion, enviando]);
  useEffect(() => { if (abierto) entrada.current?.focus(); }, [abierto]);

  // El cuadro de texto crece con lo que se escribe (hasta 6 líneas).
  useEffect(() => {
    const t = entrada.current;
    if (!t) return;
    t.style.height = "auto";
    t.style.height = `${Math.min(t.scrollHeight, 144)}px`;
  }, [pregunta]);

  const enviar = async (e, texto) => {
    e?.preventDefault();
    const q = (texto ?? pregunta).trim();
    if (q.length < 2 || enviando) return;
    // Las respuestas con datos en vivo (nombres de pacientes, camas, alertas) NO viajan como
    // historial: el historial llega al modelo externo y esos datos no deben salir de Pulso.
    const historial = conversacion.filter((m) => !m.error).slice(-TURNOS_HISTORIAL)
      .map((m) => ({ rol: m.quien === "yo" ? "usuario" : "asistente",
                     texto: m.generador === "sistema" ? "(Respondí con datos en vivo de Pulso.)" : m.texto.slice(0, 4000) }));
    setPregunta("");
    setEnviando(true);
    setConversacion((c) => [...c, { quien: "yo", texto: q }]);
    try {
      const r = await S.preguntarAsistente(q, pacienteId && soloPaciente ? pacienteId : null, historial);
      setConversacion((c) => [...c, { quien: "asistente", texto: r.respuesta, citas: r.citas || [], abstencion: r.abstencion,
                                      fuentes: r.fuentes_disponibles || [], generador: r.generador }]);
    } catch (err) {
      setConversacion((c) => [...c, { quien: "asistente", texto: err.message || "No pude responder. Intenta de nuevo.", error: true }]);
    } finally {
      setEnviando(false);
      entrada.current?.focus();
    }
  };

  const nueva = () => { setConversacion([]); setDesplegadas({}); setPregunta(""); entrada.current?.focus(); };
  const alternar = (i) => setDesplegadas((d) => ({ ...d, [i]: !d[i] }));

  if (!usuario) return null;
  const ejemplos = EJEMPLOS[usuario.rol] || (fuentes?.length ? EJEMPLOS_CLINICOS : ["¿Qué puedes hacer?"]);
  const tamano = grande
    ? "w-[min(760px,calc(100vw-2rem))] h-[min(860px,calc(100vh-8rem))]"
    : "w-[min(480px,calc(100vw-2rem))] h-[min(680px,calc(100vh-8rem))]";

  return (
    <>
      <button onClick={() => setAbierto((a) => !a)} aria-expanded={abierto} aria-controls="panel-asistente"
              className="fixed bottom-6 left-6 z-50 flex items-center gap-2 rounded-full bg-charcoal px-5 py-3 text-sm font-semibold text-white shadow-lift transition hover:bg-ink">
        {abierto ? <X size={18} aria-hidden="true" /> : <Sparkles size={18} aria-hidden="true" />}
        {abierto ? "Cerrar" : "Lati"}
      </button>

      {abierto && (
        <section id="panel-asistente" aria-label="Lati, asistente de Pulso"
                 className={`anim-pop fixed bottom-24 left-4 z-50 flex flex-col overflow-hidden rounded-[28px] bg-paper-white shadow-lift ${tamano}`}>
          <header className="flex items-start gap-3 border-b border-cloud-card px-5 py-3.5">
            <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-charcoal text-white"><Sparkles size={15} aria-hidden="true" /></span>
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold">Lati <span className="font-normal text-gray-strong">· asistente de Pulso</span></h2>
              <p className="truncate text-xs text-gray-strong">Responde con tus fuentes y te dice de dónde sale cada dato</p>
              {pacienteId && (
                <label className="mt-1.5 flex items-center gap-2 text-xs font-medium">
                  <input type="checkbox" checked={soloPaciente} onChange={(e) => setSoloPaciente(e.target.checked)} />
                  Preguntar sobre el paciente de esta ficha
                </label>
              )}
            </div>
            {conversacion.length > 0 && (
              <button onClick={nueva} title="Nueva conversación" aria-label="Nueva conversación"
                      className="grid size-8 place-items-center rounded-full text-gray-strong hover:bg-cloud-card hover:text-ink"><RotateCcw size={15} /></button>
            )}
            <button onClick={() => setGrande((g) => !g)} title={grande ? "Reducir" : "Ampliar"} aria-label={grande ? "Reducir" : "Ampliar"}
                    className="hidden size-8 place-items-center rounded-full text-gray-strong hover:bg-cloud-card hover:text-ink sm:grid">
              {grande ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
            </button>
          </header>

          <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5 text-sm" aria-live="polite">
            {conversacion.length === 0 && (
              <div className="space-y-4">
                <div>
                  <p className="text-base font-semibold">Hola, soy Lati 👋</p>
                  <p className="mt-1 text-gray-strong">{AYUDA[usuario.rol] || AYUDA_CLINICA} Puedes hablarme normal y hacer preguntas de seguimiento.</p>
                </div>
                {fuentes?.length > 0 && (
                  <details className="group rounded-2xl bg-cloud-card px-4 py-3 text-xs">
                    <summary className="flex cursor-pointer list-none items-center gap-1.5 font-medium">
                      <BookOpen size={13} aria-hidden="true" /> Mis documentos ({fuentes.length})
                      <ChevronDown size={13} className="ml-auto transition group-open:rotate-180" aria-hidden="true" />
                    </summary>
                    <ul className="mt-2 space-y-1 text-gray-strong">{fuentes.map((f) => <li key={f}>· {f}</li>)}</ul>
                  </details>
                )}
                <div className="flex flex-wrap gap-2">
                  {ejemplos.map((ej) => (
                    <button key={ej} onClick={(e) => enviar(e, ej)}
                            className="rounded-full border border-cloud-card px-3 py-1.5 text-left text-xs font-medium transition hover:border-metric-blue hover:text-metric-blue">{ej}</button>
                  ))}
                </div>
              </div>
            )}

            {conversacion.map((m, i) => m.quien === "yo" ? (
              <div key={i} className="anim-pop ml-auto w-fit max-w-[85%] rounded-3xl rounded-br-lg bg-charcoal px-4 py-2.5 text-white">
                <p className="whitespace-pre-wrap">{m.texto}</p>
              </div>
            ) : (
              <div key={i} className="anim-pop max-w-[95%]">
                <div className={m.error ? "rounded-2xl bg-coral-soft px-4 py-2.5 text-coral-ink" : ""}>
                  {(() => {
                    // [F3] → numerito según el orden en que aparecen las citas de esta respuesta.
                    const orden = Object.fromEntries((m.citas || []).map((c, j) => [c.id, j + 1]));
                    return <Markdown texto={m.texto} cita={(n, k) => orden[`F${n}`]
                      ? <Cita key={k} n={orden[`F${n}`]} onClick={() => setDesplegadas((d) => ({ ...d, [i]: true }))} /> : null} />;
                  })()}
                </div>
                {m.abstencion && m.fuentes?.length > 0 && (
                  <div className="mt-2 rounded-2xl bg-cloud-card px-4 py-2.5 text-xs text-gray-strong">
                    <p className="font-medium text-ink">Puedo ayudarte con:</p>
                    <ul className="mt-1 list-disc space-y-0.5 pl-4">{m.fuentes.map((f) => <li key={f}>{f}</li>)}</ul>
                  </div>
                )}
                <Fuentes citas={m.citas} abierta={!!desplegadas[i]} onToggle={() => alternar(i)} />
                {origen(m) && !m.citas?.length && <p className="mt-1.5 text-[11px] text-gray-strong">{origen(m)}</p>}
              </div>
            ))}
            {enviando && <Escribiendo />}
            <div ref={fin} />
          </div>

          <form onSubmit={enviar} className="border-t border-cloud-card p-3">
            <div className="flex items-end gap-2 rounded-3xl bg-cloud-card py-1.5 pl-4 pr-1.5 focus-within:ring-2 focus-within:ring-metric-blue/40">
              <label htmlFor="pregunta-asistente" className="sr-only">Mensaje</label>
              <textarea id="pregunta-asistente" ref={entrada} rows={1} maxLength={500} value={pregunta}
                        onChange={(e) => setPregunta(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) enviar(e); }}
                        placeholder="Escríbeme lo que necesites…"
                        className="max-h-36 flex-1 resize-none bg-transparent py-1.5 text-sm outline-none" />
              <button type="submit" disabled={enviando || pregunta.trim().length < 2} aria-label="Enviar"
                      className="grid size-9 shrink-0 place-items-center rounded-full bg-charcoal text-white transition disabled:opacity-30"><ArrowUp size={16} /></button>
            </div>
            <p className="mt-1.5 text-center text-[10px] text-gray-strong">Las respuestas salen de tus fuentes; verifícalas antes de decidir.</p>
          </form>
        </section>
      )}
    </>
  );
}
