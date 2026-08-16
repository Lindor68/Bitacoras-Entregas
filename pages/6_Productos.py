import streamlit as st

import db
from common import ejecutar_con_manejo, seleccionar_por_id, seleccionar_usuario_actual

db.init_db()

st.caption(
    "Catalogo opcional: en el MVP de incidencias no hace falta precargar productos aca. "
    "Los productos afectados se registran directamente en la pagina Incidencias."
)

usuario_id = seleccionar_usuario_actual()

st.title("Productos")

mostrar_inactivos = st.checkbox("Mostrar dados de baja", value=False)

sql = "SELECT id, nombre, sku, unidad, activo, fecha_creacion, fecha_modificacion FROM producto"
if not mostrar_inactivos:
    sql += " WHERE activo = 1"
sql += " ORDER BY nombre"

productos = db.consultar(sql)
st.dataframe(
    db.formatear_fechas_local(productos, ["fecha_creacion", "fecha_modificacion"]),
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.subheader("Registrar nuevo producto")
st.caption("El SKU, si se indica, es el identificador unico del producto (el nombre puede repetirse).")

with st.form("form_nuevo_producto", clear_on_submit=True):
    nombre = st.text_input("Nombre *")
    sku = st.text_input("SKU / codigo (unico, recomendado)")
    unidad = st.text_input("Unidad (unidad, kg, caja, ...)")
    if st.form_submit_button("Crear producto"):
        if not nombre.strip():
            st.error("El nombre es obligatorio.")
        else:
            _, ok = ejecutar_con_manejo(
                db.insertar,
                "producto",
                {"nombre": nombre.strip(), "sku": sku.strip() or None, "unidad": unidad.strip() or None},
                usuario_id,
                mensaje_exito=f"Producto '{nombre}' creado.",
            )
            if ok:
                st.rerun()

st.divider()
st.subheader("Editar / dar de baja producto")

activos = db.consultar("SELECT id, nombre, sku, unidad FROM producto WHERE activo = 1 ORDER BY nombre")

if activos.empty:
    st.info("No hay productos activos todavia.")
else:
    prod_id = seleccionar_por_id(
        "Selecciona un producto", activos, formato=lambda f: f"#{f['id']} - {f['nombre']} ({f['sku'] or 'sin SKU'})"
    )
    actual = activos[activos["id"] == prod_id].iloc[0]

    with st.form("form_editar_producto"):
        nombre_edit = st.text_input("Nombre", value=actual["nombre"])
        sku_edit = st.text_input("SKU / codigo", value=actual["sku"] or "")
        unidad_edit = st.text_input("Unidad", value=actual["unidad"] or "")
        guardar = st.form_submit_button("Guardar cambios")
        if guardar:
            _, ok = ejecutar_con_manejo(
                db.actualizar,
                "producto",
                prod_id,
                {"nombre": nombre_edit.strip(), "sku": sku_edit.strip() or None, "unidad": unidad_edit.strip() or None},
                usuario_id,
                mensaje_exito="Producto actualizado.",
            )
            if ok:
                st.rerun()

    with st.form("form_baja_producto"):
        st.write("Dar de baja (baja logica, no se elimina ningun dato)")
        motivo = st.text_area("Motivo de la baja *")
        dar_baja = st.form_submit_button("Dar de baja", type="secondary")
        if dar_baja:
            if not motivo.strip():
                st.error("Indica un motivo para dar de baja el producto.")
            else:
                _, ok = ejecutar_con_manejo(
                    db.anular,
                    "producto",
                    prod_id,
                    usuario_id,
                    motivo,
                    mensaje_exito="Producto dado de baja. No se elimino ningun dato.",
                )
                if ok:
                    st.rerun()
