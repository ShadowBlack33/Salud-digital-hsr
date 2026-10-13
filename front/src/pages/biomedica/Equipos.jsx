import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, RotateCcw, Wrench } from "lucide-react";
import Encabezado from "../../components/Encabezado";
import Esqueleto from "../../components/Esqueleto";
import { useAvisos } from "../../components/Avisos";
import { api } from "../../api";
import { cop, haceCuanto } from "../../lib/format";

/**
 * Ingeniería biomédica: cuando un equipo falla o entra a mantenimiento, la cama
 * o el quirófano donde está sale de servicio. Al repararlo vuelve "en limpieza"
 * y enfermería lo habilita. Es lo único que este perfil cambia; no ve pacientes.
 */
const TIPOS = [["falla", "Falla"], ["mantenimiento_correctivo", "Mantenimiento correctivo"], ["mantenimiento_preventivo", "Mantenimiento preventivo"]];
const EQUIPOS = ["Ventilador", "Monitor de signos vitales", "Bomba de infusión", "Máquina de anestesia", "Arco en C",
                 "Lámpara cielítica", "Mesa quirúrgica", "Electrobisturí", "Desfibrilador", "Cama eléctrica"];
const CON_PACIENTE = ["ocupada", "reservada", "en_proceso_alta", "en_cirugia"];
const entrada = "mt-1 w-full rounded-2xl border border-cloud-card bg-paper-white px-4 py-2.5 text-sm";

export default function Equipos() {
  const { avisar } = useAvisos();
  const [estado, setEstado] = useState({ cargando: true, lista: [], error: null });
  const [recursos, setRecursos] = useState({ cama: [], quirofano: [] });
  const [form, setForm] = useState({ recurso_tipo: "quirofano", recurso_id: "", equipo: "", tipo: "falla", descripcion: "" });
  const [enviando, setEnviando] = useState(false);
  const [devolviendo, setDevolviendo] = useState({ id: null, nota: "" });

  const cargar = useCallback(async () => {
    try {
      const [fs, camas, qx] = await Promise.all([api("/biomedica/fuera-servicio"), api("/camas?limite=400"), api("/quirofanos")]);
      setEstado({ cargando: false, lista: fs.fuera_servicio, error: null });
      setRecursos({ cama: camas, quirofano: qx });
    } catch (e) { setEstado((s) => ({ ...s, cargando: false, error: e })); }
  }, []);
  useEffect(() => { cargar(); }, [cargar]);

  const abiertas = estado.lista.filter((f) => f.abierta);
  const cerradas = estado.lista.filter((f) => !f.abierta);
  const ocupados = useMemo(() => new Set(abiertas.map((f) => `${f.recurso_tipo}-${f.recurso_id}`)), [abiertas]);
  const opciones = recursos[form.recurso_tipo].filter((r) => !ocupados.has(`${form.recurso_tipo}-${r.id}`));

  const sacar = async (e) => {
    e.preventDefault();
    setEnviando(true);
    try {
      const r = await api("/biomedica/fuera-servicio", { method: "POST", json: { ...form, recurso_id: Number(form.recurso_id) } });
      avisar(`${r.recurso} quedó fuera de servicio`);
      setForm((f) => ({ ...f, recurso_id: "", equipo: "", descripcion: "" }));
      await cargar();
    } catch (err) { avisar(err.message, "error"); }
    finally { setEnviando(false); }
  };
  const devolver = async (f) => {
    setEnviando(true);
    try {
      const r = await api(`/biomedica/fuera-servicio/${f.id}/devolver`, { method: "POST", json: { nota: devolviendo.nota || null } });
      avisar(`${r.recurso} vuelve a servicio: queda en limpieza para que enfermería lo habilite`);
      setDevolviendo({ id: null, nota: "" });
      await cargar();
    } catch (err) { avisar(err.message, "error"); await cargar(); }
    finally { setEnviando(false); }
  };

  return (
    <div className="space-y-8 pb-16">
      <Encabezado titulo="Equipos fuera de servicio"
                  subtitulo="Cuando un equipo falla o entra a mantenimiento, la cama o el quirófano donde está sale de servicio. Al repararlo vuelve en limpieza y enfermería lo habilita." />

      {estado.error && <p role="alert" className="rounded-3xl bg-coral-soft p-5 text-sm text-coral-ink">{estado.error.message}</p>}

      <section aria-labelledby="t-abiertas" className="rounded-[32px] bg-cloud-card p-6">
        <h2 id="t-abiertas" className="text-lg font-semibold">Fuera de servicio ahora {abiertas.length > 0 && <span className="text-gray-strong">({abiertas.length})</span>}</h2>
        {estado.cargando ? <Esqueleto filas={2} alto="h-16" /> : abiertas.length === 0 ? (
          <p className="mt-3 text-sm text-gray-strong">Ninguna cama ni quirófano está fuera de servicio por equipos.</p>
        ) : (
          <ul className="mt-4 grid gap-3 md:grid-cols-2">
            {abiertas.map((f) => (
              <li key={f.id} className="flex flex-col rounded-3xl bg-paper-white p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-lg font-semibold">{f.recurso_codigo} <span className="text-sm font-normal text-gray-strong">· {f.recurso_detalle}{f.servicio ? ` · ${f.servicio}` : ""}</span></p>
                    <p className="text-sm font-medium text-coral-ink">{f.tipo_texto} · {f.equipo}</p>
                  </div>
                  <span className="shrink-0 rounded-full bg-coral-soft px-3 py-1 text-xs font-semibold text-coral-ink">{f.horas} h</span>
                </div>
                <p className="mt-2 flex-1 text-sm text-gray-strong">{f.descripcion}</p>
                <p className="mt-2 text-xs text-gray-strong">Reportó {f.reportado_por_usuario} {haceCuanto(f.inicio)}{f.costo_estimado_cop ? ` · costo de oportunidad aprox. ${cop(f.costo_estimado_cop)}` : ""}</p>
                {devolviendo.id === f.id ? (
                  <div className="mt-3 space-y-2">
                    <label htmlFor={`nota-${f.id}`} className="text-xs font-medium">Qué se hizo (opcional)</label>
                    <input id={`nota-${f.id}`} value={devolviendo.nota} onChange={(e) => setDevolviendo({ id: f.id, nota: e.target.value })} className={entrada} placeholder="p. ej. se cambió el sensor de flujo" />
                    <div className="flex justify-end gap-2">
                      <button onClick={() => setDevolviendo({ id: null, nota: "" })} className="rounded-full px-3 py-2 text-sm">Cancelar</button>
                      <button onClick={() => devolver(f)} disabled={enviando} className="flex items-center gap-1.5 rounded-full bg-charcoal px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                        {enviando ? <Loader2 size={15} className="anim-spin" /> : <RotateCcw size={15} />}Confirmar
                      </button>
                    </div>
                  </div>
                ) : (
                  <button onClick={() => setDevolviendo({ id: f.id, nota: "" })} className="mt-3 w-fit rounded-full bg-charcoal px-4 py-2 text-sm font-semibold text-white">Devolver a servicio</button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="t-sacar" className="rounded-[32px] bg-paper-white p-6 shadow-lift">
        <h2 id="t-sacar" className="flex items-center gap-2 text-lg font-semibold"><Wrench size={18} aria-hidden="true" />Sacar de servicio por un equipo</h2>
        <form onSubmit={sacar} className="mt-4 grid gap-4 md:grid-cols-2">
          <fieldset className="text-sm font-medium md:col-span-2">
            <legend>Dónde está el equipo</legend>
            <div className="mt-1 flex gap-2">
              {[["quirofano", "Quirófano"], ["cama", "Cama"]].map(([v, t]) => (
                <label key={v} className={`cursor-pointer rounded-full px-4 py-2 ${form.recurso_tipo === v ? "bg-charcoal text-white" : "bg-cloud-card"}`}>
                  <input type="radio" name="recurso_tipo" value={v} checked={form.recurso_tipo === v} className="sr-only"
                         onChange={() => setForm((f) => ({ ...f, recurso_tipo: v, recurso_id: "" }))} />{t}
                </label>
              ))}
            </div>
          </fieldset>
          <label className="text-sm font-medium" htmlFor="recurso">{form.recurso_tipo === "cama" ? "Cama" : "Quirófano"}
            <select id="recurso" required value={form.recurso_id} onChange={(e) => setForm((f) => ({ ...f, recurso_id: e.target.value }))} className={entrada}>
              <option value="" disabled>Elige uno</option>
              {opciones.map((r) => (
                <option key={r.id} value={r.id} disabled={CON_PACIENTE.includes(r.estado)}>
                  {r.codigo}{r.tipo ? ` · ${r.tipo}` : r.nombre ? ` · ${r.nombre}` : ""} — {r.estado.replaceAll("_", " ")}{CON_PACIENTE.includes(r.estado) ? " (con paciente)" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-medium" htmlFor="equipo">Equipo
            <input id="equipo" required minLength={3} list="equipos" value={form.equipo} onChange={(e) => setForm((f) => ({ ...f, equipo: e.target.value }))} className={entrada} placeholder="p. ej. Ventilador" />
            <datalist id="equipos">{EQUIPOS.map((e) => <option key={e} value={e} />)}</datalist>
          </label>
          <label className="text-sm font-medium" htmlFor="tipo">Tipo
            <select id="tipo" value={form.tipo} onChange={(e) => setForm((f) => ({ ...f, tipo: e.target.value }))} className={entrada}>
              {TIPOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
            </select>
          </label>
          <label className="text-sm font-medium md:col-span-2" htmlFor="descripcion">Qué pasó
            <textarea id="descripcion" required minLength={5} rows={2} value={form.descripcion} onChange={(e) => setForm((f) => ({ ...f, descripcion: e.target.value }))} className={entrada} placeholder="p. ej. alarma de presión no se silencia; sensor de flujo dañado" />
          </label>
          <p className="text-xs text-gray-strong md:col-span-1">Una cama o quirófano con paciente no se puede sacar de servicio: primero enfermería coordina el traslado.</p>
          <button type="submit" disabled={enviando} className="flex items-center justify-center gap-2 rounded-full bg-coral-deep px-5 py-3 text-sm font-semibold text-white disabled:opacity-50 md:justify-self-end">
            {enviando && <Loader2 size={15} className="anim-spin" />}Sacar de servicio
          </button>
        </form>
      </section>

      {cerradas.length > 0 && (
        <section aria-labelledby="t-hist" className="rounded-[28px] bg-cloud-card p-6">
          <h2 id="t-hist" className="text-lg font-semibold">Últimos 30 días</h2>
          <ul className="mt-2 divide-y divide-paper-white text-sm">
            {cerradas.map((f) => (
              <li key={f.id} className="flex flex-wrap justify-between gap-2 py-3">
                <span><b>{f.recurso_codigo}</b> · {f.tipo_texto} · {f.equipo}{f.nota_cierre ? ` — ${f.nota_cierre}` : ""}</span>
                <span className="text-gray-strong">{f.horas} h fuera de servicio</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
