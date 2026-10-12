import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { Clock, HeartPulse, LayoutDashboard, LogOut, Receipt, Send, Shield, Users } from "lucide-react";
import Logo from "../../components/Logo";
import EstadoServicios from "../../components/EstadoServicios";
import { ProveedorAvisos } from "../../components/Avisos";
import Campana from "../../components/Campana";
import BannerAlertas from "../../components/BannerAlertas";
import PanelDemostracion from "../../components/PanelDemostracion";
import { cerrarSesion } from "../../api";
import { useUsuario } from "../../lib/hooks";
import { menu } from "../../lib/roles";
import { ProveedorTiempoReal } from "../../lib/tiempoReal";

const ICONOS = { admin: Shield, turno: Clock, remisiones: Send, facturacion: Receipt, salud: HeartPulse, mando: LayoutDashboard, pacientes: Users };

const enlace = ({ isActive }) =>
  `flex shrink-0 items-center gap-2 whitespace-nowrap rounded-full px-4 py-2 text-sm font-medium transition ${isActive ? "bg-charcoal text-white" : "text-ink hover:bg-cloud-card"}`;

export default function Shell() {
  const usuario = useUsuario();
  const navegar = useNavigate();
  const items = menu(usuario);   // cada rol ve solo sus pantallas (lib/roles.js)

  const salir = async () => { await cerrarSesion(); navegar("/login", { replace: true }); };
  const siglas = (usuario?.username || "?").slice(0, 2).toUpperCase();

  return (
    <ProveedorAvisos>
      <ProveedorTiempoReal>
      <a href="#contenido" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[70] focus:rounded-full focus:bg-charcoal focus:px-4 focus:py-2 focus:text-white">Saltar al contenido</a>
      <header className="sticky top-4 z-40 mx-auto w-[min(1280px,calc(100%-2rem))]">
        <nav aria-label="Principal" className="flex items-center justify-between gap-3 rounded-[32px] bg-paper-white/85 py-2.5 pl-4 pr-3 shadow-lift backdrop-blur-xl">
          <Link to="/" aria-label="Ir al inicio" className="shrink-0"><span className="hidden sm:block"><Logo /></span><span className="sm:hidden"><Logo compacto /></span></Link>

          <div className="flex min-w-0 items-center gap-1 overflow-x-auto">
            {items.map(([ruta, texto, icono]) => {
              const Icono = ICONOS[icono];
              return (
                <NavLink key={ruta} to={ruta} className={enlace} title={texto}>
                  <Icono size={16} aria-hidden="true" /><span className="hidden xl:inline">{texto}</span>
                </NavLink>
              );
            })}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <EstadoServicios className="hidden 2xl:flex" />
            <Campana />
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
        <BannerAlertas />
        <Outlet />
      </main>
      <PanelDemostracion />
      </ProveedorTiempoReal>
    </ProveedorAvisos>
  );
}
