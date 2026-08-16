-- Bitacoras-Entregas: esquema SQLite
-- No se ejecuta ningun DELETE sobre estas tablas desde la aplicacion.
-- La baja de un registro operacional es siempre logica (ver db.py).
-- Todos los timestamps se guardan en UTC (datetime('now') de SQLite ya es UTC;
-- el codigo Python usa datetime.now(timezone.utc) para ser consistente). La
-- conversion a hora local se hace unicamente al mostrar datos en la UI.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- Catalogos
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS usuario (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre              TEXT NOT NULL UNIQUE,
    activo              INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    fecha_creacion      TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_modificacion  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- El nombre NO es identificador unico de negocio (puede repetirse); el
-- codigo institucional, si existe, si debe ser unico. Los selectores de la
-- UI siempre operan por id, nunca por nombre/codigo.
CREATE TABLE IF NOT EXISTS establecimiento (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo              TEXT UNIQUE,
    nombre              TEXT NOT NULL,
    tipo                TEXT,
    direccion           TEXT,
    activo              INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    fecha_creacion      TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_modificacion  TEXT NOT NULL DEFAULT (datetime('now')),
    creado_por          INTEGER REFERENCES usuario(id),
    modificado_por      INTEGER REFERENCES usuario(id)
);

-- El nombre NO es identificador unico (puede repetirse); el SKU, si existe,
-- si debe ser unico.
CREATE TABLE IF NOT EXISTS producto (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre              TEXT NOT NULL,
    sku                 TEXT UNIQUE,
    unidad              TEXT,
    activo              INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    fecha_creacion      TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_modificacion  TEXT NOT NULL DEFAULT (datetime('now')),
    creado_por          INTEGER REFERENCES usuario(id),
    modificado_por      INTEGER REFERENCES usuario(id)
);

-- ---------------------------------------------------------------------
-- Operacional
-- Jerarquia: viaje -> establecimientos (varios) -> documentos (varios) ->
--            productos (varios) -> lotes (uno o varios)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS viaje (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo              TEXT NOT NULL,
    fecha_inicio        TEXT,
    fecha_fin_estimada  TEXT,
    estado_viaje        TEXT NOT NULL DEFAULT 'Planificado'
                            CHECK (estado_viaje IN ('Planificado', 'En curso', 'Finalizado', 'Cancelado')),
    responsable_id      INTEGER REFERENCES usuario(id),
    fecha_creacion      TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_modificacion  TEXT NOT NULL DEFAULT (datetime('now')),
    creado_por          INTEGER REFERENCES usuario(id),
    modificado_por      INTEGER REFERENCES usuario(id)
);

-- Visita de un viaje a un establecimiento (1 viaje -> varios establecimientos).
CREATE TABLE IF NOT EXISTS viaje_establecimiento (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    viaje_id            INTEGER NOT NULL REFERENCES viaje(id),
    establecimiento_id  INTEGER NOT NULL REFERENCES establecimiento(id),
    orden               INTEGER,
    activo              INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    fecha_creacion      TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_modificacion  TEXT NOT NULL DEFAULT (datetime('now')),
    creado_por          INTEGER REFERENCES usuario(id),
    modificado_por      INTEGER REFERENCES usuario(id)
);

-- 1 establecimiento visitado -> varios documentos.
CREATE TABLE IF NOT EXISTS documento (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    viaje_establecimiento_id INTEGER NOT NULL REFERENCES viaje_establecimiento(id),
    tipo_documento          TEXT NOT NULL,
    numero_documento        TEXT,
    fecha_documento         TEXT,
    estado_documento        TEXT NOT NULL DEFAULT 'Emitido'
                                CHECK (estado_documento IN ('Emitido', 'Corregido', 'Anulado')),
    estado_entrega          TEXT NOT NULL DEFAULT 'Pendiente'
                                CHECK (estado_entrega IN ('Pendiente', 'Entregado', 'Parcial', 'Rechazado', 'Devuelta')),
    fecha_creacion          TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_modificacion      TEXT NOT NULL DEFAULT (datetime('now')),
    creado_por              INTEGER REFERENCES usuario(id),
    modificado_por          INTEGER REFERENCES usuario(id)
);

-- 1 documento -> varios productos. Cantidades desagregadas para poder
-- distinguir lo pedido, lo despachado y lo efectivamente entregado; la
-- diferencia (despachado - entregado) se calcula en las consultas, no se
-- almacena, para evitar un valor derivado que pueda desincronizarse.
CREATE TABLE IF NOT EXISTS documento_producto (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id            INTEGER NOT NULL REFERENCES documento(id),
    producto_id             INTEGER NOT NULL REFERENCES producto(id),
    cantidad_solicitada     REAL NOT NULL DEFAULT 0,
    cantidad_despachada     REAL NOT NULL DEFAULT 0,
    cantidad_entregada      REAL NOT NULL DEFAULT 0,
    motivo_entrega_parcial  TEXT,
    activo                  INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    fecha_creacion          TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_modificacion      TEXT NOT NULL DEFAULT (datetime('now')),
    creado_por              INTEGER REFERENCES usuario(id),
    modificado_por          INTEGER REFERENCES usuario(id)
);

-- 1 linea de producto en un documento -> uno o varios lotes. Lote y
-- vencimiento pertenecen al detalle documental, NUNCA al catalogo de
-- productos (un mismo producto puede llegar en distintos lotes en
-- distintas entregas).
CREATE TABLE IF NOT EXISTS documento_producto_lote (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_producto_id   INTEGER NOT NULL REFERENCES documento_producto(id),
    lote                    TEXT NOT NULL,
    fecha_vencimiento       TEXT,
    cantidad_lote           REAL NOT NULL DEFAULT 0,
    activo                  INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    fecha_creacion          TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_modificacion      TEXT NOT NULL DEFAULT (datetime('now')),
    creado_por              INTEGER REFERENCES usuario(id),
    modificado_por          INTEGER REFERENCES usuario(id)
);

-- ---------------------------------------------------------------------
-- Trazabilidad
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS auditoria (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tabla        TEXT NOT NULL,
    registro_id  INTEGER NOT NULL,
    accion       TEXT NOT NULL CHECK (accion IN ('CREACION', 'MODIFICACION', 'ANULACION')),
    usuario      TEXT,
    fecha_hora   TEXT NOT NULL DEFAULT (datetime('now')),
    detalle      TEXT
);

CREATE INDEX IF NOT EXISTS idx_viaje_establecimiento_viaje ON viaje_establecimiento(viaje_id);
CREATE INDEX IF NOT EXISTS idx_viaje_establecimiento_establecimiento ON viaje_establecimiento(establecimiento_id);
CREATE INDEX IF NOT EXISTS idx_documento_viaje_establecimiento ON documento(viaje_establecimiento_id);
CREATE INDEX IF NOT EXISTS idx_documento_producto_documento ON documento_producto(documento_id);
CREATE INDEX IF NOT EXISTS idx_documento_producto_producto ON documento_producto(producto_id);
CREATE INDEX IF NOT EXISTS idx_documento_producto_lote_dp ON documento_producto_lote(documento_producto_id);
CREATE INDEX IF NOT EXISTS idx_auditoria_tabla_registro ON auditoria(tabla, registro_id);
