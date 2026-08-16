"""Utilidades de UI compartidas entre app.py y las paginas de pages/."""

import sqlite3

import streamlit as st

import db


def ejecutar_con_manejo(func, *args, mensaje_exito=None, **kwargs):
    """Ejecuta una escritura a la base de datos capturando errores esperables.

    Evita que una violacion de integridad (ej. SKU/codigo duplicado) o una
    regla de negocio (ej. `db.ErrorNegocio`) tire abajo la app con un
    traceback crudo. Devuelve (resultado, ok).
    """
    try:
        resultado = func(*args, **kwargs)
    except db.ErrorNegocio as exc:
        st.error(str(exc))
        return None, False
    except sqlite3.IntegrityError as exc:
        st.error(f"No se pudo guardar: la operacion viola una regla de integridad de datos ({exc}).")
        return None, False
    except sqlite3.Error as exc:
        st.error(f"No se pudo completar la operacion en la base de datos: {exc}")
        return None, False
    else:
        if mensaje_exito:
            st.success(mensaje_exito)
        return resultado, True


def seleccionar_por_id(label, df, columna_id="id", formato=None, **kwargs):
    """Selectbox que opera internamente por id (nunca por nombre, que puede repetirse).

    `formato(fila)` decide el texto mostrado; por defecto "#id - nombre" si
    `df` tiene columna 'nombre', o solo "#id" si no. Devuelve el id elegido
    (o None si `df` esta vacio).
    """
    if df.empty:
        return None
    if formato is None:
        if "nombre" in df.columns:
            formato = lambda fila: f"#{fila[columna_id]} - {fila['nombre']}"
        else:
            formato = lambda fila: f"#{fila[columna_id]}"
    etiquetas = {int(fila[columna_id]): formato(fila) for _, fila in df.iterrows()}
    ids = list(etiquetas.keys())
    return st.selectbox(label, ids, format_func=lambda i: etiquetas[i], **kwargs)


def seleccionar_usuario_actual():
    """Sidebar: elegir/crear el "usuario actual" de la sesion, operando por id.

    No hay autenticacion todavia; esta seleccion es lo que se guarda en
    creado_por/modificado_por y en la auditoria. Devuelve el id de usuario.
    """
    usuarios = db.consultar("SELECT id, nombre FROM usuario WHERE activo = 1 ORDER BY nombre")

    st.sidebar.subheader("Usuario actual")

    with st.sidebar.form("form_nuevo_usuario", clear_on_submit=True):
        nuevo = st.text_input("Nuevo usuario")
        if st.form_submit_button("Crear usuario") and nuevo.strip():
            nuevo_id, ok = ejecutar_con_manejo(db.insertar, "usuario", {"nombre": nuevo.strip()})
            if ok:
                st.session_state["usuario_actual_id"] = nuevo_id
                st.rerun()

    if usuarios.empty:
        st.sidebar.warning("Crea un usuario para continuar.")
        st.stop()

    id_actual = st.session_state.get("usuario_actual_id")
    ids = usuarios["id"].tolist()
    index = ids.index(id_actual) if id_actual in ids else 0
    seleccion_id = seleccionar_por_id("Trabajando como", usuarios, index=index)

    st.session_state["usuario_actual_id"] = int(seleccion_id)
    return int(seleccion_id)
