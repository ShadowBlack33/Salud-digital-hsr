import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Loader2, Plus, Sparkles, X } from "lucide-react";
import Encabezado from "../../components/Encabezado";
import Insignia from "../../components/Insignia";
import { useAvisos } from "../../components/Avisos";
import * as S from "../../lib/servicios";
import { useEventos } from "../../lib/tiempoReal";
import { cop, fechaYHora } from "../../lib/format";

const SERVICIOS = { consulta: "Consulta", analisis_ia: "Análisis de IA", remision: "Remisión" };
const ESTADO = { pagada: ["libre", "Pagada"], pendiente: ["proceso", "Pendiente"], anulada: ["bloqueado", "Anulada"] };

/** Facturación (R09). Solo identificadores de paciente: el contable no ve datos clínicos. */
export default function Facturacion() {
  const { avisar } = useAvisos();
  const [estado, setEstado] = useState({ cargando: true, lista: [], demo: false, error: null });
  const [filtro, setFiltro] = useState("todas");
  const [nuevas, setNuevas] = useState(new Set());
  const [formulario, setFormulario] = useState(false);

  const vistas = useRef(new Set());   // ids ya mostrados, para resaltar las facturas nuevas

  const cargar = useCallback(async (marcarNuevas = false) => {
    try {
      const { datos, demo } = await S.facturas();
      if (marcarNuevas) {
        setNuevas(new Set(datos.filter((f) => !vistas.current.has(f.id)).map((f) => f.id)));
        setTimeout(() => setNuevas(new Set()), 6000);
      }
      vistas.current = new Set(datos.map((f) => f.id));
      setEstado({ cargando: false, lista: datos, demo, error: null });
    } catch (err) {
      setEstado((e) => ({ ...e, cargando: false, error: err }));
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);
  useEventos((ev) => { if (ev.tipo === "factura_creada") cargar(true); });

  const pagar = async (f) => {
    try { await S.pagarFactura(f.id); avisar(`Factura ${f.id} marcada como pagada.`); cargar(); }
    catch (err) { avisar(err.message, "error"); }
  };

  const total = estado.lista.filter((f) => f.estado_pago !== "anulada").reduce((s, f) => s + Number(f.valor || 0), 0);
  const pagado = estado.lista.filter((f) => f.estado_pago === "pagada").reduce((s, f) => s + Number(f.valor || 0), 0);
  const filas = estado.lista.filter((f) => filtro === "todas" || f.estado_pago === filtro);

  return (
    <div className="space-y-8 pb-16">
      <Encabezado titulo="Facturación" subtitulo="Servicios facturados: consultas, análisis de IA y remisiones." demo={estado.demo}>
        <button onClick={() => setFormulario((v) => !v)}
                className="flex items-center gap-2 rounded-full bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink">
          {formulario ? <X size={16} /> : <Plus size={16} />}{formulario ? "Cerrar" : "Nueva factura"}
        </button>
      </Encabezado>

      <div className="grid gap-4 sm:grid-cols-3">
        <Resumen etiqueta="Facturado" valor={cop(total)} />
        <Resumen etiqueta="Pagado" valor={cop(pagado)} clase="bg-green-soft text-green-ink" />
        <Resumen etiqueta="Por cobrar" valor={cop(total - pagado)} clase="bg-gold-soft text-gold-ink" />
      </div>

      {formulario && <NuevaFactura onCreada={() => { setFormulario(false); cargar(true); avisar("Factura creada."); }} />}

      <section className="rounded-[28px] bg-paper-white p-6 shadow-lift" aria-label="Facturas">
        <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filtrar por estado">
          {["todas", "pendiente", "pagada", "anulada"].map((f) => (
            <button key={f} onClick={() => setFiltro(f)} aria-pressed={filtro === f}
                    className={`rounded-full px-4 py-1.5 text-sm capitalize transition ${filtro === f ? "bg-charcoal text-white" : "bg-cloud-card text-ink hover:bg-hero-sky"}`}>{f}</button>
          ))}
        </div>
        {estado.cargando ? (
          <p className="flex items-center gap-2 text-sm text-gray-strong"><Loader2 size={16} className="anim-spin" />Cargando…</p>
        ) : estado.error ? (
          <p role="alert" className="text-sm text-coral-ink">{estado.error.message}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead>
                <tr className="text-xs text-gray-strong">
                  <th className="pb-3 font-medium">Factura</th><th className="pb-3 font-medium">Paciente (id)</th>
                  <th className="pb-3 font-medium">Servicio</th><th className="pb-3 pr-6 text-right font-medium">Valor</th>
                  <th className="pb-3 font-medium">Fecha</th><th className="pb-3 font-medium">Estado</th><th className="pb-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-cloud-card">
                {filas.map((f) => {
                  const [grupo, etiqueta] = ESTADO[f.estado_pago] || ["bloqueado", f.estado_pago];
                  return (
                    <tr key={f.id} className={`transition-colors duration-700 ${nuevas.has(f.id) ? "bg-hero-sky" : ""}`}>
                      <td className="py-3 font-mono text-xs">{f.id}</td>
                      <td className="py-3 font-mono text-xs" title={String(f.paciente_id)}>{String(f.paciente_id).slice(0, 12)}{String(f.paciente_id).length > 12 ? "…" : ""}</td>
                      <td className="py-3">
                        <span className="font-medium">{SERVICIOS[f.servicio] || f.servicio}</span>
                        {f.reporte_id && (
                          <span title={`Generada sola al aprobar el reporte ${f.reporte_id}`}
                                className="ml-2 inline-flex items-center gap-1 rounded-full bg-hero-sky px-2 py-0.5 text-[11px] font-semibold text-metric-blue">
                            <Sparkles size={11} aria-hidden="true" />Automática
                          </span>
                        )}
                        {f.descripcion && <span className="block text-xs text-gray-strong">{f.descripcion}</span>}
                      </td>
                      <td className="py-3 pr-6 text-right font-semibold tabular-nums">{cop(f.valor)}</td>
                      <td className="py-3 text-xs text-gray-strong">{fechaYHora(f.fecha)}</td>
                      <td className="py-3"><Insignia grupo={grupo} etiqueta={etiqueta} tamano="sm" /></td>
                      <td className="py-3 text-right">
                        {f.estado_pago === "pendiente" && (
                          <button onClick={() => pagar(f)} className="inline-flex items-center gap-1 rounded-full bg-cloud-card px-3 py-1.5 text-xs font-semibold transition hover:bg-green-soft hover:text-green-ink">
                            <Check size={13} />Marcar pagada
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {filas.length === 0 && <p className="py-6 text-center text-sm text-gray-strong">No hay facturas con este filtro.</p>}
          </div>
        )}
      </section>
    </div>
  );
}

function Resumen({ etiqueta, valor, clase = "bg-cloud-card" }) {
  return (
    <div className={`rounded-[24px] p-5 ${clase}`}>
      <span className="text-xs font-medium opacity-80">{etiqueta}</span>
      <span className="mt-1 block text-2xl font-semibold tabular-nums tracking-display">{valor}</span>
    </div>
  );
}

function NuevaFactura({ onCreada }) {
  const [datos, setDatos] = useState({ paciente_id: "", servicio: "consulta", valor: "", descripcion: "" });
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);
  const campo = (k) => (e) => setDatos((d) => ({ ...d, [k]: e.target.value }));

  const enviar = async (e) => {
    e.preventDefault();
    setEnviando(true); setError(null);
    try { await S.crearFactura({ ...datos, valor: Number(datos.valor) }); onCreada(); }
    catch (err) { setError(err.message); }
    finally { setEnviando(false); }
  };

  const entrada = "w-full rounded-2xl bg-cloud-card px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-metric-blue/40";
  return (
    <form onSubmit={enviar} className="anim-pop grid gap-3 rounded-[28px] bg-paper-white p-6 shadow-lift sm:grid-cols-2">
      <h2 className="text-lg font-semibold sm:col-span-2">Nueva factura</h2>
      <label className="text-sm">Paciente (id)<input required value={datos.paciente_id} onChange={campo("paciente_id")} className={`${entrada} mt-1`} /></label>
      <label className="text-sm">Servicio
        <select value={datos.servicio} onChange={campo("servicio")} className={`${entrada} mt-1`}>
          {Object.entries(SERVICIOS).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
        </select>
      </label>
      <label className="text-sm">Valor (COP)<input required type="number" min="1" step="1" value={datos.valor} onChange={campo("valor")} className={`${entrada} mt-1`} /></label>
      <label className="text-sm">Descripción<input value={datos.descripcion} onChange={campo("descripcion")} className={`${entrada} mt-1`} /></label>
      {error && <p role="alert" className="text-sm text-coral-ink sm:col-span-2">{error}</p>}
      <div className="sm:col-span-2">
        <button type="submit" disabled={enviando} className="flex items-center gap-2 rounded-full bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50">
          {enviando && <Loader2 size={15} className="anim-spin" />}Guardar factura
        </button>
      </div>
    </form>
  );
}
