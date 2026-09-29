import { useSondeo } from "../lib/hooks";
import { salud } from "../api";

const ITEMS = [["api", "API"], ["base_datos", "Base de datos"], ["pacs", "PACS"]];

/** Puntos de estado de API, base de datos y PACS (consulta /salud cada 10 s). */
export default function EstadoServicios({ className = "", oscuro = false }) {
  const { datos, error } = useSondeo(salud, 10000);
  const estado = error && !datos ? { api: "error", base_datos: "error", pacs: "error" } : datos;
  if (!estado) return null;
  return (
    <ul className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-xs ${oscuro ? "text-cloud-card" : "text-gray-strong"} ${className}`} aria-label="Estado de los servicios">
      {ITEMS.map(([clave, etiqueta]) => {
        const ok = estado[clave] === "ok";
        return (
          <li key={clave} className="flex items-center gap-1.5" title={String(estado[clave])}>
            <span className={`size-2 rounded-full ${ok ? "anim-pulse-dot bg-green-deep" : "bg-coral-deep"}`} />
            {etiqueta}
            <span className="sr-only">{ok ? "operativo" : "sin conexión"}</span>
          </li>
        );
      })}
    </ul>
  );
}
