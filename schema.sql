-- Bitacoras-Entregas: esquema SQLite
-- No se ejecuta ningun DELETE sobre estas tablas desde la aplicacion.
-- La baja de un registro operacional es siempre logica (ver db.py).
-- Todos los timestamps se guardan en UTC (datetime('now') de SQLite ya es UTC;
-- el codigo Python usa datetime.now(timezone.utc) para ser consistente). La
-- conversion a hora local se hace unicamente al mostrar datos en la UI.
--
-- NOTA (MVP incidencias): documento_producto y documento_producto_lote
-- quedaron fuera del esquema activo -- el documento/folio es la unidad
-- principal de seguimiento, y el detalle de producto solo se registra
-- cuando hay una incidencia (ver incidencia_producto). Si una base de datos
-- existente (data/bitacora.db) todavia tiene esas tablas de una version
-- anterior, no se tocan ni se borran: simplemente esta aplicacion no las
-- referencia mas.

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

-- Catalogo de productos: se mantiene, pero en el MVP de incidencias no es
-- requisito previo de nada (la pagina que lo administra esta oculta del
-- menu principal). incidencia_producto NO tiene FK hacia esta tabla.
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
-- Jerarquia: viaje -> establecimientos (varios) -> documentos/folios
--            (varios) -> resultado de entrega (estado_documento) ->
--            incidencias de producto (cero, una o varias, solo si hay
--            discrepancia detectada en destino).
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

-- El documento/folio es la unidad principal de seguimiento. estado_documento
-- unifica en un solo campo tanto el ciclo administrativo como el resultado
-- de la entrega (antes eran dos columnas separadas: estado_documento +
-- estado_entrega).
CREATE TABLE IF NOT EXISTS documento (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    viaje_establecimiento_id INTEGER NOT NULL REFERENCES viaje_establecimiento(id),
    tipo_documento          TEXT NOT NULL,
    numero_documento        TEXT,
    fecha_documento         TEXT,
    estado_documento        TEXT NOT NULL DEFAULT 'Pendiente'
                                CHECK (estado_documento IN (
                                    'Pendiente', 'Cargado', 'Entregado', 'Entregado con observaciones',
                                    'Entrega parcial', 'No entregado', 'Rechazado', 'Devuelto', 'Anulado'
                                )),
    fecha_creacion          TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_modificacion      TEXT NOT NULL DEFAULT (datetime('now')),
    creado_por              INTEGER REFERENCES usuario(id),
    modificado_por          INTEGER REFERENCES usuario(id)
);

-- Incidencia de producto: SOLO se registra cuando hay una discrepancia
-- detectada en destino (faltante, sobrante, vencido, etc.). Un documento
-- puede tener cero, una o varias. El producto se describe en texto libre
-- (producto_codigo/producto_descripcion) -- NO hay FK al catalogo
-- `producto`, porque no se exige precargar productos para registrar una
-- incidencia. estado_resolucion es independiente del estado_documento del
-- documento al que pertenece.
CREATE TABLE IF NOT EXISTS incidencia_producto (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id            INTEGER NOT NULL REFERENCES documento(id),
    producto_codigo         TEXT,
    producto_descripcion    TEXT NOT NULL,
    tipo_incidencia         TEXT NOT NULL
                                CHECK (tipo_incidencia IN (
                                    'Faltante', 'Sobrante', 'Deteriorado', 'Rechazado',
                                    'Vencimiento próximo', 'Vencido', 'Error de lote',
                                    'Producto incorrecto', 'Cantidad incorrecta',
                                    'Problema de embalaje', 'Problema de cadena de frío', 'Otro'
                                )),
    cantidad_afectada       REAL NOT NULL DEFAULT 0,
    lote                    TEXT,
    fecha_vencimiento       TEXT,
    motivo_detalle          TEXT NOT NULL,
    accion_tomada           TEXT,
    estado_resolucion       TEXT NOT NULL DEFAULT 'Abierta'
                                CHECK (estado_resolucion IN ('Abierta', 'En gestión', 'Resuelta', 'Cerrada sin resolución')),
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
CREATE INDEX IF NOT EXISTS idx_incidencia_producto_documento ON incidencia_producto(documento_id);
CREATE INDEX IF NOT EXISTS idx_auditoria_tabla_registro ON auditoria(tabla, registro_id);
