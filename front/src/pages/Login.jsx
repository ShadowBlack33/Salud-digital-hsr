import { useState } from "react";
import { login } from "../api";
import EstadoServicios from "../components/EstadoServicios";

export default function Login({ onEntrar }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mensaje, setMensaje] = useState(null);
  const [tipoMensaje, setTipoMensaje] = useState("error"); // "error" | "bloqueo"
  const [cargando, setCargando] = useState(false);

  async function manejarEnvio(e) {
    e.preventDefault();
    setMensaje(null);
    setCargando(true);
    try {
      const usuario = await login(username, password);
      onEntrar(usuario);
    } catch (err) {
      if (err.status === 423) {
        // Cuenta bloqueada tras 3 intentos fallidos. El backend manda la
        // fecha en ISO dentro del mensaje; la reformateamos a algo legible.
        setTipoMensaje("bloqueo");
        const coincide = err.message.match(/\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:\d{2})?/);
        if (coincide) {
          const hora = new Date(coincide[0]).toLocaleTimeString("es-CO", {
            hour: "2-digit", minute: "2-digit",
          });
          setMensaje(`Cuenta bloqueada por 3 intentos fallidos. Intenta de nuevo después de las ${hora}.`);
        } else {
          setMensaje(err.message);
        }
      } else {
        setTipoMensaje("error");
        setMensaje("Usuario o contraseña incorrectos.");
      }
    } finally {
      setCargando(false);
    }
  }

  return (
    <div className="pantalla-login">
      <div className="tarjeta-login">
        <h1>Hospital San Rafael</h1>
        <p className="subtitulo">Coordinación de quirófanos, camas y urgencias</p>

        <form onSubmit={manejarEnvio}>
          <label htmlFor="username">Usuario</label>
          <input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />

          <label htmlFor="password">Contraseña</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />

          {mensaje && (
            <div className={`aviso aviso-${tipoMensaje}`}>
              {tipoMensaje === "bloqueo" ? "🔒 " : "⚠️ "}
              {mensaje}
            </div>
          )}

          <button type="submit" disabled={cargando}>
            {cargando ? "Entrando..." : "Entrar"}
          </button>
        </form>

        <EstadoServicios />
      </div>
    </div>
  );
}
