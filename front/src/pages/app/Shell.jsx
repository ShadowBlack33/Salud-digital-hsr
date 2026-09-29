import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { LayoutDashboard, LogOut, Users } from "lucide-react";
import Logo from "../../components/Logo";
import EstadoServicios from "../../components/EstadoServicios";
import { ProveedorAvisos } from "../../components/Avisos";
import { cerrarSesion, puede } from "../../api";
import { useUsuario } from "../../lib/hooks";

const enlace = ({ isActive }) =>
  `flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition ${isActive ? "bg-charcoal text-white" : "text-ink hover:bg-cloud-card"}`;

export default function Shell() {
  const usuario = useUsuario();
  const navegar = useNavigate();
  const { pathname } = useLocation();
  const veTablero = puede(usuario, "cama", "read");
  const vePacientes = puede(usuario, "paciente", "read");

  // Quien no ve el tablero (p. ej. el paciente) aterriza en lo que sí puede ver.
  if (pathname === "/app" && !veTablero) {
    if (usuario?.paciente_id) return <Navigate to={`/app/pacientes/${usuario.paciente_id}`} replace />;
    if (vePacientes) return <Navigate to="/app/pacientes" replace />;
  }

  const salir = async () => { await cerrarSesion(); navegar("/login", { replace: true }); };
  const siglas = (usuario?.username || "?").slice(0, 2).toUpperCase();

  return (
    <ProveedorAvisos>
      <a href="#contenido" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[70] focus:rounded-full focus:bg-charcoal focus:px-4 focus:py-2 focus:text-white">Saltar al contenido</a>
      <header className="sticky top-4 z-40 mx-auto w-[min(1280px,calc(100%-2rem))]">
        <nav aria-label="Principal" className="flex items-center justify-between gap-3 rounded-[32px] bg-paper-white/85 py-2.5 pl-4 pr-3 shadow-lift backdrop-blur-xl">
          <Link to="/" aria-label="Ir al inicio"><Logo /></Link>

          <div className="flex items-center gap-1">
            {veTablero && <NavLink to="/app" end className={enlace}><LayoutDashboard size={16} aria-hidden="true" /><span className="hidden sm:inline">Centro de mando</span></NavLink>}
            {vePacientes && <NavLink to="/app/pacientes" className={enlace}><Users size={16} aria-hidden="true" /><span className="hidden sm:inline">Pacientes</span></NavLink>}
          </div>

          <div className="flex items-center gap-3">
            <EstadoServicios className="hidden xl:flex" />
            <div className="flex items-center gap-2.5 rounded-full bg-cloud-card py-1 pl-1 pr-4">
              <span className="grid size-8 place-items-center rounded-full bg-charcoal text-xs font-semibold text-white" aria-hidden="true">{siglas}</span>
              <span className="hidden text-left leading-tight md:block">
                <span className="block text-[13px] font-medium">{usuario?.rol_nombre || usuario?.rol}</span>
                <span className="block text-[11px] text-gray-strong">{usuario?.username}</span>
              </span>
            </div>
            <button onClick={salir} aria-label="Cerrar sesión" title="Cerrar sesión"
                    className="grid size-10 place-items-center rounded-full text-ink transition hover:bg-cloud-card"><LogOut size={18} /></button>
          </div>
        </nav>
      </header>

      <main id="contenido" className="mx-auto w-[min(1280px,calc(100%-2rem))] pt-8">
        <Outlet />
      </main>
    </ProveedorAvisos>
  );
}
