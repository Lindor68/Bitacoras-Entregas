import streamlit as st

import db
from common import ejecutar_con_manejo, seleccionar_por_id, seleccionar_usuario_actual

st.set_page_config(page_title="Establecimientos - Bitacoras-Entregas", layout="wide")
db.init_db()

usuario_id = seleccionar_usuario_actual()

st.title("Establecimientos")

mostrar_inactivos = st.checkbox("Mostrar dados de baja", value=False)

sql = "SELECT id, codigo, nombre, tipo, direccion, activo, fecha_creacion, fecha_modificacion FROM establecimiento"
if not mostrar_inactivos:
    sql += " WHERE activo = 1"
sql += " ORDER BY nombre"

establecimientos = db.consultar(sql)
st.dataframe(
    db.formatear_fechas_local(establecimientos, ["fecha_creacion", "fecha_modificacion"]),
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.subheader("Registrar nuevo establecimiento")

with st.form("form_nuevo_establecimiento", clear_on_submit=True):
    codigo = st.text_input("Codigo institucional (unico, opcional)")
    nombre = st.text_input("Nombre *")
    tipo = st.text_input("Tipo (deposito, tienda, cliente, ...)")
    direccion = st.text_input("Direccion")
    if st.form_submit_button("Crear establecimiento"):
        if not nombre.strip():
            st.error("El nombre es obligatorio.")
        else:
            _, ok = ejecutar_con_manejo(
                db.insertar,
                "establecimiento",
                {
                    "codigo": codigo.strip() or None,
                    "nombre": nombre.strip(),
                    "tipo": tipo.strip() or None,
                    "direccion": direccion.strip() or None,
                },
                usuario_id,
                mensaje_exito=f"Establecimiento '{nombre}' creado.",
            )
            if ok:
                st.rerun()

st.divider()
st.subheader("Editar / dar de baja establecimiento")

activos = db.consultar(
    "SELECT id, codigo, nombre, tipo, direccion FROM establecimiento WHERE activo = 1 ORDER BY nombre"
)

if activos.empty:
    st.info("No hay establecimientos activos todavia.")
else:
    est_id = seleccionar_por_id("Selecciona un establecimiento", activos)
    actual = activos[activos["id"] == est_id].iloc[0]

    with st.form("form_editar_establecimiento"):
        codigo_edit = st.text_input("Codigo institucional", value=actual["codigo"] or "")
        nombre_edit = st.text_input("Nombre", value=actual["nombre"])
        tipo_edit = st.text_input("Tipo", value=actual["tipo"] or "")
        direccion_edit = st.text_input("Direccion", value=actual["direccion"] or "")
        guardar = st.form_submit_button("Guardar cambios")
        if guardar:
            _, ok = ejecutar_con_manejo(
                db.actualizar,
                "establecimiento",
                est_id,
                {
                    "codigo": codigo_edit.strip() or None,
                    "nombre": nombre_edit.strip(),
                    "tipo": tipo_edit.strip() or None,
                    "direccion": direccion_edit.strip() or None,
                },
                usuario_id,
                mensaje_exito="Establecimiento actualizado.",
            )
            if ok:
                st.rerun()

    with st.form("form_baja_establecimiento"):
        st.write("Dar de baja (baja logica, no se elimina ningun dato)")
        motivo = st.text_area("Motivo de la baja *")
        dar_baja = st.form_submit_button("Dar de baja", type="secondary")
        if dar_baja:
            if not motivo.strip():
                st.error("Indica un motivo para dar de baja el establecimiento.")
            else:
                _, ok = ejecutar_con_manejo(
                    db.anular,
                    "establecimiento",
                    est_id,
                    usuario_id,
                    motivo,
                    mensaje_exito="Establecimiento dado de baja. No se elimino ningun dato.",
                )
                if ok:
                    st.rerun()
