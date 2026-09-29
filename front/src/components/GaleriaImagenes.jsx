import { useCallback, useEffect, useRef, useState } from "react";
import { ImageOff, ImagePlus, Loader2, ScanLine } from "lucide-react";
import VisorImagen from "./VisorImagen";
import { useAvisos } from "./Avisos";
import { api, apiBlob, puede } from "../api";
import { useUsuario } from "../lib/hooks";

const fechaCorta = (d) => (d && d.length === 8 ? `${d.slice(6, 8)}/${d.slice(4, 6)}/${d.slice(0, 4)}` : "—");

/** Imágenes del paciente en el PACS (Orthanc): galería, carga y visor. */
export default function GaleriaImagenes({ pacienteId }) {
  const usuario = useUsuario();
  const { avisar } = useAvisos();
  const [estado, setEstado] = useState({ cargando: true, error: null, imagenes: [] });
  const [abierta, setAbierta] = useState(null);
  const [subiendo, setSubiendo] = useState(false);
  const urls = useRef([]);
  const entrada = useRef(null);

  const cargar = useCallback(async () => {
    setEstado((e) => ({ ...e, cargando: true, error: null }));
    try {
      const { imagenes } = await api(`/pacientes/${pacienteId}/imagenes`);
      // Un <img src> no puede enviar el token: se baja cada imagen y se muestra desde un blob.
      const conUrl = await Promise.all(imagenes.map(async (i) => {
        try {
          const url = URL.createObjectURL(await apiBlob(`/imagenes/${i.instance_id}/preview`));
          urls.current.push(url);
          return { ...i, url };
        } catch { return { ...i, url: null }; }
      }));
      setEstado({ cargando: false, error: null, imagenes: conUrl });
    } catch (e) {
      setEstado({ cargando: false, imagenes: [], error: e });
    }
  }, [pacienteId]);

  useEffect(() => {
    cargar();
    return () => { urls.current.forEach(URL.revokeObjectURL); urls.current = []; };
  }, [cargar]);

  async function subir(archivo) {
    if (!archivo) return;
    setSubiendo(true);
    const datos = new FormData();
    datos.append("archivo", archivo);
    datos.append("descripcion", archivo.name.replace(/\.[^.]+$/, "").slice(0, 60) || "Imagen clínica");
    try {
      await api(`/pacientes/${pacienteId}/imagenes`, { method: "POST", body: datos });
      avisar("Imagen guardada en el PACS");
      await cargar();
    } catch (e) {
      avisar(e.message, "error");
    } finally {
      setSubiendo(false);
      if (entrada.current) entrada.current.value = "";
    }
  }

  const { cargando, error, imagenes } = estado;
  const visibles = imagenes.filter((i) => i.url);

  return (
    <section aria-labelledby="t-img" className="rounded-[28px] bg-cloud-card p-6 sm:p-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="t-img" className="text-2xl font-semibold tracking-display">Imágenes diagnósticas</h2>
          <p className="mt-1 text-sm text-gray-strong">Estudios guardados en el PACS del hospital (DICOM).</p>
        </div>
        {puede(usuario, "imagen", "create") && (
          <>
            <input ref={entrada} type="file" accept="image/png,image/jpeg" className="sr-only" id="subir-img"
                   onChange={(e) => subir(e.target.files?.[0])} />
            <label htmlFor="subir-img"
                   className={`inline-flex cursor-pointer items-center gap-2 rounded-full bg-charcoal px-5 py-3 text-sm font-semibold text-white transition hover:bg-ink ${subiendo ? "pointer-events-none opacity-60" : ""}`}>
              {subiendo ? <Loader2 size={16} className="anim-spin" /> : <ImagePlus size={16} />}
              {subiendo ? "Subiendo…" : "Subir imagen"}
            </label>
          </>
        )}
      </div>

      <div className="mt-5">
        {cargando && <p className="flex items-center gap-2 text-sm text-gray-strong"><Loader2 size={16} className="anim-spin" />Consultando el PACS…</p>}

        {!cargando && error && (
          <p className="flex items-start gap-3 rounded-2xl bg-paper-white p-5 text-sm text-gray-strong">
            <ImageOff size={20} className="mt-0.5 shrink-0" aria-hidden="true" />
            {error.status === 503 || error.status === 502
              ? "El PACS no está disponible en este momento. Revisa que el contenedor de Orthanc esté encendido."
              : error.status === 403 ? "Tu rol no tiene permiso para ver imágenes de este paciente." : error.message}
          </p>
        )}

        {!cargando && !error && visibles.length === 0 && (
          <p className="flex items-start gap-3 rounded-2xl bg-paper-white p-5 text-sm text-gray-strong">
            <ScanLine size={20} className="mt-0.5 shrink-0" aria-hidden="true" />Este paciente aún no tiene imágenes.
          </p>
        )}

        {visibles.length > 0 && (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {visibles.map((i, n) => (
              <li key={i.instance_id}>
                <button onClick={() => setAbierta(n)} className="group block w-full overflow-hidden rounded-2xl bg-paper-white text-left transition hover:-translate-y-0.5 hover:shadow-lift">
                  <span className="grid aspect-square place-items-center bg-charcoal">
                    <img src={i.url} alt={i.description} loading="lazy" className="size-full object-contain transition group-hover:scale-[1.03]" />
                  </span>
                  <span className="block p-3">
                    <span className="block truncate text-sm font-medium">{i.description}</span>
                    <span className="mt-0.5 block text-xs text-gray-strong">{i.modality || "—"} · {fechaCorta(i.date)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {abierta !== null && (
        <VisorImagen imagenes={visibles} indice={abierta} onCambiar={setAbierta} onCerrar={() => setAbierta(null)} />
      )}
    </section>
  );
}
