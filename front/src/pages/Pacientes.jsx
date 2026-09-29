import { useEffect, useState } from "react";
import { api } from "../api";

export default function Pacientes({ onSeleccionar }) {
  const [pacientes, setPacientes] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);
  const [busqueda, setBusqueda] = useState("");

  // Búsqueda por documento EXACTO contra el servidor (usa el índice ciego,
  // funciona sobre los 4.000 pacientes, no solo sobre la página cargada).
  const [buscandoDocumento, setBuscandoDocumento] = useState(false);
  const [resultadoDocumento, setResultadoDocumento] = useState(null);
  const [errorDocumento, setErrorDocumento] = useState(null);

  useEffect(() => {
    api("/pacientes?limite=100")
      .then(setPacientes)
      .catch(() => setError("No se pudo cargar la lista de pacientes."))
      .finally(() => setCargando(false));
  }, []);

  async function buscarPorDocumento(e) {
    e.preventDefault();
    setResultadoDocumento(null);
    setErrorDocumento(null);
    const documento = busqueda.trim();
    if (!documento) return;
    setBuscandoDocumento(true);
    try {
      const p = await api(`/pacientes/buscar?documento=${encodeURIComponent(documento)}`);
      setResultadoDocumento(p);
    } catch (err) {
      setErrorDocumento(err.status === 404
        ? "No existe ningún paciente con ese documento exacto."
        : "No se pudo buscar.");
    } finally {
      setBuscandoDocumento(false);
    }
  }

  // Filtro rápido, solo dentro de los pacientes ya cargados en esta página
  // (para eso sirve mientras escribes; la búsqueda de verdad, sobre los
  // 4.000, es la de arriba, por documento exacto).
  const filtrados = pacientes.filter((p) => {
    const q = busqueda.toLowerCase();
    return (
      p.nombre.toLowerCase().includes(q) ||
      p.apellido.toLowerCase().includes(q) ||
      p.documento.includes(q)
    );
  });

  if (cargando) return <p className="texto-tenue">Cargando pacientes...</p>;
  if (error) return <div className="aviso aviso-error">⚠️ {error}</div>;

  return (
    <div>
      <form onSubmit={buscarPorDocumento} className="buscador-form">
        <input
          className="buscador"
          placeholder="Escribe un número de documento exacto y dale Enter, o filtra la lista de abajo escribiendo un nombre..."
          value={busqueda}
          onChange={(e) => { setBusqueda(e.target.value); setResultadoDocumento(null); setErrorDocumento(null); }}
        />
        <button type="submit" disabled={buscandoDocumento}>
          {buscandoDocumento ? "Buscando..." : "Buscar documento exacto"}
        </button>
      </form>
      <p className="texto-tenue" style={{ marginTop: "-0.6rem", marginBottom: "1rem" }}>
        La tabla de abajo solo muestra 100 de los 4.000 pacientes. Si buscas a alguien
        específico y no aparece en la tabla, usa "Buscar documento exacto" arriba.
      </p>

      {errorDocumento && <div className="aviso aviso-error">⚠️ {errorDocumento}</div>}
      {resultadoDocumento && (
        <div className="resultado-documento">
          <div>
            <strong>{resultadoDocumento.nombre} {resultadoDocumento.apellido}</strong>
            <span className="texto-tenue"> — {resultadoDocumento.tipo_documento} {resultadoDocumento.documento}</span>
          </div>
          <button onClick={() => onSeleccionar(resultadoDocumento.paciente_id)}>Ver ficha</button>
        </div>
      )}

      <table className="tabla-pacientes">
        <thead>
          <tr>
            <th>Documento</th>
            <th>Nombre</th>
            <th>Sexo</th>
            <th>Fecha de nacimiento</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {filtrados.map((p) => (
            <tr key={p.paciente_id}>
              <td>{p.tipo_documento} {p.documento}</td>
              <td>{p.nombre} {p.apellido}</td>
              <td>{p.sexo}</td>
              <td>{p.fecha_nacimiento}</td>
              <td>
                <button onClick={() => onSeleccionar(p.paciente_id)}>Ver ficha</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {filtrados.length === 0 && <p className="texto-tenue">Sin resultados.</p>}
    </div>
  );
}
