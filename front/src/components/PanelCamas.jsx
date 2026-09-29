import { useMemo, useState } from "react";
import BedCard from "./BedCard";
import { FILTROS_ESTADO, TIPOS_CAMA, infoCama } from "../lib/estados";

/** Matriz de camas: pestañas por tipo, filtros por estado y una tarjeta por cama. */
export default function PanelCamas({ camas, ahora, seleccionadaId, onAbrir }) {
  const [tipo, setTipo] = useState("UCI");
  const [filtro, setFiltro] = useState("todas");

  const delTipo = useMemo(() => camas.filter((c) => tipo === "todos" || c.tipo_cama === tipo), [camas, tipo]);
  const conteo = useMemo(() => {
    const r = { todas: delTipo.length, libre: 0, ocupado: 0, proceso: 0, bloqueado: 0 };
    delTipo.forEach((c) => { r[infoCama(c.estado_cama).grupo]++; });
    return r;
  }, [delTipo]);
  const visibles = useMemo(
    () => delTipo.filter((c) => filtro === "todas" || infoCama(c.estado_cama).grupo === filtro),
    [delTipo, filtro],
  );
  const conteoTipo = (cod) => camas.filter((c) => c.tipo_cama === cod).length;

  return (
    <section aria-labelledby="t-camas" className="rounded-[28px] bg-cloud-card p-6 sm:p-7">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 id="t-camas" className="text-2xl font-semibold tracking-display">Camas</h2>
          <p className="mt-1 text-sm text-gray-strong">Toca una cama para ver quién la ocupa y cambiar su estado.</p>
        </div>
        <div role="tablist" aria-label="Tipo de cama" className="flex flex-wrap gap-1.5 rounded-full bg-paper-white p-1">
          {[{ codigo: "todos", corto: "Todas" }, ...TIPOS_CAMA].map((t) => {
            const on = tipo === t.codigo;
            return (
              <button key={t.codigo} role="tab" aria-selected={on} onClick={() => setTipo(t.codigo)}
                      className={`rounded-full px-3.5 py-1.5 text-[13px] font-medium transition ${on ? "bg-charcoal text-cloud-card" : "text-gray-strong hover:text-ink"}`}>
                {t.corto} <span className={on ? "text-cloud-card/70" : "text-gray-strong/80"}>{t.codigo === "todos" ? camas.length : conteoTipo(t.codigo)}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2" role="group" aria-label="Filtrar por estado">
        {FILTROS_ESTADO.map((f) => {
          const on = filtro === f.clave;
          return (
            <button key={f.clave} aria-pressed={on} onClick={() => setFiltro(f.clave)}
                    className={`rounded-full border px-3.5 py-1.5 text-[13px] font-medium transition ${on ? "border-charcoal bg-charcoal text-cloud-card" : "border-transparent bg-paper-white text-ink hover:border-body-gray/40"}`}>
              {f.etiqueta} <span className={on ? "text-cloud-card/70" : "text-gray-strong"}>{conteo[f.clave]}</span>
            </button>
          );
        })}
      </div>

      {visibles.length === 0 ? (
        <p className="mt-8 rounded-2xl bg-paper-white p-8 text-center text-sm text-gray-strong">No hay camas con ese filtro.</p>
      ) : (
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
          {visibles.map((c) => (
            <BedCard key={c.cama_id} cama={c} ahora={ahora} seleccionada={seleccionadaId === c.cama_id} onAbrir={onAbrir} />
          ))}
        </div>
      )}
    </section>
  );
}
