import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { Ban, Check, ChevronLeft, ChevronRight, Download, Filter, Loader2, Plus, RotateCcw, Search, Sparkles, X } from "lucide-react";
import GraficaCobro from "../../components/GraficaCobro";
import Esqueleto from "../../components/Esqueleto";
import Encabezado from "../../components/Encabezado";
import Insignia from "../../components/Insignia";
import { useAvisos } from "../../components/Avisos";
import * as S from "../../lib/servicios";
import { useEventos } from "../../lib/tiempoReal";
import { cop, fechaYHora } from "../../lib/format";
import { ENTIDADES, ESTADOS_PAGO, TIPOS_COBRO, repartir, textoEntidad } from "../../lib/facturacion";

const PERIODOS = [["hoy", "Hoy", 1], ["7d", "7 días", 7], ["30d", "30 días", 30], ["todo", "Todo", null]];
const POR_PAGINA = [25, 50, 100];
const VACIO = { tipo: "", estado: "", entidad: "", q: "", periodo: "7d" };
const normalizar = (t) => String(t ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/**
 * Facturación (R09). Pensada para el volumen real de un hospital (miles de
 * movimientos al día): se filtra en cascada por tipo de cobro, estado,
 * entidad responsable y paciente, con totales que respetan los filtros.
 * El contable ve quién paga (el paciente o su entidad), nunca datos clínicos.
 */
export default function Facturacion() {
  const { avisar } = useAvisos();
  const [estado, setEstado] = useState({ cargando: true, lista: [], demo: false, error: null });
  const [f, setF] = useState(VACIO);
  const q = useDeferredValue(f.q);
  const [pagina, setPagina] = useState(0);
  const [porPagina, setPorPagina] = useState(25);
  const [nuevas, setNuevas] = useState(new Set());
  const [formulario, setFormulario] = useState(false);
  const vistas = useRef(new Set());

  const cargar = useCallback(async (marcarNuevas = false) => {
    try {
      const { datos, demo } = await S.facturas();
      if (marcarNuevas) {
        setNuevas(new Set(datos.filter((x) => !vistas.current.has(x.id)).map((x) => x.id)));
        setTimeout(() => setNuevas(new Set()), 6000);
      }
      vistas.current = new Set(datos.map((x) => x.id));
      setEstado({ cargando: false, lista: datos, demo, error: null });
    } catch (err) {
      setEstado((e) => ({ ...e, cargando: false, error: err }));
    }
  }, []);
  useEffect(() => { cargar(); }, [cargar]);
  useEventos((ev) => { if (ev.tipo === "factura_creada") cargar(true); });
  useEffect(() => { setPagina(0); }, [f.tipo, f.estado, f.entidad, q, f.periodo, porPagina]);
  const poner = (k, v) => setF((x) => ({ ...x, [k]: x[k] === v ? "" : v }));

  // Cascada: cada nivel cuenta sobre lo que dejan los anteriores.
  const desde = useMemo(() => {
    const dias = PERIODOS.find(([k]) => k === f.periodo)?.[2];
    if (!dias) return 0;
    const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - (dias - 1));
    return d.getTime();
  }, [f.periodo]);
  const enPeriodo = useMemo(() => estado.lista.filter((x) => !desde || Date.parse(x.fecha) >= desde), [estado.lista, desde]);
  const porTipo = useMemo(() => enPeriodo.filter((x) => !f.tipo || x.tipo_cobro === f.tipo), [enPeriodo, f.tipo]);
  const porEstado = useMemo(() => porTipo.filter((x) => !f.estado || x.estado_pago === f.estado), [porTipo, f.estado]);
  const porEntidad = useMemo(() => porEstado.filter((x) => !f.entidad || textoEntidad(x.cobertura) === f.entidad || x.cobertura?.entidad === f.entidad), [porEstado, f.entidad]);
  const filas = useMemo(() => {
    const t = normalizar(q.trim());
    if (!t) return porEntidad;
    return porEntidad.filter((x) => normalizar(`${x.paciente_nombre} ${x.paciente_documento} ${x.paciente_id} ${x.id} ${x.descripcion} ${x.cups}`).includes(t));
  }, [porEntidad, q]);

  const cuenta = (lista, clave) => lista.reduce((m, x) => { const k = clave(x); m[k] = (m[k] || 0) + 1; return m; }, {});
  const conteoTipo = useMemo(() => cuenta(enPeriodo, (x) => x.tipo_cobro), [enPeriodo]);
  const conteoEstado = useMemo(() => cuenta(porTipo, (x) => x.estado_pago), [porTipo]);
  const conteoEntidad = useMemo(() => cuenta(porEstado, (x) => x.cobertura?.entidad || "Particular"), [porEstado]);

  const validas = filas.filter((x) => x.estado_pago !== "anulada");
  const suma = (lista, k) => lista.reduce((s, x) => s + Number(x[k] || 0), 0);
  const total = suma(validas, "valor");
  const cobrado = suma(validas.filter((x) => x.estado_pago === "pagada"), "valor");
  const totalPaciente = suma(validas, "valor_paciente");
  const totalEntidad = suma(validas, "valor_entidad");
  const paginas = Math.max(1, Math.ceil(filas.length / porPagina));
  const visibles = filas.slice(pagina * porPagina, (pagina + 1) * porPagina);
  const hayFiltros = f.tipo || f.estado || f.entidad || f.q;

  const accion = async (fn, x, texto) => {
    try { await fn(x.id); avisar(`Factura ${x.id} ${texto}.`); cargar(); } catch (err) { avisar(err.message, "error"); }
  };

  // CSV con BOM y punto y coma: Excel en español lo abre bien sin configurar nada.
  const exportar = () => {
    const celda = (v) => `"${String(v ?? "").replaceAll('"', '""')}"`;
    const cab = ["factura", "fecha", "paciente_id", "paciente", "documento", "tipo_cobro", "cups", "servicio", "cantidad",
      "valor_total", "a_cargo_paciente", "a_cargo_entidad", "responsable", "regimen", "estado", "origen", "reporte_id"];
    const lineas = filas.map((x) => [x.id, x.fecha, x.paciente_id, x.paciente_nombre, x.paciente_documento, TIPOS_COBRO[x.tipo_cobro],
      x.cups, x.descripcion, x.cantidad, x.valor, x.valor_paciente, x.valor_entidad, x.cobertura?.entidad, x.cobertura?.regimen,
      x.estado_pago, x.origen, x.reporte_id].map(celda).join(";"));
    const blob = new Blob(["﻿" + [cab.join(";"), ...lineas].join("\r\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    Object.assign(document.createElement("a"), { href: url, download: `facturas_${new Date().toISOString().slice(0, 10)}.csv` }).click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  };

  return (
    <div className="space-y-6 pb-16">
      <Encabezado titulo="Facturación" subtitulo="Todos los cobros del hospital: quién paga (el paciente o su entidad) y en qué estado está cada uno." demo={estado.demo}>
        <button onClick={exportar} disabled={filas.length === 0}
                className="flex items-center gap-2 rounded-full bg-cloud-card px-5 py-2.5 text-sm font-semibold transition hover:bg-hero-sky disabled:opacity-40">
          <Download size={16} />Exportar {filas.length.toLocaleString("es-CO")}
        </button>
        <button onClick={() => setFormulario((v) => !v)}
                className="flex items-center gap-2 rounded-full bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink">
          {formulario ? <X size={16} /> : <Plus size={16} />}{formulario ? "Cerrar" : "Nueva factura"}
        </button>
      </Encabezado>

      {formulario && <NuevaFactura onCreada={() => { setFormulario(false); cargar(true); avisar("Factura creada."); }} />}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Resumen etiqueta="Movimientos" valor={filas.length.toLocaleString("es-CO")} />
        <Resumen etiqueta="Facturado" valor={cop(total)} />
        <Resumen etiqueta="A cargo de entidades" valor={cop(totalEntidad)} />
        <Resumen etiqueta="A cargo de pacientes" valor={cop(totalPaciente)} />
        <Resumen etiqueta="Por cobrar" valor={cop(total - cobrado)} clase="bg-gold-soft text-gold-ink" />
      </div>

      <section className="space-y-4 rounded-[28px] bg-cloud-card p-5" aria-label="Filtros">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="flex items-center gap-2 text-sm font-semibold"><Filter size={15} aria-hidden="true" />Filtrar</p>
          <div className="flex items-center gap-1 rounded-full bg-paper-white p-1" role="group" aria-label="Periodo">
            {PERIODOS.map(([k, t]) => (
              <button key={k} onClick={() => setF((x) => ({ ...x, periodo: k }))} aria-pressed={f.periodo === k}
                      className={`rounded-full px-3 py-1.5 text-xs font-semibold ${f.periodo === k ? "bg-charcoal text-white" : "hover:bg-cloud-card"}`}>{t}</button>
            ))}
          </div>
        </div>
        <Nivel n={1} titulo="Tipo de cobro">
          {Object.entries(TIPOS_COBRO).filter(([k]) => conteoTipo[k]).map(([k, t]) => (
            <Chip key={k} activo={f.tipo === k} onClick={() => poner("tipo", k)} texto={t} n={conteoTipo[k]} />
          ))}
        </Nivel>
        <Nivel n={2} titulo="Estado">
          {Object.entries(ESTADOS_PAGO).filter(([k]) => conteoEstado[k]).map(([k, [, t]]) => (
            <Chip key={k} activo={f.estado === k} onClick={() => poner("estado", k)} texto={t} n={conteoEstado[k]} />
          ))}
        </Nivel>
        <Nivel n={3} titulo="Responsable del pago">
          {ENTIDADES.filter((e) => conteoEntidad[e.entidad]).map((e) => (
            <Chip key={e.entidad} activo={f.entidad === e.entidad} onClick={() => poner("entidad", e.entidad)} texto={e.entidad} n={conteoEntidad[e.entidad]} />
          ))}
        </Nivel>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <span className="w-44 shrink-0 text-xs font-semibold uppercase tracking-wide text-gray-strong">4 · Paciente o factura</span>
          <div className="relative flex-1">
            <Search size={15} className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-strong" aria-hidden="true" />
            <input type="search" value={f.q} onChange={(e) => setF((x) => ({ ...x, q: e.target.value }))}
                   placeholder="Nombre, últimos dígitos del documento, número de factura o código CUPS" aria-label="Buscar paciente o factura"
                   className="w-full rounded-full bg-paper-white py-2.5 pl-10 pr-4 text-sm outline-none focus:ring-2 focus:ring-metric-blue" />
          </div>
          {hayFiltros && (
            <button onClick={() => setF((x) => ({ ...VACIO, periodo: x.periodo }))} className="flex items-center justify-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium hover:bg-paper-white">
              <RotateCcw size={14} aria-hidden="true" />Limpiar
            </button>
          )}
        </div>
      </section>

      {!estado.cargando && <GraficaCobro facturas={filas} />}

      <section className="rounded-[28px] bg-paper-white p-6 shadow-lift" aria-label="Facturas">
        {estado.cargando ? <Esqueleto filas={6} /> : estado.error ? (
          <p role="alert" className="text-sm text-coral-ink">{estado.error.message}</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1040px] text-left text-sm">
                <thead>
                  <tr className="text-xs text-gray-strong">
                    <th className="pb-3 font-medium">Factura</th><th className="pb-3 font-medium">Paciente</th>
                    <th className="pb-3 font-medium">Servicio</th><th className="pb-3 font-medium">Responsable</th>
                    <th className="pb-3 pr-4 text-right font-medium">Paciente paga</th><th className="pb-3 pr-4 text-right font-medium">Entidad paga</th>
                    <th className="pb-3 pr-4 text-right font-medium">Total</th><th className="pb-3 font-medium">Estado</th><th className="pb-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-cloud-card">
                  {visibles.map((x) => {
                    const [grupo, etiqueta] = ESTADOS_PAGO[x.estado_pago] || ["bloqueado", x.estado_pago];
                    return (
                      <tr key={x.id} className={`align-top transition-colors duration-700 ${nuevas.has(x.id) ? "bg-hero-sky" : ""}`}>
                        <td className="py-3 pr-3"><span className="block font-mono text-xs">{x.id}</span><span className="text-xs text-gray-strong">{fechaYHora(x.fecha)}</span></td>
                        <td className="py-3 pr-3">
                          <span className="block font-medium">{x.paciente_nombre || "—"}</span>
                          <span className="font-mono text-xs text-gray-strong" title={String(x.paciente_id)}>{x.paciente_documento || String(x.paciente_id).slice(0, 12)}</span>
                        </td>
                        <td className="max-w-[260px] py-3 pr-3">
                          <span className="block font-medium">{x.descripcion}{x.cantidad > 1 ? ` × ${x.cantidad}` : ""}</span>
                          <span className="text-xs text-gray-strong">{TIPOS_COBRO[x.tipo_cobro]}{x.cups ? ` · ${x.cups}` : ""}</span>
                          {x.reporte_id && (
                            <span title={`Generada sola al aprobar el reporte ${x.reporte_id}`} className="ml-2 inline-flex items-center gap-1 rounded-full bg-hero-sky px-2 py-0.5 text-[11px] font-semibold text-ink">
                              <Sparkles size={11} className="text-metric-blue" aria-hidden="true" />Automática
                            </span>
                          )}
                        </td>
                        <td className="py-3 pr-3 text-xs">
                          <span className={`inline-block rounded-full px-2.5 py-1 font-semibold ${x.cobertura?.tipo === "particular" ? "bg-gold-soft text-gold-ink" : "bg-cloud-card text-ink"}`}>{textoEntidad(x.cobertura)}</span>
                        </td>
                        <td className="py-3 pr-4 text-right tabular-nums">{cop(x.valor_paciente)}</td>
                        <td className="py-3 pr-4 text-right tabular-nums">{cop(x.valor_entidad)}</td>
                        <td className="py-3 pr-4 text-right font-semibold tabular-nums">{cop(x.valor)}</td>
                        <td className="py-3"><Insignia grupo={grupo} etiqueta={etiqueta} tamano="sm" /></td>
                        <td className="py-3 text-right">
                          {["pendiente", "radicada", "glosada"].includes(x.estado_pago) && (
                            <span className="inline-flex gap-1">
                              <button onClick={() => accion(S.pagarFactura, x, "marcada como pagada")} title="Marcar pagada" aria-label={`Marcar pagada ${x.id}`}
                                      className="grid size-8 place-items-center rounded-full bg-cloud-card transition hover:bg-green-soft hover:text-green-ink"><Check size={14} /></button>
                              <button onClick={() => accion((id) => S.anularFactura(id, "Anulada por el contable"), x, "anulada")} title="Anular" aria-label={`Anular ${x.id}`}
                                      className="grid size-8 place-items-center rounded-full bg-cloud-card transition hover:bg-coral-soft hover:text-coral-ink"><Ban size={14} /></button>
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {filas.length === 0 && <p className="py-6 text-center text-sm text-gray-strong">No hay facturas con estos filtros.</p>}
            </div>
            {filas.length > 0 && (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
                <span className="text-gray-strong">
                  {(pagina * porPagina + 1).toLocaleString("es-CO")}–{Math.min(filas.length, (pagina + 1) * porPagina).toLocaleString("es-CO")} de {filas.length.toLocaleString("es-CO")}
                </span>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-2 text-gray-strong">Por página
                    <select value={porPagina} onChange={(e) => setPorPagina(Number(e.target.value))} className="rounded-full bg-cloud-card px-3 py-1.5 text-ink outline-none">
                      {POR_PAGINA.map((n) => <option key={n} value={n}>{n}</option>)}
                    </select>
                  </label>
                  <button onClick={() => setPagina((p) => Math.max(0, p - 1))} disabled={pagina === 0} aria-label="Página anterior" className="grid size-9 place-items-center rounded-full bg-cloud-card disabled:opacity-40"><ChevronLeft size={16} /></button>
                  <span className="tabular-nums">{pagina + 1} / {paginas}</span>
                  <button onClick={() => setPagina((p) => Math.min(paginas - 1, p + 1))} disabled={pagina >= paginas - 1} aria-label="Página siguiente" className="grid size-9 place-items-center rounded-full bg-cloud-card disabled:opacity-40"><ChevronRight size={16} /></button>
                </div>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function Nivel({ n, titulo, children }) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
      <span className="w-44 shrink-0 pt-1.5 text-xs font-semibold uppercase tracking-wide text-gray-strong">{n} · {titulo}</span>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function Chip({ activo, onClick, texto, n }) {
  return (
    <button onClick={onClick} aria-pressed={activo}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition ${activo ? "bg-charcoal text-white" : "bg-paper-white text-ink hover:bg-hero-sky"}`}>
      {texto}<span className={`rounded-full px-1.5 tabular-nums ${activo ? "bg-white/20" : "bg-cloud-card"}`}>{n.toLocaleString("es-CO")}</span>
    </button>
  );
}

function Resumen({ etiqueta, valor, clase = "bg-cloud-card" }) {
  return (
    <div className={`rounded-[24px] p-5 ${clase}`}>
      <span className="text-xs font-medium opacity-80">{etiqueta}</span>
      <span className="mt-1 block text-xl font-semibold tabular-nums tracking-display">{valor}</span>
    </div>
  );
}

function NuevaFactura({ onCreada }) {
  const [tarifas, setTarifas] = useState([]);
  const [d, setD] = useState({ paciente_id: "", paciente_nombre: "", cups: "", cantidad: 1, entidad: "Particular" });
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { S.tarifario().then((r) => setTarifas(r.datos)).catch(() => setTarifas([])); }, []);
  const campo = (k) => (e) => setD((x) => ({ ...x, [k]: e.target.value }));
  const tarifa = tarifas.find((t) => t.codigo === d.cups);
  const cobertura = ENTIDADES.find((e) => e.entidad === d.entidad) || ENTIDADES[0];
  const valor = tarifa ? tarifa.valor * Math.max(1, Number(d.cantidad) || 1) : 0;
  const reparto = repartir(valor, cobertura, tarifa?.tipo_cobro);
  const grupos = useMemo(() => {
    const g = {};
    tarifas.forEach((t) => { (g[t.tipo_cobro] ||= []).push(t); });
    return Object.entries(g);
  }, [tarifas]);

  const enviar = async (e) => {
    e.preventDefault();
    if (!tarifa) return;
    setEnviando(true); setError(null);
    try {
      await S.crearFactura({
        paciente_id: d.paciente_id.trim(), paciente_nombre: d.paciente_nombre.trim() || undefined,
        servicio: tarifa.tipo_cobro === "ia" ? "analisis_ia" : tarifa.tipo_cobro, tipo_cobro: tarifa.tipo_cobro,
        cups: tarifa.codigo, descripcion: tarifa.nombre, cantidad: Number(d.cantidad), valor_unitario: tarifa.valor, valor,
        cobertura, ...reparto,
      });
      onCreada();
    } catch (err) { setError(err.message); }
    finally { setEnviando(false); }
  };

  const entrada = "w-full rounded-2xl bg-cloud-card px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-metric-blue/40";
  return (
    <form onSubmit={enviar} className="anim-pop grid gap-3 rounded-[28px] bg-paper-white p-6 shadow-lift md:grid-cols-2 xl:grid-cols-3">
      <h2 className="text-lg font-semibold md:col-span-2 xl:col-span-3">Nueva factura</h2>
      <label className="text-sm">Paciente (id)<input required value={d.paciente_id} onChange={campo("paciente_id")} className={`${entrada} mt-1`} /></label>
      <label className="text-sm">Nombre (opcional)<input value={d.paciente_nombre} onChange={campo("paciente_nombre")} className={`${entrada} mt-1`} /></label>
      <label className="text-sm">Responsable del pago
        <select value={d.entidad} onChange={campo("entidad")} className={`${entrada} mt-1`}>
          {ENTIDADES.map((x) => <option key={x.entidad} value={x.entidad}>{textoEntidad(x)}</option>)}
        </select>
      </label>
      <label className="text-sm md:col-span-2">Servicio (tarifario)
        <select required value={d.cups} onChange={campo("cups")} className={`${entrada} mt-1`}>
          <option value="">Elige…</option>
          {grupos.map(([tipo, ts]) => (
            <optgroup key={tipo} label={TIPOS_COBRO[tipo] || tipo}>{ts.map((t) => <option key={t.codigo} value={t.codigo}>{t.codigo} · {t.nombre} · {cop(t.valor)}</option>)}</optgroup>
          ))}
        </select>
      </label>
      <label className="text-sm">Cantidad<input type="number" min="1" step="1" value={d.cantidad} onChange={campo("cantidad")} className={`${entrada} mt-1`} /></label>
      <div className="grid grid-cols-3 gap-2 rounded-2xl bg-cloud-card p-4 text-sm md:col-span-2 xl:col-span-3">
        <span>Total<b className="block text-lg tabular-nums">{cop(valor)}</b></span>
        <span>Paga el paciente<b className="block text-lg tabular-nums">{cop(reparto.valor_paciente)}</b></span>
        <span>Paga {cobertura.tipo === "particular" ? "—" : cobertura.entidad}<b className="block text-lg tabular-nums">{cop(reparto.valor_entidad)}</b></span>
      </div>
      {error && <p role="alert" className="text-sm text-coral-ink md:col-span-2 xl:col-span-3">{error}</p>}
      <div className="md:col-span-2 xl:col-span-3">
        <button type="submit" disabled={enviando || !tarifa} className="flex items-center gap-2 rounded-full bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50">
          {enviando && <Loader2 size={15} className="anim-spin" />}Guardar factura
        </button>
      </div>
    </form>
  );
}
