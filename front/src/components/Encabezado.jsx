import ChipDemo from "./ChipDemo";

/** Título de pantalla con subtítulo, acciones a la derecha y aviso de demostración. */
export default function Encabezado({ titulo, subtitulo, demo, children }) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-[34px] font-semibold leading-tight tracking-display">{titulo}</h1>
        {subtitulo && <p className="mt-1 text-[15px] text-gray-strong">{subtitulo}</p>}
        {demo && <div className="mt-2"><ChipDemo visible /></div>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}
