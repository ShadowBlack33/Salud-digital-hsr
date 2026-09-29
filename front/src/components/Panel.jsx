import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

/** Panel lateral deslizable (drawer). Se cierra con Esc, con la X o tocando fuera. */
export default function Panel({ abierto, onCerrar, titulo, subtitulo, children, pie }) {
  const cerrar = useRef(null);

  useEffect(() => {
    if (!abierto) return;
    const previo = document.activeElement;
    const alTeclear = (e) => { if (e.key === "Escape") onCerrar(); };
    document.addEventListener("keydown", alTeclear);
    document.body.style.overflow = "hidden";
    cerrar.current?.focus();
    return () => {
      document.removeEventListener("keydown", alTeclear);
      document.body.style.overflow = "";
      previo?.focus?.();
    };
  }, [abierto, onCerrar]);

  if (!abierto) return null;
  return createPortal(
    <div className="fixed inset-0 z-50">
      <div className="anim-fade absolute inset-0 bg-ink/30 backdrop-blur-[2px]" onClick={onCerrar} />
      <aside role="dialog" aria-modal="true" aria-label={titulo}
             className="anim-drawer absolute right-0 top-0 flex h-full w-full max-w-[460px] flex-col rounded-l-[32px] bg-paper-white shadow-drawer">
        <header className="flex items-start justify-between gap-4 px-7 pb-4 pt-7">
          <div className="min-w-0">
            <h2 className="truncate text-[26px] font-semibold leading-tight tracking-display">{titulo}</h2>
            {subtitulo && <p className="mt-1 text-sm text-gray-strong">{subtitulo}</p>}
          </div>
          <button ref={cerrar} onClick={onCerrar} aria-label="Cerrar panel"
                  className="grid size-10 shrink-0 place-items-center rounded-full bg-cloud-card text-ink transition hover:bg-hero-sky">
            <X size={18} />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-7 pb-6">{children}</div>
        {pie && <footer className="border-t border-cloud-card px-7 py-5">{pie}</footer>}
      </aside>
    </div>,
    document.body,
  );
}
