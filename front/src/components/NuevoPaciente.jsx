import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, UserPlus } from "lucide-react";
import Panel from "./Panel";
import { api } from "../api";
import { useAvisos } from "./Avisos";

const VACIO = { tipo_documento: "CC", documento: "", nombre: "", apellido: "", fecha_nacimiento: "",
                sexo: "F", telefono: "", email: "", consentimiento_datos: false };

const HOY = new Date().toISOString().slice(0, 10);
const campo = "w-full rounded-2xl bg-cloud-card px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-metric-blue";
const etiqueta = "mb-1 block text-xs font-medium text-gray-strong";

/**
 * Registrar un paciente (R01: el médico crea pacientes). Al guardarlo queda a
 * cargo de quien lo registró, se publica en FHIR y se abre su ficha.
 */
export default function NuevoPaciente() {
  const [abierto, setAbierto] = useState(false);
  const [f, setF] = useState(VACIO);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);
  const { avisar } = useAvisos();
  const navegar = useNavigate();
  const cambiar = (k) => (e) => setF((v) => ({ ...v, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  const guardar = async (e) => {
    e.preventDefault();
    setError(null);
    if (!f.consentimiento_datos) { setError("Sin la autorización del paciente no se pueden tratar sus datos de salud (Ley 1581)."); return; }
    setEnviando(true);
    try {
      const datos = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ""));
      const p = await api("/pacientes", { method: "POST", json: datos });
      avisar(`Paciente ${p.nombre} ${p.apellido} registrado.`);
      setAbierto(false);
      setF(VACIO);
      navegar(`/app/pacientes/${p.paciente_id}`);
    } catch (err) {
      setError(err.status === 409 ? "Ya existe un paciente con ese documento." : err.message);
    } finally { setEnviando(false); }
  };

  return (
    <>
      <button onClick={() => setAbierto(true)}
              className="flex items-center gap-2 rounded-full bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink">
        <UserPlus size={16} aria-hidden="true" />Nuevo paciente
      </button>
      <Panel abierto={abierto} onCerrar={() => setAbierto(false)} titulo="Nuevo paciente"
             subtitulo="Queda a tu cargo. Los datos personales se guardan cifrados.">
        <form id="form-nuevo-paciente" onSubmit={guardar} className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <label className="col-span-1"><span className={etiqueta}>Tipo</span>
              <select value={f.tipo_documento} onChange={cambiar("tipo_documento")} className={campo}>
                {["CC", "TI", "CE", "PA", "RC"].map((t) => <option key={t}>{t}</option>)}
              </select>
            </label>
            <label className="col-span-2"><span className={etiqueta}>Documento</span>
              <input required inputMode="numeric" value={f.documento} onChange={cambiar("documento")} className={campo} />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label><span className={etiqueta}>Nombre</span>
              <input required value={f.nombre} onChange={cambiar("nombre")} className={campo} /></label>
            <label><span className={etiqueta}>Apellido</span>
              <input required value={f.apellido} onChange={cambiar("apellido")} className={campo} /></label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label><span className={etiqueta}>Fecha de nacimiento</span>
              <input required type="date" max={HOY} value={f.fecha_nacimiento}
                     onChange={cambiar("fecha_nacimiento")} className={campo} /></label>
            <label><span className={etiqueta}>Sexo</span>
              <select value={f.sexo} onChange={cambiar("sexo")} className={campo}>
                <option value="F">Femenino</option><option value="M">Masculino</option><option value="O">Otro</option>
              </select></label>
          </div>
          <label className="block"><span className={etiqueta}>Teléfono (opcional)</span>
            <input type="tel" value={f.telefono} onChange={cambiar("telefono")} className={campo} /></label>
          <label className="block"><span className={etiqueta}>Correo (opcional)</span>
            <input type="email" value={f.email} onChange={cambiar("email")} className={campo} /></label>
          <label className="flex items-start gap-3 rounded-2xl bg-cloud-card p-4 text-sm">
            <input type="checkbox" checked={f.consentimiento_datos} onChange={cambiar("consentimiento_datos")} className="mt-0.5 size-4" />
            <span>El paciente autorizó el tratamiento de sus datos de salud para su atención.</span>
          </label>
          {error && <p role="alert" className="text-sm text-coral-ink">{error}</p>}
          <button type="submit" disabled={enviando}
                  className="flex w-full items-center justify-center gap-2 rounded-full bg-charcoal px-5 py-3 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50">
            {enviando && <Loader2 size={16} className="anim-spin" />}Registrar paciente
          </button>
        </form>
      </Panel>
    </>
  );
}
