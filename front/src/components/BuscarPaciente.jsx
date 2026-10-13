import { useEffect, useRef, useState } from "react";
import { Loader2, Search, X } from "lucide-react";
import { api } from "../api";
import { edadLegible } from "../lib/format";

/**
 * Elegir un paciente por nombre o documento. Los nombres están cifrados en la
 * base: la API los compara en memoria y devuelve el documento enmascarado.
 * Con solo dígitos busca el documento exacto (índice ciego).
 */
export default function BuscarPaciente({ valor, onElegir, id = "buscar-paciente", etiqueta = "Paciente" }) {
  const [texto, setTexto] = useState("");
  const [lista, setLista] = useState([]);
  const [cargando, setCargando] = useState(false);
  const [abierto, setAbierto] = useState(false);
  const temporizador = useRef(null);

  useEffect(() => {
    clearTimeout(temporizador.current);
    if (valor || texto.trim().length < 3) { setLista([]); return; }
    temporizador.current = setTimeout(() => {
      setCargando(true);
      api(`/pacientes/sugerir?q=${encodeURIComponent(texto.trim())}`)
        .then((l) => { setLista(l); setAbierto(true); }).catch(() => setLista([])).finally(() => setCargando(false));
    }, 300);
    return () => clearTimeout(temporizador.current);
  }, [texto, valor]);

  if (valor) {
    return (
      <div className="text-sm">
        <span className="block">{etiqueta}</span>
        <div className="mt-1 flex items-center justify-between gap-2 rounded-2xl bg-cloud-card px-4 py-2.5">
          <span><b>{valor.nombre}</b> <span className="text-gray-strong">· {valor.tipo_documento} {valor.documento}{valor.fecha_nacimiento ? ` · ${edadLegible(valor.fecha_nacimiento)}` : ""}</span></span>
          <button type="button" onClick={() => { onElegir(null); setTexto(""); }} aria-label="Cambiar paciente" className="rounded-full p-1 hover:bg-paper-white"><X size={15} /></button>
        </div>
      </div>
    );
  }
  return (
    <div className="relative text-sm">
      <label htmlFor={id} className="block">{etiqueta}</label>
      <div className="relative mt-1">
        <Search size={15} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-strong" aria-hidden="true" />
        <input id={id} value={texto} onChange={(e) => setTexto(e.target.value)} onFocus={() => lista.length && setAbierto(true)}
               placeholder="Nombre, apellido o número de documento" autoComplete="off" role="combobox"
               aria-expanded={abierto} aria-controls={`${id}-lista`}
               className="w-full rounded-2xl border border-cloud-card bg-paper-white py-2.5 pl-10 pr-10 text-sm" />
        {cargando && <Loader2 size={15} className="anim-spin absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-strong" />}
      </div>
      {abierto && texto.trim().length >= 3 && !cargando && (
        <ul id={`${id}-lista`} role="listbox" className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-2xl bg-paper-white p-1 shadow-lift">
          {lista.length === 0 ? <li className="px-3 py-2 text-gray-strong">Sin resultados. Prueba con el apellido o el documento completo.</li> :
            lista.map((p) => (
              <li key={p.paciente_id} role="option" aria-selected="false">
                <button type="button" onClick={() => { onElegir(p); setAbierto(false); }}
                        className="w-full rounded-xl px-3 py-2 text-left hover:bg-cloud-card">
                  <b>{p.nombre}</b> <span className="text-gray-strong">· {p.tipo_documento} {p.documento}{p.fecha_nacimiento ? ` · ${edadLegible(p.fecha_nacimiento)}` : ""}</span>
                </button>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
