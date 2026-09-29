import { createContext, useCallback, useContext, useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

const Contexto = createContext({ avisar: () => {} });
export const useAvisos = () => useContext(Contexto);

/** Avisos breves ("Cama UCI-002: disponible") abajo al centro. */
export function ProveedorAvisos({ children }) {
  const [lista, setLista] = useState([]);
  const avisar = useCallback((texto, tipo = "ok") => {
    const id = Math.random();
    setLista((l) => [...l, { id, texto, tipo }]);
    setTimeout(() => setLista((l) => l.filter((a) => a.id !== id)), 4200);
  }, []);
  return (
    <Contexto.Provider value={{ avisar }}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-6 z-[60] flex flex-col items-center gap-2" aria-live="polite">
        {lista.map((a) => (
          <div key={a.id} className="anim-pop pointer-events-auto flex items-center gap-2.5 rounded-full bg-charcoal px-5 py-3 text-sm font-medium text-cloud-card shadow-lift">
            {a.tipo === "ok"
              ? <CheckCircle2 size={16} className="text-recovery-green" />
              : <AlertTriangle size={16} className="text-signal-gold" />}
            {a.texto}
          </div>
        ))}
      </div>
    </Contexto.Provider>
  );
}
