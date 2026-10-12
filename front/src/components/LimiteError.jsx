import { Component } from "react";
import ErrorEstado from "./ErrorEstado";

/** Si una pantalla falla al dibujarse, muestra un aviso en vez de dejar la página en blanco. */
export default class LimiteError extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  componentDidUpdate(previas) {
    // Al cambiar de pantalla se vuelve a intentar.
    if (previas.clave !== this.props.clave && this.state.error) this.setState({ error: null });
  }
  render() {
    if (this.state.error) return <ErrorEstado titulo="Esta pantalla tuvo un problema" detalle="Ya quedó registrado en la consola. Prueba ir a tu inicio o recargar." />;
    return this.props.children;
  }
}
