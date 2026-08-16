"""Acceso a datos para Bitacoras-Entregas.

Todas las escrituras pasan por `insertar`, `actualizar` o `anular`/`anular_documento`,
que registran un asiento en `auditoria`. Nunca se ejecuta DELETE sobre tablas
operacionales: la baja de un registro es siempre logica.

Todos los timestamps se guardan en UTC. La conversion a hora local es
responsabilidad exclusiva de la capa de presentacion (ver `formatear_fechas_local`).

Los nombres de tabla y columna que se interpolan en SQL dinamico se validan
siempre contra una lista blanca (`TABLAS_PERMITIDAS` / `_columnas`) antes de
construir la sentencia; los valores siempre viajan parametrizados con `?`.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "bitacora.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"

ESTADOS_VIAJE = ["Planificado", "En curso", "Finalizado", "Cancelado"]
ESTADOS_DOCUMENTO = ["Emitido", "Corregido", "Anulado"]
ESTADOS_ENTREGA = ["Pendiente", "Entregado", "Parcial", "Rechazado", "Devuelta"]

# Lista blanca de tablas que pueden recibir escrituras dinamicas (insertar/
# actualizar/anular). "auditoria" queda deliberadamente fuera: solo se
# escribe desde `_registrar_auditoria`, nunca desde codigo de paginas.
TABLAS_PERMITIDAS = {
    "usuario",
    "establecimiento",
    "producto",
    "viaje",
    "viaje_establecimiento",
    "documento",
    "documento_producto",
    "documento_producto_lote",
}


class ErrorNegocio(ValueError):
    """Violacion de una regla de negocio (no de integridad de la base)."""


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def _now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _utc_a_local(valor):
    """Convierte un timestamp UTC 'YYYY-MM-DD HH:MM:SS' a hora local del sistema.

    Solo para visualizacion: nunca se usa este resultado para escribir en la base.
    """
    if not valor:
        return valor
    try:
        dt_utc = datetime.strptime(str(valor), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return valor
    return dt_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def formatear_fechas_local(df, columnas):
    """Devuelve una copia de `df` con las `columnas` de fecha UTC convertidas a hora local."""
    df = df.copy()
    for col in columnas:
        if col in df.columns:
            df[col] = df[col].apply(_utc_a_local)
    return df


def _validar_tabla(tabla):
    if tabla not in TABLAS_PERMITIDAS:
        raise ValueError(f"Tabla no permitida: {tabla!r}")


def _columnas(conn, tabla):
    _validar_tabla(tabla)
    return {fila["name"] for fila in conn.execute(f"PRAGMA table_info({tabla})")}


def _validar_columnas(campos_tabla, columnas):
    invalidas = [c for c in columnas if c not in campos_tabla]
    if invalidas:
        raise ValueError(f"Columnas no permitidas: {invalidas}")


def _nombre_usuario(conn, usuario_id):
    if usuario_id is None:
        return None
    fila = conn.execute("SELECT nombre FROM usuario WHERE id = ?", (usuario_id,)).fetchone()
    return fila["nombre"] if fila else None


def _registrar_auditoria(conn, tabla, registro_id, accion, usuario_id, detalle=None):
    conn.execute(
        "INSERT INTO auditoria (tabla, registro_id, accion, usuario, fecha_hora, detalle) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (tabla, registro_id, accion, _nombre_usuario(conn, usuario_id), _now_utc(), detalle),
    )


def consultar(sql, params=()):
    """Ejecuta un SELECT (con SQL fijo y parametros) y devuelve un DataFrame."""
    conn = get_connection()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def insertar(tabla, datos, usuario_id=None):
    """Inserta un registro nuevo y registra CREACION en auditoria. Devuelve el id creado."""
    conn = get_connection()
    try:
        campos_tabla = _columnas(conn, tabla)
        datos = dict(datos)
        _validar_columnas(campos_tabla, datos.keys())
        if "creado_por" in campos_tabla:
            datos["creado_por"] = usuario_id
        if "modificado_por" in campos_tabla:
            datos["modificado_por"] = usuario_id
        columnas = list(datos.keys())
        placeholders = ", ".join("?" for _ in columnas)
        sql = f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({placeholders})"
        cur = conn.execute(sql, [datos[c] for c in columnas])
        registro_id = cur.lastrowid
        _registrar_auditoria(conn, tabla, registro_id, "CREACION", usuario_id)
        conn.commit()
        return registro_id
    finally:
        conn.close()


def actualizar(tabla, registro_id, datos, usuario_id=None, detalle=None):
    """Actualiza campos de un registro existente y registra MODIFICACION en auditoria."""
    conn = get_connection()
    try:
        campos_tabla = _columnas(conn, tabla)
        datos = dict(datos)
        _validar_columnas(campos_tabla, datos.keys())
        if "fecha_modificacion" in campos_tabla:
            datos["fecha_modificacion"] = _now_utc()
        if "modificado_por" in campos_tabla:
            datos["modificado_por"] = usuario_id
        columnas = list(datos.keys())
        set_clause = ", ".join(f"{c} = ?" for c in columnas)
        sql = f"UPDATE {tabla} SET {set_clause} WHERE id = ?"
        conn.execute(sql, [datos[c] for c in columnas] + [registro_id])
        _registrar_auditoria(conn, tabla, registro_id, "MODIFICACION", usuario_id, detalle)
        conn.commit()
    finally:
        conn.close()


def anular(tabla, registro_id, usuario_id, motivo, campo_estado=None, valor_anulado=None):
    """Baja logica de un registro operacional. Motivo y usuario son obligatorios.

    Si la tabla tiene un estado de negocio propio (`campo_estado`), la anulacion
    fija ese campo a `valor_anulado` (ej. estado_viaje='Cancelado'). Si no, apaga
    la columna `activo`. En ningun caso se borra la fila. Queda un asiento
    ANULACION en `auditoria` con el motivo, el usuario y la fecha/hora (UTC).
    """
    if not usuario_id:
        raise ErrorNegocio("Se requiere un usuario responsable para anular un registro.")
    if not motivo or not motivo.strip():
        raise ErrorNegocio("Se requiere un motivo para anular un registro.")

    conn = get_connection()
    try:
        campos_tabla = _columnas(conn, tabla)
        datos = {campo_estado: valor_anulado} if campo_estado else {"activo": 0}
        _validar_columnas(campos_tabla, datos.keys())
        if "fecha_modificacion" in campos_tabla:
            datos["fecha_modificacion"] = _now_utc()
        if "modificado_por" in campos_tabla:
            datos["modificado_por"] = usuario_id
        columnas = list(datos.keys())
        set_clause = ", ".join(f"{c} = ?" for c in columnas)
        sql = f"UPDATE {tabla} SET {set_clause} WHERE id = ?"
        conn.execute(sql, [datos[c] for c in columnas] + [registro_id])
        _registrar_auditoria(conn, tabla, registro_id, "ANULACION", usuario_id, motivo.strip())
        conn.commit()
    finally:
        conn.close()


def anular_documento(documento_id, usuario_id, motivo):
    """Anula un documento aplicando las reglas de coherencia de negocio:

    - No se puede anular un documento cuya entrega ya fue completada
      (estado_entrega='Entregado'); primero hay que corregir/revertir ese
      estado desde el formulario de edicion (por ejemplo a 'Devuelta' o
      'Rechazado') y recien despues anular el documento.
    - Al anular, las lineas de producto (`documento_producto`) que sigan
      activas y sus lotes (`documento_producto_lote`) se dan de baja logica
      en cascada, dejando su propio asiento de auditoria. Nada se borra:
      una entrega completa, parcial, rechazada o devuelta se conserva
      siempre para trazabilidad.
    """
    if not usuario_id:
        raise ErrorNegocio("Se requiere un usuario responsable para anular el documento.")
    if not motivo or not motivo.strip():
        raise ErrorNegocio("Se requiere un motivo para anular el documento.")
    motivo = motivo.strip()

    conn = get_connection()
    try:
        fila = conn.execute(
            "SELECT estado_documento, estado_entrega FROM documento WHERE id = ?", (documento_id,)
        ).fetchone()
        if fila is None:
            raise ErrorNegocio("El documento no existe.")
        if fila["estado_documento"] == "Anulado":
            raise ErrorNegocio("El documento ya esta anulado.")
        if fila["estado_entrega"] == "Entregado":
            raise ErrorNegocio(
                "No se puede anular un documento con la entrega ya completada. Primero corrige "
                "el estado de la entrega (por ejemplo a 'Devuelta' o 'Rechazado') desde el "
                "formulario de edicion del documento, y luego anulalo."
            )

        ahora = _now_utc()
        conn.execute(
            "UPDATE documento SET estado_documento = 'Anulado', fecha_modificacion = ?, "
            "modificado_por = ? WHERE id = ?",
            (ahora, usuario_id, documento_id),
        )
        _registrar_auditoria(conn, "documento", documento_id, "ANULACION", usuario_id, motivo)

        lineas = conn.execute(
            "SELECT id FROM documento_producto WHERE documento_id = ? AND activo = 1", (documento_id,)
        ).fetchall()
        for linea in lineas:
            dp_id = linea["id"]
            conn.execute(
                "UPDATE documento_producto SET activo = 0, fecha_modificacion = ?, modificado_por = ? "
                "WHERE id = ?",
                (ahora, usuario_id, dp_id),
            )
            detalle_cascada = f"Baja en cascada por anulacion del documento #{documento_id}: {motivo}"
            _registrar_auditoria(conn, "documento_producto", dp_id, "ANULACION", usuario_id, detalle_cascada)

            lotes = conn.execute(
                "SELECT id FROM documento_producto_lote WHERE documento_producto_id = ? AND activo = 1",
                (dp_id,),
            ).fetchall()
            for lote in lotes:
                lote_id = lote["id"]
                conn.execute(
                    "UPDATE documento_producto_lote SET activo = 0, fecha_modificacion = ?, "
                    "modificado_por = ? WHERE id = ?",
                    (ahora, usuario_id, lote_id),
                )
                _registrar_auditoria(
                    conn, "documento_producto_lote", lote_id, "ANULACION", usuario_id, detalle_cascada
                )

        conn.commit()
    finally:
        conn.close()
