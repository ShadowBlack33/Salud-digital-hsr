import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import Esqueleto from "./components/Esqueleto";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Shell from "./pages/app/Shell";
import Inicio from "./pages/app/Inicio";
import NoEncontrado from "./pages/app/NoEncontrado";
import Permitido from "./components/Permitido";
import ErrorEstado from "./components/ErrorEstado";
import { esAdmin, esClinico, esContable, esCoordinador, esEspecialista, esMedico, esPaciente, programaCirugias } from "./lib/roles";
import { estaAutenticado, puede } from "./api";
import { useUsuario } from "./lib/hooks";

// Cada pantalla se descarga solo cuando se abre: el paciente en el celular no
// baja el código del panel de admin ni del centro de mando.
const CambiarClave = lazy(() => import("./pages/CambiarClave"));
const Comando = lazy(() => import("./pages/app/Comando"));
const Pacientes = lazy(() => import("./pages/app/Pacientes"));
const Ficha = lazy(() => import("./pages/app/Ficha"));
const MiTurno = lazy(() => import("./pages/medico/MiTurno"));
const Remisiones = lazy(() => import("./pages/especialista/Remisiones"));
const Facturacion = lazy(() => import("./pages/contable/Facturacion"));
const AdminPanel = lazy(() => import("./pages/admin/AdminPanel"));
const MiSalud = lazy(() => import("./pages/paciente/MiSalud"));
const MisPacientes = lazy(() => import("./pages/clinico/MisPacientes"));
const MisCirugias = lazy(() => import("./pages/especialista/MisCirugias"));
const Cirugias = lazy(() => import("./pages/cirugias/CoordinacionQuirurgica"));
const Hospital = lazy(() => import("./pages/coordinador/Hospital"));

/** Solo deja pasar con sesión iniciada; si no, manda al login y vuelve después. */
function RequiereSesion({ children }) {
  const usuario = useUsuario(); // se re-evalúa al cerrar sesión o si vence la renovación
  const { pathname } = useLocation();
  if (!estaAutenticado() || !usuario) return <Navigate to="/login" replace state={{ desde: pathname }} />;
  return children;
}

/** Un médico o especialista no busca en todo el hospital: va a "Mis pacientes". */
function PacientesSegunPerfil() {
  const usuario = useUsuario();
  return esClinico(usuario) ? <Navigate to="/app/mis-pacientes" replace /> : <Pacientes />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<div className="mx-auto w-[min(1280px,calc(100%-2rem))] pt-32"><Esqueleto filas={4} alto="h-16" /></div>}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/cambiar-clave" element={<RequiereSesion><CambiarClave /></RequiereSesion>} />
        <Route path="/app" element={<RequiereSesion><Shell /></RequiereSesion>}>
          <Route index element={<Inicio />} />
          <Route path="mando" element={<Permitido si={(u) => puede(u, "cama", "read") && !esCoordinador(u)}><Comando /></Permitido>} />
          <Route path="hospital" element={<Permitido si={(u) => esCoordinador(u) || esAdmin(u)}><Hospital /></Permitido>} />
          <Route path="cirugias" element={<Permitido si={programaCirugias}><Cirugias /></Permitido>} />
          <Route path="mis-pacientes" element={<Permitido si={esClinico}><MisPacientes /></Permitido>} />
          <Route path="mis-cirugias" element={<Permitido si={(u) => esEspecialista(u) || esMedico(u)}><MisCirugias /></Permitido>} />
          <Route path="turno" element={<Permitido si={esMedico}><MiTurno /></Permitido>} />
          <Route path="remisiones" element={<Permitido si={esClinico}><Remisiones /></Permitido>} />
          <Route path="facturacion" element={<Permitido si={(u) => esContable(u) || esAdmin(u)}><Facturacion /></Permitido>} />
          <Route path="admin" element={<Permitido si={esAdmin}><AdminPanel /></Permitido>} />
          <Route path="mi-salud" element={<Permitido si={esPaciente}><MiSalud /></Permitido>} />
          <Route path="sin-pantalla" element={<ErrorEstado status={403} titulo="Tu rol aún no tiene pantallas" detalle="Tu cuenta está activa, pero este rol no tiene vistas en el sistema todavía. Habla con el administrador." accion={false} />} />
          <Route path="*" element={<NoEncontrado />} />
          <Route path="pacientes" element={<Permitido si={(u) => puede(u, "paciente", "read") && !esPaciente(u)}>{<PacientesSegunPerfil />}</Permitido>} />
          <Route path="pacientes/:id" element={<Ficha />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
