import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { AlertTriangle, ArrowLeft, Eye, EyeOff, Loader2, LockKeyhole, WifiOff } from "lucide-react";
import Logo from "../components/Logo";
import EstadoServicios from "../components/EstadoServicios";
import { estaAutenticado, login } from "../api";
import { horaConSegundos } from "../lib/format";

const CUENTAS = [
  { usuario: "admin", rol: "Administrador", detalle: "Acceso completo" },
  { usuario: "coordinador", rol: "Coordinación quirúrgica", detalle: "Camas y quirófanos" },
  { usuario: "enfe0082", rol: "Jefe de enfermería", detalle: "Tablero de camas" },
  { usuario: "medi0001", rol: "Médico especialista", detalle: "Pacientes e imágenes" },
  { usuario: "paciente_demo", rol: "Paciente", detalle: "Solo su propia ficha" },
];
const CLAVE_DEMO = import.meta.env.VITE_DEMO_PASSWORD || "";
const OCULTAR_CUENTAS = import.meta.env.VITE_OCULTAR_CUENTAS_DEMO === "true";

/** Hora hasta la que sigue bloqueada la cuenta: el servidor nuevo la manda como
 *  campo; uno anterior la trae solo dentro del mensaje. */
function leerBloqueo(e) {
  const iso = e.data?.bloqueado_hasta || e.message.match(/\d{4}-\d{2}-\d{2}T[\d:.]+[+-]\d{2}:\d{2}/)?.[0];
  const t = iso ? Date.parse(iso) : NaN;
  return Number.isNaN(t) ? Date.now() + 15 * 60000 : t;
}

function CuentaRegresiva({ hasta, onTermina }) {
  const [ahora, setAhora] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setAhora(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const falta = Math.max(0, hasta - ahora);
  useEffect(() => { if (falta === 0) onTermina(); }, [falta, onTermina]);
  const m = Math.floor(falta / 60000), s = Math.floor((falta % 60000) / 1000);
  return <span className="text-3xl font-semibold tabular-nums" role="timer" aria-label={`${m} minutos y ${s} segundos`}>{String(m).padStart(2, "0")}:{String(s).padStart(2, "0")}</span>;
}

function Intentos({ restantes, max }) {
  return (
    <div className="flex items-center gap-2" aria-hidden="true">
      {Array.from({ length: max }, (_, i) => (
        <span key={i} className={`h-1.5 flex-1 rounded-full transition-colors duration-500 ${i < max - restantes ? "bg-coral-deep" : "bg-cloud-card"}`} />
      ))}
    </div>
  );
}

export default function Login() {
  const navegar = useNavigate();
  const { state } = useLocation();
  const [usuario, setUsuario] = useState("");
  const [clave, setClave] = useState("");
  const [ver, setVer] = useState(false);
  const [cargando, setCargando] = useState(false);
  const [fallo, setFallo] = useState(null);
  const [sacudiendo, setSacudiendo] = useState(false);
  const campoClave = useRef(null);

  if (estaAutenticado()) return <Navigate to={state?.desde || "/app"} replace />;

  const bloqueado = fallo?.tipo === "bloqueo";

  async function enviar(e) {
    e.preventDefault();
    if (bloqueado || cargando) return;
    setCargando(true); setFallo(null);
    try {
      await login(usuario.trim(), clave);
      navegar(state?.desde || "/app", { replace: true });
    } catch (err) {
      if (err.status === 423) setFallo({ tipo: "bloqueo", hasta: leerBloqueo(err) });
      else if (err.status === 401) { setFallo({ tipo: "credenciales", restantes: err.data?.intentos_restantes, max: err.data?.max_intentos ?? 3 }); setSacudiendo(true); setTimeout(() => setSacudiendo(false), 500); }
      else if (err.status === 0) setFallo({ tipo: "red" });
      else setFallo({ tipo: "otro", mensaje: err.message });
      setClave("");
      campoClave.current?.focus();
    } finally { setCargando(false); }
  }

  function elegir(c) {
    setUsuario(c.usuario); setClave(CLAVE_DEMO); setFallo(null);
    campoClave.current?.focus();
  }

  const conContador = fallo?.tipo === "credenciales" && typeof fallo.restantes === "number";
  const ultimo = conContador && fallo.restantes === 1;

  return (
    <div className="relative min-h-dvh overflow-hidden bg-gradient-to-b from-hero-sky via-[#e9f1ff] to-paper-white">
      <div aria-hidden="true" className="anim-drift pointer-events-none absolute -left-32 top-10 size-[420px] rounded-full bg-sleep-lilac/25 blur-3xl" />
      <div aria-hidden="true" className="anim-drift pointer-events-none absolute -right-24 top-64 size-[380px] rounded-full bg-metric-blue/15 blur-3xl [animation-delay:-6s]" />

      <div className="relative mx-auto flex min-h-dvh w-[min(480px,calc(100%-2rem))] flex-col justify-center py-10">
        <Link to="/" className="mb-5 inline-flex w-fit items-center gap-1.5 rounded-full bg-paper-white/70 px-4 py-2 text-sm font-medium backdrop-blur transition hover:bg-paper-white">
          <ArrowLeft size={15} aria-hidden="true" />Volver al inicio
        </Link>

        <main className="anim-rise rounded-[32px] bg-paper-white p-7 shadow-lift sm:p-9">
          <div className={sacudiendo ? "anim-shake" : ""}>
          <Logo />
          <h1 className="mt-7 text-[32px] font-semibold leading-[1.1] tracking-display">Ingresa al centro de mando</h1>
          <p className="mt-2 text-[15px] text-gray-strong">Usa tu usuario institucional. Cada acceso queda en la auditoría.</p>

          {bloqueado && (
            <div role="alert" className="anim-pop mt-6 rounded-3xl bg-coral-soft p-5 text-coral-ink">
              <p className="flex items-center gap-2 font-semibold"><LockKeyhole size={18} aria-hidden="true" />Cuenta bloqueada temporalmente</p>
              <p className="mt-1 text-sm">Fallaste 3 veces seguidas. Por seguridad, podrás volver a intentar a las {horaConSegundos(fallo.hasta)}</p>
              <p className="mt-3 flex items-center gap-3 text-ink"><CuentaRegresiva hasta={fallo.hasta} onTermina={() => setFallo(null)} /><span className="text-sm text-coral-ink">para desbloquearse</span></p>
            </div>
          )}

          <form onSubmit={enviar} className="mt-6 space-y-4" noValidate>
            <div>
              <label htmlFor="usuario" className="mb-1.5 block text-sm font-medium">Usuario</label>
              <input id="usuario" value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="username" autoCapitalize="none" spellCheck={false}
                     disabled={bloqueado} required
                     className="w-full rounded-2xl bg-cloud-card px-4 py-3.5 text-[15px] outline-none transition placeholder:text-gray-strong focus:ring-2 focus:ring-metric-blue disabled:opacity-50" placeholder="p. ej. coordinador" />
            </div>
            <div>
              <label htmlFor="clave" className="mb-1.5 block text-sm font-medium">Contraseña</label>
              <div className="relative">
                <input id="clave" ref={campoClave} type={ver ? "text" : "password"} value={clave} onChange={(e) => setClave(e.target.value)} autoComplete="current-password"
                       disabled={bloqueado} required aria-describedby={fallo && !bloqueado ? "aviso-login" : undefined}
                       className="w-full rounded-2xl bg-cloud-card py-3.5 pl-4 pr-12 text-[15px] outline-none transition focus:ring-2 focus:ring-metric-blue disabled:opacity-50" />
                <button type="button" onClick={() => setVer((v) => !v)} aria-label={ver ? "Ocultar contraseña" : "Mostrar contraseña"} aria-pressed={ver}
                        className="absolute right-2 top-1/2 grid size-9 -translate-y-1/2 place-items-center rounded-full text-gray-strong transition hover:bg-paper-white hover:text-ink">
                  {ver ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            {fallo && !bloqueado && (
              <div id="aviso-login" role="alert" className={`anim-pop rounded-2xl p-4 text-sm ${ultimo ? "bg-coral-soft text-coral-ink" : fallo.tipo === "credenciales" ? "bg-gold-soft text-gold-ink" : "bg-coral-soft text-coral-ink"}`}>
                <p className="flex items-start gap-2 font-medium">
                  {fallo.tipo === "red" ? <WifiOff size={17} className="mt-0.5 shrink-0" aria-hidden="true" /> : <AlertTriangle size={17} className="mt-0.5 shrink-0" aria-hidden="true" />}
                  {fallo.tipo === "credenciales" && (conContador
                    ? (ultimo ? "Contraseña incorrecta. Te queda 1 intento antes del bloqueo temporal." : `Usuario o contraseña incorrectos. Te quedan ${fallo.restantes} intentos.`)
                    : "Usuario o contraseña incorrectos.")}
                  {fallo.tipo === "red" && "No se pudo conectar con el servidor. Revisa que la API esté encendida."}
                  {fallo.tipo === "otro" && fallo.mensaje}
                </p>
                {conContador && <div className="mt-3"><Intentos restantes={fallo.restantes} max={fallo.max} /></div>}
              </div>
            )}

            <button type="submit" disabled={cargando || bloqueado || !usuario || !clave}
                    className="flex w-full items-center justify-center gap-2 rounded-full bg-charcoal px-6 py-4 text-[15px] font-semibold text-white transition hover:bg-ink disabled:cursor-not-allowed disabled:opacity-50">
              {cargando && <Loader2 size={17} className="anim-spin" aria-hidden="true" />}{cargando ? "Verificando…" : "Ingresar"}
            </button>
          </form>
          </div>
        </main>

        {!OCULTAR_CUENTAS && (
          <section aria-labelledby="t-demo" className="mt-4 rounded-[28px] bg-paper-white/70 p-5 backdrop-blur">
            <h2 id="t-demo" className="text-sm font-semibold">Cuentas de demostración</h2>
            <p className="mt-0.5 text-xs text-gray-strong">
              {CLAVE_DEMO ? "Toca una para llenar el formulario y pulsa Ingresar." : "Toca una para llenar el usuario; la contraseña es la de la demostración."}
            </p>
            <ul className="mt-3 flex flex-wrap gap-2">
              {CUENTAS.map((c) => (
                <li key={c.usuario}>
                  <button type="button" onClick={() => elegir(c)} disabled={bloqueado} title={c.detalle}
                          className={`rounded-full px-3.5 py-2 text-left text-xs font-medium transition disabled:opacity-50 ${usuario === c.usuario ? "bg-charcoal text-white" : "bg-cloud-card hover:bg-hero-sky"}`}>
                    <span className="block font-semibold">{c.rol}</span>
                    <span className={`block font-mono text-[11px] ${usuario === c.usuario ? "text-cloud-card/70" : "text-gray-strong"}`}>{c.usuario}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <EstadoServicios className="mt-6 justify-center" />
      </div>
    </div>
  );
}
