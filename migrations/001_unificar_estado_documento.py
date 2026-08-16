"""Migracion 001: unificar documento.estado_documento + estado_entrega en un solo campo.

Uso:
    python migrations/001_unificar_estado_documento.py --db-path <ruta_a_la_base> [--dry-run]

Este script NUNCA se ejecuta automaticamente: no esta enganchado a
db.init_db() ni a app.py. Requiere la ruta de la base como argumento
explicito -- no hay ningun default -- para que sea imposible correrlo por
error contra el archivo equivocado.

Reglas de la migracion (todas confirmadas explicitamente antes de escribir
este script):

1. `documento_producto` y `documento_producto_lote` NUNCA se tocan: no se
   les hace DROP, no se les borra ningun dato, no se leen ni se escriben.
   Quedan inertes como informacion historica del modelo anterior.

2. Solo se migran filas de `documento` cuya combinacion
   (estado_documento, estado_entrega) esta en MAPEO_DIRECTO. Si aparece
   una sola fila fuera de ese mapeo (cualquier 'Corregido', o 'Anulado'
   combinado con algo distinto de 'Pendiente'), la migracion se ABORTA
   POR COMPLETO: no se aplica nada, ni siquiera parcialmente.

3. Cada fila migrada genera un asiento en `auditoria` (accion
   'MODIFICACION', usuario 'MIGRACION_ESQUEMA_001') con el detalle exacto
   del mapeo aplicado, para no perder la informacion de `estado_entrega`
   aunque la columna desaparezca de `documento`.

4. Todo corre dentro de una unica transaccion explicita. Se valida
   `PRAGMA foreign_key_check` antes de hacer commit; si hay cualquier
   violacion, se hace rollback y no se aplica nada.

5. Es idempotente: si `documento` ya tiene el esquema nuevo (sin la
   columna `estado_entrega`), el script no hace nada y lo informa.
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Mapeo directo confirmado explicitamente. Cualquier combinacion que NO
# este aca (en particular cualquier 'Corregido', o 'Anulado' con
# estado_entrega distinto de 'Pendiente') se considera dudosa y bloquea
# toda la migracion.
MAPEO_DIRECTO = {
    ("Emitido", "Pendiente"): "Pendiente",
    ("Emitido", "Entregado"): "Entregado",
    ("Emitido", "Parcial"): "Entrega parcial",
    ("Emitido", "Rechazado"): "Rechazado",
    ("Emitido", "Devuelta"): "Devuelto",
    ("Anulado", "Pendiente"): "Anulado",
}

DDL_DOCUMENTO_NUEVO = """
CREATE TABLE documento_new (
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
)
"""


def _now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _tiene_esquema_nuevo(conn):
    fila = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='documento'"
    ).fetchone()
    if fila is None or fila[0] is None:
        raise SystemExit("No existe la tabla 'documento' en esta base. Nada que migrar.")
    return "estado_entrega" not in fila[0]


def _clasificar_filas(conn):
    """Devuelve (migrables, dudosas) como listas de sqlite3.Row de `documento`."""
    filas = conn.execute("SELECT * FROM documento").fetchall()
    migrables, dudosas = [], []
    for fila in filas:
        clave = (fila["estado_documento"], fila["estado_entrega"])
        (migrables if clave in MAPEO_DIRECTO else dudosas).append(fila)
    return migrables, dudosas


def _reportar_clasificacion(total, migrables, dudosas):
    print(f"Filas en 'documento': {total}")
    print(f"  Migrables (mapeo directo confirmado): {len(migrables)}")
    print(f"  Dudosas (fuera del mapeo confirmado): {len(dudosas)}")
    if dudosas:
        print()
        print("Filas dudosas (bloquean toda la migracion si se ejecuta):")
        for fila in dudosas:
            print(
                f"  id={fila['id']} estado_documento={fila['estado_documento']!r} "
                f"estado_entrega={fila['estado_entrega']!r}"
            )


def dry_run(db_path: Path):
    """Solo lectura: clasifica las filas y reporta, sin abrir ninguna transaccion de escritura."""
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if _tiene_esquema_nuevo(conn):
            print(f"'{db_path}' ya tiene el esquema nuevo de 'documento' (sin 'estado_entrega'). Nada que migrar.")
            return
        total = conn.execute("SELECT COUNT(*) AS n FROM documento").fetchone()["n"]
        migrables, dudosas = _clasificar_filas(conn)
        _reportar_clasificacion(total, migrables, dudosas)
        print()
        if dudosas:
            print("[DRY RUN] Con estos datos, la migracion real ABORTARIA sin aplicar nada.")
        else:
            print("[DRY RUN] Con estos datos, la migracion real se aplicaria sin bloqueos.")
    finally:
        conn.close()


def migrar(db_path: Path):
    if not db_path.exists():
        raise SystemExit(f"No existe el archivo: {db_path}")

    conn = sqlite3.connect(db_path, isolation_level=None)  # control manual de transaccion
    conn.row_factory = sqlite3.Row

    try:
        if _tiene_esquema_nuevo(conn):
            print(f"'{db_path}' ya tiene el esquema nuevo de 'documento' (sin 'estado_entrega'). Nada que hacer.")
            return

        total_antes = conn.execute("SELECT COUNT(*) AS n FROM documento").fetchone()["n"]
        migrables, dudosas = _clasificar_filas(conn)
        _reportar_clasificacion(total_antes, migrables, dudosas)

        if dudosas:
            print()
            print("MIGRACION ABORTADA: hay filas fuera del mapeo directo confirmado.")
            print("No se aplico ningun cambio (no se abrio transaccion de escritura).")
            raise SystemExit(1)

        # foreign_keys solo puede cambiarse fuera de una transaccion activa.
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")

        conn.execute(DDL_DOCUMENTO_NUEVO)

        ahora = _now_utc()
        for fila in migrables:
            clave = (fila["estado_documento"], fila["estado_entrega"])
            nuevo_estado = MAPEO_DIRECTO[clave]
            conn.execute(
                """
                INSERT INTO documento_new
                    (id, viaje_establecimiento_id, tipo_documento, numero_documento, fecha_documento,
                     estado_documento, fecha_creacion, fecha_modificacion, creado_por, modificado_por)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fila["id"], fila["viaje_establecimiento_id"], fila["tipo_documento"],
                    fila["numero_documento"], fila["fecha_documento"], nuevo_estado,
                    fila["fecha_creacion"], fila["fecha_modificacion"],
                    fila["creado_por"], fila["modificado_por"],
                ),
            )
            detalle = (
                f"Migracion de esquema 001: estado_documento={fila['estado_documento']!r} + "
                f"estado_entrega={fila['estado_entrega']!r} -> estado_documento={nuevo_estado!r}"
            )
            conn.execute(
                "INSERT INTO auditoria (tabla, registro_id, accion, usuario, fecha_hora, detalle) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("documento", fila["id"], "MODIFICACION", "MIGRACION_ESQUEMA_001", ahora, detalle),
            )

        conn.execute("DROP TABLE documento")
        conn.execute("ALTER TABLE documento_new RENAME TO documento")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_documento_viaje_establecimiento "
            "ON documento(viaje_establecimiento_id)"
        )

        violaciones = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violaciones:
            conn.execute("ROLLBACK")
            print()
            print("MIGRACION ABORTADA: PRAGMA foreign_key_check encontro violaciones tras reconstruir la tabla.")
            for v in violaciones:
                print(" ", dict(v))
            raise SystemExit(1)

        total_despues = conn.execute("SELECT COUNT(*) AS n FROM documento").fetchone()["n"]
        if total_despues != total_antes:
            conn.execute("ROLLBACK")
            print()
            print(f"MIGRACION ABORTADA: el conteo de filas no coincide ({total_antes} antes, {total_despues} despues).")
            raise SystemExit(1)

        conn.execute("COMMIT")
        conn.execute("PRAGMA foreign_keys = ON")

        print()
        print(f"Migracion aplicada con exito: {total_despues} documento(s) migrado(s).")
        print("documento_producto y documento_producto_lote no fueron tocadas (siguen inertes, sin DROP).")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-path", required=True, help="Ruta explicita al archivo .db a migrar (sin default).")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Solo clasifica y reporta (conexion de solo lectura); no escribe nada.",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if args.dry_run:
        dry_run(db_path)
    else:
        migrar(db_path)


if __name__ == "__main__":
    sys.exit(main())
