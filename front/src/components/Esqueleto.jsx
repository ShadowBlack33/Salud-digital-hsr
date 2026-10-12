/** Bloques grises que laten mientras carga: la pantalla no salta al llegar los datos. */
export function Linea({ className = "" }) {
  return <span className={`block animate-pulse rounded-full bg-cloud-card ${className}`} aria-hidden="true" />;
}

/** Lista de filas de carga (por ejemplo, para tablas o listas de pacientes). */
export default function Esqueleto({ filas = 5, alto = "h-12" }) {
  return (
    <div role="status" aria-label="Cargando" className="space-y-2">
      {Array.from({ length: filas }, (_, i) => (
        <div key={i} className={`flex items-center gap-3 rounded-2xl px-3 ${alto}`}>
          <Linea className="size-8 shrink-0 rounded-full" />
          <span className="flex-1 space-y-1.5"><Linea className="h-3 w-1/3" /><Linea className="h-2.5 w-1/2" /></span>
          <Linea className="h-6 w-20" />
        </div>
      ))}
    </div>
  );
}
