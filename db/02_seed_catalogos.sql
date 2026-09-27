-- ============================================================================
-- SEED DE CATÁLOGOS
-- Roles del personal hospitalario, permisos RBAC granular y catálogos clínicos
-- ============================================================================

-- ============================================================================
-- ROLES  (12 roles cubriendo todo el personal con acceso al sistema)
-- El spec de la Semana 6 exige mínimo 3; se implementan 12 porque el sistema
-- real requiere granularidad y porque mapean al diagrama de actores (Semana 3).
-- ============================================================================
INSERT INTO roles (codigo, nombre, descripcion, es_asistencial, es_cuenta_tecnica, nivel_jerarquico) VALUES
('admin',                'Administrador del sistema',
 'Control total. Gestión de usuarios y roles. ÚNICO rol que puede restaurar registros eliminados.',
 FALSE, FALSE, 1),

('director_medico',      'Director médico',
 'Vista completa de indicadores clínicos y operativos. Acceso a analítica y caso de negocio. No opera registros individuales.',
 FALSE, FALSE, 1),

('coordinador_quirurgico','Coordinador de quirófanos',
 'Gestiona la programación quirúrgica, asigna quirófanos y camas, resuelve conflictos de capacidad. Es el cuello de botella identificado en el AS-IS.',
 FALSE, FALSE, 2),

('medico_especialista',  'Médico especialista',
 'Cirujano o especialista. Crea y edita sus propios registros clínicos, solicita cirugía, registra observaciones.',
 TRUE, FALSE, 2),

('medico_general',       'Médico general',
 'Atiende consulta y urgencias, registra valoración inicial y observaciones, solicita interconsulta al especialista.',
 TRUE, FALSE, 3),

('anestesiologo',        'Anestesiólogo',
 'Valoración preanestésica y registro intraoperatorio. Puede bloquear un quirófano por criterio clínico.',
 TRUE, FALSE, 2),

('enfermero_jefe',       'Enfermero(a) jefe',
 'Coordina el servicio. Gestiona disponibilidad de camas, autoriza cambios de estado y supervisa al personal de enfermería.',
 TRUE, FALSE, 3),

('enfermero',            'Enfermero(a) asistencial',
 'Registra signos vitales y actualiza el estado de camas y quirófanos. Es el actualizador principal del estado de recursos.',
 TRUE, FALSE, 4),

('instrumentador',       'Instrumentador(a) quirúrgico',
 'Prepara el quirófano y actualiza su estado entre procedimientos (preparación, en cirugía, limpieza).',
 TRUE, FALSE, 4),

('auxiliar_enfermeria',  'Auxiliar de enfermería',
 'Apoyo asistencial. Registra signos vitales básicos. Sin permiso de eliminación.',
 TRUE, FALSE, 5),

('secretaria',           'Secretaria / auxiliar administrativo',
 'Agenda citas y cirugías, registra datos administrativos del paciente. Sin acceso a datos clínicos ni observaciones.',
 FALSE, FALSE, 4),

('facturacion',          'Analista de facturación',
 'Consulta encuentros y procedimientos para facturación y glosas. Solo lectura sobre datos clínicos.',
 FALSE, FALSE, 4),

('servicio_integracion', 'Servicio de integración (cuenta técnica)',
 'Cuenta de máquina del ETL BD->FHIR. Permiso exclusivo de escritura en endpoints de sincronización. Sin acceso a ningún otro endpoint.',
 FALSE, TRUE, 6),

('paciente',             'Paciente',
 'Consulta únicamente su propia información: estado de su cirugía, citas y resultados.',
 FALSE, FALSE, 9);

-- ============================================================================
-- PERMISOS  (formato recurso:accion:alcance)
--   alcance: all      -> cualquier registro
--            own      -> solo los que él creó
--            assigned -> solo los que le fueron asignados
--            self     -> solo su propia información (paciente)
-- ============================================================================
INSERT INTO permisos (codigo, recurso, accion, alcance, descripcion) VALUES
-- Pacientes
('paciente:create:all',      'paciente','create','all','Registrar pacientes'),
('paciente:read:all',        'paciente','read','all','Ver cualquier paciente'),
('paciente:read:assigned',   'paciente','read','assigned','Ver pacientes a su cargo'),
('paciente:read:self',       'paciente','read','self','Ver su propia información'),
('paciente:update:all',      'paciente','update','all','Editar cualquier paciente'),
('paciente:update:own',      'paciente','update','own','Editar los que él registró'),
('paciente:delete:all',      'paciente','delete','all','Soft delete de cualquier paciente'),
('paciente:delete:own',      'paciente','delete','own','Soft delete de los propios'),
('paciente:restore',         'paciente','restore','all','Restaurar paciente eliminado'),
-- Encuentros
('encuentro:create:all',     'encuentro','create','all','Crear encuentros'),
('encuentro:read:all',       'encuentro','read','all','Ver cualquier encuentro'),
('encuentro:read:assigned',  'encuentro','read','assigned','Ver encuentros asignados'),
('encuentro:read:self',      'encuentro','read','self','Ver sus propios encuentros'),
('encuentro:update:all',     'encuentro','update','all','Editar cualquier encuentro'),
('encuentro:update:own',     'encuentro','update','own','Editar los propios'),
('encuentro:delete:all',     'encuentro','delete','all','Soft delete de cualquiera'),
('encuentro:delete:own',     'encuentro','delete','own','Soft delete de los propios'),
('encuentro:restore',        'encuentro','restore','all','Restaurar encuentro'),
-- Observaciones
('observacion:create:all',   'observacion','create','all','Registrar observaciones'),
('observacion:read:all',     'observacion','read','all','Ver observaciones'),
('observacion:read:self',    'observacion','read','self','Ver sus propias observaciones'),
('observacion:update:own',   'observacion','update','own','Editar las propias'),
('observacion:delete:own',   'observacion','delete','own','Soft delete de las propias'),
('observacion:delete:all',   'observacion','delete','all','Soft delete de cualquiera'),
('observacion:restore',      'observacion','restore','all','Restaurar observación'),
-- Recursos físicos
('cama:read:all',            'cama','read','all','Ver estado de camas'),
('cama:update:all',          'cama','update','all','Cambiar estado de camas'),
('quirofano:read:all',       'quirofano','read','all','Ver estado de quirófanos'),
('quirofano:update:all',     'quirofano','update','all','Cambiar estado de quirófanos'),
-- Agenda
('agenda:create:all',        'agenda','create','all','Programar cirugías y citas'),
('agenda:read:all',          'agenda','read','all','Ver la agenda'),
('agenda:update:all',        'agenda','update','all','Reprogramar'),
('agenda:priorizar',         'agenda','priorizar','all','Resolver conflictos de capacidad'),
-- Interoperabilidad
('fhir:sync:write',          'fhir','sync','all','Sincronizar recursos hacia HAPI FHIR'),
('fhir:read:all',            'fhir','read','all','Consultar recursos FHIR'),
-- Administración
('usuario:manage',           'usuario','manage','all','Gestionar usuarios y roles'),
('auditoria:read',           'auditoria','read','all','Consultar el log de auditoría'),
('analitica:read',           'analitica','read','all','Ver indicadores y caso de negocio'),
('facturacion:read',         'facturacion','read','all','Consultar datos para facturación');

-- ============================================================================
-- ASIGNACIÓN DE PERMISOS POR ROL
-- ============================================================================

-- admin: todos los permisos
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permisos p WHERE r.codigo = 'admin';

-- director_medico: lectura amplia + analítica, sin operar registros
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'director_medico' AND p.codigo IN (
    'paciente:read:all','encuentro:read:all','observacion:read:all',
    'cama:read:all','quirofano:read:all','agenda:read:all',
    'analitica:read','auditoria:read','fhir:read:all');

-- coordinador_quirurgico: gestiona agenda y recursos, NO restaura
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'coordinador_quirurgico' AND p.codigo IN (
    'paciente:create:all','paciente:read:all','paciente:update:all',
    'encuentro:create:all','encuentro:read:all','encuentro:update:all',
    'observacion:read:all',
    'cama:read:all','cama:update:all',
    'quirofano:read:all','quirofano:update:all',
    'agenda:create:all','agenda:read:all','agenda:update:all','agenda:priorizar',
    'analitica:read','fhir:read:all');

-- medico_especialista: crea y edita lo suyo, soft delete solo de lo propio
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'medico_especialista' AND p.codigo IN (
    'paciente:create:all','paciente:read:all','paciente:update:own','paciente:delete:own',
    'encuentro:create:all','encuentro:read:all','encuentro:update:own','encuentro:delete:own',
    'observacion:create:all','observacion:read:all','observacion:update:own','observacion:delete:own',
    'cama:read:all','quirofano:read:all',
    'agenda:create:all','agenda:read:all','fhir:read:all');

-- medico_general
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'medico_general' AND p.codigo IN (
    'paciente:create:all','paciente:read:all','paciente:update:own',
    'encuentro:create:all','encuentro:read:all','encuentro:update:own','encuentro:delete:own',
    'observacion:create:all','observacion:read:all','observacion:update:own','observacion:delete:own',
    'cama:read:all','quirofano:read:all','agenda:read:all','fhir:read:all');

-- anestesiologo: puede bloquear quirófano por criterio clínico
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'anestesiologo' AND p.codigo IN (
    'paciente:read:all',
    'encuentro:read:all','encuentro:update:own',
    'observacion:create:all','observacion:read:all','observacion:update:own','observacion:delete:own',
    'cama:read:all','quirofano:read:all','quirofano:update:all',
    'agenda:read:all','fhir:read:all');

-- enfermero_jefe: gestiona camas del servicio y supervisa
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'enfermero_jefe' AND p.codigo IN (
    'paciente:read:all',
    'encuentro:create:all','encuentro:read:all','encuentro:update:own','encuentro:delete:own',
    'observacion:create:all','observacion:read:all','observacion:update:own','observacion:delete:own',
    'cama:read:all','cama:update:all',
    'quirofano:read:all','quirofano:update:all',
    'agenda:read:all','analitica:read','fhir:read:all');

-- enfermero: actualizador principal del estado de recursos
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'enfermero' AND p.codigo IN (
    'paciente:read:assigned',
    'encuentro:read:assigned',
    'observacion:create:all','observacion:read:all','observacion:update:own','observacion:delete:own',
    'cama:read:all','cama:update:all',
    'quirofano:read:all','quirofano:update:all',
    'agenda:read:all');

-- instrumentador: solo estado de quirófano
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'instrumentador' AND p.codigo IN (
    'encuentro:read:assigned',
    'quirofano:read:all','quirofano:update:all',
    'agenda:read:all');

-- auxiliar_enfermeria: registra pero NO elimina
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'auxiliar_enfermeria' AND p.codigo IN (
    'paciente:read:assigned',
    'encuentro:read:assigned',
    'observacion:create:all','observacion:read:all',
    'cama:read:all','cama:update:all');

-- secretaria: administrativo puro, SIN acceso a datos clínicos
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'secretaria' AND p.codigo IN (
    'paciente:create:all','paciente:read:all','paciente:update:own',
    'encuentro:create:all','encuentro:read:all',
    'agenda:create:all','agenda:read:all','agenda:update:all',
    'cama:read:all','quirofano:read:all');

-- facturacion: solo lectura
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'facturacion' AND p.codigo IN (
    'paciente:read:all','encuentro:read:all',
    'facturacion:read','analitica:read');

-- servicio_integracion: SOLO sincronización (mínimo privilegio estricto)
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'servicio_integracion' AND p.codigo IN (
    'fhir:sync:write','fhir:read:all',
    'paciente:read:all','encuentro:read:all','observacion:read:all');

-- paciente: solo lo suyo
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id FROM roles r, permisos p
WHERE r.codigo = 'paciente' AND p.codigo IN (
    'paciente:read:self','encuentro:read:self','observacion:read:self');

-- ============================================================================
-- CATÁLOGOS CLÍNICOS
-- ============================================================================

INSERT INTO especialidades (codigo, nombre, codigo_snomed, requiere_uci) VALUES
('CIR_GEN',  'Cirugía general',        NULL, FALSE),
('CIR_CAR',  'Cirugía cardiovascular', NULL, TRUE),
('NEUROCIR', 'Neurocirugía',           NULL, TRUE),
('ORTO',     'Ortopedia y traumatología', NULL, FALSE),
('URO',      'Urología',               NULL, FALSE),
('GINE',     'Ginecobstetricia',       NULL, FALSE),
('CIR_PLA',  'Cirugía plástica',       NULL, FALSE),
('CIR_VAS',  'Cirugía vascular',       NULL, TRUE),
('OFTAL',    'Oftalmología',           NULL, FALSE),
('ORL',      'Otorrinolaringología',   NULL, FALSE),
('ANEST',    'Anestesiología',         NULL, FALSE),
('MED_INT',  'Medicina interna',       NULL, FALSE),
('MED_GEN',  'Medicina general',       NULL, FALSE),
('URG',      'Medicina de urgencias',  NULL, FALSE);
-- NOTA: codigo_snomed pendiente de verificar en https://browser.ihtsdotools.org/

INSERT INTO tipos_cama (codigo, nombre, nivel_complejidad, codigo_snomed, costo_dia_cop) VALUES
('UCI',        'Unidad de Cuidados Intensivos',   4, '309904001', 1800000.00),
('UCIN',       'UCI Neonatal',                     4, NULL,        1900000.00),
('INTERMEDIA', 'Cuidados Intermedios',             3, NULL,         950000.00),
('GENERAL',    'Hospitalización general',          1, NULL,         420000.00),
('OBSERV_URG', 'Observación de urgencias',         2, NULL,         380000.00);
-- costo_dia_cop UCI: ~$1.800.000 (D.F. De la Cruz, com. personal, 6 sep 2026)
-- Los demás son estimaciones proporcionales; ajustar con datos institucionales.

INSERT INTO servicios (codigo, nombre, piso) VALUES
('URG',     'Urgencias',                    1),
('UCI_ADU', 'UCI Adultos',                  3),
('UCI_PED', 'UCI Pediátrica',               3),
('CIR',     'Cirugía / Salas de operación', 2),
('HOSP_1',  'Hospitalización piso 4',       4),
('HOSP_2',  'Hospitalización piso 5',       5),
('HOSP_3',  'Hospitalización piso 6',       6),
('MAT',     'Maternidad',                   4),
('CE',      'Consulta externa',             1);

INSERT INTO diagnosticos_cie10 (codigo, descripcion, capitulo) VALUES
('K35', 'Apendicitis aguda',                        'Enfermedades del sistema digestivo'),
('K80', 'Colelitiasis',                             'Enfermedades del sistema digestivo'),
('K40', 'Hernia inguinal',                          'Enfermedades del sistema digestivo'),
('I21', 'Infarto agudo del miocardio',              'Enfermedades del sistema circulatorio'),
('I25', 'Enfermedad isquémica crónica del corazón', 'Enfermedades del sistema circulatorio'),
('N20', 'Cálculo del riñón y del uréter',           'Enfermedades del sistema genitourinario'),
('S72', 'Fractura del fémur',                       'Traumatismos'),
('S06', 'Traumatismo intracraneal',                 'Traumatismos'),
('O82', 'Parto único por cesárea',                  'Embarazo, parto y puerperio'),
('H25', 'Catarata senil',                           'Enfermedades del ojo'),
('I70', 'Aterosclerosis',                           'Enfermedades del sistema circulatorio'),
('A41', 'Sepsis',                                   'Enfermedades infecciosas');

-- Causas de cancelación según taxonomía de Muñoz-Caicedo et al. (2019)
INSERT INTO catalogo_causas_cancelacion (codigo, descripcion, responsable, origen, evitable) VALUES
('PAC_NO_ASISTE',    'Paciente no se presenta a la cirugía',           'paciente',   NULL,            TRUE),
('PAC_NO_AYUNO',     'Paciente no cumplió el tiempo de ayuno',         'paciente',   NULL,            TRUE),
('PAC_GRIPA',        'Paciente con gripa, tos o fiebre',               'paciente',   NULL,            FALSE),
('PAC_INESTABLE',    'Paciente hemodinámicamente inestable',           'paciente',   NULL,            FALSE),
('PAC_NO_ACEPTA',    'Paciente no acepta el procedimiento',            'paciente',   NULL,            TRUE),
('PAC_SIN_COPAGO',   'Paciente no tiene dinero para el copago',        'paciente',   NULL,            TRUE),
('PRE_PROLONG_ANT',  'Prolongación de la cirugía anterior',            'prestador',  'administrativo',TRUE),
('PRE_SIN_CAMA_UCI', 'No disponibilidad de cama en UCI',               'prestador',  'administrativo',TRUE),
('PRE_SALA_OCUPADA', 'Reprogramación por sala ocupada',                'prestador',  'administrativo',TRUE),
('PRE_SIN_CAMILLA',  'Salas bloqueadas por falta de camillas',         'prestador',  'administrativo',TRUE),
('PRE_EQUIPO_DANADO','Equipo biomédico dañado o no disponible',        'prestador',  'administrativo',TRUE),
('PRE_SIN_INSUMO',   'Insumo o material quirúrgico no disponible',     'prestador',  'administrativo',TRUE),
('PRE_PROLONG_RECUP','Prolongación de los tiempos de recuperación',    'prestador',  'administrativo',TRUE),
('PRE_MED_TARDE',    'Médico llega tarde',                             'prestador',  'asistencial',   TRUE),
('PRE_MED_NO_ASISTE','Médico no se presenta',                          'prestador',  'asistencial',   TRUE),
('PRE_CAMBIO_CONDUCTA','Cambio de conducta médica',                    'prestador',  'asistencial',   FALSE),
('PRE_NO_REQUIERE',  'Paciente no requiere el procedimiento',          'prestador',  'asistencial',   FALSE),
('ASE_SIN_AUTORIZ',  'Exámenes o procedimiento no autorizados por EPS','asegurador', NULL,            TRUE),
('ASE_ORDEN_MAL',    'Orden de apoyo mal diligenciada',                'asegurador', NULL,            TRUE),
('ASE_ORDEN_INCOMP', 'Orden de apoyo incompleta',                      'asegurador', NULL,            TRUE);

INSERT INTO eps (codigo, nombre, regimen) VALUES
('EPS001', 'EPS Alfa',    'contributivo'),
('EPS002', 'EPS Beta',    'contributivo'),
('EPS003', 'EPS Gamma',   'subsidiado'),
('EPS004', 'EPS Delta',   'contributivo'),
('EPS005', 'EPS Epsilon', 'subsidiado'),
('EPS006', 'Régimen especial', 'especial'),
('PART',   'Particular',  NULL);

-- Catálogo de procedimientos.
-- duracion_estimada_min y tipo_cama_requerida reflejan el hallazgo de campo:
-- cirugías de órganos delicados (corazón, riñón, neuro) -> UCI.
INSERT INTO catalogo_procedimientos
 (codigo_interno, nombre, codigo_snomed, especialidad_id, duracion_estimada_min,
  duracion_desviacion_min, tipo_cama_requerida_id, requiere_arco_c, complejidad, tarifa_referencia_cop)
SELECT v.cod, v.nom, NULL, e.id, v.dur, v.desv, tc.id, v.arco, v.compl, v.tarifa
FROM (VALUES
 ('APENDIC',   'Apendicectomía',                        'CIR_GEN', 60,  20, 'GENERAL',    FALSE, 2,  3200000),
 ('COLECIST',  'Colecistectomía laparoscópica',         'CIR_GEN', 90,  25, 'GENERAL',    FALSE, 2,  4800000),
 ('HERNIO',    'Herniorrafia inguinal',                 'CIR_GEN', 75,  20, 'GENERAL',    FALSE, 2,  3600000),
 ('LAPAROT',   'Laparotomía exploratoria',              'CIR_GEN',150,  50, 'INTERMEDIA', FALSE, 3,  7500000),
 ('REVASC',    'Revascularización miocárdica',          'CIR_CAR',300,  75, 'UCI',        TRUE,  4, 45000000),
 ('VALVULA',   'Reemplazo valvular aórtico',            'CIR_CAR',270,  70, 'UCI',        TRUE,  4, 42000000),
 ('CRANEOT',   'Craneotomía',                           'NEUROCIR',240, 65, 'UCI',        TRUE,  4, 28000000),
 ('LAMINEC',   'Laminectomía lumbar',                   'NEUROCIR',150, 40, 'INTERMEDIA', TRUE,  3, 12000000),
 ('OSTEOS',    'Osteosíntesis de fémur',                'ORTO',    120, 35, 'GENERAL',    TRUE,  3,  8500000),
 ('ARTROPL',   'Artroplastia total de cadera',          'ORTO',    150, 40, 'GENERAL',    TRUE,  3, 15000000),
 ('ARTROSC',   'Artroscopia de rodilla',                'ORTO',     60, 20, 'GENERAL',    FALSE, 2,  4200000),
 ('NEFREC',    'Nefrectomía',                           'URO',     180, 45, 'UCI',        FALSE, 4, 14000000),
 ('RTU',       'Resección transuretral de próstata',    'URO',      90, 25, 'GENERAL',    FALSE, 2,  5500000),
 ('LITOT',     'Litotricia / nefrolitotomía',           'URO',      90, 30, 'GENERAL',    TRUE,  2,  6200000),
 ('CESAREA',   'Cesárea',                               'GINE',     45, 15, 'GENERAL',    FALSE, 2,  3800000),
 ('HISTER',    'Histerectomía abdominal',               'GINE',    120, 35, 'GENERAL',    FALSE, 3,  6800000),
 ('BYPASS_FEM','Bypass femoropoplíteo',                 'CIR_VAS', 180, 50, 'INTERMEDIA', TRUE,  4, 18000000),
 ('ANEURISM',  'Corrección de aneurisma aórtico',       'CIR_VAS', 240, 70, 'UCI',        TRUE,  4, 38000000),
 ('FACO',      'Facoemulsificación de catarata',        'OFTAL',    30, 10, 'GENERAL',    FALSE, 1,  2800000),
 ('AMIGDAL',   'Amigdalectomía',                        'ORL',      45, 15, 'GENERAL',    FALSE, 1,  2600000),
 ('SEPTO',     'Septoplastia',                          'ORL',      60, 20, 'GENERAL',    FALSE, 2,  3400000),
 ('INJERTO',   'Injerto de piel',                       'CIR_PLA',  90, 30, 'GENERAL',    FALSE, 2,  5000000)
) AS v(cod, nom, esp, dur, desv, cama, arco, compl, tarifa)
JOIN especialidades e ON e.codigo = v.esp
JOIN tipos_cama tc    ON tc.codigo = v.cama;
