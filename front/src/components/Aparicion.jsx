import { useAparicion } from "../lib/hooks";

/** Envuelve un bloque para que aparezca suavemente al hacer scroll. */
export default function Aparicion({ children, retraso = 0, className = "", ...resto }) {
  const [ref, visible] = useAparicion();
  return (
    <div ref={ref} style={{ transitionDelay: `${retraso}ms` }}
         className={`reveal ${visible ? "is-visible" : ""} ${className}`} {...resto}>
      {children}
    </div>
  );
}
