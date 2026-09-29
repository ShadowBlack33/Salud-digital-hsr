import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Search, SearchX } from "lucide-react";
import Insignia from "../../components/Insignia";
import { api, puede } from "../../api";
import { CAMA_CON_PACIENTE, cortoTipo, infoCama } from "../../lib/estados";
import { duracion, enmascarar, minutosDesde } from "../../lib/format";
import { useReloj, useSondeo, useUsuario } from "../../lib/hooks";

const POR_PAGINA = 20;

export default function Pacientes() {
  const usuario = useUsuario();
  const navegar = useNavigate();
  const ahora = useReloj(60000);
  const [documento, setDocumento] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [error, setError] = useState(null);
  const [filtro, setFiltro] = useState("");
  const [mostrar, setMostrar] = useState(POR_PAGINA);
  const veCamas = puede(usuario, "cama", "read");

  const camas = useSondeo(() => (veCamas ? api("/camas/ocupacion?solo_ocupadas=false") : Promise.resolve([])), 30000);

  // Pacientes con una hospitalización en curso en una cama que hoy los tiene.
  const hospitalizados = useMemo(() => (camas.datos || [])
    .filter((c) => c.encuentro_activo && c.encuentro_tipo === "hospitalizacion" && CAMA_CON_PACIENTE.includes(c.estado_cama))
    .sort((a, b) => Date.parse(a.hora_real_inicio) - Date.parse(b.hora_real_inicio)), [camas.datos]);

  const filtrados = useMemo(() => {
    const q = filtro.trim().toLowerCase();
    if (!q) return hospitalizados;
    return hospitalizados.filter((c) => [c.paciente_nombre_corto, c.cama_codigo, c.medico_nombre, c.diagnostico].some((v) => v?.toLowerCase().includes(q)));
  }, [hospitalizados, filtro]);

  async function buscar(e) {
    e.preventDefault();
    const doc = documento.trim();
    if (!/^\d{6,10}$/.test(doc)) { setError("El documento debe tener entre 6 y 10 dígitos."); return; }
    setBuscando(true); setError(null);
    try {
      const p = await api(`/pacientes/buscar?documento=${encodeURIComponent(doc)}`);
      navegar(`/app/pacientes/${p.paciente_id}`);
    } catch (err) {
      setError(err.status === 404 ? "No hay un paciente con ese documento." : err.status === 403 ? "Tu rol no puede consultar pacientes." : err.message);
    } finally { setBuscando(false); }
  }

  return (
    <div className="space-y-6 pb-16">
      <div>
        <h1 className="text-[34px] font-semibold leading-tight tracking-display">Pacientes</h1>
        <p className="mt-1 text-sm text-gray-strong">Busca por número de documento o entra desde la lista de hospitalizados.</p>
      </div>

      <form onSubmit={buscar} className="rounded-[28px] bg-cloud-card p-6 sm:p-7" noValidate>
        <label htmlFor="doc" className="text-sm font-semibold">Buscar por documento</label>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row">
          <input id="doc" value={documento} onChange={(e) => setDocumento(e.target.value.replace(/\D/g, ""))} inputMode="numeric" maxLength={10}
                 placeholder="Cédula, tarjeta de identidad o registro civil" aria-describedby={error ? "doc-error" : undefined} aria-invalid={!!error}
                 className="min-w-0 flex-1 rounded-full bg-paper-white px-5 py-3.5 text-[15px] outline-none placeholder:text-gray-strong focus:ring-2 focus:ring-metric-blue" />
          <button disabled={buscando} className="inline-flex items-center justify-center gap-2 rounded-full bg-charcoal px-7 py-3.5 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-60">
            {buscando ? <Loader2 size={16} className="anim-spin" /> : <Search size={16} />}Buscar
          </button>
        </div>
        {error && <p id="doc-error" role="alert" className="mt-3 text-sm font-medium text-coral-ink">{error}</p>}
        <p className="mt-3 text-xs text-gray-strong">La búsqueda es exacta: el documento se guarda cifrado y se compara sin descifrar la base.</p>
      </form>

      {veCamas && (
        <section aria-labelledby="t-hosp" className="rounded-[28px] bg-cloud-card p-6 sm:p-7">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 id="t-hosp" className="text-2xl font-semibold tracking-display">Hospitalizados ahora</h2>
              <p className="mt-1 text-sm text-gray-strong">{hospitalizados.length} pacientes con una cama asignada</p>
            </div>
            <input value={filtro} onChange={(e) => { setFiltro(e.target.value); setMostrar(POR_PAGINA); }} type="search" aria-label="Filtrar hospitalizados"
                   placeholder="Filtrar por nombre, cama o médico"
                   className="w-full rounded-full bg-paper-white px-5 py-2.5 text-sm outline-none placeholder:text-gray-strong focus:ring-2 focus:ring-metric-blue sm:w-72" />
          </div>

          {camas.cargando && !camas.datos && <p className="mt-6 flex items-center gap-2 text-sm text-gray-strong"><Loader2 size={16} className="anim-spin" />Cargando…</p>}

          {filtrados.length === 0 && camas.datos && (
            <p className="mt-6 flex items-center gap-3 rounded-2xl bg-paper-white p-6 text-sm text-gray-strong">
              <SearchX size={20} aria-hidden="true" />
              {hospitalizados.length === 0
                ? "No hay hospitalizaciones activas registradas. Para llenar el tablero con una jornada de ejemplo, corre scripts/simular_jornada.py."
                : "Ningún paciente coincide con el filtro."}
            </p>
          )}

          {filtrados.length > 0 && (
            <>
              <div className="mt-5 hidden grid-cols-[1.2fr_1fr_1.4fr_1.3fr_.8fr] gap-4 px-4 pb-2 text-xs font-semibold uppercase tracking-wider text-gray-strong lg:grid" aria-hidden="true">
                <span>Paciente</span><span>Cama</span><span>Médico</span><span>Estado</span><span className="text-right">Hospitalizado</span>
              </div>
              <ul className="space-y-2">
                {filtrados.slice(0, mostrar).map((c) => {
                  const info = infoCama(c.estado_cama);
                  return (
                    <li key={c.cama_id}>
                      <button onClick={() => navegar(`/app/pacientes/${c.paciente_id}`)}
                              className="grid w-full grid-cols-2 items-center gap-x-4 gap-y-2 rounded-2xl bg-paper-white p-4 text-left transition hover:shadow-lift lg:grid-cols-[1.2fr_1fr_1.4fr_1.3fr_.8fr]">
                        <span className="min-w-0">
                          <span className="block truncate font-semibold">{c.paciente_nombre_corto}</span>
                          <span className="block text-xs text-gray-strong">{c.paciente_tipo_documento} {enmascarar(c.paciente_documento)}</span>
                        </span>
                        <span>
                          <span className="block font-mono text-sm font-semibold">{c.cama_codigo}</span>
                          <span className="block text-xs text-gray-strong">{cortoTipo(c.tipo_cama)}</span>
                        </span>
                        <span className="col-span-2 min-w-0 lg:col-span-1">
                          <span className="block truncate text-sm">{c.medico_nombre || "—"}</span>
                          <span className="block truncate text-xs text-gray-strong">{c.medico_especialidad}</span>
                        </span>
                        <span><Insignia grupo={info.grupo} etiqueta={info.etiqueta} tamano="sm" /></span>
                        <span className="text-right text-sm tabular-nums text-gray-strong">{duracion(minutosDesde(c.hora_real_inicio, ahora))}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
              {filtrados.length > mostrar && (
                <button onClick={() => setMostrar((m) => m + POR_PAGINA)} className="mx-auto mt-5 block rounded-full bg-paper-white px-6 py-3 text-sm font-semibold transition hover:shadow-lift">
                  Mostrar más ({filtrados.length - mostrar} restantes)
                </button>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
