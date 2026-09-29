import { useState } from "react";
import { cerrarSesion, estaAutenticado, getUsuario } from "./api";
import Login from "./pages/Login";
import Pacientes from "./pages/Pacientes";
import PacienteDetalle from "./pages/PacienteDetalle";
import EstadoServicios from "./components/EstadoServicios";

export default function App() {
  const [usuario, setUsuario] = useState(estaAutenticado() ? getUsuario() : null);
  const [pacienteId, setPacienteId] = useState(null);

  if (!usuario) {
    return <Login onEntrar={setUsuario} />;
  }

  function salir() {
    cerrarSesion();
    setUsuario(null);
    setPacienteId(null);
  }

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <strong>Hospital San Rafael</strong>
          <span className="texto-tenue"> · {usuario.username} ({usuario.rol_nombre})</span>
        </div>
        <div className="app-header-derecha">
          <EstadoServicios />
          <button className="boton-salir" onClick={salir}>Salir</button>
        </div>
      </header>

      <main className="app-contenido">
        {pacienteId ? (
          <PacienteDetalle pacienteId={pacienteId} onVolver={() => setPacienteId(null)} />
        ) : (
          <Pacientes onSeleccionar={setPacienteId} />
        )}
      </main>
    </div>
  );
}
