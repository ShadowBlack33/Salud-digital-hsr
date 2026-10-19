import { useEffect, useState } from "react";
import { Loader2, Pencil, UserRound } from "lucide-react";
import Panel from "./Panel";
import { useAvisos } from "./Avisos";
import * as S from "../lib/servicios";

const campo = "w-full rounded-2xl bg-cloud-card px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-metric-blue";
const etiqueta = "mb-1 block text-xs font-medium text-gray-strong";
const CONTACTO = [["telefono", "Teléfono"], ["email", "Correo"], ["direccion", "Dirección"]];

/**
 * Mis datos (portal del paciente). Ley 1581 de 2012: el titular puede conocer y
 * actualizar sus datos cuando quiera. Edita su contacto; los datos de identidad
 * se corrigen en admisiones. Cada cambio queda en el historial y la auditoría.
 */
export default function MisDatos() {
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  const [abierto, setAbierto] = useState(false);
  const [f, setF] = useState({ telefono: "", email: "", direccion: "" });
  const [enviando, setEnviando] = useState(false);
  const [errorForm, setErrorForm] = useState(null);
  const { avisar } = useAvisos();

  useEffect(() => { S.misDatos().then(setD).catch(setError); }, []);

  const abrir = () => {
    setF({ telefono: d?.telefono ?? "", email: d?.email ?? "", direccion: d?.direccion ?? "" });
    setErrorForm(null);
    setAbierto(true);
  };
  const cambiar = (k) => (e) => setF((v) => ({ ...v, [k]: e.target.value }));

  const guardar = async (e) => {
    e.preventDefault();
    setErrorForm(null);
    const datos = Object.fromEntries(Object.entries(f)
      .map(([k, v]) => [k, v.trim()])
      .filter(([k, v]) => v !== "" && v !== (d?.[k] ?? "")));
    if (Object.keys(datos).length === 0) { setErrorForm("No cambiaste ningún dato."); return; }
    setEnviando(true);
    try {
      setD(await S.actualizarMisDatos(datos));
      avisar("Tus datos quedaron actualizados.");
      setAbierto(false);
    } catch (err) {
      setErrorForm(err.status === 422 ? "Revisa el formato: teléfono de 7 a 15 dígitos y un correo válido." : err.message);
    } finally { setEnviando(false); }
  };

  if (error) return null;
  return (
    <section aria-labelledby="t-datos" className="rounded-[28px] bg-paper-white p-6 shadow-lift">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="t-datos" className="flex items-center gap-2 text-lg font-semibold"><UserRound size={18} className="text-metric-blue" aria-hidden="true" />Mis datos</h2>
        <button onClick={abrir} disabled={!d}
                className="flex items-center gap-2 rounded-full bg-charcoal px-4 py-2 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50">
          <Pencil size={14} aria-hidden="true" />Actualizar mis datos
        </button>
      </div>
      {d && (
        <dl className="mt-4 grid gap-2 sm:grid-cols-2">
          <div className="rounded-2xl bg-cloud-card px-4 py-3"><dt className="text-xs text-gray-strong">Nombre</dt><dd className="font-medium">{d.nombre} {d.apellido}</dd></div>
          <div className="rounded-2xl bg-cloud-card px-4 py-3"><dt className="text-xs text-gray-strong">Documento</dt><dd className="font-medium tabular-nums">{d.tipo_documento} {d.documento}</dd></div>
          {CONTACTO.map(([k, t]) => (
            <div key={k} className="rounded-2xl bg-cloud-card px-4 py-3"><dt className="text-xs text-gray-strong">{t}</dt><dd className="break-words font-medium">{d[k] || "Sin registrar"}</dd></div>
          ))}
        </dl>
      )}
      <p className="mt-3 text-xs text-gray-strong">Puedes actualizar tu contacto cuando quieras. Para corregir tu nombre o documento, acércate a admisiones con tu documento de identidad.</p>

      <Panel abierto={abierto} onCerrar={() => setAbierto(false)} titulo="Actualizar mis datos"
             subtitulo="Solo cambia lo que escribas; lo demás queda igual.">
        <form onSubmit={guardar} className="space-y-4">
          <label className="block"><span className={etiqueta}>Teléfono</span>
            <input inputMode="tel" value={f.telefono} onChange={cambiar("telefono")} className={campo} /></label>
          <label className="block"><span className={etiqueta}>Correo</span>
            <input type="email" value={f.email} onChange={cambiar("email")} className={campo} /></label>
          <label className="block"><span className={etiqueta}>Dirección</span>
            <input value={f.direccion} onChange={cambiar("direccion")} className={campo} /></label>
          {errorForm && <p role="alert" className="text-sm text-coral-ink">{errorForm}</p>}
          <button type="submit" disabled={enviando}
                  className="flex w-full items-center justify-center gap-2 rounded-full bg-charcoal px-5 py-3 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50">
            {enviando && <Loader2 size={16} className="anim-spin" />}Guardar cambios
          </button>
        </form>
      </Panel>
    </section>
  );
}
