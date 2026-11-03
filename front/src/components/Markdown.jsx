/**
 * Markdown mínimo y seguro para las respuestas del asistente: párrafos, listas (- , * , 1.),
 * **negrita**, *cursiva* y `código`. Las marcas [F1] se vuelven numeritos de cita. No usa
 * dangerouslySetInnerHTML: todo se arma con elementos de React, así que el texto del modelo
 * nunca se interpreta como HTML.
 */
const INLINE = /\*\*(.+?)\*\*|`([^`\n]+)`|\[F(\d+)\]|(?<![*\w])\*(?!\s)([^*\n]+?)\*(?![*\w])/g;

function enLinea(texto, cita, clave) {
  const partes = [];
  let ultimo = 0;
  for (const m of texto.matchAll(INLINE)) {
    if (m.index > ultimo) partes.push(texto.slice(ultimo, m.index));
    const k = `${clave}-${m.index}`;
    if (m[1] !== undefined) partes.push(<strong key={k} className="font-semibold">{enLinea(m[1], cita, k)}</strong>);
    else if (m[2] !== undefined) partes.push(<code key={k} className="rounded bg-paper-white/70 px-1 font-mono text-[0.85em]">{m[2]}</code>);
    else if (m[3] !== undefined) partes.push(cita ? cita(Number(m[3]), k) : null);
    else partes.push(<em key={k}>{enLinea(m[4], cita, k)}</em>);
    ultimo = m.index + m[0].length;
  }
  if (ultimo < texto.length) partes.push(texto.slice(ultimo));
  // Sin espacio colgando antes de un numerito de cita ("dato [F1]" → "dato¹").
  return partes.map((p, i) => (typeof p === "string" && typeof partes[i + 1] === "object" && partes[i + 1]?.props?.["data-cita"])
    ? p.replace(/\s+$/, "") : p);
}

const VINETA = /^\s*[-*•]\s+(.*)$/;
const NUMERO = /^\s*\d+[.)]\s+(.*)$/;

/** Agrupa las líneas en bloques: párrafo, lista con viñetas o lista numerada. */
function bloques(texto) {
  const salida = [];
  let actual = null;
  for (const linea of texto.replace(/\r\n/g, "\n").split("\n")) {
    const v = linea.match(VINETA), n = linea.match(NUMERO);
    const tipo = v ? "ul" : n ? "ol" : linea.trim() ? "p" : null;
    if (!tipo) { actual = null; continue; }
    const contenido = (v || n)?.[1] ?? linea.trim().replace(/^#{1,6}\s+/, "");
    const esTitulo = tipo === "p" && /^#{1,6}\s+/.test(linea.trim());
    if (actual && actual.tipo === tipo && !esTitulo && !actual.titulo) {
      actual.items.push(contenido);
    } else if (actual && tipo === "p" && actual.tipo !== "p" && /^\s{2,}/.test(linea)) {
      actual.items[actual.items.length - 1] += " " + contenido;     // continuación de un ítem
    } else {
      actual = { tipo, items: [contenido], titulo: esTitulo };
      salida.push(actual);
    }
  }
  return salida;
}

export default function Markdown({ texto, cita }) {
  return (
    <div className="space-y-2 leading-relaxed">
      {bloques(texto || "").map((b, i) => {
        if (b.tipo === "p") {
          return <p key={i} className={b.titulo ? "font-semibold" : undefined}>{enLinea(b.items.join(" "), cita, `p${i}`)}</p>;
        }
        const Lista = b.tipo;
        return (
          <Lista key={i} className={`space-y-1 pl-5 ${b.tipo === "ul" ? "list-disc" : "list-decimal"} marker:text-gray-strong`}>
            {b.items.map((it, j) => <li key={j}>{enLinea(it, cita, `l${i}-${j}`)}</li>)}
          </Lista>
        );
      })}
    </div>
  );
}
