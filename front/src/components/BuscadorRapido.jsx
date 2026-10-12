import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { CornerDownLeft, Loader2, Search, UserRound } from "lucide-react";
import { api, puede } from "../api";
import { useUsuario } from "../lib/hooks";
import { edadLegible } from "../lib/format";

const soloDigitos = (t) => /^\d{5,}$/.test(t);
const normalizar = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/**
 * Búsqueda rápida de pacientes (Ctrl + K) desde cualquier pantalla.
 * · Un número de documento se busca con el índice ciego: la base nunca descifra la tabla.
 * · Un nombre se filtra sobre la primera página de pacientes ya cargada.
 */
export default function BuscadorRapido() {
  const usuario = useUsuario();
  const navegar = useNavigate();
  const habilitado = puede(usuario, "paciente", "read") && usuario?.rol !== "paciente";
  const [abierto, setAbierto] = useState(false);
  const [texto, setTexto] = useState("");
  const [lista, setLista] = useState(null);
  const [porDocumento, setPorDocumento] = useState({ estado: "inactivo" });
  const [activo, setActivo] = useState(0);
  const entrada = useRef(null);

  useEffect(() => {
    if (!habilitado) return;
    const tecla = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setAbierto((v) => !v); }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [habilitado]);

  useEffect(() => {
    if (!abierto) return;
    setTexto(""); setActivo(0); setPorDocumento({ estado: "inactivo" });
    setTimeout(() => entrada.current?.focus(), 0);
    if (!lista) api("/pacientes?limite=200").then(setLista).catch(() => setLista([]));
  }, [abierto, lista]);

  // Documento exacto: blind index en la API (con una pequeña espera al escribir).
  useEffect(() => {
    const t = texto.trim();
    if (!abierto || !soloDigitos(t)) { setPorDocumento({ estado: "inactivo" }); return; }
    setPorDocumento({ estado: "buscando" });
    const id = setTimeout(() => {
      api(`/pacientes/buscar?documento=${encodeURIComponent(t)}`)
        .then((p) => setPorDocumento({ estado: "listo", paciente: p }))
        .catch(() => setPorDocumento({ estado: "nada" }));
    }, 350);
    return () => clearTimeout(id);
  }, [texto, abierto]);

  const resultados = useMemo(() => {
    const t = normalizar(texto.trim());
    if (porDocumento.paciente) return [porDocumento.paciente];
    if (!t || soloDigitos(t) || !lista) return [];
    return lista.filter((p) => normalizar(`${p.nombre} ${p.apellido}`).includes(t)).slice(0, 8);
  }, [texto, lista, porDocumento]);

  if (!habilitado || !abierto) return null;

  const ir = (p) => { setAbierto(false); navegar(`/app/pacientes/${p.paciente_id}`); };
  const teclas = (e) => {
    if (e.key === "Escape") setAbierto(false);
    else if (e.key === "ArrowDown") { e.preventDefault(); setActivo((i) => Math.min(i + 1, resultados.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActivo((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter" && resultados[activo]) ir(resultados[activo]);
  };

  return createPortal(
    <div className="fixed inset-0 z-[65] flex items-start justify-center px-4 pt-[12vh]">
      <div className="anim-fade absolute inset-0 bg-ink/30 backdrop-blur-[2px]" onClick={() => setAbierto(false)} />
      <div role="dialog" aria-modal="true" aria-label="Buscar paciente" className="anim-pop relative w-full max-w-xl overflow-hidden rounded-[28px] bg-paper-white shadow-drawer">
        <div className="flex items-center gap-3 border-b border-cloud-card px-5 py-4">
          <Search size={18} className="text-gray-strong" aria-hidden="true" />
          <input ref={entrada} value={texto} onChange={(e) => { setTexto(e.target.value); setActivo(0); }} onKeyDown={teclas}
                 placeholder="Nombre o número de documento" aria-label="Buscar paciente" role="combobox" aria-expanded={resultados.length > 0}
                 className="flex-1 bg-transparent text-[16px] outline-none placeholder:text-gray-strong" />
          <kbd className="rounded-md bg-cloud-card px-1.5 py-0.5 font-mono text-[11px] text-gray-strong">Esc</kbd>
        </div>
        <ul role="listbox" className="max-h-[50vh] overflow-y-auto p-2">
          {porDocumento.estado === "buscando" && <li className="flex items-center gap-2 px-3 py-3 text-sm text-gray-strong"><Loader2 size={15} className="anim-spin" />Buscando por documento (índice ciego)…</li>}
          {porDocumento.estado === "nada" && <li className="px-3 py-3 text-sm text-gray-strong">No hay un paciente activo con ese documento.</li>}
          {resultados.map((p, i) => (
            <li key={p.paciente_id} role="option" aria-selected={i === activo}>
              <button onClick={() => ir(p)} onMouseEnter={() => setActivo(i)}
                      className={`flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left transition ${i === activo ? "bg-cloud-card" : ""}`}>
                <span className="grid size-9 place-items-center rounded-full bg-paper-white"><UserRound size={16} aria-hidden="true" /></span>
                <span className="flex-1">
                  <span className="block text-sm font-medium">{p.nombre} {p.apellido}</span>
                  <span className="block text-xs text-gray-strong">{p.tipo_documento} {p.documento} · {edadLegible(p.fecha_nacimiento)}</span>
                </span>
                {i === activo && <CornerDownLeft size={15} className="text-gray-strong" aria-hidden="true" />}
              </button>
            </li>
          ))}
          {!texto && <li className="px-3 py-3 text-sm text-gray-strong">Escribe un nombre, o un documento completo para buscarlo sin descifrar la base.</li>}
          {texto && !soloDigitos(texto.trim()) && resultados.length === 0 && lista && <li className="px-3 py-3 text-sm text-gray-strong">Sin coincidencias entre los primeros {lista.length} pacientes.</li>}
        </ul>
      </div>
    </div>,
    document.body,
  );
}
