-- ============================================================================
-- ESQUEMA COMPLETO de Pulso (Hospital San Rafael) en un solo archivo.
--
-- Reemplaza a las migraciones db/historial/01..15: es el estado final que
-- dejan aplicadas en orden (estructura, funciones, triggers, extensión
-- vector del RAG) más los catálogos (roles, permisos, especialidades, EPS,
-- CIE-10, procedimientos, causas de cancelación, servicios, tipos de cama).
-- No trae datos de personas: esos los genera scripts/generar_datos.py, que
-- también crea las cuentas de demostración (medico01, especialista01, ...).
--
-- Base nueva, en orden:
--   python scripts/aplicar_sql.py db/esquema_completo.sql
--   python scripts/generar_datos.py --salida db/03_datos_sinteticos.sql
--   python scripts/aplicar_sql.py db/03_datos_sinteticos.sql
--   (o con psql: psql "$URL" -v ON_ERROR_STOP=1 -f db/esquema_completo.sql)
--
-- Se generó con pg_dump sobre una base PostgreSQL 16 + pgvector con
-- 01, 02, los datos sintéticos y 04, 06..15 aplicados (el orden del CI), sin
-- los datos de las tablas de personas, y se verificó que una base creada
-- desde este archivo queda con la misma estructura y pasa las pruebas.
-- Un cambio nuevo de estructura va como migración numerada (db/16_...sql)
-- y luego se incorpora aquí.
-- ============================================================================

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
-- (sin set_config('search_path', '', false) de pg_dump: con el pooler de Neon
-- ese ajuste quedaba pegado a la conexión y afectaba a los siguientes clientes;
-- todos los nombres de este archivo ya van con su esquema)
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: citext; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public;


--
-- Name: EXTENSION citext; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION citext IS 'data type for case-insensitive character strings';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: fn_auditoria_inmutable(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_auditoria_inmutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'log_auditoria es append-only: operación % no permitida', TG_OP;
END;
$$;


--
-- Name: fn_reportes_ia_inmutables(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_reportes_ia_inmutables() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Los reportes de IA no se borran (R10): queda como evidencia el reporte %', OLD.id;
    END IF;
    IF OLD.estado <> 'pendiente' AND NEW.estado IS DISTINCT FROM OLD.estado THEN
        RAISE EXCEPTION 'El reporte % ya está % y no puede cambiar de estado', OLD.id, OLD.estado;
    END IF;
    IF NEW.payload_enviado IS DISTINCT FROM OLD.payload_enviado THEN
        RAISE EXCEPTION 'El payload enviado al modelo no se modifica (reporte %)', OLD.id;
    END IF;
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: agenda_consulta_externa; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agenda_consulta_externa (
    id integer NOT NULL,
    paciente_id character(64) NOT NULL,
    medico_general_id integer,
    especialista_id integer,
    modulo character varying(20),
    hora_programada timestamp with time zone NOT NULL,
    duracion_programada_min smallint DEFAULT 20 NOT NULL,
    hora_real_inicio timestamp with time zone,
    hora_real_fin timestamp with time zone,
    estado character varying(20) DEFAULT 'planned'::character varying NOT NULL,
    activo boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by integer
);


--
-- Name: agenda_consulta_externa_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agenda_consulta_externa_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agenda_consulta_externa_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agenda_consulta_externa_id_seq OWNED BY public.agenda_consulta_externa.id;


--
-- Name: alertas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alertas (
    id bigint NOT NULL,
    tipo character varying(40) NOT NULL,
    severidad character varying(15) DEFAULT 'media'::character varying NOT NULL,
    titulo character varying(200) NOT NULL,
    mensaje text,
    entidad_tipo character varying(20),
    entidad_id integer,
    dirigida_a_rol integer,
    dirigida_a_usuario integer,
    leida_at timestamp with time zone,
    resuelta_at timestamp with time zone,
    resuelta_por integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    paciente_id character(64),
    estado character varying(12) DEFAULT 'activa'::character varying NOT NULL,
    nota_reconocimiento text,
    reconocida_por integer,
    reconocida_at timestamp with time zone,
    escalada_at timestamp with time zone,
    reporte_id bigint,
    CONSTRAINT ck_alerta_estado CHECK (((estado)::text = ANY ((ARRAY['activa'::character varying, 'reconocida'::character varying])::text[])))
);


--
-- Name: alertas_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.alertas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: alertas_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.alertas_id_seq OWNED BY public.alertas.id;


--
-- Name: camas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.camas (
    id integer NOT NULL,
    codigo character varying(20) NOT NULL,
    tipo_cama_id integer NOT NULL,
    servicio_id integer NOT NULL,
    estado character varying(20) DEFAULT 'disponible'::character varying NOT NULL,
    estado_desde timestamp with time zone DEFAULT now() NOT NULL,
    fhir_location_id character varying(64),
    activo boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by integer,
    CONSTRAINT ck_camas_estado CHECK (((estado)::text = ANY ((ARRAY['disponible'::character varying, 'reservada'::character varying, 'ocupada'::character varying, 'en_proceso_alta'::character varying, 'en_limpieza'::character varying, 'bloqueada'::character varying, 'contaminada'::character varying, 'aislamiento'::character varying])::text[])))
);


--
-- Name: camas_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.camas_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: camas_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.camas_id_seq OWNED BY public.camas.id;


--
-- Name: cancelaciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cancelaciones (
    id integer NOT NULL,
    encuentro_id integer NOT NULL,
    causa_id integer NOT NULL,
    detalle text,
    minutos_anticipacion integer,
    reprogramada boolean DEFAULT false NOT NULL,
    encuentro_nuevo_id integer,
    costo_estimado_cop numeric(12,2),
    registrado_por integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: cancelaciones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cancelaciones_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cancelaciones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cancelaciones_id_seq OWNED BY public.cancelaciones.id;


--
-- Name: catalogo_causas_cancelacion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.catalogo_causas_cancelacion (
    id integer NOT NULL,
    codigo character varying(30) NOT NULL,
    descripcion character varying(200) NOT NULL,
    responsable character varying(20) NOT NULL,
    origen character varying(20),
    evitable boolean DEFAULT true,
    CONSTRAINT ck_causa_responsable CHECK (((responsable)::text = ANY ((ARRAY['paciente'::character varying, 'prestador'::character varying, 'asegurador'::character varying])::text[])))
);


--
-- Name: catalogo_causas_cancelacion_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.catalogo_causas_cancelacion_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: catalogo_causas_cancelacion_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.catalogo_causas_cancelacion_id_seq OWNED BY public.catalogo_causas_cancelacion.id;


--
-- Name: catalogo_procedimientos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.catalogo_procedimientos (
    id integer NOT NULL,
    codigo_interno character varying(20) NOT NULL,
    nombre character varying(200) NOT NULL,
    codigo_snomed character varying(20),
    codigo_cups character varying(20),
    especialidad_id integer NOT NULL,
    duracion_estimada_min smallint NOT NULL,
    duracion_desviacion_min smallint DEFAULT 20 NOT NULL,
    tipo_cama_requerida_id integer NOT NULL,
    requiere_arco_c boolean DEFAULT false NOT NULL,
    complejidad smallint DEFAULT 2 NOT NULL,
    tarifa_referencia_cop numeric(12,2),
    activo boolean DEFAULT true NOT NULL
);


--
-- Name: catalogo_procedimientos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.catalogo_procedimientos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: catalogo_procedimientos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.catalogo_procedimientos_id_seq OWNED BY public.catalogo_procedimientos.id;


--
-- Name: diagnosticos_cie10; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diagnosticos_cie10 (
    id integer NOT NULL,
    codigo character varying(10) NOT NULL,
    descripcion character varying(250) NOT NULL,
    capitulo character varying(120)
);


--
-- Name: diagnosticos_cie10_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.diagnosticos_cie10_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: diagnosticos_cie10_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.diagnosticos_cie10_id_seq OWNED BY public.diagnosticos_cie10.id;


--
-- Name: encuentros; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.encuentros (
    id integer NOT NULL,
    uuid uuid DEFAULT gen_random_uuid() NOT NULL,
    paciente_id character(64) NOT NULL,
    tipo character varying(25) NOT NULL,
    estado character varying(20) DEFAULT 'planned'::character varying NOT NULL,
    origen character varying(15) DEFAULT 'electiva'::character varying NOT NULL,
    prioridad_clinica smallint DEFAULT 3 NOT NULL,
    nivel_triage smallint,
    diagnostico_cie10_id integer,
    procedimiento_id integer,
    quirofano_id integer,
    cama_id integer,
    medico_responsable_id integer,
    anestesiologo_id integer,
    hora_programada_inicio timestamp with time zone,
    hora_programada_fin timestamp with time zone,
    hora_real_inicio timestamp with time zone,
    hora_real_fin timestamp with time zone,
    minutos_desviacion integer GENERATED ALWAYS AS (
CASE
    WHEN ((hora_real_fin IS NOT NULL) AND (hora_programada_fin IS NOT NULL)) THEN ((EXTRACT(epoch FROM (hora_real_fin - hora_programada_fin)))::integer / 60)
    ELSE NULL::integer
END) STORED,
    fhir_encounter_id character varying(64),
    observaciones_texto text,
    activo boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by integer,
    updated_at timestamp with time zone,
    CONSTRAINT ck_enc_estado CHECK (((estado)::text = ANY ((ARRAY['planned'::character varying, 'arrived'::character varying, 'triaged'::character varying, 'in-progress'::character varying, 'onleave'::character varying, 'finished'::character varying, 'cancelled'::character varying])::text[]))),
    CONSTRAINT ck_enc_origen CHECK (((origen)::text = ANY ((ARRAY['electiva'::character varying, 'urgencia'::character varying])::text[]))),
    CONSTRAINT ck_enc_tipo CHECK (((tipo)::text = ANY ((ARRAY['urgencias'::character varying, 'cirugia'::character varying, 'hospitalizacion'::character varying, 'consulta_externa'::character varying])::text[])))
);


--
-- Name: encuentros_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.encuentros_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: encuentros_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.encuentros_id_seq OWNED BY public.encuentros.id;


--
-- Name: eps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.eps (
    id integer NOT NULL,
    codigo character varying(20) NOT NULL,
    nombre character varying(150) NOT NULL,
    regimen character varying(20),
    activo boolean DEFAULT true NOT NULL
);


--
-- Name: eps_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.eps_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: eps_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.eps_id_seq OWNED BY public.eps.id;


--
-- Name: especialidades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.especialidades (
    id integer NOT NULL,
    codigo character varying(30) NOT NULL,
    nombre character varying(120) NOT NULL,
    codigo_snomed character varying(20),
    requiere_uci boolean DEFAULT false NOT NULL,
    activo boolean DEFAULT true NOT NULL
);


--
-- Name: especialidades_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.especialidades_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: especialidades_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.especialidades_id_seq OWNED BY public.especialidades.id;


--
-- Name: eventos_estado; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.eventos_estado (
    id bigint NOT NULL,
    entidad_tipo character varying(20) NOT NULL,
    entidad_id integer NOT NULL,
    estado_anterior character varying(30),
    estado_nuevo character varying(30) NOT NULL,
    duracion_estado_anterior_min integer,
    motivo character varying(200),
    usuario_id integer,
    origen character varying(20) DEFAULT 'manual'::character varying NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    entidad_subtipo character varying(30)
);


--
-- Name: eventos_estado_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.eventos_estado_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: eventos_estado_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.eventos_estado_id_seq OWNED BY public.eventos_estado.id;


--
-- Name: eventos_fhir; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.eventos_fhir (
    id bigint NOT NULL,
    recurso_tipo character varying(30) NOT NULL,
    recurso_id character varying(64) NOT NULL,
    version character varying(20) DEFAULT ''::character varying NOT NULL,
    paciente_id character(64),
    resultado character varying(20) DEFAULT 'procesado'::character varying NOT NULL,
    recibido_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: eventos_fhir_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.eventos_fhir_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: eventos_fhir_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.eventos_fhir_id_seq OWNED BY public.eventos_fhir.id;


--
-- Name: historial_cambios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.historial_cambios (
    id bigint NOT NULL,
    entidad_tipo character varying(40) NOT NULL,
    entidad_id character varying(64) NOT NULL,
    version integer NOT NULL,
    campo character varying(60) NOT NULL,
    valor_anterior text,
    valor_nuevo text,
    era_cifrado boolean DEFAULT false NOT NULL,
    usuario_id integer,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: historial_cambios_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.historial_cambios_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: historial_cambios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.historial_cambios_id_seq OWNED BY public.historial_cambios.id;


--
-- Name: log_auditoria; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.log_auditoria (
    id bigint NOT NULL,
    usuario_id integer,
    rol_codigo character varying(40),
    entidad_tipo character varying(40) NOT NULL,
    entidad_id character varying(64),
    operacion character varying(20) NOT NULL,
    resultado character varying(15) DEFAULT 'exito'::character varying NOT NULL,
    valor_anterior jsonb,
    valor_nuevo jsonb,
    ip_origen inet,
    user_agent text,
    endpoint character varying(200),
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: log_auditoria_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.log_auditoria_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: log_auditoria_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.log_auditoria_id_seq OWNED BY public.log_auditoria.id;


--
-- Name: notificaciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notificaciones (
    id bigint NOT NULL,
    usuario_id integer NOT NULL,
    tipo character varying(40) NOT NULL,
    mensaje text NOT NULL,
    paciente_id character(64),
    datos jsonb DEFAULT '{}'::jsonb NOT NULL,
    leida boolean DEFAULT false NOT NULL,
    leida_at timestamp with time zone,
    fecha timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: notificaciones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.notificaciones_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: notificaciones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notificaciones_id_seq OWNED BY public.notificaciones.id;


--
-- Name: observaciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.observaciones (
    id integer NOT NULL,
    uuid uuid DEFAULT gen_random_uuid() NOT NULL,
    encuentro_id integer NOT NULL,
    paciente_id character(64) NOT NULL,
    categoria character varying(25) DEFAULT 'vital-signs'::character varying NOT NULL,
    codigo_loinc character varying(20) NOT NULL,
    display_loinc character varying(150),
    valor_numerico numeric(12,3),
    valor_texto character varying(200),
    unidad_ucum character varying(20),
    estado character varying(20) DEFAULT 'final'::character varying NOT NULL,
    es_critico boolean DEFAULT false NOT NULL,
    fecha_hora timestamp with time zone DEFAULT now() NOT NULL,
    registrado_por integer,
    fhir_observation_id character varying(64),
    activo boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by integer,
    CONSTRAINT ck_obs_estado CHECK (((estado)::text = ANY ((ARRAY['registered'::character varying, 'preliminary'::character varying, 'final'::character varying, 'amended'::character varying, 'cancelled'::character varying])::text[])))
);


--
-- Name: observaciones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.observaciones_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: observaciones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.observaciones_id_seq OWNED BY public.observaciones.id;


--
-- Name: pacientes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pacientes (
    documento_bidx character(64) NOT NULL,
    uuid uuid DEFAULT gen_random_uuid() NOT NULL,
    tipo_documento character varying(5) NOT NULL,
    documento_cifrado bytea NOT NULL,
    nombre_cifrado bytea NOT NULL,
    apellido_cifrado bytea NOT NULL,
    telefono_cifrado bytea,
    email_cifrado bytea,
    direccion_cifrada bytea,
    fecha_nacimiento date NOT NULL,
    sexo character(1) NOT NULL,
    eps_id integer,
    tiene_comorbilidades boolean DEFAULT false NOT NULL,
    riesgo_asa smallint,
    consentimiento_datos boolean DEFAULT false NOT NULL,
    consentimiento_fecha timestamp with time zone,
    fhir_patient_id character varying(64),
    activo boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by integer,
    updated_at timestamp with time zone,
    CONSTRAINT ck_pacientes_sexo CHECK ((sexo = ANY (ARRAY['M'::bpchar, 'F'::bpchar, 'O'::bpchar])))
);


--
-- Name: permisos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.permisos (
    id integer NOT NULL,
    codigo character varying(80) NOT NULL,
    recurso character varying(40) NOT NULL,
    accion character varying(30) NOT NULL,
    alcance character varying(20) DEFAULT 'all'::character varying NOT NULL,
    descripcion text
);


--
-- Name: permisos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.permisos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: permisos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.permisos_id_seq OWNED BY public.permisos.id;


--
-- Name: personal; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.personal (
    id integer NOT NULL,
    uuid uuid DEFAULT gen_random_uuid() NOT NULL,
    documento_cifrado bytea NOT NULL,
    documento_bidx character(64) NOT NULL,
    nombre_cifrado bytea NOT NULL,
    apellido_cifrado bytea NOT NULL,
    telefono_cifrado bytea,
    email_cifrado bytea,
    registro_profesional_cifrado bytea,
    especialidad_id integer,
    tipo_personal character varying(40) NOT NULL,
    tiempo_desplazamiento_min smallint,
    turno_habitual character varying(20),
    activo boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by integer,
    updated_at timestamp with time zone
);


--
-- Name: personal_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.personal_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: personal_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.personal_id_seq OWNED BY public.personal.id;


--
-- Name: predicciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.predicciones (
    id bigint NOT NULL,
    modelo character varying(50) NOT NULL,
    version_modelo character varying(20),
    entidad_tipo character varying(20) NOT NULL,
    entidad_id integer NOT NULL,
    valor_predicho numeric(12,3),
    probabilidad numeric(5,4),
    intervalo_inferior numeric(12,3),
    intervalo_superior numeric(12,3),
    features_usadas jsonb,
    valor_real numeric(12,3),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: predicciones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.predicciones_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: predicciones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.predicciones_id_seq OWNED BY public.predicciones.id;


--
-- Name: quirofanos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quirofanos (
    id integer NOT NULL,
    codigo character varying(20) NOT NULL,
    nombre character varying(80),
    servicio_id integer,
    tiene_arco_c boolean DEFAULT false NOT NULL,
    tiene_circulacion_extracorporea boolean DEFAULT false NOT NULL,
    estado character varying(20) DEFAULT 'disponible'::character varying NOT NULL,
    estado_desde timestamp with time zone DEFAULT now() NOT NULL,
    fhir_location_id character varying(64),
    activo boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by integer,
    CONSTRAINT ck_quirofanos_estado CHECK (((estado)::text = ANY ((ARRAY['disponible'::character varying, 'en_preparacion'::character varying, 'en_cirugia'::character varying, 'en_limpieza'::character varying, 'bloqueado'::character varying])::text[])))
);


--
-- Name: quirofanos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.quirofanos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: quirofanos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.quirofanos_id_seq OWNED BY public.quirofanos.id;


--
-- Name: rag_consultas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rag_consultas (
    id bigint NOT NULL,
    usuario_id integer NOT NULL,
    rol text,
    pregunta text NOT NULL,
    paciente_id text,
    metodo text NOT NULL,
    fuentes jsonb DEFAULT '[]'::jsonb NOT NULL,
    abstencion boolean NOT NULL,
    confianza real,
    generador text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: rag_consultas_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rag_consultas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rag_consultas_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rag_consultas_id_seq OWNED BY public.rag_consultas.id;


--
-- Name: rag_fragmentos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rag_fragmentos (
    id bigint NOT NULL,
    documento_id text NOT NULL,
    tipo text NOT NULL,
    paciente_id text,
    estado text DEFAULT 'aprobado'::text NOT NULL,
    titulo text NOT NULL,
    seccion text DEFAULT ''::text NOT NULL,
    fuente text DEFAULT ''::text NOT NULL,
    texto text NOT NULL,
    embedding public.vector(384),
    modelo_embedding text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT rag_fragmentos_check CHECK ((((tipo = 'guia'::text) AND (paciente_id IS NULL)) OR ((tipo = 'historia'::text) AND (paciente_id IS NOT NULL)))),
    CONSTRAINT rag_fragmentos_estado_check CHECK ((estado = ANY (ARRAY['aprobado'::text, 'pendiente'::text, 'rechazado'::text]))),
    CONSTRAINT rag_fragmentos_tipo_check CHECK ((tipo = ANY (ARRAY['guia'::text, 'historia'::text])))
);


--
-- Name: rag_fragmentos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rag_fragmentos_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rag_fragmentos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rag_fragmentos_id_seq OWNED BY public.rag_fragmentos.id;


--
-- Name: remisiones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.remisiones (
    id integer NOT NULL,
    paciente_id character(64) NOT NULL,
    medico_id integer,
    remitido_por integer NOT NULL,
    especialista_id integer NOT NULL,
    motivo text NOT NULL,
    prioridad character varying(12) DEFAULT 'prioritaria'::character varying NOT NULL,
    estado character varying(12) DEFAULT 'pendiente'::character varying NOT NULL,
    respuesta text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    aceptada_at timestamp with time zone,
    aceptada_por integer,
    cerrada_at timestamp with time zone,
    cerrada_por integer,
    CONSTRAINT ck_rem_estado CHECK (((estado)::text = ANY ((ARRAY['pendiente'::character varying, 'aceptada'::character varying, 'rechazada'::character varying, 'atendida'::character varying])::text[]))),
    CONSTRAINT ck_rem_prioridad CHECK (((prioridad)::text = ANY ((ARRAY['rutinaria'::character varying, 'prioritaria'::character varying, 'urgente'::character varying])::text[])))
);


--
-- Name: remisiones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.remisiones_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: remisiones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.remisiones_id_seq OWNED BY public.remisiones.id;


--
-- Name: reportes_ia; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reportes_ia (
    id bigint NOT NULL,
    paciente_id character(64) NOT NULL,
    creado_por integer NOT NULL,
    estado character varying(12) DEFAULT 'pendiente'::character varying NOT NULL,
    resultado jsonb,
    probabilidad numeric(5,4),
    critico boolean DEFAULT false NOT NULL,
    payload_enviado jsonb NOT NULL,
    modelo_version character varying(30),
    observaciones text,
    revisado_por integer,
    revisado_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_rep_estado CHECK (((estado)::text = ANY ((ARRAY['pendiente'::character varying, 'aprobado'::character varying, 'rechazado'::character varying])::text[]))),
    CONSTRAINT ck_rep_probabilidad CHECK (((probabilidad IS NULL) OR ((probabilidad >= (0)::numeric) AND (probabilidad <= (1)::numeric)))),
    CONSTRAINT ck_rep_revision CHECK (((((estado)::text = 'pendiente'::text) AND (revisado_por IS NULL) AND (revisado_at IS NULL)) OR (((estado)::text <> 'pendiente'::text) AND (revisado_por IS NOT NULL) AND (revisado_at IS NOT NULL))))
);


--
-- Name: reportes_ia_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.reportes_ia_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: reportes_ia_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.reportes_ia_id_seq OWNED BY public.reportes_ia.id;


--
-- Name: roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles (
    id integer NOT NULL,
    codigo character varying(40) NOT NULL,
    nombre character varying(120) NOT NULL,
    descripcion text,
    es_asistencial boolean DEFAULT false NOT NULL,
    es_cuenta_tecnica boolean DEFAULT false NOT NULL,
    nivel_jerarquico smallint DEFAULT 5 NOT NULL,
    activo boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE roles; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.roles IS 'Roles del sistema. Ver 02_seed_catalogos.sql para el catálogo poblado.';


--
-- Name: roles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.roles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: roles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.roles_id_seq OWNED BY public.roles.id;


--
-- Name: roles_permisos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles_permisos (
    rol_id integer NOT NULL,
    permiso_id integer NOT NULL
);


--
-- Name: servicios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.servicios (
    id integer NOT NULL,
    codigo character varying(20) NOT NULL,
    nombre character varying(80) NOT NULL,
    piso smallint,
    activo boolean DEFAULT true NOT NULL
);


--
-- Name: servicios_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.servicios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: servicios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.servicios_id_seq OWNED BY public.servicios.id;


--
-- Name: sesiones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sesiones (
    id integer NOT NULL,
    usuario_id integer NOT NULL,
    refresh_token_hash character(64) NOT NULL,
    ip_origen inet,
    user_agent text,
    emitido_at timestamp with time zone DEFAULT now() NOT NULL,
    expira_at timestamp with time zone NOT NULL,
    revocado_at timestamp with time zone
);


--
-- Name: sesiones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sesiones_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sesiones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sesiones_id_seq OWNED BY public.sesiones.id;


--
-- Name: tipos_cama; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tipos_cama (
    id integer NOT NULL,
    codigo character varying(20) NOT NULL,
    nombre character varying(80) NOT NULL,
    nivel_complejidad smallint NOT NULL,
    codigo_snomed character varying(20),
    costo_dia_cop numeric(12,2),
    activo boolean DEFAULT true NOT NULL
);


--
-- Name: tipos_cama_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tipos_cama_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tipos_cama_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tipos_cama_id_seq OWNED BY public.tipos_cama.id;


--
-- Name: traslados; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.traslados (
    id integer NOT NULL,
    paciente_id character(64) NOT NULL,
    encuentro_origen_id integer NOT NULL,
    servicio_origen_id integer NOT NULL,
    servicio_destino_id integer NOT NULL,
    motivo text NOT NULL,
    prioridad character varying(12) DEFAULT 'prioritaria'::character varying NOT NULL,
    estado character varying(12) DEFAULT 'pendiente'::character varying NOT NULL,
    cama_destino_id integer,
    respuesta text,
    solicitado_por integer NOT NULL,
    resuelto_por integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    resuelto_at timestamp with time zone,
    CONSTRAINT traslados_estado_check CHECK (((estado)::text = ANY ((ARRAY['pendiente'::character varying, 'aceptado'::character varying, 'rechazado'::character varying, 'cancelado'::character varying])::text[]))),
    CONSTRAINT traslados_prioridad_check CHECK (((prioridad)::text = ANY ((ARRAY['rutinaria'::character varying, 'prioritaria'::character varying, 'urgente'::character varying])::text[])))
);


--
-- Name: traslados_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.traslados_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: traslados_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.traslados_id_seq OWNED BY public.traslados.id;


--
-- Name: turnos_area; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.turnos_area (
    id integer NOT NULL,
    servicio_id integer NOT NULL,
    usuario_id integer NOT NULL,
    inicio timestamp with time zone NOT NULL,
    fin timestamp with time zone NOT NULL,
    tipo character varying(12) NOT NULL,
    motivo text,
    created_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT turnos_area_check CHECK ((fin > inicio)),
    CONSTRAINT turnos_area_tipo_check CHECK (((tipo)::text = ANY ((ARRAY['manana'::character varying, 'tarde'::character varying, 'noche'::character varying, 'cobertura'::character varying])::text[])))
);


--
-- Name: turnos_area_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.turnos_area_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: turnos_area_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.turnos_area_id_seq OWNED BY public.turnos_area.id;


--
-- Name: usuarios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.usuarios (
    id integer NOT NULL,
    uuid uuid DEFAULT gen_random_uuid() NOT NULL,
    username public.citext NOT NULL,
    password_hash text NOT NULL,
    rol_id integer NOT NULL,
    personal_id integer,
    paciente_id character(64),
    mfa_habilitado boolean DEFAULT false NOT NULL,
    mfa_secret_cifrado bytea,
    intentos_fallidos smallint DEFAULT 0 NOT NULL,
    bloqueado_hasta timestamp with time zone,
    ultimo_acceso timestamp with time zone,
    password_actualizado_at timestamp with time zone DEFAULT now() NOT NULL,
    debe_cambiar_password boolean DEFAULT true NOT NULL,
    activo boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by integer,
    servicio_id integer
);


--
-- Name: usuarios_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.usuarios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: usuarios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.usuarios_id_seq OWNED BY public.usuarios.id;


--
-- Name: v_camas_ocupacion_detalle; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_camas_ocupacion_detalle AS
 SELECT DISTINCT ON (c.id) c.id AS cama_id,
    c.codigo AS cama_codigo,
    tc.codigo AS tipo_cama,
    c.estado AS estado_cama,
    c.estado_desde AS estado_cama_desde,
    e.id AS encuentro_id,
    e.paciente_id,
    e.estado AS estado_encuentro,
    e.hora_real_inicio,
    e.hora_real_fin,
    p.tipo_documento AS paciente_tipo_documento,
    p.fecha_nacimiento AS paciente_fecha_nacimiento,
    p.sexo AS paciente_sexo
   FROM (((public.camas c
     JOIN public.tipos_cama tc ON ((tc.id = c.tipo_cama_id)))
     LEFT JOIN public.encuentros e ON (((e.cama_id = c.id) AND e.activo)))
     LEFT JOIN public.pacientes p ON ((p.documento_bidx = e.paciente_id)))
  WHERE c.activo
  ORDER BY c.id, e.hora_real_inicio DESC NULLS LAST, e.id DESC;


--
-- Name: v_desviacion_quirurgica; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_desviacion_quirurgica AS
 SELECT cp.nombre AS procedimiento,
    esp.nombre AS especialidad,
    count(*) AS n_cirugias,
    round(avg(cp.duracion_estimada_min), 1) AS duracion_estimada,
    round(avg((EXTRACT(epoch FROM (e.hora_real_fin - e.hora_real_inicio)) / (60)::numeric)), 1) AS duracion_real_promedio,
    round(avg(e.minutos_desviacion), 1) AS desviacion_promedio_min
   FROM ((public.encuentros e
     JOIN public.catalogo_procedimientos cp ON ((cp.id = e.procedimiento_id)))
     JOIN public.especialidades esp ON ((esp.id = cp.especialidad_id)))
  WHERE (((e.tipo)::text = 'cirugia'::text) AND (e.hora_real_fin IS NOT NULL) AND e.activo)
  GROUP BY cp.id, cp.nombre, esp.nombre, cp.duracion_estimada_min
  ORDER BY (round(avg(e.minutos_desviacion), 1)) DESC NULLS LAST;


--
-- Name: v_gastos_paciente; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_gastos_paciente AS
 WITH gasto_procedimientos AS (
         SELECT e.paciente_id,
            count(*) AS procedimientos_realizados,
            sum(cp.tarifa_referencia_cop) AS gasto_procedimientos_cop
           FROM (public.encuentros e
             JOIN public.catalogo_procedimientos cp ON ((cp.id = e.procedimiento_id)))
          WHERE (((e.estado)::text = 'finished'::text) AND e.activo)
          GROUP BY e.paciente_id
        ), gasto_camas AS (
         SELECT e.paciente_id,
            sum((EXTRACT(epoch FROM (COALESCE(e.hora_real_fin, now()) - e.hora_real_inicio)) / 3600.0)) AS horas_cama_total,
            sum(((EXTRACT(epoch FROM (COALESCE(e.hora_real_fin, now()) - e.hora_real_inicio)) / 3600.0) * (tc.costo_dia_cop / (24)::numeric))) AS gasto_estancia_cop
           FROM ((public.encuentros e
             JOIN public.camas c ON ((c.id = e.cama_id)))
             JOIN public.tipos_cama tc ON ((tc.id = c.tipo_cama_id)))
          WHERE ((e.hora_real_inicio IS NOT NULL) AND e.activo)
          GROUP BY e.paciente_id
        )
 SELECT p.documento_bidx AS paciente_id,
    p.tipo_documento,
    COALESCE(gp.procedimientos_realizados, (0)::bigint) AS procedimientos_realizados,
    round(COALESCE(gp.gasto_procedimientos_cop, (0)::numeric), 0) AS gasto_procedimientos_cop,
    round(COALESCE(gc.horas_cama_total, (0)::numeric), 1) AS horas_cama_total,
    round(COALESCE(gc.gasto_estancia_cop, (0)::numeric), 0) AS gasto_estancia_cop,
    round((COALESCE(gp.gasto_procedimientos_cop, (0)::numeric) + COALESCE(gc.gasto_estancia_cop, (0)::numeric)), 0) AS gasto_total_cop
   FROM ((public.pacientes p
     LEFT JOIN gasto_procedimientos gp ON ((gp.paciente_id = p.documento_bidx)))
     LEFT JOIN gasto_camas gc ON ((gc.paciente_id = p.documento_bidx)))
  WHERE p.activo;


--
-- Name: v_horas_ociosas_camas; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_horas_ociosas_camas AS
 SELECT date_trunc('month'::text, e."timestamp") AS mes,
    tc.codigo AS tipo_cama,
    ((sum(e.duracion_estado_anterior_min))::numeric / 60.0) AS horas_disponible,
    round((((sum(e.duracion_estado_anterior_min))::numeric / 60.0) * (tc.costo_dia_cop / (24)::numeric)), 0) AS costo_oportunidad_cop
   FROM ((public.eventos_estado e
     JOIN public.camas c ON ((c.id = e.entidad_id)))
     JOIN public.tipos_cama tc ON ((tc.id = c.tipo_cama_id)))
  WHERE (((e.entidad_tipo)::text = 'cama'::text) AND ((e.estado_anterior)::text = 'disponible'::text) AND (e.duracion_estado_anterior_min IS NOT NULL))
  GROUP BY (date_trunc('month'::text, e."timestamp")), tc.codigo, tc.costo_dia_cop
  ORDER BY (date_trunc('month'::text, e."timestamp")) DESC, tc.codigo;


--
-- Name: v_indicador_cancelacion; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_indicador_cancelacion AS
 SELECT date_trunc('month'::text, e.hora_programada_inicio) AS mes,
    count(*) AS programadas,
    count(*) FILTER (WHERE ((e.estado)::text = 'cancelled'::text)) AS canceladas,
    round(((100.0 * (count(*) FILTER (WHERE ((e.estado)::text = 'cancelled'::text)))::numeric) / (NULLIF(count(*), 0))::numeric), 2) AS pct_cancelacion,
    count(*) FILTER (WHERE ((cc.responsable)::text = 'prestador'::text)) AS por_prestador,
    count(*) FILTER (WHERE cc.evitable) AS evitables
   FROM ((public.encuentros e
     LEFT JOIN public.cancelaciones can ON ((can.encuentro_id = e.id)))
     LEFT JOIN public.catalogo_causas_cancelacion cc ON ((cc.id = can.causa_id)))
  WHERE (((e.tipo)::text = 'cirugia'::text) AND e.activo)
  GROUP BY (date_trunc('month'::text, e.hora_programada_inicio))
  ORDER BY (date_trunc('month'::text, e.hora_programada_inicio)) DESC;


--
-- Name: v_ocupacion_camas; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_ocupacion_camas AS
 SELECT tc.codigo AS tipo_cama,
    tc.nombre,
    count(*) AS total,
    count(*) FILTER (WHERE ((c.estado)::text = 'ocupada'::text)) AS ocupadas,
    count(*) FILTER (WHERE ((c.estado)::text = 'disponible'::text)) AS disponibles,
    count(*) FILTER (WHERE ((c.estado)::text = 'en_limpieza'::text)) AS en_limpieza,
    round(((100.0 * (count(*) FILTER (WHERE ((c.estado)::text = 'ocupada'::text)))::numeric) / (NULLIF(count(*), 0))::numeric), 1) AS pct_ocupacion
   FROM (public.camas c
     JOIN public.tipos_cama tc ON ((tc.id = c.tipo_cama_id)))
  WHERE c.activo
  GROUP BY tc.id, tc.codigo, tc.nombre, tc.nivel_complejidad
  ORDER BY tc.nivel_complejidad DESC;


--
-- Name: agenda_consulta_externa id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_consulta_externa ALTER COLUMN id SET DEFAULT nextval('public.agenda_consulta_externa_id_seq'::regclass);


--
-- Name: alertas id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alertas ALTER COLUMN id SET DEFAULT nextval('public.alertas_id_seq'::regclass);


--
-- Name: camas id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.camas ALTER COLUMN id SET DEFAULT nextval('public.camas_id_seq'::regclass);


--
-- Name: cancelaciones id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cancelaciones ALTER COLUMN id SET DEFAULT nextval('public.cancelaciones_id_seq'::regclass);


--
-- Name: catalogo_causas_cancelacion id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.catalogo_causas_cancelacion ALTER COLUMN id SET DEFAULT nextval('public.catalogo_causas_cancelacion_id_seq'::regclass);


--
-- Name: catalogo_procedimientos id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.catalogo_procedimientos ALTER COLUMN id SET DEFAULT nextval('public.catalogo_procedimientos_id_seq'::regclass);


--
-- Name: diagnosticos_cie10 id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnosticos_cie10 ALTER COLUMN id SET DEFAULT nextval('public.diagnosticos_cie10_id_seq'::regclass);


--
-- Name: encuentros id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.encuentros ALTER COLUMN id SET DEFAULT nextval('public.encuentros_id_seq'::regclass);


--
-- Name: eps id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eps ALTER COLUMN id SET DEFAULT nextval('public.eps_id_seq'::regclass);


--
-- Name: especialidades id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.especialidades ALTER COLUMN id SET DEFAULT nextval('public.especialidades_id_seq'::regclass);


--
-- Name: eventos_estado id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eventos_estado ALTER COLUMN id SET DEFAULT nextval('public.eventos_estado_id_seq'::regclass);


--
-- Name: eventos_fhir id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eventos_fhir ALTER COLUMN id SET DEFAULT nextval('public.eventos_fhir_id_seq'::regclass);


--
-- Name: historial_cambios id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historial_cambios ALTER COLUMN id SET DEFAULT nextval('public.historial_cambios_id_seq'::regclass);


--
-- Name: log_auditoria id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.log_auditoria ALTER COLUMN id SET DEFAULT nextval('public.log_auditoria_id_seq'::regclass);


--
-- Name: notificaciones id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notificaciones ALTER COLUMN id SET DEFAULT nextval('public.notificaciones_id_seq'::regclass);


--
-- Name: observaciones id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.observaciones ALTER COLUMN id SET DEFAULT nextval('public.observaciones_id_seq'::regclass);


--
-- Name: permisos id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permisos ALTER COLUMN id SET DEFAULT nextval('public.permisos_id_seq'::regclass);


--
-- Name: personal id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal ALTER COLUMN id SET DEFAULT nextval('public.personal_id_seq'::regclass);


--
-- Name: predicciones id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.predicciones ALTER COLUMN id SET DEFAULT nextval('public.predicciones_id_seq'::regclass);


--
-- Name: quirofanos id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quirofanos ALTER COLUMN id SET DEFAULT nextval('public.quirofanos_id_seq'::regclass);


--
-- Name: rag_consultas id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_consultas ALTER COLUMN id SET DEFAULT nextval('public.rag_consultas_id_seq'::regclass);


--
-- Name: rag_fragmentos id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_fragmentos ALTER COLUMN id SET DEFAULT nextval('public.rag_fragmentos_id_seq'::regclass);


--
-- Name: remisiones id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.remisiones ALTER COLUMN id SET DEFAULT nextval('public.remisiones_id_seq'::regclass);


--
-- Name: reportes_ia id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reportes_ia ALTER COLUMN id SET DEFAULT nextval('public.reportes_ia_id_seq'::regclass);


--
-- Name: roles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles ALTER COLUMN id SET DEFAULT nextval('public.roles_id_seq'::regclass);


--
-- Name: servicios id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.servicios ALTER COLUMN id SET DEFAULT nextval('public.servicios_id_seq'::regclass);


--
-- Name: sesiones id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sesiones ALTER COLUMN id SET DEFAULT nextval('public.sesiones_id_seq'::regclass);


--
-- Name: tipos_cama id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tipos_cama ALTER COLUMN id SET DEFAULT nextval('public.tipos_cama_id_seq'::regclass);


--
-- Name: traslados id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traslados ALTER COLUMN id SET DEFAULT nextval('public.traslados_id_seq'::regclass);


--
-- Name: turnos_area id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turnos_area ALTER COLUMN id SET DEFAULT nextval('public.turnos_area_id_seq'::regclass);


--
-- Name: usuarios id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios ALTER COLUMN id SET DEFAULT nextval('public.usuarios_id_seq'::regclass);


--
-- Data for Name: catalogo_causas_cancelacion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.catalogo_causas_cancelacion VALUES
	(1, 'PAC_NO_ASISTE', 'Paciente no se presenta a la cirugía', 'paciente', NULL, true),
	(2, 'PAC_NO_AYUNO', 'Paciente no cumplió el tiempo de ayuno', 'paciente', NULL, true),
	(3, 'PAC_GRIPA', 'Paciente con gripa, tos o fiebre', 'paciente', NULL, false),
	(4, 'PAC_INESTABLE', 'Paciente hemodinámicamente inestable', 'paciente', NULL, false),
	(5, 'PAC_NO_ACEPTA', 'Paciente no acepta el procedimiento', 'paciente', NULL, true),
	(6, 'PAC_SIN_COPAGO', 'Paciente no tiene dinero para el copago', 'paciente', NULL, true),
	(7, 'PRE_PROLONG_ANT', 'Prolongación de la cirugía anterior', 'prestador', 'administrativo', true),
	(8, 'PRE_SIN_CAMA_UCI', 'No disponibilidad de cama en UCI', 'prestador', 'administrativo', true),
	(9, 'PRE_SALA_OCUPADA', 'Reprogramación por sala ocupada', 'prestador', 'administrativo', true),
	(10, 'PRE_SIN_CAMILLA', 'Salas bloqueadas por falta de camillas', 'prestador', 'administrativo', true),
	(11, 'PRE_EQUIPO_DANADO', 'Equipo biomédico dañado o no disponible', 'prestador', 'administrativo', true),
	(12, 'PRE_SIN_INSUMO', 'Insumo o material quirúrgico no disponible', 'prestador', 'administrativo', true),
	(13, 'PRE_PROLONG_RECUP', 'Prolongación de los tiempos de recuperación', 'prestador', 'administrativo', true),
	(14, 'PRE_MED_TARDE', 'Médico llega tarde', 'prestador', 'asistencial', true),
	(15, 'PRE_MED_NO_ASISTE', 'Médico no se presenta', 'prestador', 'asistencial', true),
	(16, 'PRE_CAMBIO_CONDUCTA', 'Cambio de conducta médica', 'prestador', 'asistencial', false),
	(17, 'PRE_NO_REQUIERE', 'Paciente no requiere el procedimiento', 'prestador', 'asistencial', false),
	(18, 'ASE_SIN_AUTORIZ', 'Exámenes o procedimiento no autorizados por EPS', 'asegurador', NULL, true),
	(19, 'ASE_ORDEN_MAL', 'Orden de apoyo mal diligenciada', 'asegurador', NULL, true),
	(20, 'ASE_ORDEN_INCOMP', 'Orden de apoyo incompleta', 'asegurador', NULL, true),
	(21, 'OTRO_PACIENTE', 'Otra causa atribuible al paciente, no listada — ver detalle', 'paciente', NULL, NULL),
	(22, 'OTRO_PRESTADOR', 'Otra causa atribuible al prestador, no listada — ver detalle', 'prestador', NULL, NULL),
	(23, 'OTRO_ASEGURADOR', 'Otra causa atribuible al asegurador, no listada — ver detalle', 'asegurador', NULL, NULL);


--
-- Data for Name: catalogo_procedimientos; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.catalogo_procedimientos VALUES
	(1, 'ANEURISM', 'Corrección de aneurisma aórtico', NULL, NULL, 8, 240, 70, 1, true, 4, 38000000.00, true),
	(2, 'NEFREC', 'Nefrectomía', NULL, NULL, 5, 180, 45, 1, false, 4, 14000000.00, true),
	(3, 'CRANEOT', 'Craneotomía', NULL, NULL, 3, 240, 65, 1, true, 4, 28000000.00, true),
	(4, 'REVASC', 'Revascularización miocárdica', NULL, NULL, 2, 300, 75, 1, true, 4, 45000000.00, true),
	(5, 'VALVULA', 'Reemplazo valvular aórtico', NULL, NULL, 2, 270, 70, 1, true, 4, 42000000.00, true),
	(6, 'BYPASS_FEM', 'Bypass femoropoplíteo', NULL, NULL, 8, 180, 50, 3, true, 4, 18000000.00, true),
	(7, 'LAMINEC', 'Laminectomía lumbar', NULL, NULL, 3, 150, 40, 3, true, 3, 12000000.00, true),
	(8, 'LAPAROT', 'Laparotomía exploratoria', NULL, NULL, 1, 150, 50, 3, false, 3, 7500000.00, true),
	(9, 'AMIGDAL', 'Amigdalectomía', NULL, NULL, 10, 45, 15, 4, false, 1, 2600000.00, true),
	(10, 'SEPTO', 'Septoplastia', NULL, NULL, 10, 60, 20, 4, false, 2, 3400000.00, true),
	(11, 'FACO', 'Facoemulsificación de catarata', NULL, NULL, 9, 30, 10, 4, false, 1, 2800000.00, true),
	(12, 'INJERTO', 'Injerto de piel', NULL, NULL, 7, 90, 30, 4, false, 2, 5000000.00, true),
	(13, 'CESAREA', 'Cesárea', NULL, NULL, 6, 45, 15, 4, false, 2, 3800000.00, true),
	(14, 'HISTER', 'Histerectomía abdominal', NULL, NULL, 6, 120, 35, 4, false, 3, 6800000.00, true),
	(15, 'RTU', 'Resección transuretral de próstata', NULL, NULL, 5, 90, 25, 4, false, 2, 5500000.00, true),
	(16, 'LITOT', 'Litotricia / nefrolitotomía', NULL, NULL, 5, 90, 30, 4, true, 2, 6200000.00, true),
	(17, 'OSTEOS', 'Osteosíntesis de fémur', NULL, NULL, 4, 120, 35, 4, true, 3, 8500000.00, true),
	(18, 'ARTROPL', 'Artroplastia total de cadera', NULL, NULL, 4, 150, 40, 4, true, 3, 15000000.00, true),
	(19, 'ARTROSC', 'Artroscopia de rodilla', NULL, NULL, 4, 60, 20, 4, false, 2, 4200000.00, true),
	(20, 'APENDIC', 'Apendicectomía', NULL, NULL, 1, 60, 20, 4, false, 2, 3200000.00, true),
	(21, 'COLECIST', 'Colecistectomía laparoscópica', NULL, NULL, 1, 90, 25, 4, false, 2, 4800000.00, true),
	(22, 'HERNIO', 'Herniorrafia inguinal', NULL, NULL, 1, 75, 20, 4, false, 2, 3600000.00, true);


--
-- Data for Name: diagnosticos_cie10; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.diagnosticos_cie10 VALUES
	(1, 'K35', 'Apendicitis aguda', 'Enfermedades del sistema digestivo'),
	(2, 'K80', 'Colelitiasis', 'Enfermedades del sistema digestivo'),
	(3, 'K40', 'Hernia inguinal', 'Enfermedades del sistema digestivo'),
	(4, 'I21', 'Infarto agudo del miocardio', 'Enfermedades del sistema circulatorio'),
	(5, 'I25', 'Enfermedad isquémica crónica del corazón', 'Enfermedades del sistema circulatorio'),
	(6, 'N20', 'Cálculo del riñón y del uréter', 'Enfermedades del sistema genitourinario'),
	(7, 'S72', 'Fractura del fémur', 'Traumatismos'),
	(8, 'S06', 'Traumatismo intracraneal', 'Traumatismos'),
	(9, 'O82', 'Parto único por cesárea', 'Embarazo, parto y puerperio'),
	(10, 'H25', 'Catarata senil', 'Enfermedades del ojo'),
	(11, 'I70', 'Aterosclerosis', 'Enfermedades del sistema circulatorio'),
	(12, 'A41', 'Sepsis', 'Enfermedades infecciosas');


--
-- Data for Name: eps; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.eps VALUES
	(1, 'EPS001', 'EPS Alfa', 'contributivo', true),
	(2, 'EPS002', 'EPS Beta', 'contributivo', true),
	(3, 'EPS003', 'EPS Gamma', 'subsidiado', true),
	(4, 'EPS004', 'EPS Delta', 'contributivo', true),
	(5, 'EPS005', 'EPS Epsilon', 'subsidiado', true),
	(6, 'EPS006', 'Régimen especial', 'especial', true),
	(7, 'PART', 'Particular', NULL, true);


--
-- Data for Name: especialidades; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.especialidades VALUES
	(1, 'CIR_GEN', 'Cirugía general', NULL, false, true),
	(2, 'CIR_CAR', 'Cirugía cardiovascular', NULL, true, true),
	(3, 'NEUROCIR', 'Neurocirugía', NULL, true, true),
	(4, 'ORTO', 'Ortopedia y traumatología', NULL, false, true),
	(5, 'URO', 'Urología', NULL, false, true),
	(6, 'GINE', 'Ginecobstetricia', NULL, false, true),
	(7, 'CIR_PLA', 'Cirugía plástica', NULL, false, true),
	(8, 'CIR_VAS', 'Cirugía vascular', NULL, true, true),
	(9, 'OFTAL', 'Oftalmología', NULL, false, true),
	(10, 'ORL', 'Otorrinolaringología', NULL, false, true),
	(11, 'ANEST', 'Anestesiología', NULL, false, true),
	(12, 'MED_INT', 'Medicina interna', NULL, false, true),
	(13, 'MED_GEN', 'Medicina general', NULL, false, true),
	(14, 'URG', 'Medicina de urgencias', NULL, false, true);


--
-- Data for Name: permisos; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.permisos VALUES
	(1, 'paciente:create:all', 'paciente', 'create', 'all', 'Registrar pacientes'),
	(2, 'paciente:read:all', 'paciente', 'read', 'all', 'Ver cualquier paciente'),
	(3, 'paciente:read:assigned', 'paciente', 'read', 'assigned', 'Ver pacientes a su cargo'),
	(4, 'paciente:read:self', 'paciente', 'read', 'self', 'Ver su propia información'),
	(5, 'paciente:update:all', 'paciente', 'update', 'all', 'Editar cualquier paciente'),
	(6, 'paciente:update:own', 'paciente', 'update', 'own', 'Editar los que él registró'),
	(7, 'paciente:delete:all', 'paciente', 'delete', 'all', 'Soft delete de cualquier paciente'),
	(8, 'paciente:delete:own', 'paciente', 'delete', 'own', 'Soft delete de los propios'),
	(9, 'paciente:restore', 'paciente', 'restore', 'all', 'Restaurar paciente eliminado'),
	(10, 'encuentro:create:all', 'encuentro', 'create', 'all', 'Crear encuentros'),
	(11, 'encuentro:read:all', 'encuentro', 'read', 'all', 'Ver cualquier encuentro'),
	(12, 'encuentro:read:assigned', 'encuentro', 'read', 'assigned', 'Ver encuentros asignados'),
	(13, 'encuentro:read:self', 'encuentro', 'read', 'self', 'Ver sus propios encuentros'),
	(14, 'encuentro:update:all', 'encuentro', 'update', 'all', 'Editar cualquier encuentro'),
	(15, 'encuentro:update:own', 'encuentro', 'update', 'own', 'Editar los propios'),
	(16, 'encuentro:delete:all', 'encuentro', 'delete', 'all', 'Soft delete de cualquiera'),
	(17, 'encuentro:delete:own', 'encuentro', 'delete', 'own', 'Soft delete de los propios'),
	(18, 'encuentro:restore', 'encuentro', 'restore', 'all', 'Restaurar encuentro'),
	(19, 'observacion:create:all', 'observacion', 'create', 'all', 'Registrar observaciones'),
	(20, 'observacion:read:all', 'observacion', 'read', 'all', 'Ver observaciones'),
	(21, 'observacion:read:self', 'observacion', 'read', 'self', 'Ver sus propias observaciones'),
	(22, 'observacion:update:own', 'observacion', 'update', 'own', 'Editar las propias'),
	(23, 'observacion:delete:own', 'observacion', 'delete', 'own', 'Soft delete de las propias'),
	(24, 'observacion:delete:all', 'observacion', 'delete', 'all', 'Soft delete de cualquiera'),
	(25, 'observacion:restore', 'observacion', 'restore', 'all', 'Restaurar observación'),
	(26, 'imagen:create:all', 'imagen', 'create', 'all', 'Subir una imagen al PACS'),
	(27, 'imagen:read:all', 'imagen', 'read', 'all', 'Ver imágenes de cualquier paciente'),
	(28, 'imagen:read:self', 'imagen', 'read', 'self', 'Ver sus propias imágenes'),
	(29, 'imagen:delete:all', 'imagen', 'delete', 'all', 'Eliminar una imagen del PACS (solo admin, a propósito)'),
	(30, 'cama:read:all', 'cama', 'read', 'all', 'Ver estado de camas'),
	(31, 'cama:update:all', 'cama', 'update', 'all', 'Cambiar estado de camas'),
	(32, 'quirofano:read:all', 'quirofano', 'read', 'all', 'Ver estado de quirófanos'),
	(33, 'quirofano:update:all', 'quirofano', 'update', 'all', 'Cambiar estado de quirófanos'),
	(34, 'agenda:create:all', 'agenda', 'create', 'all', 'Programar cirugías y citas'),
	(35, 'agenda:read:all', 'agenda', 'read', 'all', 'Ver la agenda'),
	(36, 'agenda:update:all', 'agenda', 'update', 'all', 'Reprogramar'),
	(37, 'agenda:priorizar', 'agenda', 'priorizar', 'all', 'Resolver conflictos de capacidad'),
	(38, 'fhir:sync:write', 'fhir', 'sync', 'all', 'Sincronizar recursos hacia HAPI FHIR'),
	(39, 'fhir:read:all', 'fhir', 'read', 'all', 'Consultar recursos FHIR'),
	(40, 'usuario:manage', 'usuario', 'manage', 'all', 'Gestionar usuarios y roles'),
	(41, 'auditoria:read', 'auditoria', 'read', 'all', 'Consultar el log de auditoría'),
	(42, 'analitica:read', 'analitica', 'read', 'all', 'Ver indicadores y caso de negocio'),
	(43, 'facturacion:read', 'facturacion', 'read', 'all', 'Consultar datos para facturación'),
	(48, 'remision:create:all', 'remision', 'create', 'all', 'Remitir pacientes a especialista'),
	(49, 'remision:read:all', 'remision', 'read', 'all', 'Ver todas las remisiones'),
	(50, 'remision:read:assigned', 'remision', 'read', 'assigned', 'Ver las remisiones que envió o recibió'),
	(51, 'remision:update:assigned', 'remision', 'update', 'assigned', 'Aceptar o rechazar las remisiones recibidas'),
	(52, 'alta:create:assigned', 'alta', 'create', 'assigned', 'Dar de alta a sus pacientes (médico tratante)'),
	(53, 'alta:create:all', 'alta', 'create', 'all', 'Dar de alta a cualquier paciente'),
	(54, 'ia:create:assigned', 'ia', 'create', 'assigned', 'Ejecutar el análisis de IA sobre sus pacientes'),
	(55, 'ia:read:assigned', 'ia', 'read', 'assigned', 'Ver los reportes de IA de sus pacientes'),
	(56, 'ia:read:self', 'ia', 'read', 'self', 'Ver sus propios reportes de IA aprobados'),
	(57, 'ia:read:all', 'ia', 'read', 'all', 'Ver todos los reportes de IA'),
	(58, 'ia:approve:assigned', 'ia', 'approve', 'assigned', 'Aprobar o rechazar reportes de IA de sus pacientes'),
	(59, 'alerta:read:assigned', 'alerta', 'read', 'assigned', 'Ver las alertas críticas dirigidas a él'),
	(60, 'alerta:read:all', 'alerta', 'read', 'all', 'Ver todas las alertas críticas'),
	(61, 'alerta:update:assigned', 'alerta', 'update', 'assigned', 'Reconocer las alertas críticas dirigidas a él');


--
-- Data for Name: roles; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.roles VALUES
	(1, 'admin', 'Administrador del sistema', 'Control total. Gestión de usuarios y roles. ÚNICO rol que puede restaurar registros eliminados.', false, false, 1, true, '2026-11-01 16:48:15.977918-05'),
	(6, 'anestesiologo', 'Anestesiólogo', 'Valoración preanestésica y registro intraoperatorio. Puede bloquear un quirófano por criterio clínico.', true, false, 2, true, '2026-11-01 16:48:15.977918-05'),
	(8, 'enfermero', 'Enfermero(a) asistencial', 'Registra signos vitales y actualiza el estado de camas y quirófanos. Es el actualizador principal del estado de recursos.', true, false, 4, true, '2026-11-01 16:48:15.977918-05'),
	(9, 'instrumentador', 'Instrumentador(a) quirúrgico', 'Prepara el quirófano y actualiza su estado entre procedimientos (preparación, en cirugía, limpieza).', true, false, 4, true, '2026-11-01 16:48:15.977918-05'),
	(10, 'auxiliar_enfermeria', 'Auxiliar de enfermería', 'Apoyo asistencial. Registra signos vitales básicos. Sin permiso de eliminación.', true, false, 5, true, '2026-11-01 16:48:15.977918-05'),
	(11, 'secretaria', 'Secretaria / auxiliar administrativo', 'Agenda citas y cirugías, registra datos administrativos del paciente. Sin acceso a datos clínicos ni observaciones.', false, false, 4, true, '2026-11-01 16:48:15.977918-05'),
	(13, 'servicio_integracion', 'Servicio de integración (cuenta técnica)', 'Cuenta de máquina del ETL BD->FHIR. Permiso exclusivo de escritura en endpoints de sincronización. Sin acceso a ningún otro endpoint.', false, true, 6, true, '2026-11-01 16:48:15.977918-05'),
	(14, 'paciente', 'Paciente', 'Consulta únicamente su propia información: estado de su cirugía, citas y resultados.', false, false, 9, true, '2026-11-01 16:48:15.977918-05'),
	(15, 'medico', 'Médico general', 'Atiende consulta y urgencias. Ve solo sus pacientes: registra, ejecuta el análisis de IA, lo aprueba o rechaza y remite al especialista.', true, false, 3, true, '2026-11-01 16:48:16.578041-05'),
	(16, 'especialista', 'Médico especialista', 'Recibe remisiones y atiende a sus pacientes. Ve si un paciente suyo está en cirugía y si él está asignado. Puede aprobar reportes de IA.', true, false, 2, true, '2026-11-01 16:48:16.578041-05'),
	(17, 'contable', 'Contable / facturación', 'Gestiona la facturación de servicios (particular y EPS), pagos y anulaciones. No ve datos clínicos.', false, false, 4, true, '2026-11-01 16:48:16.578041-05'),
	(2, 'coordinador', 'Coordinador del hospital', 'Supervisa el hospital completo: capacidad por área, riesgo de colapso, ingresos y pérdidas, desempeño de la IA. No opera ni consulta pacientes individuales.', false, false, 1, true, '2026-11-01 16:48:15.977918-05'),
	(7, 'enfermero_jefe', 'Enfermero(a) jefe', 'Coordina el servicio y la programación quirúrgica: programa, reprograma y mueve cirugías ante una urgencia; gestiona camas y quirófanos.', true, false, 3, true, '2026-11-01 16:48:15.977918-05');


--
-- Data for Name: roles_permisos; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.roles_permisos VALUES
	(1, 1),
	(1, 2),
	(1, 3),
	(1, 4),
	(1, 5),
	(1, 6),
	(1, 7),
	(1, 8),
	(1, 9),
	(1, 10),
	(1, 11),
	(1, 12),
	(1, 13),
	(1, 14),
	(1, 15),
	(1, 16),
	(1, 17),
	(1, 18),
	(1, 19),
	(1, 20),
	(1, 21),
	(1, 22),
	(1, 23),
	(1, 24),
	(1, 25),
	(1, 26),
	(1, 27),
	(1, 28),
	(1, 29),
	(1, 30),
	(1, 31),
	(1, 32),
	(1, 33),
	(1, 34),
	(1, 35),
	(1, 36),
	(1, 37),
	(1, 38),
	(1, 39),
	(1, 40),
	(1, 41),
	(1, 42),
	(1, 43),
	(6, 2),
	(6, 11),
	(6, 15),
	(6, 19),
	(6, 20),
	(6, 22),
	(6, 23),
	(6, 26),
	(6, 27),
	(6, 30),
	(6, 32),
	(6, 33),
	(6, 35),
	(6, 39),
	(8, 3),
	(8, 12),
	(8, 19),
	(8, 20),
	(8, 22),
	(8, 23),
	(8, 26),
	(8, 27),
	(8, 30),
	(8, 31),
	(8, 32),
	(8, 33),
	(8, 35),
	(9, 12),
	(9, 32),
	(9, 33),
	(9, 35),
	(10, 3),
	(10, 12),
	(10, 19),
	(10, 20),
	(10, 26),
	(10, 27),
	(10, 30),
	(10, 31),
	(11, 1),
	(11, 2),
	(11, 6),
	(11, 10),
	(11, 11),
	(11, 30),
	(11, 32),
	(11, 34),
	(11, 35),
	(11, 36),
	(13, 2),
	(13, 11),
	(13, 20),
	(13, 38),
	(13, 39),
	(14, 4),
	(14, 13),
	(14, 21),
	(14, 28),
	(15, 1),
	(15, 3),
	(15, 6),
	(15, 10),
	(15, 12),
	(15, 15),
	(15, 17),
	(15, 19),
	(15, 20),
	(15, 22),
	(15, 23),
	(15, 26),
	(15, 27),
	(15, 39),
	(16, 1),
	(16, 3),
	(16, 6),
	(16, 8),
	(16, 10),
	(16, 12),
	(16, 15),
	(16, 17),
	(16, 19),
	(16, 20),
	(16, 22),
	(16, 23),
	(16, 26),
	(16, 27),
	(16, 32),
	(16, 39),
	(17, 42),
	(17, 43),
	(2, 30),
	(2, 32),
	(2, 35),
	(2, 42),
	(2, 43),
	(7, 2),
	(7, 10),
	(7, 11),
	(7, 14),
	(7, 17),
	(7, 19),
	(7, 20),
	(7, 22),
	(7, 23),
	(7, 26),
	(7, 27),
	(7, 30),
	(7, 31),
	(7, 32),
	(7, 33),
	(7, 34),
	(7, 35),
	(7, 36),
	(7, 37),
	(7, 39),
	(7, 42),
	(1, 48),
	(15, 48),
	(16, 48),
	(1, 49),
	(15, 50),
	(16, 50),
	(1, 51),
	(16, 51),
	(1, 53),
	(15, 52),
	(16, 52),
	(15, 54),
	(16, 54),
	(15, 55),
	(16, 55),
	(14, 56),
	(1, 57),
	(15, 58),
	(16, 58),
	(15, 59),
	(16, 59),
	(1, 60),
	(15, 61),
	(16, 61);


--
-- Data for Name: servicios; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.servicios VALUES
	(1, 'URG', 'Urgencias', 1, true),
	(2, 'UCI_ADU', 'UCI Adultos', 3, true),
	(3, 'UCI_PED', 'UCI Pediátrica', 3, true),
	(4, 'CIR', 'Cirugía / Salas de operación', 2, true),
	(5, 'HOSP_1', 'Hospitalización piso 4', 4, true),
	(6, 'HOSP_2', 'Hospitalización piso 5', 5, true),
	(7, 'HOSP_3', 'Hospitalización piso 6', 6, true),
	(8, 'MAT', 'Maternidad', 4, true),
	(9, 'CE', 'Consulta externa', 1, true);


--
-- Data for Name: tipos_cama; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.tipos_cama VALUES
	(1, 'UCI', 'Unidad de Cuidados Intensivos', 4, '309904001', 1800000.00, true),
	(2, 'UCIN', 'UCI Neonatal', 4, NULL, 1900000.00, true),
	(3, 'INTERMEDIA', 'Cuidados Intermedios', 3, NULL, 950000.00, true),
	(4, 'GENERAL', 'Hospitalización general', 1, NULL, 420000.00, true),
	(5, 'OBSERV_URG', 'Observación de urgencias', 2, NULL, 380000.00, true);


--
-- Name: agenda_consulta_externa_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agenda_consulta_externa_id_seq', 1, false);


--
-- Name: alertas_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.alertas_id_seq', 1, false);


--
-- Name: camas_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.camas_id_seq', 1, false);


--
-- Name: cancelaciones_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.cancelaciones_id_seq', 1, false);


--
-- Name: catalogo_causas_cancelacion_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.catalogo_causas_cancelacion_id_seq', 33, true);


--
-- Name: catalogo_procedimientos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.catalogo_procedimientos_id_seq', 33, true);


--
-- Name: diagnosticos_cie10_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.diagnosticos_cie10_id_seq', 33, true);


--
-- Name: encuentros_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.encuentros_id_seq', 1, false);


--
-- Name: eps_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.eps_id_seq', 33, true);


--
-- Name: especialidades_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.especialidades_id_seq', 33, true);


--
-- Name: eventos_estado_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.eventos_estado_id_seq', 1, false);


--
-- Name: eventos_fhir_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.eventos_fhir_id_seq', 1, false);


--
-- Name: historial_cambios_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.historial_cambios_id_seq', 1, false);


--
-- Name: log_auditoria_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.log_auditoria_id_seq', 1, false);


--
-- Name: notificaciones_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.notificaciones_id_seq', 1, false);


--
-- Name: observaciones_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.observaciones_id_seq', 1, false);


--
-- Name: permisos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.permisos_id_seq', 66, true);


--
-- Name: personal_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.personal_id_seq', 1, false);


--
-- Name: predicciones_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.predicciones_id_seq', 1, false);


--
-- Name: quirofanos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.quirofanos_id_seq', 1, false);


--
-- Name: rag_consultas_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.rag_consultas_id_seq', 1, false);


--
-- Name: rag_fragmentos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.rag_fragmentos_id_seq', 1, false);


--
-- Name: remisiones_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.remisiones_id_seq', 1, false);


--
-- Name: reportes_ia_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.reportes_ia_id_seq', 1, false);


--
-- Name: roles_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.roles_id_seq', 33, true);


--
-- Name: servicios_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.servicios_id_seq', 33, true);


--
-- Name: sesiones_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.sesiones_id_seq', 1, false);


--
-- Name: tipos_cama_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.tipos_cama_id_seq', 33, true);


--
-- Name: traslados_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.traslados_id_seq', 1, false);


--
-- Name: turnos_area_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.turnos_area_id_seq', 1, false);


--
-- Name: usuarios_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.usuarios_id_seq', 1, false);


--
-- Name: agenda_consulta_externa agenda_consulta_externa_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_consulta_externa
    ADD CONSTRAINT agenda_consulta_externa_pkey PRIMARY KEY (id);


--
-- Name: alertas alertas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alertas
    ADD CONSTRAINT alertas_pkey PRIMARY KEY (id);


--
-- Name: camas camas_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.camas
    ADD CONSTRAINT camas_codigo_key UNIQUE (codigo);


--
-- Name: camas camas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.camas
    ADD CONSTRAINT camas_pkey PRIMARY KEY (id);


--
-- Name: cancelaciones cancelaciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cancelaciones
    ADD CONSTRAINT cancelaciones_pkey PRIMARY KEY (id);


--
-- Name: catalogo_causas_cancelacion catalogo_causas_cancelacion_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.catalogo_causas_cancelacion
    ADD CONSTRAINT catalogo_causas_cancelacion_codigo_key UNIQUE (codigo);


--
-- Name: catalogo_causas_cancelacion catalogo_causas_cancelacion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.catalogo_causas_cancelacion
    ADD CONSTRAINT catalogo_causas_cancelacion_pkey PRIMARY KEY (id);


--
-- Name: catalogo_procedimientos catalogo_procedimientos_codigo_interno_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.catalogo_procedimientos
    ADD CONSTRAINT catalogo_procedimientos_codigo_interno_key UNIQUE (codigo_interno);


--
-- Name: catalogo_procedimientos catalogo_procedimientos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.catalogo_procedimientos
    ADD CONSTRAINT catalogo_procedimientos_pkey PRIMARY KEY (id);


--
-- Name: diagnosticos_cie10 diagnosticos_cie10_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnosticos_cie10
    ADD CONSTRAINT diagnosticos_cie10_codigo_key UNIQUE (codigo);


--
-- Name: diagnosticos_cie10 diagnosticos_cie10_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnosticos_cie10
    ADD CONSTRAINT diagnosticos_cie10_pkey PRIMARY KEY (id);


--
-- Name: encuentros encuentros_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.encuentros
    ADD CONSTRAINT encuentros_pkey PRIMARY KEY (id);


--
-- Name: encuentros encuentros_uuid_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.encuentros
    ADD CONSTRAINT encuentros_uuid_key UNIQUE (uuid);


--
-- Name: eps eps_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eps
    ADD CONSTRAINT eps_codigo_key UNIQUE (codigo);


--
-- Name: eps eps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eps
    ADD CONSTRAINT eps_pkey PRIMARY KEY (id);


--
-- Name: especialidades especialidades_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.especialidades
    ADD CONSTRAINT especialidades_codigo_key UNIQUE (codigo);


--
-- Name: especialidades especialidades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.especialidades
    ADD CONSTRAINT especialidades_pkey PRIMARY KEY (id);


--
-- Name: eventos_estado eventos_estado_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eventos_estado
    ADD CONSTRAINT eventos_estado_pkey PRIMARY KEY (id);


--
-- Name: eventos_fhir eventos_fhir_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eventos_fhir
    ADD CONSTRAINT eventos_fhir_pkey PRIMARY KEY (id);


--
-- Name: historial_cambios historial_cambios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historial_cambios
    ADD CONSTRAINT historial_cambios_pkey PRIMARY KEY (id);


--
-- Name: log_auditoria log_auditoria_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.log_auditoria
    ADD CONSTRAINT log_auditoria_pkey PRIMARY KEY (id);


--
-- Name: notificaciones notificaciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notificaciones
    ADD CONSTRAINT notificaciones_pkey PRIMARY KEY (id);


--
-- Name: observaciones observaciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.observaciones
    ADD CONSTRAINT observaciones_pkey PRIMARY KEY (id);


--
-- Name: observaciones observaciones_uuid_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.observaciones
    ADD CONSTRAINT observaciones_uuid_key UNIQUE (uuid);


--
-- Name: pacientes pacientes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pacientes
    ADD CONSTRAINT pacientes_pkey PRIMARY KEY (documento_bidx);


--
-- Name: pacientes pacientes_uuid_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pacientes
    ADD CONSTRAINT pacientes_uuid_key UNIQUE (uuid);


--
-- Name: permisos permisos_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permisos
    ADD CONSTRAINT permisos_codigo_key UNIQUE (codigo);


--
-- Name: permisos permisos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permisos
    ADD CONSTRAINT permisos_pkey PRIMARY KEY (id);


--
-- Name: personal personal_documento_bidx_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal
    ADD CONSTRAINT personal_documento_bidx_key UNIQUE (documento_bidx);


--
-- Name: personal personal_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal
    ADD CONSTRAINT personal_pkey PRIMARY KEY (id);


--
-- Name: personal personal_uuid_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal
    ADD CONSTRAINT personal_uuid_key UNIQUE (uuid);


--
-- Name: predicciones predicciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.predicciones
    ADD CONSTRAINT predicciones_pkey PRIMARY KEY (id);


--
-- Name: quirofanos quirofanos_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quirofanos
    ADD CONSTRAINT quirofanos_codigo_key UNIQUE (codigo);


--
-- Name: quirofanos quirofanos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quirofanos
    ADD CONSTRAINT quirofanos_pkey PRIMARY KEY (id);


--
-- Name: rag_consultas rag_consultas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_consultas
    ADD CONSTRAINT rag_consultas_pkey PRIMARY KEY (id);


--
-- Name: rag_fragmentos rag_fragmentos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_fragmentos
    ADD CONSTRAINT rag_fragmentos_pkey PRIMARY KEY (id);


--
-- Name: remisiones remisiones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.remisiones
    ADD CONSTRAINT remisiones_pkey PRIMARY KEY (id);


--
-- Name: reportes_ia reportes_ia_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reportes_ia
    ADD CONSTRAINT reportes_ia_pkey PRIMARY KEY (id);


--
-- Name: roles roles_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_codigo_key UNIQUE (codigo);


--
-- Name: roles_permisos roles_permisos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles_permisos
    ADD CONSTRAINT roles_permisos_pkey PRIMARY KEY (rol_id, permiso_id);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--
-- Name: servicios servicios_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.servicios
    ADD CONSTRAINT servicios_codigo_key UNIQUE (codigo);


--
-- Name: servicios servicios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.servicios
    ADD CONSTRAINT servicios_pkey PRIMARY KEY (id);


--
-- Name: sesiones sesiones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sesiones
    ADD CONSTRAINT sesiones_pkey PRIMARY KEY (id);


--
-- Name: sesiones sesiones_refresh_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sesiones
    ADD CONSTRAINT sesiones_refresh_token_hash_key UNIQUE (refresh_token_hash);


--
-- Name: tipos_cama tipos_cama_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tipos_cama
    ADD CONSTRAINT tipos_cama_codigo_key UNIQUE (codigo);


--
-- Name: tipos_cama tipos_cama_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tipos_cama
    ADD CONSTRAINT tipos_cama_pkey PRIMARY KEY (id);


--
-- Name: traslados traslados_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traslados
    ADD CONSTRAINT traslados_pkey PRIMARY KEY (id);


--
-- Name: turnos_area turnos_area_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turnos_area
    ADD CONSTRAINT turnos_area_pkey PRIMARY KEY (id);


--
-- Name: eventos_fhir uq_evento_fhir; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eventos_fhir
    ADD CONSTRAINT uq_evento_fhir UNIQUE (recurso_tipo, recurso_id, version);


--
-- Name: usuarios usuarios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_pkey PRIMARY KEY (id);


--
-- Name: usuarios usuarios_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_username_key UNIQUE (username);


--
-- Name: usuarios usuarios_uuid_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_uuid_key UNIQUE (uuid);


--
-- Name: idx_alerta_activas; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerta_activas ON public.alertas USING btree (dirigida_a_usuario, created_at) WHERE ((estado)::text = 'activa'::text);


--
-- Name: idx_alertas_pendientes; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alertas_pendientes ON public.alertas USING btree (severidad, created_at DESC) WHERE (resuelta_at IS NULL);


--
-- Name: idx_audit_entidad; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_entidad ON public.log_auditoria USING btree (entidad_tipo, entidad_id, "timestamp" DESC);


--
-- Name: idx_audit_op; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_op ON public.log_auditoria USING btree (operacion, "timestamp" DESC);


--
-- Name: idx_audit_usuario; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_usuario ON public.log_auditoria USING btree (usuario_id, "timestamp" DESC);


--
-- Name: idx_camas_estado; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_camas_estado ON public.camas USING btree (estado, tipo_cama_id) WHERE activo;


--
-- Name: idx_canc_encuentro; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_canc_encuentro ON public.cancelaciones USING btree (encuentro_id);


--
-- Name: idx_consulta_especialista; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_consulta_especialista ON public.agenda_consulta_externa USING btree (especialista_id, hora_programada);


--
-- Name: idx_enc_estado; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enc_estado ON public.encuentros USING btree (estado, tipo) WHERE activo;


--
-- Name: idx_enc_paciente; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enc_paciente ON public.encuentros USING btree (paciente_id) WHERE activo;


--
-- Name: idx_enc_programado; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enc_programado ON public.encuentros USING btree (hora_programada_inicio) WHERE activo;


--
-- Name: idx_enc_quirofano; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enc_quirofano ON public.encuentros USING btree (quirofano_id) WHERE activo;


--
-- Name: idx_evt_entidad; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_evt_entidad ON public.eventos_estado USING btree (entidad_tipo, entidad_id, "timestamp" DESC);


--
-- Name: idx_evt_subtipo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_evt_subtipo ON public.eventos_estado USING btree (entidad_tipo, entidad_subtipo);


--
-- Name: idx_evt_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_evt_ts ON public.eventos_estado USING btree ("timestamp" DESC);


--
-- Name: idx_hist_entidad; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hist_entidad ON public.historial_cambios USING btree (entidad_tipo, entidad_id, version DESC);


--
-- Name: idx_notif_usuario; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_notif_usuario ON public.notificaciones USING btree (usuario_id, leida, fecha DESC);


--
-- Name: idx_obs_critico; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_obs_critico ON public.observaciones USING btree (es_critico) WHERE (activo AND es_critico);


--
-- Name: idx_obs_encuentro; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_obs_encuentro ON public.observaciones USING btree (encuentro_id) WHERE activo;


--
-- Name: idx_obs_loinc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_obs_loinc ON public.observaciones USING btree (codigo_loinc) WHERE activo;


--
-- Name: idx_pacientes_eps; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pacientes_eps ON public.pacientes USING btree (eps_id) WHERE activo;


--
-- Name: idx_personal_especialidad; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_personal_especialidad ON public.personal USING btree (especialidad_id) WHERE activo;


--
-- Name: idx_personal_tipo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_personal_tipo ON public.personal USING btree (tipo_personal) WHERE activo;


--
-- Name: idx_pred_entidad; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pred_entidad ON public.predicciones USING btree (entidad_tipo, entidad_id);


--
-- Name: idx_pred_modelo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pred_modelo ON public.predicciones USING btree (modelo, created_at DESC);


--
-- Name: idx_quirofanos_estado; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_quirofanos_estado ON public.quirofanos USING btree (estado) WHERE activo;


--
-- Name: idx_rem_especialista; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rem_especialista ON public.remisiones USING btree (especialista_id, estado);


--
-- Name: idx_rem_paciente; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rem_paciente ON public.remisiones USING btree (paciente_id);


--
-- Name: idx_rep_paciente; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rep_paciente ON public.reportes_ia USING btree (paciente_id, estado, created_at DESC);


--
-- Name: idx_rep_pendientes; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rep_pendientes ON public.reportes_ia USING btree (creado_por) WHERE ((estado)::text = 'pendiente'::text);


--
-- Name: idx_sesiones_usuario; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sesiones_usuario ON public.sesiones USING btree (usuario_id) WHERE (revocado_at IS NULL);


--
-- Name: idx_traslado_destino; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_traslado_destino ON public.traslados USING btree (servicio_destino_id, estado);


--
-- Name: idx_turnos_area_tiempo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_turnos_area_tiempo ON public.turnos_area USING btree (servicio_id, inicio, fin);


--
-- Name: idx_usuarios_rol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_usuarios_rol ON public.usuarios USING btree (rol_id) WHERE activo;


--
-- Name: ix_rag_consultas_usuario; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rag_consultas_usuario ON public.rag_consultas USING btree (usuario_id, created_at DESC);


--
-- Name: ix_rag_frag_documento; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rag_frag_documento ON public.rag_fragmentos USING btree (documento_id);


--
-- Name: ix_rag_frag_filtro; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rag_frag_filtro ON public.rag_fragmentos USING btree (tipo, estado, paciente_id);


--
-- Name: uq_alerta_reporte; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_alerta_reporte ON public.alertas USING btree (reporte_id) WHERE (reporte_id IS NOT NULL);


--
-- Name: ux_traslado_abierto; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_traslado_abierto ON public.traslados USING btree (paciente_id) WHERE ((estado)::text = 'pendiente'::text);


--
-- Name: log_auditoria trg_auditoria_no_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_auditoria_no_update BEFORE DELETE OR UPDATE ON public.log_auditoria FOR EACH ROW EXECUTE FUNCTION public.fn_auditoria_inmutable();


--
-- Name: reportes_ia trg_reportes_ia_inmutables; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_reportes_ia_inmutables BEFORE DELETE OR UPDATE ON public.reportes_ia FOR EACH ROW EXECUTE FUNCTION public.fn_reportes_ia_inmutables();


--
-- Name: agenda_consulta_externa agenda_consulta_externa_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_consulta_externa
    ADD CONSTRAINT agenda_consulta_externa_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.usuarios(id);


--
-- Name: agenda_consulta_externa agenda_consulta_externa_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_consulta_externa
    ADD CONSTRAINT agenda_consulta_externa_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.usuarios(id);


--
-- Name: agenda_consulta_externa agenda_consulta_externa_especialista_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_consulta_externa
    ADD CONSTRAINT agenda_consulta_externa_especialista_id_fkey FOREIGN KEY (especialista_id) REFERENCES public.personal(id);


--
-- Name: agenda_consulta_externa agenda_consulta_externa_medico_general_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_consulta_externa
    ADD CONSTRAINT agenda_consulta_externa_medico_general_id_fkey FOREIGN KEY (medico_general_id) REFERENCES public.personal(id);


--
-- Name: agenda_consulta_externa agenda_consulta_externa_paciente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_consulta_externa
    ADD CONSTRAINT agenda_consulta_externa_paciente_id_fkey FOREIGN KEY (paciente_id) REFERENCES public.pacientes(documento_bidx);


--
-- Name: alertas alertas_dirigida_a_rol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alertas
    ADD CONSTRAINT alertas_dirigida_a_rol_fkey FOREIGN KEY (dirigida_a_rol) REFERENCES public.roles(id);


--
-- Name: alertas alertas_dirigida_a_usuario_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alertas
    ADD CONSTRAINT alertas_dirigida_a_usuario_fkey FOREIGN KEY (dirigida_a_usuario) REFERENCES public.usuarios(id);


--
-- Name: alertas alertas_paciente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alertas
    ADD CONSTRAINT alertas_paciente_id_fkey FOREIGN KEY (paciente_id) REFERENCES public.pacientes(documento_bidx);


--
-- Name: alertas alertas_reconocida_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alertas
    ADD CONSTRAINT alertas_reconocida_por_fkey FOREIGN KEY (reconocida_por) REFERENCES public.usuarios(id);


--
-- Name: alertas alertas_reporte_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alertas
    ADD CONSTRAINT alertas_reporte_id_fkey FOREIGN KEY (reporte_id) REFERENCES public.reportes_ia(id);


--
-- Name: alertas alertas_resuelta_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alertas
    ADD CONSTRAINT alertas_resuelta_por_fkey FOREIGN KEY (resuelta_por) REFERENCES public.usuarios(id);


--
-- Name: camas camas_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.camas
    ADD CONSTRAINT camas_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.usuarios(id);


--
-- Name: camas camas_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.camas
    ADD CONSTRAINT camas_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.usuarios(id);


--
-- Name: camas camas_servicio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.camas
    ADD CONSTRAINT camas_servicio_id_fkey FOREIGN KEY (servicio_id) REFERENCES public.servicios(id);


--
-- Name: camas camas_tipo_cama_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.camas
    ADD CONSTRAINT camas_tipo_cama_id_fkey FOREIGN KEY (tipo_cama_id) REFERENCES public.tipos_cama(id);


--
-- Name: cancelaciones cancelaciones_causa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cancelaciones
    ADD CONSTRAINT cancelaciones_causa_id_fkey FOREIGN KEY (causa_id) REFERENCES public.catalogo_causas_cancelacion(id);


--
-- Name: cancelaciones cancelaciones_encuentro_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cancelaciones
    ADD CONSTRAINT cancelaciones_encuentro_id_fkey FOREIGN KEY (encuentro_id) REFERENCES public.encuentros(id);


--
-- Name: cancelaciones cancelaciones_encuentro_nuevo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cancelaciones
    ADD CONSTRAINT cancelaciones_encuentro_nuevo_id_fkey FOREIGN KEY (encuentro_nuevo_id) REFERENCES public.encuentros(id);


--
-- Name: cancelaciones cancelaciones_registrado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cancelaciones
    ADD CONSTRAINT cancelaciones_registrado_por_fkey FOREIGN KEY (registrado_por) REFERENCES public.usuarios(id);


--
-- Name: catalogo_procedimientos catalogo_procedimientos_especialidad_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.catalogo_procedimientos
    ADD CONSTRAINT catalogo_procedimientos_especialidad_id_fkey FOREIGN KEY (especialidad_id) REFERENCES public.especialidades(id);


--
-- Name: catalogo_procedimientos catalogo_procedimientos_tipo_cama_requerida_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.catalogo_procedimientos
    ADD CONSTRAINT catalogo_procedimientos_tipo_cama_requerida_id_fkey FOREIGN KEY (tipo_cama_requerida_id) REFERENCES public.tipos_cama(id);


--
-- Name: encuentros encuentros_anestesiologo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.encuentros
    ADD CONSTRAINT encuentros_anestesiologo_id_fkey FOREIGN KEY (anestesiologo_id) REFERENCES public.personal(id);


--
-- Name: encuentros encuentros_cama_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.encuentros
    ADD CONSTRAINT encuentros_cama_id_fkey FOREIGN KEY (cama_id) REFERENCES public.camas(id);


--
-- Name: encuentros encuentros_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.encuentros
    ADD CONSTRAINT encuentros_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.usuarios(id);


--
-- Name: encuentros encuentros_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.encuentros
    ADD CONSTRAINT encuentros_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.usuarios(id);


--
-- Name: encuentros encuentros_diagnostico_cie10_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.encuentros
    ADD CONSTRAINT encuentros_diagnostico_cie10_id_fkey FOREIGN KEY (diagnostico_cie10_id) REFERENCES public.diagnosticos_cie10(id);


--
-- Name: encuentros encuentros_medico_responsable_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.encuentros
    ADD CONSTRAINT encuentros_medico_responsable_id_fkey FOREIGN KEY (medico_responsable_id) REFERENCES public.personal(id);


--
-- Name: encuentros encuentros_paciente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.encuentros
    ADD CONSTRAINT encuentros_paciente_id_fkey FOREIGN KEY (paciente_id) REFERENCES public.pacientes(documento_bidx);


--
-- Name: encuentros encuentros_procedimiento_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.encuentros
    ADD CONSTRAINT encuentros_procedimiento_id_fkey FOREIGN KEY (procedimiento_id) REFERENCES public.catalogo_procedimientos(id);


--
-- Name: encuentros encuentros_quirofano_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.encuentros
    ADD CONSTRAINT encuentros_quirofano_id_fkey FOREIGN KEY (quirofano_id) REFERENCES public.quirofanos(id);


--
-- Name: eventos_estado eventos_estado_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.eventos_estado
    ADD CONSTRAINT eventos_estado_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id);


--
-- Name: usuarios fk_usuarios_paciente; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT fk_usuarios_paciente FOREIGN KEY (paciente_id) REFERENCES public.pacientes(documento_bidx);


--
-- Name: historial_cambios historial_cambios_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historial_cambios
    ADD CONSTRAINT historial_cambios_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id);


--
-- Name: log_auditoria log_auditoria_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.log_auditoria
    ADD CONSTRAINT log_auditoria_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id);


--
-- Name: notificaciones notificaciones_paciente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notificaciones
    ADD CONSTRAINT notificaciones_paciente_id_fkey FOREIGN KEY (paciente_id) REFERENCES public.pacientes(documento_bidx);


--
-- Name: notificaciones notificaciones_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notificaciones
    ADD CONSTRAINT notificaciones_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id);


--
-- Name: observaciones observaciones_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.observaciones
    ADD CONSTRAINT observaciones_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.usuarios(id);


--
-- Name: observaciones observaciones_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.observaciones
    ADD CONSTRAINT observaciones_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.usuarios(id);


--
-- Name: observaciones observaciones_encuentro_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.observaciones
    ADD CONSTRAINT observaciones_encuentro_id_fkey FOREIGN KEY (encuentro_id) REFERENCES public.encuentros(id);


--
-- Name: observaciones observaciones_paciente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.observaciones
    ADD CONSTRAINT observaciones_paciente_id_fkey FOREIGN KEY (paciente_id) REFERENCES public.pacientes(documento_bidx);


--
-- Name: observaciones observaciones_registrado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.observaciones
    ADD CONSTRAINT observaciones_registrado_por_fkey FOREIGN KEY (registrado_por) REFERENCES public.personal(id);


--
-- Name: pacientes pacientes_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pacientes
    ADD CONSTRAINT pacientes_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.usuarios(id);


--
-- Name: pacientes pacientes_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pacientes
    ADD CONSTRAINT pacientes_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.usuarios(id);


--
-- Name: pacientes pacientes_eps_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pacientes
    ADD CONSTRAINT pacientes_eps_id_fkey FOREIGN KEY (eps_id) REFERENCES public.eps(id);


--
-- Name: personal personal_especialidad_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal
    ADD CONSTRAINT personal_especialidad_id_fkey FOREIGN KEY (especialidad_id) REFERENCES public.especialidades(id);


--
-- Name: quirofanos quirofanos_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quirofanos
    ADD CONSTRAINT quirofanos_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.usuarios(id);


--
-- Name: quirofanos quirofanos_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quirofanos
    ADD CONSTRAINT quirofanos_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.usuarios(id);


--
-- Name: quirofanos quirofanos_servicio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quirofanos
    ADD CONSTRAINT quirofanos_servicio_id_fkey FOREIGN KEY (servicio_id) REFERENCES public.servicios(id);


--
-- Name: remisiones remisiones_aceptada_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.remisiones
    ADD CONSTRAINT remisiones_aceptada_por_fkey FOREIGN KEY (aceptada_por) REFERENCES public.usuarios(id);


--
-- Name: remisiones remisiones_cerrada_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.remisiones
    ADD CONSTRAINT remisiones_cerrada_por_fkey FOREIGN KEY (cerrada_por) REFERENCES public.usuarios(id);


--
-- Name: remisiones remisiones_especialista_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.remisiones
    ADD CONSTRAINT remisiones_especialista_id_fkey FOREIGN KEY (especialista_id) REFERENCES public.personal(id);


--
-- Name: remisiones remisiones_medico_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.remisiones
    ADD CONSTRAINT remisiones_medico_id_fkey FOREIGN KEY (medico_id) REFERENCES public.personal(id);


--
-- Name: remisiones remisiones_paciente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.remisiones
    ADD CONSTRAINT remisiones_paciente_id_fkey FOREIGN KEY (paciente_id) REFERENCES public.pacientes(documento_bidx);


--
-- Name: remisiones remisiones_remitido_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.remisiones
    ADD CONSTRAINT remisiones_remitido_por_fkey FOREIGN KEY (remitido_por) REFERENCES public.usuarios(id);


--
-- Name: reportes_ia reportes_ia_creado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reportes_ia
    ADD CONSTRAINT reportes_ia_creado_por_fkey FOREIGN KEY (creado_por) REFERENCES public.usuarios(id);


--
-- Name: reportes_ia reportes_ia_paciente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reportes_ia
    ADD CONSTRAINT reportes_ia_paciente_id_fkey FOREIGN KEY (paciente_id) REFERENCES public.pacientes(documento_bidx);


--
-- Name: reportes_ia reportes_ia_revisado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reportes_ia
    ADD CONSTRAINT reportes_ia_revisado_por_fkey FOREIGN KEY (revisado_por) REFERENCES public.usuarios(id);


--
-- Name: roles_permisos roles_permisos_permiso_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles_permisos
    ADD CONSTRAINT roles_permisos_permiso_id_fkey FOREIGN KEY (permiso_id) REFERENCES public.permisos(id) ON DELETE CASCADE;


--
-- Name: roles_permisos roles_permisos_rol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles_permisos
    ADD CONSTRAINT roles_permisos_rol_id_fkey FOREIGN KEY (rol_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: sesiones sesiones_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sesiones
    ADD CONSTRAINT sesiones_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id) ON DELETE CASCADE;


--
-- Name: traslados traslados_cama_destino_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traslados
    ADD CONSTRAINT traslados_cama_destino_id_fkey FOREIGN KEY (cama_destino_id) REFERENCES public.camas(id);


--
-- Name: traslados traslados_encuentro_origen_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traslados
    ADD CONSTRAINT traslados_encuentro_origen_id_fkey FOREIGN KEY (encuentro_origen_id) REFERENCES public.encuentros(id);


--
-- Name: traslados traslados_paciente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traslados
    ADD CONSTRAINT traslados_paciente_id_fkey FOREIGN KEY (paciente_id) REFERENCES public.pacientes(documento_bidx);


--
-- Name: traslados traslados_resuelto_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traslados
    ADD CONSTRAINT traslados_resuelto_por_fkey FOREIGN KEY (resuelto_por) REFERENCES public.usuarios(id);


--
-- Name: traslados traslados_servicio_destino_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traslados
    ADD CONSTRAINT traslados_servicio_destino_id_fkey FOREIGN KEY (servicio_destino_id) REFERENCES public.servicios(id);


--
-- Name: traslados traslados_servicio_origen_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traslados
    ADD CONSTRAINT traslados_servicio_origen_id_fkey FOREIGN KEY (servicio_origen_id) REFERENCES public.servicios(id);


--
-- Name: traslados traslados_solicitado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traslados
    ADD CONSTRAINT traslados_solicitado_por_fkey FOREIGN KEY (solicitado_por) REFERENCES public.usuarios(id);


--
-- Name: turnos_area turnos_area_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turnos_area
    ADD CONSTRAINT turnos_area_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.usuarios(id);


--
-- Name: turnos_area turnos_area_servicio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turnos_area
    ADD CONSTRAINT turnos_area_servicio_id_fkey FOREIGN KEY (servicio_id) REFERENCES public.servicios(id);


--
-- Name: turnos_area turnos_area_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turnos_area
    ADD CONSTRAINT turnos_area_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id);


--
-- Name: usuarios usuarios_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.usuarios(id);


--
-- Name: usuarios usuarios_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.usuarios(id);


--
-- Name: usuarios usuarios_personal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_personal_id_fkey FOREIGN KEY (personal_id) REFERENCES public.personal(id);


--
-- Name: usuarios usuarios_rol_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_rol_id_fkey FOREIGN KEY (rol_id) REFERENCES public.roles(id);


--
-- Name: usuarios usuarios_servicio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_servicio_id_fkey FOREIGN KEY (servicio_id) REFERENCES public.servicios(id);


--
-- PostgreSQL database dump complete
--


