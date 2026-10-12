import { useCallback, useEffect, useRef, useState } from "react";
import Esqueleto from "../../components/Esqueleto";
import { Activity, Ban, KeyRound, Loader2, Lock, RefreshCw, ShieldCheck, Unlock, UserPlus, X } from "lucide-react";
import Encabezado from "../../components/Encabezado";
import Insignia from "../../components/Insignia";
import CampoClave, { claveValida } from "../../components/CampoClave";
import { useAvisos } from "../../components/Avisos";
import * as S from "../../lib/servicios";
import { useEventos, useTiempoReal } from "../../lib/tiempoReal";
import { useSondeo } from "../../lib/hooks";
import { salud } from "../../api";
import { fechaYHora, haceCuanto } from "../../lib/format";

const PESTANAS = [["usuarios", "Usuarios"], ["bloqueadas", "Cuentas bloqueadas"], ["auditoria", "Auditoría"], ["servicios", "Servicios"]];

/** Panel del admin: crear usuarios (R01), desbloquear cuentas (R02) y consultar la auditoría (R13). */
export default function AdminPanel() {
  const [pestana, setPestana] = useState("usuarios");
  const [usuarios, setUsuarios] = useState({ cargando: true, lista: [], error: null });

  const cargarUsuarios = useCallback(async () => {
    try { setUsuarios({ cargando: false, lista: await S.usuarios(), error: null }); }
    catch (err) { setUsuarios((u) => ({ ...u, cargando: false, error: err })); }
  }, []);
  useEffect(() => { cargarUsuarios(); }, [cargarUsuarios]);
  useEventos((ev) => { if (ev.tipo === "cuenta_bloqueada") cargarUsuarios(); });

  const bloqueadas = usuarios.lista.filter((u) => u.bloqueada);

  return (
    <div className="space-y-6 pb-16">
      <Encabezado titulo="Administración" subtitulo="Usuarios, cuentas bloqueadas, auditoría y estado del sistema." />
      <ResumenHoy bloqueadas={bloqueadas.length} />

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Secciones">
        {PESTANAS.map(([id, texto]) => (
          <button key={id} role="tab" aria-selected={pestana === id}
                  onClick={() => { setPestana(id); if (id === "usuarios" || id === "bloqueadas") cargarUsuarios(); }}
                  className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition ${pestana === id ? "bg-charcoal text-white" : "bg-cloud-card text-ink hover:bg-hero-sky"}`}>
            {texto}
            {id === "bloqueadas" && bloqueadas.length > 0 && (
              <span className="grid min-w-5 place-items-center rounded-full bg-coral-deep px-1.5 text-[11px] font-semibold text-white">{bloqueadas.length}</span>
            )}
          </button>
        ))}
      </div>

      {pestana === "usuarios" && <Usuarios estado={usuarios} onCambio={cargarUsuarios} />}
      {pestana === "bloqueadas" && <Bloqueadas lista={bloqueadas} onCambio={cargarUsuarios} />}
      {pestana === "auditoria" && <Auditoria />}
      {pestana === "servicios" && <Servicios />}
    </div>
  );
}

const tarjeta = "rounded-[28px] bg-paper-white p-6 shadow-lift";

const esHoy = (iso) => iso && new Date(iso).toDateString() === new Date().toDateString();

/** Indicadores del día sacados de la auditoría (R13). Se recalculan con cada evento. */
function ResumenHoy({ bloqueadas }) {
  const [registros, setRegistros] = useState(null);
  const cargar = useCallback(() => S.auditoria({ limite: 500 }).then((l) => setRegistros(l.filter((r) => esHoy(r.timestamp)))).catch(() => setRegistros([])), []);
  useEffect(() => { cargar(); }, [cargar]);
  useEventos((ev) => { if (!ev.local) cargar(); });

  const contar = (f) => (registros ? registros.filter(f).length : "—");
  const tarjetas = [
    ["Logins fallidos hoy", contar((r) => r.operacion === "login" && r.resultado === "denegado"), KeyRound, "text-gold-deep"],
    ["Cuentas bloqueadas ahora", bloqueadas, Lock, "text-coral-deep"],
    ["Accesos denegados hoy", contar((r) => r.resultado === "denegado"), Ban, "text-coral-deep"],
    ["Eventos FHIR recibidos hoy", contar((r) => r.operacion === "fhir_evento"), Activity, "text-sleep-lilac"],
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Resumen de hoy">
      {tarjetas.map(([etiqueta, valor, Icono, tono]) => (
        <div key={etiqueta} className="rounded-[24px] bg-cloud-card p-5">
          <div className="flex items-center justify-between gap-2 text-xs font-medium"><span>{etiqueta}</span><Icono size={16} className={tono} aria-hidden="true" /></div>
          <span key={valor} className="anim-pop mt-2 block text-3xl font-semibold tabular-nums tracking-display">{valor}</span>
        </div>
      ))}
    </div>
  );
}
const entrada = "w-full rounded-2xl bg-cloud-card px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-metric-blue/40";

function Usuarios({ estado, onCambio }) {
  const [crear, setCrear] = useState(false);
  const [buscar, setBuscar] = useState("");
  const [cuantos, setCuantos] = useState(25);
  const q = buscar.trim().toLowerCase();
  const filtrados = estado.lista.filter((u) => !q || u.username.toLowerCase().includes(q) || (u.rol_nombre || u.rol || "").toLowerCase().includes(q));
  return (
    <section className={tarjeta} aria-label="Usuarios">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Usuarios del sistema</h2>
        <button onClick={() => setCrear((v) => !v)} className="flex items-center gap-2 rounded-full bg-charcoal px-4 py-2 text-sm font-semibold text-white transition hover:bg-ink">
          {crear ? <X size={15} /> : <UserPlus size={15} />}{crear ? "Cerrar" : "Crear usuario"}
        </button>
      </div>
      {crear && <CrearUsuario onCreado={() => { setCrear(false); onCambio(); }} />}
      <input type="search" value={buscar} onChange={(e) => { setBuscar(e.target.value); setCuantos(25); }} aria-label="Buscar usuario"
             placeholder={`Buscar entre ${estado.lista.length} usuarios por nombre o rol`} className={`${entrada} mb-3 max-w-md`} />
      {estado.cargando ? <Esqueleto filas={6} alto="h-10" /> : estado.error ? <ErrorTexto error={estado.error} /> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead><tr className="text-xs text-gray-strong"><th className="pb-3 font-medium">Usuario</th><th className="pb-3 font-medium">Rol</th><th className="pb-3 font-medium">Último acceso</th><th className="pb-3 font-medium">Estado</th></tr></thead>
            <tbody className="divide-y divide-cloud-card">
              {filtrados.slice(0, cuantos).map((u) => (
                <tr key={u.id}>
                  <td className="py-2.5 font-medium">{u.username}</td>
                  <td className="py-2.5 text-gray-strong">{u.rol_nombre || u.rol}</td>
                  <td className="py-2.5 text-gray-strong">{u.ultimo_acceso ? haceCuanto(u.ultimo_acceso) : "Nunca"}</td>
                  <td className="py-2.5">{u.bloqueada ? <Insignia grupo="bloqueado" etiqueta="Bloqueada" tamano="sm" /> : <Insignia grupo="libre" etiqueta="Activa" tamano="sm" />}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtrados.length > cuantos && (
            <button onClick={() => setCuantos((c) => c + 50)} className="mt-3 rounded-full bg-cloud-card px-4 py-2 text-sm font-medium transition hover:bg-hero-sky">
              Mostrar más ({filtrados.length - cuantos} restantes)
            </button>
          )}
          {filtrados.length === 0 && <p className="py-6 text-center text-sm text-gray-strong">Ningún usuario coincide.</p>}
        </div>
      )}
    </section>
  );
}

// Igual que app/api/usuarios.py:normalizar_usuario, para mostrar cómo quedará.
const normalizar = (t) => t.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").trim().toLowerCase()
  .replace(/[^a-z0-9_.-]+/g, ".").replace(/\.{2,}/g, ".").replace(/^[._-]+|[._-]+$/g, "");

function CrearUsuario({ onCreado }) {
  const { avisar } = useAvisos();
  const [roles, setRoles] = useState([]);
  const [datos, setDatos] = useState({ username: "", rol: "medico", password: "", documento_paciente: "" });
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { S.rolesDisponibles().then(setRoles).catch(() => {}); }, []);
  const campo = (k) => (e) => setDatos((d) => ({ ...d, [k]: e.target.value }));

  const enviar = async (e) => {
    e.preventDefault();
    if (!claveValida(datos.password)) { setError("La contraseña inicial no cumple las reglas marcadas en gris."); return; }
    setEnviando(true); setError(null);
    try {
      const cuerpo = { username: datos.username.trim(), rol: datos.rol, password: datos.password };
      if (datos.rol === "paciente") cuerpo.documento_paciente = datos.documento_paciente.trim();
      const creado = await S.crearUsuario(cuerpo);
      avisar(`Usuario ${creado?.username || cuerpo.username} creado. Deberá cambiar la contraseña al entrar.`);
      onCreado();
    } catch (err) { setError(err.message); }
    finally { setEnviando(false); }
  };

  return (
    <form onSubmit={enviar} className="anim-pop mb-6 grid gap-3 rounded-3xl bg-cloud-card/60 p-5 sm:grid-cols-2">
      <label className="text-sm">Usuario
        <input required minLength={3} value={datos.username} onChange={campo("username")} placeholder="Nombre o usuario, p. ej. Carlos Orozco" className={`${entrada} mt-1 bg-paper-white`} />
        {datos.username.trim() && normalizar(datos.username) !== datos.username.trim() && (
          <span className="mt-1 block text-xs text-gray-strong">Entrará como <b className="font-semibold text-ink">{normalizar(datos.username) || "…"}</b></span>
        )}
      </label>
      <label className="text-sm">Rol
        <select value={datos.rol} onChange={campo("rol")} className={`${entrada} mt-1 bg-paper-white`}>
          {(roles.length ? roles : [{ codigo: "medico", nombre: "Médico" }]).map((r) => <option key={r.codigo} value={r.codigo}>{r.nombre}</option>)}
        </select>
      </label>
      <CampoClave id="clave-inicial" etiqueta="Contraseña inicial (temporal)" valor={datos.password} reglas generar
                  onCambio={(v) => setDatos((d) => ({ ...d, password: v }))} claseEntrada={`${entrada} bg-paper-white`} />
      {datos.rol === "paciente" && (
        <label className="text-sm">Documento del paciente<input required value={datos.documento_paciente} onChange={campo("documento_paciente")} className={`${entrada} mt-1 bg-paper-white`} /></label>
      )}
      {error && <p role="alert" className="text-sm text-coral-ink sm:col-span-2">{error}</p>}
      <div className="sm:col-span-2">
        <button type="submit" disabled={enviando} className="flex items-center gap-2 rounded-full bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50">
          {enviando && <Loader2 size={15} className="anim-spin" />}Crear
        </button>
      </div>
    </form>
  );
}

function Bloqueadas({ lista, onCambio }) {
  const { avisar } = useAvisos();
  const tr = useTiempoReal();
  const [ocupado, setOcupado] = useState(null);
  const desbloquear = async (u) => {
    setOcupado(u.id);
    try { await S.desbloquear(u.id); avisar(`Cuenta ${u.username} desbloqueada. Quedó en la auditoría.`); tr?.marcarHito("cuenta_desbloqueada"); onCambio(); }
    catch (err) { avisar(err.message, "error"); }
    finally { setOcupado(null); }
  };
  return (
    <section className={tarjeta} aria-label="Cuentas bloqueadas">
      <h2 className="text-lg font-semibold">Cuentas bloqueadas</h2>
      <p className="mb-4 text-sm text-gray-strong">Se bloquean tras 3 intentos fallidos seguidos y solo un administrador puede liberarlas.</p>
      {lista.length === 0 ? (
        <div className="flex items-center gap-3 rounded-3xl bg-green-soft p-5 text-green-ink"><ShieldCheck size={20} aria-hidden="true" />No hay cuentas bloqueadas.</div>
      ) : (
        <ul className="space-y-2">
          {lista.map((u) => (
            <li key={u.id} className="anim-pop flex flex-col gap-3 rounded-3xl bg-cloud-card p-4 sm:flex-row sm:items-center sm:justify-between">
              <span className="flex items-center gap-3">
                <span className="grid size-10 place-items-center rounded-full bg-paper-white"><Lock size={17} className="text-slate-ink" aria-hidden="true" /></span>
                <span><span className="block font-semibold">{u.username}</span><span className="text-xs text-gray-strong">{u.rol_nombre || u.rol}</span></span>
              </span>
              <button onClick={() => desbloquear(u)} disabled={ocupado === u.id}
                      className="flex items-center justify-center gap-2 rounded-full bg-charcoal px-4 py-2 text-sm font-semibold text-white transition hover:bg-ink disabled:opacity-50">
                {ocupado === u.id ? <Loader2 size={15} className="anim-spin" /> : <Unlock size={15} />}Desbloquear
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const OPERACIONES = ["", "login", "bloqueo", "desbloqueo", "create", "update", "soft_delete", "restore",
                     "ia_analisis", "aprobacion", "rechazo", "remision_crear", "remision_aceptar", "factura", "alerta", "alerta_reconocida", "fhir_evento"];

function Auditoria() {
  const marcarHito = useTiempoReal()?.marcarHito;
  const [filtro, setFiltro] = useState({ operacion: "", entidad: "" });
  useEffect(() => { marcarHito?.("auditoria_vista"); }, [marcarHito]);
  const [estado, setEstado] = useState({ cargando: true, lista: [], error: null });
  const [nuevas, setNuevas] = useState(new Set());
  const vistas = useRef(null);
  const cargar = useCallback(async () => {
    setEstado((e) => ({ ...e, cargando: true }));
    try {
      const lista = await S.auditoria({ ...filtro, limite: 200 });
      // Las filas que no estaban antes entran resaltadas: la auditoría se ve "en vivo".
      if (vistas.current) setNuevas(new Set(lista.filter((a) => !vistas.current.has(a.id)).map((a) => a.id)));
      vistas.current = new Set(lista.map((a) => a.id));
      setEstado({ cargando: false, lista, error: null });
    } catch (err) { setEstado({ cargando: false, lista: [], error: err }); }
  }, [filtro]);
  useEffect(() => { cargar(); }, [cargar]);
  useEventos((ev) => { if (!ev.local) cargar(); });

  return (
    <section className={tarjeta} aria-label="Auditoría">
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="text-sm">Operación
          <select value={filtro.operacion} onChange={(e) => setFiltro((f) => ({ ...f, operacion: e.target.value }))} className={`${entrada} mt-1 w-48`}>
            {OPERACIONES.map((o) => <option key={o} value={o}>{o || "Todas"}</option>)}
          </select>
        </label>
        <label className="text-sm">Recurso
          <input value={filtro.entidad} onChange={(e) => setFiltro((f) => ({ ...f, entidad: e.target.value.trim() }))} placeholder="usuario, paciente…" className={`${entrada} mt-1 w-48`} />
        </label>
        <button onClick={cargar} aria-label="Recargar" className="grid size-10 place-items-center rounded-full bg-cloud-card transition hover:bg-hero-sky"><RefreshCw size={16} /></button>
      </div>
      {estado.cargando && estado.lista.length === 0 ? <Esqueleto filas={6} alto="h-10" /> : estado.error ? <ErrorTexto error={estado.error} /> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead><tr className="text-xs text-gray-strong">
              <th className="pb-3 font-medium">Fecha</th><th className="pb-3 font-medium">Usuario</th><th className="pb-3 font-medium">Operación</th>
              <th className="pb-3 font-medium">Recurso</th><th className="pb-3 font-medium">Resultado</th><th className="pb-3 font-medium">Origen</th>
            </tr></thead>
            <tbody className="divide-y divide-cloud-card">
              {estado.lista.map((a) => (
                <tr key={a.id} className={`transition-colors duration-1000 ${nuevas.has(a.id) ? "anim-pop bg-hero-sky" : a.resultado === "denegado" ? "bg-coral-soft/50" : ""}`}>
                  <td className="whitespace-nowrap py-2.5 text-xs text-gray-strong">{fechaYHora(a.timestamp)}</td>
                  <td className="py-2.5">{a.usuario_id ?? "—"} <span className="text-xs text-gray-strong">{a.rol}</span></td>
                  <td className="py-2.5"><span className="rounded-full bg-cloud-card px-2.5 py-0.5 text-xs font-medium">{a.operacion}</span></td>
                  <td className="py-2.5 text-xs"><span className="font-medium">{a.entidad}</span> <span className="font-mono text-gray-strong">{String(a.entidad_id ?? "").slice(0, 12)}</span></td>
                  <td className="py-2.5">{a.resultado === "denegado" ? <Insignia grupo="ocupado" etiqueta="Denegado" tamano="sm" /> : a.resultado === "exito" ? <Insignia grupo="libre" etiqueta="Éxito" tamano="sm" /> : <Insignia grupo="proceso" etiqueta={a.resultado} tamano="sm" />}</td>
                  <td className="py-2.5 font-mono text-xs text-gray-strong">{a.ip || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {estado.lista.length === 0 && <p className="py-6 text-center text-sm text-gray-strong">Sin registros para este filtro.</p>}
        </div>
      )}
    </section>
  );
}

const SERVICIOS = [["api", "API"], ["base_datos", "Base de datos"], ["servidor_fhir", "Servidor FHIR"], ["pacs", "PACS (imágenes)"], ["ml", "Servicio de IA"], ["mongo", "MongoDB (contabilidad)"]];

function Servicios() {
  const { datos, error, actualizado } = useSondeo(salud, 10000);
  return (
    <section className={tarjeta} aria-label="Estado de los servicios">
      <p className="mb-4 text-sm text-gray-strong">Consulta /salud cada 10 segundos{actualizado ? ` · última: ${haceCuanto(new Date(actualizado).toISOString())}` : ""}.</p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {SERVICIOS.map(([clave, nombre]) => {
          const valor = error && !datos ? "error" : datos?.[clave];
          // servidor_fhir llega como URL: si está, la API lo tiene configurado.
          const ok = valor === "ok" || (clave === "servidor_fhir" && typeof valor === "string" && valor.startsWith("http"));
          const sinDato = valor === undefined;
          return (
            <div key={clave} className="flex items-center justify-between gap-3 rounded-3xl bg-cloud-card p-4">
              <span className="text-sm font-medium">{nombre}</span>
              {sinDato ? <Insignia grupo="bloqueado" etiqueta="Sin reporte" tamano="sm" />
                : ok ? <Insignia grupo="libre" etiqueta="En línea" tamano="sm" />
                : <Insignia grupo="ocupado" etiqueta="Caído" tamano="sm" />}
            </div>
          );
        })}
      </div>
    </section>
  );
}

const ErrorTexto = ({ error }) => <p role="alert" className="text-sm text-coral-ink">{error.message}</p>;
