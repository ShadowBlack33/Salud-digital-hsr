import ErrorEstado from "./ErrorEstado";
import { useUsuario } from "../lib/hooks";

/**
 * Muestra la pantalla solo si el rol puede verla; si no, un 403 amable.
 * La API vuelve a validar cada petición: esto evita mostrar una pantalla vacía
 * llena de errores cuando alguien escribe la dirección a mano.
 */
export default function Permitido({ si, children }) {
  const usuario = useUsuario();
  return si(usuario) ? children : <ErrorEstado status={403} />;
}
