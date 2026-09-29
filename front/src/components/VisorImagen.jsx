import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronLeft, ChevronRight, Contrast, RotateCcw, ZoomIn, X } from "lucide-react";

const fechaDicom = (d) => (d && d.length === 8 ? `${d.slice(6, 8)}/${d.slice(4, 6)}/${d.slice(0, 4)}` : "—");

function Control({ etiqueta, valor, min, max, paso = 1, onChange, sufijo = "%" }) {
  return (
    <label className="block text-sm">
      <span className="mb-1.5 flex justify-between"><span>{etiqueta}</span><span className="tabular-nums text-cloud-card/60">{Math.round(valor * (sufijo === "×" ? 10 : 1)) / (sufijo === "×" ? 10 : 1)}{sufijo}</span></span>
      <input type="range" min={min} max={max} step={paso} value={valor} onChange={(e) => onChange(Number(e.target.value))}
             className="w-full accent-metric-blue" />
    </label>
  );
}

/** Visor de imágenes: brillo, contraste, zoom e inversión, como un visor radiológico básico. */
export default function VisorImagen({ imagenes, indice, onCambiar, onCerrar }) {
  const img = imagenes[indice];
  const [brillo, setBrillo] = useState(100);
  const [contraste, setContraste] = useState(100);
  const [zoom, setZoom] = useState(1);
  const [invertir, setInvertir] = useState(false);

  const reiniciar = () => { setBrillo(100); setContraste(100); setZoom(1); setInvertir(false); };
  useEffect(reiniciar, [indice]);

  useEffect(() => {
    const previo = document.activeElement;
    const tecla = (e) => {
      if (e.key === "Escape") onCerrar();
      if (e.key === "ArrowLeft" && indice > 0) onCambiar(indice - 1);
      if (e.key === "ArrowRight" && indice < imagenes.length - 1) onCambiar(indice + 1);
    };
    document.addEventListener("keydown", tecla);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", tecla); document.body.style.overflow = ""; previo?.focus?.(); };
  }, [indice, imagenes.length, onCambiar, onCerrar]);

  if (!img) return null;
  return createPortal(
    <div className="anim-fade fixed inset-0 z-50 flex flex-col bg-charcoal/95 text-cloud-card lg:flex-row" role="dialog" aria-modal="true" aria-label={`Imagen: ${img.description}`}>
      <div className="relative grid min-h-0 flex-1 place-items-center overflow-hidden p-4">
        <img src={img.url} alt={`${img.description}, ${img.modality || "imagen"}`} draggable={false}
             className="max-h-full max-w-full select-none object-contain transition-[filter,transform] duration-150"
             style={{ filter: `brightness(${brillo}%) contrast(${contraste}%) ${invertir ? "invert(1)" : ""}`, transform: `scale(${zoom})` }} />
        {indice > 0 && (
          <button onClick={() => onCambiar(indice - 1)} aria-label="Imagen anterior" className="absolute left-4 top-1/2 grid size-11 -translate-y-1/2 place-items-center rounded-full bg-white/10 transition hover:bg-white/20"><ChevronLeft /></button>
        )}
        {indice < imagenes.length - 1 && (
          <button onClick={() => onCambiar(indice + 1)} aria-label="Imagen siguiente" className="absolute right-4 top-1/2 grid size-11 -translate-y-1/2 place-items-center rounded-full bg-white/10 transition hover:bg-white/20"><ChevronRight /></button>
        )}
      </div>

      <aside className="w-full shrink-0 space-y-6 overflow-y-auto rounded-t-[28px] bg-ink p-6 lg:w-[340px] lg:rounded-l-[28px] lg:rounded-tr-none">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold tracking-display">{img.description}</h2>
            <p className="mt-1 text-sm text-cloud-card/60">{img.modality || "—"} · {fechaDicom(img.date)} · {img.columns}×{img.rows} px</p>
          </div>
          <button onClick={onCerrar} aria-label="Cerrar visor" className="grid size-10 shrink-0 place-items-center rounded-full bg-white/10 transition hover:bg-white/20"><X size={18} /></button>
        </div>

        <div className="space-y-4">
          <Control etiqueta="Brillo" valor={brillo} min={40} max={200} onChange={setBrillo} />
          <Control etiqueta="Contraste" valor={contraste} min={40} max={250} onChange={setContraste} />
          <Control etiqueta="Zoom" valor={zoom} min={0.5} max={4} paso={0.1} onChange={setZoom} sufijo="×" />
        </div>

        <div className="flex gap-2">
          <button onClick={() => setInvertir((v) => !v)} aria-pressed={invertir}
                  className={`flex flex-1 items-center justify-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold transition ${invertir ? "bg-cloud-card text-ink" : "bg-white/10 hover:bg-white/20"}`}>
            <Contrast size={16} />Invertir
          </button>
          <button onClick={reiniciar} className="flex flex-1 items-center justify-center gap-2 rounded-full bg-white/10 px-4 py-2.5 text-sm font-semibold transition hover:bg-white/20">
            <RotateCcw size={16} />Restablecer
          </button>
        </div>

        <p className="flex gap-2 text-xs leading-relaxed text-cloud-card/55">
          <ZoomIn size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          Vista previa en 8 bits para revisión. Los ajustes son solo visuales y no modifican el archivo DICOM. No reemplaza un visor diagnóstico.
        </p>
        <p className="text-xs text-cloud-card/40">{indice + 1} de {imagenes.length} · usa las flechas del teclado para cambiar</p>
      </aside>
    </div>,
    document.body,
  );
}
