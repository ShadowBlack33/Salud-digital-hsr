import { useCallback, useEffect, useState } from "react";
import { Activity, Brain, Gauge, KeyRound, ShieldAlert, Users } from "lucide-react";
import Encabezado from "../../components/Encabezado";
import Esqueleto from "../../components/Esqueleto";
import ErrorEstado from "../../components/ErrorEstado";
import { api } from "../../api";

/** Rendimiento (solo admin): cómo funciona la API, la seguridad, el uso por perfil y el modelo de IA. Todo agregado. */
function Tarjeta({ icono: Icono, etiqueta, valor, detalle, alerta = false }) {
  return (
    <div className={`rounded-[28px] p-6 ${alerta ? "bg-coral-soft" : "bg-cloud-card"}`}>
      <p className="flex items-center justify-between gap-2 text-sm font-medium">{etiqueta}<Icono size={19} className={alerta ? "text-coral-deep" : "text-metric-blue"} aria-hidden="true" /></p>
      <p className="mt-4 text-4xl font-semibold tabular-nums tracking-display">{valor ?? "—"}</p>
      {detalle && <p className="mt-1 text-xs text-gray-strong">{detalle}</p>}
    </div>
  );
}

function Tabla({ titulo, columnas, filas, vacio }) {
  return (
    <section className="rounded-[28px] bg-paper-white p-6 shadow-lift">
      <h2 className="text-lg font-semibold">{titulo}</h2>
      {filas.length === 0 ? <p className="mt-2 text-sm text-gray-strong">{vacio}</p> : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-gray-strong">{columnas.map(([k, t]) => <th key={k} className="py-2 pr-4 font-medium">{t}</th>)}</tr></thead>
            <tbody>{filas.map((f, i) => (
              <tr key={i} className="border-t border-cloud-card">{columnas.map(([k]) => <td key={k} className="py-2 pr-4 tabular-nums">{f[k] ?? "—"}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function Rendimiento() {
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  const cargar = useCallback(() => api("/admin/rendimiento").then(setD).catch(setError), []);
  useEffect(() => { cargar(); const t = setInterval(cargar, 30000); return () => clearInterval(t); }, [cargar]);

  if (error) return <ErrorEstado status={error.status} detalle={error.message} />;
  if (!d) return <Esqueleto filas={4} alto="h-24" />;
  const h = d.api.ultima_hora;
  const m = d.ia.metricas;
  return (
    <div className="space-y-8 pb-16">
      <Encabezado titulo="Rendimiento del sistema"
                  subtitulo={`API, seguridad, uso y modelo de IA. Sin datos de pacientes. La API lleva ${d.api.minutos_activo} min encendida; se actualiza cada 30 s.`} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tarjeta icono={Activity} etiqueta="Peticiones en la última hora" valor={h.peticiones}
                 detalle={`${h.errores_cliente} con error del cliente (4xx) · ${h.errores_servidor} del servidor (5xx)`} alerta={h.errores_servidor > 0} />
        <Tarjeta icono={Gauge} etiqueta="Tiempo de respuesta (p95)" valor={h.p95_ms != null ? `${h.p95_ms} ms` : "—"}
                 detalle={`Mediana ${h.p50_ms ?? "—"} ms`} alerta={(h.p95_ms ?? 0) > 1500} />
        <Tarjeta icono={KeyRound} etiqueta="Inicios de sesión (24 h)" valor={d.seguridad.logins_ok}
                 detalle={`${d.seguridad.logins_fallidos} fallidos · ${d.seguridad.cuentas_bloqueadas} cuentas bloqueadas ahora · ${d.seguridad.sesiones_activas} sesiones abiertas`}
                 alerta={d.seguridad.cuentas_bloqueadas > 0} />
        <Tarjeta icono={ShieldAlert} etiqueta="Accesos denegados (24 h)" valor={d.seguridad.accesos_denegados}
                 detalle={`${d.seguridad.eventos} eventos auditados en 24 h`} />
      </div>

      <section className="rounded-[28px] bg-cloud-card p-6">
        <h2 className="flex items-center gap-2 text-lg font-semibold"><Brain size={18} aria-hidden="true" />Modelo de IA</h2>
        <p className="mt-1 text-sm text-gray-strong">Servicio: {d.ia.servicio}
          {d.ia.reportes && <> · reportes: {Object.entries(d.ia.reportes).map(([k, v]) => `${v} ${k}`).join(", ")}</>}</p>
        {m ? (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(m).filter(([, v]) => typeof v === "number" || typeof v === "string").slice(0, 8).map(([k, v]) => (
              <div key={k} className="rounded-2xl bg-paper-white p-4">
                <p className="text-xs text-gray-strong">{k.replaceAll("_", " ")}</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">{typeof v === "number" ? Math.round(v * 1000) / 1000 : v}</p>
              </div>
            ))}
          </div>
        ) : <p className="mt-3 text-sm text-gray-strong">Las métricas aparecen aquí cuando el servicio de IA publique <code>/metricas</code> (sensibilidad, especificidad, umbral, etc.).</p>}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Tabla titulo="Rutas más usadas" vacio="Aún no hay tráfico desde que arrancó la API."
               columnas={[["ruta", "Ruta"], ["peticiones", "Peticiones"], ["p95_ms", "p95 ms"], ["errores_4xx", "4xx"], ["errores_5xx", "5xx"]]}
               filas={d.api.rutas} />
        <Tabla titulo="Accesos denegados por perfil (24 h)" vacio="Nadie intentó algo que su perfil no permite."
               columnas={[["rol", "Perfil"], ["recurso", "Recurso"], ["operacion", "Acción"], ["n", "Veces"]]} filas={d.denegados} />
        <Tabla titulo="Uso por perfil" vacio="—"
               columnas={[["nombre", "Perfil"], ["usuarios", "Cuentas"], ["activos_24h", "Entraron en 24 h"]]} filas={d.uso_por_perfil} />
        <Tabla titulo="Qué se hizo en las últimas 24 h" vacio="Sin actividad."
               columnas={[["recurso", "Recurso"], ["operacion", "Acción"], ["n", "Veces"]]} filas={d.acciones_24h} />
      </div>
      <p className="flex items-center gap-2 text-xs text-gray-strong"><Users size={13} aria-hidden="true" />Las métricas de la API viven en memoria y se reinician al reiniciar el contenedor; las de seguridad y uso salen de la auditoría.</p>
    </div>
  );
}
