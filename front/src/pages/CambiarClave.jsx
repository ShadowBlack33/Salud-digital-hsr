import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Check, Circle, Eye, EyeOff, KeyRound, Loader2 } from "lucide-react";
import Logo from "../components/Logo";
import { cambiarPassword } from "../api";
import { useUsuario } from "../lib/hooks";

// La misma política que valida la API (app/core/security.py · validar_fortaleza).
const REGLAS = [
  ["Al menos 12 caracteres", (c) => c.length >= 12],
  ["Una mayúscula", (c) => /\p{Lu}/u.test(c)],
  ["Una minúscula", (c) => /\p{Ll}/u.test(c)],
  ["Un número", (c) => /\d/.test(c)],
  ["Un carácter especial", (c) => /[^\p{L}\p{N}]/u.test(c)],
];

/** Cambio de contraseña. Obligatorio la primera vez que entra un usuario creado por el admin. */
export default function CambiarClave() {
  const usuario = useUsuario();
  const navegar = useNavigate();
  const obligatorio = !!usuario?.debe_cambiar_password;
  const [datos, setDatos] = useState({ actual: "", nueva: "", repetir: "" });
  const [ver, setVer] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);

  const cumple = REGLAS.map(([, f]) => f(datos.nueva));
  const valida = cumple.every(Boolean) && datos.nueva === datos.repetir && datos.nueva !== datos.actual;
  const campo = (k) => (e) => setDatos((d) => ({ ...d, [k]: e.target.value }));

  const enviar = async (e) => {
    e.preventDefault();
    if (!valida) return;
    setEnviando(true); setError(null);
    try {
      await cambiarPassword(datos.actual, datos.nueva);
      navegar("/login", { replace: true, state: { mensaje: "Contraseña actualizada. Entra de nuevo con la nueva." } });
    } catch (err) {
      setError(err.message);
      setEnviando(false);
    }
  };

  const entrada = "w-full rounded-2xl bg-cloud-card px-4 py-3 text-[15px] outline-none transition focus:bg-paper-white focus:ring-2 focus:ring-metric-blue/40";
  return (
    <div className="relative min-h-dvh overflow-hidden bg-gradient-to-b from-hero-sky via-[#e9f1ff] to-paper-white">
      <div className="relative mx-auto flex min-h-dvh w-[min(480px,calc(100%-2rem))] flex-col justify-center py-10">
        {!obligatorio && (
          <Link to="/app" className="mb-5 inline-flex w-fit items-center gap-1.5 rounded-full bg-paper-white/70 px-4 py-2 text-sm font-medium backdrop-blur transition hover:bg-paper-white">
            <ArrowLeft size={15} aria-hidden="true" />Volver
          </Link>
        )}
        <main className="anim-rise rounded-[32px] bg-paper-white p-7 shadow-lift sm:p-9">
          <Logo />
          <h1 className="mt-7 flex items-center gap-2 text-[30px] font-semibold leading-[1.1] tracking-display"><KeyRound size={26} aria-hidden="true" />Cambia tu contraseña</h1>
          <p className="mt-2 text-[15px] text-gray-strong">
            {obligatorio ? "Es tu primer ingreso: la contraseña que te dio el administrador es temporal. Elige una propia para continuar." : "Al cambiarla se cierran tus sesiones abiertas en todos los equipos."}
          </p>

          <form onSubmit={enviar} className="mt-6 space-y-4" noValidate>
            <div>
              <label htmlFor="clave-actual" className="block text-sm font-medium">Contraseña actual</label>
              <input id="clave-actual" type={ver ? "text" : "password"} autoComplete="current-password" required value={datos.actual} onChange={campo("actual")} className={`${entrada} mt-1.5`} />
            </div>
            <div>
              <label htmlFor="clave-nueva" className="block text-sm font-medium">Nueva contraseña</label>
              <div className="relative mt-1.5">
                <input id="clave-nueva" type={ver ? "text" : "password"} autoComplete="new-password" required value={datos.nueva} onChange={campo("nueva")} className={`${entrada} pr-12`} aria-describedby="reglas" />
                <button type="button" onClick={() => setVer((v) => !v)} aria-label={ver ? "Ocultar contraseñas" : "Mostrar contraseñas"}
                        className="absolute right-2 top-1/2 grid size-9 -translate-y-1/2 place-items-center rounded-full text-gray-strong hover:bg-paper-white">
                  {ver ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </div>
            <ul id="reglas" className="grid grid-cols-1 gap-1 text-sm sm:grid-cols-2" aria-label="Requisitos">
              {REGLAS.map(([texto], i) => (
                <li key={texto} className={`flex items-center gap-1.5 ${cumple[i] ? "text-green-ink" : "text-gray-strong"}`}>
                  {cumple[i] ? <Check size={14} aria-hidden="true" /> : <Circle size={12} aria-hidden="true" />}{texto}
                  <span className="sr-only">{cumple[i] ? "cumplido" : "pendiente"}</span>
                </li>
              ))}
            </ul>
            <div>
              <label htmlFor="clave-repetir" className="block text-sm font-medium">Repite la nueva contraseña</label>
              <input id="clave-repetir" type={ver ? "text" : "password"} autoComplete="new-password" required value={datos.repetir} onChange={campo("repetir")} className={`${entrada} mt-1.5`} />
            </div>
            {datos.repetir && datos.nueva !== datos.repetir && <p className="text-sm text-coral-ink">Las contraseñas no coinciden.</p>}
            {datos.nueva && datos.nueva === datos.actual && <p className="text-sm text-coral-ink">La nueva debe ser distinta de la actual.</p>}
            {error && <p role="alert" className="rounded-2xl bg-coral-soft px-4 py-3 text-sm text-coral-ink">{error}</p>}
            <button type="submit" disabled={!valida || enviando}
                    className="flex w-full items-center justify-center gap-2 rounded-full bg-charcoal py-3.5 text-[15px] font-semibold text-white transition hover:bg-ink disabled:opacity-40">
              {enviando && <Loader2 size={17} className="anim-spin" />}Guardar contraseña
            </button>
          </form>
        </main>
      </div>
    </div>
  );
}
