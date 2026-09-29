import { Activity, CheckCircle2, Clock, Lock } from "lucide-react";

/* Semáforo clínico de cuatro estados. Cada estado se comunica con color,
   ícono y texto: nunca solo con color (daltonismo). Las clases están escritas
   completas a propósito: Tailwind solo genera las que ve escritas. */
export const GRUPOS = {
  libre: {
    clave: "libre", etiqueta: "Disponible", icono: CheckCircle2,
    badge: "bg-green-soft text-green-ink", punto: "bg-green-deep",
    relleno: "bg-recovery-green", texto: "text-green-ink", borde: "border-green-deep",
  },
  ocupado: {
    clave: "ocupado", etiqueta: "Ocupado", icono: Activity,
    badge: "bg-coral-soft text-coral-ink", punto: "bg-coral-deep",
    relleno: "bg-coral-signal", texto: "text-coral-ink", borde: "border-coral-deep",
  },
  proceso: {
    clave: "proceso", etiqueta: "En proceso", icono: Clock,
    badge: "bg-gold-soft text-gold-ink", punto: "bg-gold-deep",
    relleno: "bg-signal-gold", texto: "text-gold-ink", borde: "border-gold-deep",
  },
  bloqueado: {
    clave: "bloqueado", etiqueta: "Bloqueado", icono: Lock,
    badge: "bg-slate-soft text-slate-ink", punto: "bg-body-gray",
    relleno: "bg-body-gray", texto: "text-slate-ink", borde: "border-body-gray",
  },
};

export const ORDEN_GRUPOS = ["libre", "ocupado", "proceso", "bloqueado"];

/* Estados que tiene cada recurso en la base de datos (ver recursos.py).
   `reservada` se pinta como ocupada: la cama ya no se puede asignar. `contaminada`
   espera limpieza terminal, así que es "en proceso". `aislamiento` no se puede
   asignar y no es una ocupación normal, así que se agrupa con los bloqueados. */
export const CAMA = {
  disponible:      { grupo: "libre",     etiqueta: "Disponible" },
  reservada:       { grupo: "ocupado",   etiqueta: "Reservada" },
  ocupada:         { grupo: "ocupado",   etiqueta: "Ocupada" },
  en_proceso_alta: { grupo: "proceso",   etiqueta: "Proceso de alta" },
  en_limpieza:     { grupo: "proceso",   etiqueta: "En limpieza" },
  contaminada:     { grupo: "proceso",   etiqueta: "Contaminada" },
  bloqueada:       { grupo: "bloqueado", etiqueta: "Bloqueada" },
  aislamiento:     { grupo: "bloqueado", etiqueta: "Aislamiento" },
};

export const QUIROFANO = {
  disponible:     { grupo: "libre",     etiqueta: "Disponible" },
  en_cirugia:     { grupo: "ocupado",   etiqueta: "En cirugía" },
  en_preparacion: { grupo: "proceso",   etiqueta: "En preparación" },
  en_limpieza:    { grupo: "proceso",   etiqueta: "En limpieza" },
  bloqueado:      { grupo: "bloqueado", etiqueta: "Bloqueado" },
};

export const infoCama = (estado) => CAMA[estado] || { grupo: "bloqueado", etiqueta: estado };
export const infoQx = (estado) => QUIROFANO[estado] || { grupo: "bloqueado", etiqueta: estado };

/* Una cama en estos estados tiene (o está por tener) un paciente encima. */
export const CAMA_CON_PACIENTE = ["ocupada", "reservada", "en_proceso_alta"];

/* Tipos de cama, en el orden en que se muestran. Los nombres cortos son para
   las pestañas; el nombre completo lo trae la API. */
export const TIPOS_CAMA = [
  { codigo: "UCI",        corto: "UCI adultos" },
  { codigo: "UCIN",       corto: "UCI neonatal" },
  { codigo: "INTERMEDIA", corto: "Intermedios" },
  { codigo: "GENERAL",    corto: "Hospitalización" },
  { codigo: "OBSERV_URG", corto: "Observación" },
];
export const cortoTipo = (codigo) => TIPOS_CAMA.find((t) => t.codigo === codigo)?.corto || codigo;

export const FILTROS_ESTADO = [
  { clave: "todas", etiqueta: "Todas" },
  { clave: "libre", etiqueta: "Disponibles" },
  { clave: "ocupado", etiqueta: "Ocupadas" },
  { clave: "proceso", etiqueta: "En proceso" },
  { clave: "bloqueado", etiqueta: "Bloqueadas" },
];
