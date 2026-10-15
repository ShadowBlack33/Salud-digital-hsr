import { Navigate } from "react-router-dom";
import { useUsuario } from "../../lib/hooks";
import { rutaInicio } from "../../lib/roles";

/** /app lleva a cada rol a su propia pantalla de inicio. */
export default function Inicio() {
  const usuario = useUsuario();
  return <Navigate to={rutaInicio(usuario)} replace />;
}
