import { useEffect, useState } from "react";
import { API_BASE } from "../api";

const ETIQUETAS = { api: "API", base_datos: "Base de datos", pacs: "PACS" };

export default function EstadoServicios() {
  const [estado, setEstado] = useState(null);

  useEffect(() => {
    let activo = true;
    async function consultar() {
      try {
        const r = await fetch(`${API_BASE}/salud`);
        const datos = await r.json();
        if (activo) setEstado(datos);
      } catch {
        if (activo) setEstado({ api: "error", base_datos: "error", pacs: "error" });
      }
    }
    consultar();
    const intervalo = setInterval(consultar, 10000);
    return () => { activo = false; clearInterval(intervalo); };
  }, []);

  if (!estado) return null;

  return (
    <div className="estado-servicios">
      {Object.entries(ETIQUETAS).map(([clave, etiqueta]) => {
        const valor = estado[clave];
        const ok = valor === "ok";
        return (
          <span className="estado-item" key={clave} title={valor}>
            <span className={`punto ${ok ? "punto-ok" : "punto-mal"}`} />
            {etiqueta}
          </span>
        );
      })}
    </div>
  );
}
