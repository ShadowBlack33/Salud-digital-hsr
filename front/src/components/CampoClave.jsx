import { useState } from "react";
import { Check, Eye, EyeOff, Wand2 } from "lucide-react";

// Reglas de app/core/security.py:validar_fortaleza. Se muestran mientras se
// escribe para que nadie se entere de ellas recién al recibir el error.
export const REGLAS_CLAVE = [
  ["12 caracteres o más", (c) => c.length >= 12],
  ["Una mayúscula", (c) => /[A-ZÁÉÍÓÚÑ]/.test(c)],
  ["Una minúscula", (c) => /[a-záéíóúñ]/.test(c)],
  ["Un número", (c) => /\d/.test(c)],
  ["Un símbolo", (c) => /[^A-Za-z0-9ÁÉÍÓÚÑáéíóúñ]/.test(c)],
];
export const claveValida = (c) => REGLAS_CLAVE.every(([, ok]) => ok(c));

/** Contraseña aleatoria que cumple todas las reglas (para la clave inicial). */
export function generarClave() {
  const grupos = ["ABCDEFGHJKLMNPQRSTUVWXYZ", "abcdefghijkmnpqrstuvwxyz", "23456789", "#$%&*+-=?@"];
  const todos = grupos.join("");
  const azar = (n) => { const a = new Uint32Array(1); crypto.getRandomValues(a); return a[0] % n; };
  const letras = grupos.map((g) => g[azar(g.length)]);
  while (letras.length < 14) letras.push(todos[azar(todos.length)]);
  for (let i = letras.length - 1; i > 0; i--) { const j = azar(i + 1); [letras[i], letras[j]] = [letras[j], letras[i]]; }
  return letras.join("");
}

/** Campo de contraseña con botón para ver lo que se escribe y, opcional,
 *  la lista de reglas y un generador. */
export default function CampoClave({ id, etiqueta, valor, onCambio, autoComplete = "new-password", reglas = false,
                                     generar = false, claseEntrada = "", requerido = true }) {
  const [ver, setVer] = useState(false);
  return (
    <div className="text-sm">
      <label htmlFor={id}>{etiqueta}</label>
      <div className="relative mt-1">
        <input id={id} type={ver ? "text" : "password"} autoComplete={autoComplete} required={requerido}
               value={valor} onChange={(e) => onCambio(e.target.value)} spellCheck={false}
               aria-describedby={reglas ? `${id}-reglas` : undefined}
               className={`${claseEntrada} ${generar ? "pr-24" : "pr-12"}`} />
        <div className="absolute inset-y-0 right-1.5 flex items-center gap-0.5">
          {generar && (
            <button type="button" onClick={() => { onCambio(generarClave()); setVer(true); }}
                    title="Generar una contraseña segura" aria-label="Generar una contraseña segura"
                    className="grid size-9 place-items-center rounded-full text-ink transition hover:bg-cloud-card"><Wand2 size={16} /></button>
          )}
          <button type="button" onClick={() => setVer((v) => !v)} aria-pressed={ver}
                  aria-label={ver ? "Ocultar contraseña" : "Mostrar contraseña"} title={ver ? "Ocultar" : "Mostrar"}
                  className="grid size-9 place-items-center rounded-full text-ink transition hover:bg-cloud-card">
            {ver ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
      </div>
      {reglas && (
        <ul id={`${id}-reglas`} className="mt-2 flex flex-wrap gap-1.5">
          {REGLAS_CLAVE.map(([texto, ok]) => {
            const cumple = ok(valor);
            return (
              <li key={texto} className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${cumple ? "bg-green-soft text-green-ink" : "bg-cloud-card text-gray-strong"}`}>
                {cumple && <Check size={12} aria-hidden="true" />}{texto}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
