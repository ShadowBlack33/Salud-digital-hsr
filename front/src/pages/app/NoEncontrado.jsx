import ErrorEstado from "../../components/ErrorEstado";

export default function NoEncontrado() {
  return <ErrorEstado status={404} titulo="Esta página no existe" detalle="Revisa la dirección o vuelve a tu pantalla de inicio." />;
}
