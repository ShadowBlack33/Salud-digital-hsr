import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Shell from "./pages/app/Shell";
import Comando from "./pages/app/Comando";
import Pacientes from "./pages/app/Pacientes";
import Ficha from "./pages/app/Ficha";
import { estaAutenticado } from "./api";
import { useUsuario } from "./lib/hooks";

/** Solo deja pasar con sesión iniciada; si no, manda al login y vuelve después. */
function RequiereSesion({ children }) {
  const usuario = useUsuario(); // se re-evalúa al cerrar sesión o si vence la renovación
  const { pathname } = useLocation();
  if (!estaAutenticado() || !usuario) return <Navigate to="/login" replace state={{ desde: pathname }} />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/app" element={<RequiereSesion><Shell /></RequiereSesion>}>
          <Route index element={<Comando />} />
          <Route path="pacientes" element={<Pacientes />} />
          <Route path="pacientes/:id" element={<Ficha />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
