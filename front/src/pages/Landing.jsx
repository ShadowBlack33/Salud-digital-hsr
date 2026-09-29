import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, BedDouble, CalendarClock, Database, HeartPulse, Lock, ScanLine, ShieldCheck, Workflow } from "lucide-react";
import Anillo from "../components/Anillo";
import Aparicion from "../components/Aparicion";
import Logo from "../components/Logo";
import { estaAutenticado } from "../api";
import { GRUPOS, ORDEN_GRUPOS } from "../lib/estados";
import { cop } from "../lib/format";
import { useAparicion, useContador } from "../lib/hooks";

const COSTO_HORA_UCI = 75000; // ≈ $1.800.000 por día / 24 h (comunicación personal, ver Evidencia)

/* ----------------------------------------------------------------- NAVEGACIÓN */
function Navegacion() {
  const dentro = estaAutenticado();
  const enlaces = [["#impacto", "Impacto"], ["#semaforo", "Semáforo"], ["#arquitectura", "Arquitectura"], ["#evidencia", "Evidencia"]];
  return (
    <header className="fixed inset-x-0 top-4 z-40 mx-auto w-[min(1120px,calc(100%-2rem))]">
      <nav aria-label="Principal" className="flex items-center justify-between rounded-[32px] bg-paper-white/80 py-2.5 pl-4 pr-2.5 shadow-lift backdrop-blur-xl">
        <Link to="/" aria-label="San Rafael OS, inicio"><Logo /></Link>
        <ul className="hidden items-center gap-1 md:flex">
          {enlaces.map(([href, texto]) => (
            <li key={href}><a href={href} className="rounded-full px-4 py-2 text-sm font-medium text-ink transition hover:bg-cloud-card">{texto}</a></li>
          ))}
        </ul>
        <Link to={dentro ? "/app" : "/login"} className="inline-flex items-center gap-2 rounded-full bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-ink">
          {dentro ? "Ir al centro de mando" : "Ingresar"}<ArrowRight size={15} aria-hidden="true" />
        </Link>
      </nav>
    </header>
  );
}

/* ---------------------------------------------------------- VISTA ILUSTRATIVA */
const PATRON = "ooolooooto" + "oolooootoo" + "olooooooto" + "loooltolol";
const TILE = {
  l: { fondo: "bg-green-soft", punto: "bg-green-deep", texto: "text-green-ink" },
  o: { fondo: "bg-coral-soft", punto: "bg-coral-deep", texto: "text-coral-ink" },
  t: { fondo: "bg-gold-soft", punto: "bg-gold-deep", texto: "text-gold-ink" },
};

function VistaIlustrativa() {
  const [tiles, setTiles] = useState(() => PATRON.split(""));
  const [ultimo, setUltimo] = useState(-1);

  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const id = setInterval(() => {
      setTiles((prev) => {
        const t = prev.slice();
        const r = Math.random();
        const [de, a] = r < 0.45 ? ["t", "l"] : r < 0.75 ? ["o", "t"] : ["l", "o"];
        const candidatos = t.map((c, i) => (c === de ? i : -1)).filter((i) => i >= 0);
        if (candidatos.length === 0 || (de === "l" && candidatos.length <= 3)) return prev;
        const i = candidatos[Math.floor(Math.random() * candidatos.length)];
        t[i] = a;
        setUltimo(i);
        return t;
      });
    }, 1800);
    return () => clearInterval(id);
  }, []);

  const n = (c) => tiles.filter((x) => x === c).length;
  const ocupadas = n("o");
  return (
    <div className="relative mx-auto mt-16 max-w-4xl" aria-hidden="true">
      <div className="anim-float rounded-[32px] bg-paper-white p-5 shadow-float sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs text-gray-strong">Camas · vista ilustrativa</p>
            <p className="text-lg font-semibold">UCI adultos</p>
          </div>
          <div className="flex gap-2 text-xs font-semibold">
            <span className="rounded-full bg-green-soft px-3 py-1 text-green-ink">{n("l")} libres</span>
            <span className="rounded-full bg-coral-soft px-3 py-1 text-coral-ink">{ocupadas} ocupadas</span>
            <span className="rounded-full bg-gold-soft px-3 py-1 text-gold-ink">{n("t")} en limpieza</span>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-8 gap-1.5 sm:grid-cols-10 sm:gap-2">
          {tiles.map((c, i) => (
            <div key={i} className={`flex h-10 flex-col justify-between rounded-lg p-1.5 transition-colors duration-700 sm:h-12 ${TILE[c].fondo} ${i === ultimo ? "ring-2 ring-green-deep" : ""}`}>
              <span className={`size-1.5 rounded-full transition-colors duration-700 ${TILE[c].punto}`} />
              <span className={`font-mono text-[9px] font-semibold ${TILE[c].texto}`}>{String(i + 1).padStart(3, "0")}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="absolute -bottom-8 left-4 hidden items-center gap-3 rounded-3xl bg-cloud-card p-3 pr-5 shadow-lift sm:flex lg:-left-10">
        <Anillo valor={(ocupadas / 40) * 100} tamano={64} grosor={8} color="var(--color-metric-blue)">
          <span className="text-sm font-semibold tabular-nums">{Math.round((ocupadas / 40) * 100)}%</span>
        </Anillo>
        <span className="text-left text-xs leading-tight text-gray-strong">Ocupación<span className="block text-sm font-semibold text-ink">UCI</span></span>
      </div>
      <div className="absolute -bottom-6 -right-2 hidden rounded-3xl bg-charcoal p-4 text-cloud-card shadow-lift sm:block lg:-right-8">
        <p className="text-xs text-cloud-card/60">Quirófano 09</p>
        <p className="text-sm font-semibold">Nefrectomía parcial</p>
        <span className="mt-2 inline-block rounded-full bg-coral-soft px-2.5 py-0.5 text-xs font-semibold text-coral-ink">+25 min de retraso</span>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------------- HERO */
function Hero() {
  return (
    <section className="relative overflow-hidden bg-gradient-to-b from-hero-sky via-[#eaf2ff] to-paper-white px-6 pb-28 pt-40">
      <div aria-hidden="true" className="anim-drift pointer-events-none absolute -left-24 top-24 size-[460px] rounded-full bg-sleep-lilac/30 blur-3xl" />
      <div aria-hidden="true" className="anim-drift pointer-events-none absolute -right-20 top-48 size-[420px] rounded-full bg-signal-gold/20 blur-3xl [animation-delay:-7s]" />
      <div className="relative mx-auto max-w-5xl text-center">
        <p className="anim-rise inline-flex items-center gap-2 rounded-full bg-paper-white/80 px-4 py-2 text-sm font-medium shadow-lift backdrop-blur">
          <HeartPulse size={16} className="text-coral-deep" aria-hidden="true" />Caso de estudio · Hospital San Rafael
        </p>
        <h1 className="anim-rise mt-7 text-[44px] font-semibold leading-[1.02] tracking-display [animation-delay:80ms] sm:text-6xl lg:text-[76px]">
          El centro de comando en tiempo real para camas, quirófanos y urgencias
        </h1>
        <p className="anim-rise mx-auto mt-7 max-w-2xl text-lg leading-relaxed text-gray-strong [animation-delay:160ms]">
          Un solo tablero para saber qué cama está libre, qué quirófano va retrasado y quién ocupa cada espacio, sin depender de llamadas. Pensado para reducir las cancelaciones que se pueden evitar.
        </p>
        <div className="anim-rise mt-9 flex flex-wrap items-center justify-center gap-3 [animation-delay:240ms]">
          <Link to="/login" className="inline-flex items-center gap-2 rounded-full bg-charcoal px-8 py-4 text-[15px] font-semibold text-white transition hover:-translate-y-0.5 hover:bg-ink">
            Probar la demostración<ArrowRight size={16} aria-hidden="true" />
          </Link>
          <a href="#arquitectura" className="rounded-full bg-paper-white px-8 py-4 text-[15px] font-semibold shadow-lift transition hover:-translate-y-0.5">Ver cómo está construido</a>
        </div>
        <VistaIlustrativa />
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------- IMPACTO */
function CostoQueCorre() {
  const [ref, visible] = useAparicion(0.4);
  const [seg, setSeg] = useState(0);
  useEffect(() => {
    if (!visible) return;
    const t0 = performance.now();
    const id = setInterval(() => setSeg((performance.now() - t0) / 1000), 100);
    return () => clearInterval(id);
  }, [visible]);
  return (
    <div ref={ref} className="mt-6 rounded-2xl bg-paper-white p-4">
      <p className="text-xs text-gray-strong">Simulación: lo que costaría una cama de UCI vacía desde que abriste esta página</p>
      <p className="mt-1 text-3xl font-semibold tabular-nums" aria-hidden="true">{cop((seg / 3600) * COSTO_HORA_UCI)}</p>
    </div>
  );
}

function Impacto() {
  const [ref, visible] = useAparicion(0.3);
  const evitables = useContador(62.5, visible);
  const admin = useContador(44, visible);
  const fuente = "text-xs text-gray-strong";
  return (
    <section id="impacto" className="mx-auto max-w-6xl scroll-mt-24 px-6 py-24">
      <Aparicion>
        <p className="text-sm font-semibold uppercase tracking-widest text-gray-strong">El problema, con números</p>
        <h2 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight tracking-display sm:text-5xl">La coordinación manual tiene un costo que casi nadie mide.</h2>
      </Aparicion>

      <div className="mt-12 grid gap-4 lg:grid-cols-12">
        <Aparicion className="lg:col-span-7">
          <article ref={ref} className="h-full rounded-[32px] bg-cloud-card p-8 sm:p-10">
            <div className="flex flex-col items-center gap-8 sm:flex-row">
              <Anillo valor={evitables} tamano={168} grosor={16} color="var(--color-metric-blue)" etiqueta="Entre 60 y 65 por ciento de las cancelaciones son evitables">
                <span className="text-[38px] font-semibold leading-none tabular-nums">60–65<span className="text-2xl">%</span></span>
              </Anillo>
              <div>
                <h3 className="text-2xl font-semibold tracking-display">La mayoría de las cancelaciones se podría evitar</h3>
                <p className="mt-3 leading-relaxed text-gray-strong">
                  Entre 60 % y 65 % de las cirugías canceladas se consideran evitables, y cerca de <strong className="font-semibold text-ink">{Math.round(admin)} %</strong> de las cancelaciones tiene causas administrativas, es decir, de coordinación.
                </p>
                <p className={`mt-4 ${fuente}`}>Segnini et al., Iatreia, 2022; Domínguez-Lozano et al., 2020.</p>
              </div>
            </div>
          </article>
        </Aparicion>

        <Aparicion retraso={120} className="lg:col-span-5">
          <article className="h-full rounded-[32px] bg-cloud-card p-8 sm:p-10">
            <BedDouble size={28} className="text-metric-blue" aria-hidden="true" />
            <h3 className="mt-4 text-2xl font-semibold tracking-display">Una cama de UCI vacía cuesta ≈ {cop(COSTO_HORA_UCI)} por hora</h3>
            <p className="mt-3 leading-relaxed text-gray-strong">Con un costo cercano a $1.800.000 por día, cada hora que espera una llamada es dinero que no se recupera.</p>
            <CostoQueCorre />
            <p className={`mt-3 ${fuente}`}>Aproximado, según enfermería de alta complejidad en Cali (comunicación personal, 2026).</p>
          </article>
        </Aparicion>

        <Aparicion retraso={60} className="lg:col-span-5">
          <article className="h-full rounded-[32px] bg-cloud-card p-8 sm:p-10">
            <CalendarClock size={28} className="text-coral-deep" aria-hidden="true" />
            <p className="mt-4 text-[40px] font-semibold leading-none tracking-tight tabular-nums">$128.120.642</p>
            <p className="mt-1 text-sm font-medium text-gray-strong">pesos colombianos</p>
            <p className="mt-4 leading-relaxed text-gray-strong">Dejados de facturar en un solo trimestre por cirugías canceladas en una clínica de Popayán.</p>
            <p className={`mt-4 ${fuente}`}>Muñoz-Caicedo et al., Rev. Fac. Med., 2019.</p>
          </article>
        </Aparicion>

        <Aparicion retraso={180} className="lg:col-span-7">
          <article className="h-full rounded-[32px] bg-cloud-card p-8 sm:p-10">
            <Workflow size={28} className="text-sleep-lilac" aria-hidden="true" />
            <h3 className="mt-4 text-2xl font-semibold tracking-display">Habla el idioma de los sistemas clínicos</h3>
            <p className="mt-3 max-w-xl leading-relaxed text-gray-strong">El estado de cada cama y quirófano se publica como <span className="font-mono text-sm text-ink">Location.operationalStatus</span> en HL7 FHIR R4, con esta equivalencia:</p>
            <ul className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {[["Disponible", "U"], ["Ocupada", "O"], ["En limpieza", "H"], ["Bloqueada", "C"], ["Contaminada", "K"], ["Aislamiento", "I"]].map(([e, c]) => (
                <li key={e} className="flex items-center justify-between rounded-2xl bg-paper-white px-4 py-3 text-sm">
                  <span>{e}</span><span className="font-mono font-semibold">{c}</span>
                </li>
              ))}
            </ul>
          </article>
        </Aparicion>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------- SEMÁFORO */
const DESCRIPCION = {
  libre: { texto: "Lista para recibir un paciente o una cirugía.", estados: "Cama disponible · Quirófano disponible" },
  ocupado: { texto: "Con un paciente, reservada o con una cirugía en curso.", estados: "Cama ocupada o reservada · Quirófano en cirugía" },
  proceso: { texto: "Se está preparando: pronto cambia de estado.", estados: "Limpieza · Contaminada · Proceso de alta · En preparación" },
  bloqueado: { texto: "Fuera de servicio: no se puede asignar.", estados: "Bloqueada · Aislamiento · Quirófano bloqueado" },
};

function Semaforo() {
  return (
    <section id="semaforo" className="mx-auto max-w-6xl scroll-mt-24 px-6 pb-24">
      <Aparicion>
        <p className="text-sm font-semibold uppercase tracking-widest text-gray-strong">Camas y quirófanos</p>
        <h2 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight tracking-display sm:text-5xl">Un semáforo que se entiende en un segundo.</h2>
        <p className="mt-4 max-w-2xl text-lg text-gray-strong">Ocho estados de cama y cinco de quirófano se resumen en cuatro. Cada uno se muestra con color, ícono y texto, para que nadie dependa solo del color.</p>
      </Aparicion>
      <ul className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {ORDEN_GRUPOS.map((clave, i) => {
          const g = GRUPOS[clave];
          const Icono = g.icono;
          return (
            <Aparicion key={clave} retraso={i * 80}>
              <li className="h-full rounded-[28px] bg-cloud-card p-7 transition duration-300 hover:-translate-y-1 hover:shadow-lift">
                <span className={`grid size-12 place-items-center rounded-2xl ${g.badge}`}><Icono size={24} aria-hidden="true" /></span>
                <h3 className="mt-5 text-xl font-semibold tracking-display">{g.etiqueta}</h3>
                <p className="mt-2 leading-relaxed text-gray-strong">{DESCRIPCION[clave].texto}</p>
                <p className="mt-4 text-xs font-medium text-slate-ink">{DESCRIPCION[clave].estados}</p>
              </li>
            </Aparicion>
          );
        })}
      </ul>
    </section>
  );
}

/* ---------------------------------------------------------------- ARQUITECTURA */
function Cifra({ meta, etiqueta, activo }) {
  const v = useContador(meta, activo);
  return (
    <div className="border-t border-white/15 pt-5">
      <p className="text-5xl font-semibold tracking-tight tabular-nums">{Math.round(v).toLocaleString("es-CO")}</p>
      <p className="mt-2 text-sm text-cloud-card/70">{etiqueta}</p>
    </div>
  );
}

function Arquitectura() {
  const [ref, visible] = useAparicion(0.25);
  const columnas = [
    { icono: Lock, titulo: "Datos protegidos", puntos: ["Cédula, nombre y teléfono cifrados con AES-256-GCM", "Búsqueda por documento sin descifrar la base (índice ciego)", "Auditoría que no se puede editar y bloqueo tras 3 intentos fallidos"] },
    { icono: Database, titulo: "Estándares clínicos", puntos: ["HL7 FHIR R4 sobre un servidor HAPI", "CIE-10 para diagnósticos y CUPS para procedimientos", "14 roles con permisos en dos niveles"] },
    { icono: ScanLine, titulo: "Imágenes y tiempo real", puntos: ["Servidor PACS Orthanc con imágenes DICOM", "Visor con brillo, contraste y zoom", "Tablero que se actualiza solo cada 15 segundos"] },
  ];
  return (
    <section id="arquitectura" ref={ref} className="mx-auto max-w-6xl scroll-mt-24 px-6 pb-24">
      <div className="rounded-[40px] bg-charcoal p-8 text-cloud-card sm:p-14">
        <Aparicion>
          <p className="text-sm font-semibold uppercase tracking-widest text-cloud-card/60">Arquitectura</p>
          <h2 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight tracking-display text-white sm:text-5xl">Construido y probado de extremo a extremo.</h2>
        </Aparicion>
        <div className="mt-12 grid grid-cols-2 gap-6 lg:grid-cols-4">
          <Cifra meta={300} etiqueta="camas, en 5 tipos de cuidado" activo={visible} />
          <Cifra meta={13} etiqueta="quirófanos con capacidades propias" activo={visible} />
          <Cifra meta={14} etiqueta="roles de usuario" activo={visible} />
          <Cifra meta={63} etiqueta="pruebas automáticas de extremo a extremo" activo={visible} />
        </div>
        <ul className="mt-14 grid gap-4 lg:grid-cols-3">
          {columnas.map(({ icono: Icono, titulo, puntos }) => (
            <li key={titulo} className="rounded-[28px] bg-white/[0.06] p-7">
              <Icono size={24} className="text-sleep-lilac" aria-hidden="true" />
              <h3 className="mt-4 text-xl font-semibold text-white">{titulo}</h3>
              <ul className="mt-4 space-y-2.5 text-sm leading-relaxed text-cloud-card/80">
                {puntos.map((p) => <li key={p} className="flex gap-2.5"><ShieldCheck size={16} className="mt-0.5 shrink-0 text-recovery-green" aria-hidden="true" />{p}</li>)}
              </ul>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------- EVIDENCIA */
const FUENTES = [
  ["Segnini et al. (2022). Cancelación de cirugías programadas en Colombia. Iatreia, 35(2).", "2,7 % a 7,6 % de cancelación; 60 % a 65 % evitables"],
  ["Domínguez-Lozano et al. (2020). Cancelación de cirugías en una institución de Barranquilla.", "Causas administrativas cerca del 38 %"],
  ["Muñoz-Caicedo et al. (2019). Costos de la cancelación de cirugías. Rev. Fac. Med.", "$128.120.642 COP dejados de facturar en un trimestre"],
  ["Enfermería de alta complejidad en Cali (comunicación personal, 2026).", "Costo de una cama UCI, aproximado; reglas de asignación de cama y prioridad de urgencias"],
];

function Evidencia() {
  return (
    <section id="evidencia" className="mx-auto max-w-6xl scroll-mt-24 px-6 pb-24">
      <Aparicion>
        <p className="text-sm font-semibold uppercase tracking-widest text-gray-strong">Evidencia</p>
        <h2 className="mt-3 text-4xl font-semibold leading-tight tracking-display">De dónde salen los números.</h2>
      </Aparicion>
      <ul className="mt-8 divide-y divide-cloud-card rounded-[28px] bg-cloud-card p-2">
        {FUENTES.map(([fuente, dato]) => (
          <li key={fuente} className="grid gap-1 rounded-3xl p-5 sm:grid-cols-[1.4fr_1fr] sm:gap-8">
            <span className="text-[15px] font-medium">{fuente}</span>
            <span className="text-sm text-gray-strong">{dato}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/* ------------------------------------------------------------------------ CIERRE */
function Cierre() {
  return (
    <section className="mx-auto max-w-6xl px-6 pb-24">
      <div className="relative overflow-hidden rounded-[40px] bg-gradient-to-br from-hero-sky to-[#eee8ff] p-10 text-center sm:p-16">
        <h2 className="mx-auto max-w-3xl text-4xl font-semibold leading-tight tracking-display sm:text-5xl">Que la próxima cama libre no espere a que alguien conteste el teléfono.</h2>
        <Link to="/login" className="mt-8 inline-flex items-center gap-2 rounded-full bg-charcoal px-8 py-4 text-[15px] font-semibold text-white transition hover:-translate-y-0.5 hover:bg-ink">
          Entrar a la demostración<ArrowRight size={16} aria-hidden="true" />
        </Link>
      </div>
    </section>
  );
}

export default function Landing() {
  return (
    <div className="bg-paper-white">
      <Navegacion />
      <main>
        <Hero />
        <Impacto />
        <Semaforo />
        <Arquitectura />
        <Evidencia />
        <Cierre />
      </main>
      <footer className="border-t border-cloud-card px-6 py-8 text-center text-sm text-gray-strong">
        Hospital San Rafael es un caso de estudio hipotético. Los datos del sistema son sintéticos. Proyecto integrador · Sistemas en Salud Digital · Universidad Autónoma de Occidente · 2026
      </footer>
    </div>
  );
}
