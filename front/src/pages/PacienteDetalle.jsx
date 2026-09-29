import { useEffect, useState } from "react";
import { api } from "../api";
import GaleriaImagenes from "../components/GaleriaImagenes";

export default function PacienteDetalle({ pacienteId, onVolver }) {
  const [paciente, setPaciente] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api(`/pacientes/${pacienteId}`)
      .then(setPaciente)
      .catch(() => setError("No se pudo cargar la ficha del paciente."));
  }, [pacienteId]);

  return (
    <div>
      <button className="boton-volver" onClick={onVolver}>← Volver a la lista</button>

      {error && <div className="aviso aviso-error">⚠️ {error}</div>}

      {paciente && (
        <>
          <div className="ficha-cabecera">
            <h2>{paciente.nombre} {paciente.apellido}</h2>
            <p className="texto-tenue">
              {paciente.tipo_documento} {paciente.documento} ·
              {" "}{paciente.sexo} · nacido el {paciente.fecha_nacimiento}
            </p>
          </div>

          <GaleriaImagenes pacienteId={pacienteId} />
        </>
      )}
    </div>
  );
}
