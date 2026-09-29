/** Fila etiqueta / valor para los paneles laterales. */
export default function Dato({ etiqueta, children }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2 text-sm">
      <dt className="shrink-0 text-gray-strong">{etiqueta}</dt>
      <dd className="text-right font-medium">{children}</dd>
    </div>
  );
}
