import { useEffect, useRef, useState } from "react";
import { api, apiBlob } from "../api";
import VisorImagen from "./VisorImagen";

export default function GaleriaImagenes({ pacienteId }) {
  const [imagenes, setImagenes] = useState([]);
  const [urls, setUrls] = useState({});        // instance_id -> URL temporal (blob:)
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);
  const [subiendo, setSubiendo] = useState(false);
  const [abierta, setAbierta] = useState(null); // instance_id de la imagen en el visor
  const inputArchivo = useRef(null);
  const urlsRef = useRef({});

  async function cargar() {
    setCargando(true);
    setError(null);
    try {
      const datos = await api(`/pacientes/${pacienteId}/imagenes`);
      setImagenes(datos.imagenes);
      for (const img of datos.imagenes) {
        if (urlsRef.current[img.instance_id]) continue;
        try {
          const blob = await apiBlob(`/imagenes/${img.instance_id}/preview`);
          const url = URL.createObjectURL(blob);
          urlsRef.current[img.instance_id] = url;
          setUrls((prev) => ({ ...prev, [img.instance_id]: url }));
        } catch {
          // si una miniatura puntual falla, seguimos con las demás
        }
      }
    } catch (err) {
      if (err.status === 503) {
        setError("El servidor de imágenes (PACS) no está disponible en este momento.");
      } else if (err.status === 403) {
        setError("No tienes permiso para ver las imágenes de este paciente.");
      } else {
        setError("No se pudieron cargar las imágenes.");
      }
    } finally {
      setCargando(false);
    }
  }

  useEffect(() => {
    cargar();
    return () => {
      Object.values(urlsRef.current).forEach(URL.revokeObjectURL);
      urlsRef.current = {};
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pacienteId]);

  async function subir(e) {
    e.preventDefault();
    const archivo = inputArchivo.current.files[0];
    if (!archivo) return;
    setSubiendo(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("archivo", archivo);
      form.append("descripcion", "Imagen subida desde el panel");
      await api(`/pacientes/${pacienteId}/imagenes`, { method: "POST", body: form });
      inputArchivo.current.value = "";
      await cargar();
    } catch (err) {
      setError(err.status === 422
        ? "El archivo no es una imagen válida (solo se aceptan PNG o JPEG)."
        : "No se pudo subir la imagen.");
    } finally {
      setSubiendo(false);
    }
  }

  return (
    <div className="galeria">
      <div className="galeria-cabecera">
        <h3>Imágenes</h3>
        <form onSubmit={subir} className="galeria-form-subida">
          <input ref={inputArchivo} type="file" accept="image/png,image/jpeg" />
          <button type="submit" disabled={subiendo}>
            {subiendo ? "Subiendo..." : "Subir imagen"}
          </button>
        </form>
      </div>

      {error && <div className="aviso aviso-error">⚠️ {error}</div>}
      {cargando && <p className="texto-tenue">Cargando imágenes...</p>}

      {!cargando && !error && imagenes.length === 0 && (
        <p className="texto-tenue">Este paciente todavía no tiene imágenes.</p>
      )}

      <div className="galeria-grilla">
        {imagenes.map((img) => (
          <button
            key={img.instance_id}
            className="galeria-miniatura"
            onClick={() => setAbierta(img.instance_id)}
            disabled={!urls[img.instance_id]}
          >
            {urls[img.instance_id] ? (
              <img src={urls[img.instance_id]} alt={img.description} />
            ) : (
              <span className="texto-tenue">...</span>
            )}
            <span className="galeria-miniatura-etiqueta">{img.description}</span>
          </button>
        ))}
      </div>

      {abierta && urls[abierta] && (
        <VisorImagen url={urls[abierta]} onCerrar={() => setAbierta(null)} />
      )}
    </div>
  );
}
