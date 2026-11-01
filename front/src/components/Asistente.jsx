import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { BookOpen, Loader2, MessageCircleQuestion, Send, X } from "lucide-react";
import * as S from "../lib/servicios";
import { useUsuario } from "../lib/hooks";

// Lo que cada perfil puede preguntar (la API filtra de verdad; esto solo orienta).
const AYUDA = {
  paciente: "Pregunta sobre tu historia aprobada: por ejemplo, qué dijo tu último reporte.",
  contable: "Pregunta sobre facturación: estados, copagos, cuotas moderadoras, anulaciones.",
  coordinador: "Pregunta sobre los protocolos de Pulso: alertas, reportes de IA, remisiones.",
};
const AYUDA_CLINICA = "Pregunta a las guías clínicas y a la historia aprobada de tus pacientes.";

// Preguntas de ejemplo por perfil: un clic las envía.
const EJEMPLOS = {
  paciente: ["¿Qué dijo mi último reporte de IA aprobado?", "¿Qué te puedo preguntar?"],
  contable: ["¿Se puede anular una factura que ya está pagada?", "¿Cuánto paga de cuota moderadora un paciente contributivo en urgencias?"],
  coordinador: ["¿Hay alertas sin atender?", "¿Cuántas camas libres hay?",
                "¿Qué pasa si nadie reconoce una alerta crítica en 5 minutos?"],
};
const EJEMPLOS_CLINICOS = ["¿Cuántos pacientes tengo?", "¿Tengo alertas?",
                           "¿Desde qué cifra de potasio la hiperpotasemia es grave?",
                           "¿Con qué hemoglobina se transfunde a un paciente estable?"];

/**
 * Asistente con recuperación aumentada (RAG, semana 12). Disponible para todos
 * los perfiles; cada uno solo recupera las fuentes que le corresponden y la
 * respuesta trae sus citas. En la ficha de un paciente se puede limitar la
 * pregunta a ese paciente.
 */
export default function Asistente() {
  const usuario = useUsuario();
  const { pathname } = useLocation();
  const [abierto, setAbierto] = useState(false);
  const [pregunta, setPregunta] = useState("");
  const [conversacion, setConversacion] = useState([]);
  const [enviando, setEnviando] = useState(false);
  const [soloPaciente, setSoloPaciente] = useState(true);
  const [fuentes, setFuentes] = useState(null);
  const fin = useRef(null);

  // Qué puede consultar este perfil: se pide una vez, al abrir el asistente.
  useEffect(() => {
    if (abierto && fuentes === null) S.fuentesAsistente().then((r) => setFuentes(r.fuentes || [])).catch(() => setFuentes([]));
  }, [abierto, fuentes]);

  const enFicha = pathname.match(/^\/app\/pacientes\/([^/]+)/);
  const pacienteId = enFicha && usuario?.rol !== "paciente" ? decodeURIComponent(enFicha[1]) : null;

  useEffect(() => { fin.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [conversacion, enviando]);

  const enviar = async (e, texto) => {
    e?.preventDefault();
    const q = (texto ?? pregunta).trim();
    if (q.length < 5 || enviando) return;
    setPregunta("");
    setEnviando(true);
    setConversacion((c) => [...c, { quien: "yo", texto: q }]);
    try {
      const r = await S.preguntarAsistente(q, pacienteId && soloPaciente ? pacienteId : null);
      setConversacion((c) => [...c, { quien: "asistente", texto: r.respuesta, citas: r.citas || [], abstencion: r.abstencion,
                                      fuentes: r.fuentes_disponibles || [] }]);
    } catch (err) {
      setConversacion((c) => [...c, { quien: "asistente", texto: err.message, error: true }]);
    } finally { setEnviando(false); }
  };

  if (!usuario) return null;
  return (
    <>
      <button onClick={() => setAbierto((a) => !a)} aria-expanded={abierto} aria-controls="panel-asistente"
              className="fixed bottom-6 left-6 z-50 flex items-center gap-2 rounded-full bg-charcoal px-5 py-3 text-sm font-semibold text-white shadow-lift transition hover:bg-ink">
        {abierto ? <X size={18} aria-hidden="true" /> : <MessageCircleQuestion size={18} aria-hidden="true" />}
        {abierto ? "Cerrar" : "Asistente"}
      </button>

      {abierto && (
        <section id="panel-asistente" aria-label="Asistente"
                 className="anim-pop fixed bottom-24 left-4 z-50 flex max-h-[min(640px,calc(100vh-8rem))] w-[min(420px,calc(100vw-2rem))] flex-col rounded-[28px] bg-paper-white shadow-lift">
          <header className="border-b border-cloud-card px-5 py-4">
            <h2 className="font-semibold">Asistente de Pulso</h2>
            <p className="mt-0.5 text-xs text-gray-strong">{AYUDA[usuario.rol] || AYUDA_CLINICA} Responde solo con fuentes autorizadas para tu perfil, y cita cada una.</p>
            {pacienteId && (
              <label className="mt-2 flex items-center gap-2 text-xs font-medium">
                <input type="checkbox" checked={soloPaciente} onChange={(e) => setSoloPaciente(e.target.checked)} />
                Preguntar sobre el paciente de esta ficha
              </label>
            )}
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4" aria-live="polite">
            {conversacion.length === 0 && (
              <div className="space-y-3 text-sm">
                <p className="text-gray-strong">Respondo con estos documentos, citando la fuente, y con datos en vivo de Pulso según tu perfil (tus pacientes, alertas, remisiones…). Pregúntame «¿qué te puedo preguntar?» para ver todo.</p>
                {fuentes?.length > 0 && (
                  <ul className="space-y-1 text-xs text-gray-strong">
                    {fuentes.map((f) => <li key={f} className="flex gap-1.5"><BookOpen size={12} className="mt-0.5 shrink-0" aria-hidden="true" />{f}</li>)}
                  </ul>
                )}
                {fuentes?.length === 0 && <p className="text-xs text-gray-strong">Tu perfil no tiene fuentes en el asistente.</p>}
                <div className="flex flex-col items-start gap-2">
                  {(EJEMPLOS[usuario.rol] || (fuentes?.length ? EJEMPLOS_CLINICOS : [])).map((ej) => (
                    <button key={ej} onClick={(e) => enviar(e, ej)} className="rounded-2xl bg-cloud-card px-3 py-2 text-left text-xs font-medium hover:bg-hero-sky">{ej}</button>
                  ))}
                </div>
              </div>
            )}
            {conversacion.map((m, i) => (
              <div key={i} className={m.quien === "yo" ? "ml-8 rounded-2xl bg-charcoal px-4 py-2.5 text-sm text-white" : `mr-4 rounded-2xl px-4 py-2.5 text-sm ${m.error ? "bg-coral-soft text-coral-ink" : "bg-cloud-card"}`}>
                <p className="whitespace-pre-wrap">{m.texto}</p>
                {m.abstencion && m.fuentes?.length > 0 && (
                  <div className="mt-2 border-t border-paper-white pt-2 text-xs text-gray-strong">
                    <p className="font-medium">Puedo responder sobre:</p>
                    <ul className="mt-1 list-disc space-y-0.5 pl-4">{m.fuentes.map((f) => <li key={f}>{f}</li>)}</ul>
                  </div>
                )}
                {m.citas?.length > 0 && (
                  <ul className="mt-2 space-y-1 border-t border-paper-white pt-2 text-xs text-gray-strong">
                    {m.citas.map((c) => (
                      <li key={c.id} className="flex gap-1.5">
                        <BookOpen size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
                        <span><strong>[{c.id}]</strong> {c.titulo}{c.seccion ? ` · ${c.seccion}` : ""}{c.paciente ? ` · paciente ${c.paciente}` : ""}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
            {enviando && <p className="flex items-center gap-2 text-sm text-gray-strong"><Loader2 size={14} className="anim-spin" aria-hidden="true" />Buscando en las fuentes…</p>}
            <div ref={fin} />
          </div>

          <form onSubmit={enviar} className="flex items-end gap-2 border-t border-cloud-card p-3">
            <label htmlFor="pregunta-asistente" className="sr-only">Pregunta</label>
            <textarea id="pregunta-asistente" rows={2} maxLength={500} value={pregunta}
                      onChange={(e) => setPregunta(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) enviar(e); }}
                      placeholder="Escribe tu pregunta…"
                      className="flex-1 resize-none rounded-2xl bg-cloud-card px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-metric-blue/40" />
            <button type="submit" disabled={enviando || pregunta.trim().length < 5} aria-label="Enviar pregunta"
                    className="grid size-10 place-items-center rounded-full bg-charcoal text-white disabled:opacity-40"><Send size={16} /></button>
          </form>
        </section>
      )}
    </>
  );
}
