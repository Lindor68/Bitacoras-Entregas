import streamlit as st

import db
from common import ejecutar_con_manejo, seleccionar_por_id, seleccionar_usuario_actual

db.init_db()

usuario_id = seleccionar_usuario_actual()

st.title("Incidencias de entrega")
st.caption(
    "Los productos solo se registran aca, cuando hay una discrepancia detectada en destino "
    "(faltante, sobrante, deteriorado, vencido, etc.). Un documento puede tener cero, una o "
    "varias incidencias."
)

# ---------------------------------------------------------------------------
# 1. Ubicar el documento/folio (mismo recorrido que en la pagina Documentos)
# ---------------------------------------------------------------------------

viajes = db.consultar(
    "SELECT id, codigo, estado_viaje FROM viaje WHERE estado_viaje != 'Cancelado' ORDER BY fecha_creacion DESC"
)
if viajes.empty:
    st.info("No hay viajes activos. Crea uno en la pagina Viajes.")
    st.stop()

viaje_id = seleccionar_por_id(
    "Viaje", viajes, formato=lambda f: f"#{f['id']} - {f['codigo']} ({f['estado_viaje']})"
)

visitas = db.consultar(
    """
    SELECT ve.id, e.nombre AS establecimiento
    FROM viaje_establecimiento ve
    JOIN establecimiento e ON e.id = ve.establecimiento_id
    WHERE ve.viaje_id = ? AND ve.activo = 1
    ORDER BY ve.orden, ve.fecha_creacion
    """,
    (viaje_id,),
)
if visitas.empty:
    st.info("Este viaje no tiene establecimientos asociados todavia. Ve a la pagina Documentos.")
    st.stop()

visita_id = seleccionar_por_id(
    "Establecimiento", visitas, formato=lambda f: f"#{f['id']} - {f['establecimiento']}"
)

documentos = db.consultar(
    """
    SELECT id, tipo_documento, numero_documento, estado_documento
    FROM documento
    WHERE viaje_establecimiento_id = ?
    ORDER BY fecha_creacion DESC
    """,
    (visita_id,),
)
if documentos.empty:
    st.info("Este establecimiento no tiene documentos todavia. Ve a la pagina Documentos.")
    st.stop()

documento_id = seleccionar_por_id(
    "Documento",
    documentos,
    formato=lambda f: f"#{f['id']} - {f['tipo_documento']} {f['numero_documento'] or ''} ({f['estado_documento']})".strip(),
)

st.divider()
st.subheader(f"Incidencias del documento #{documento_id}")

incidencias = db.consultar(
    """
    SELECT id, producto_codigo, producto_descripcion, tipo_incidencia, cantidad_afectada,
           lote, fecha_vencimiento, motivo_detalle, accion_tomada, estado_resolucion,
           fecha_creacion
    FROM incidencia_producto
    WHERE documento_id = ? AND activo = 1
    ORDER BY fecha_creacion DESC
    """,
    (documento_id,),
)
st.dataframe(
    db.formatear_fechas_local(incidencias, ["fecha_creacion"]), use_container_width=True, hide_index=True
)

st.markdown("**Registrar nueva incidencia**")
with st.form("form_nueva_incidencia", clear_on_submit=True):
    col1, col2 = st.columns(2)
    producto_codigo = col1.text_input("Codigo de producto (opcional)")
    producto_descripcion = col2.text_input("Producto / descripcion *")
    tipo_incidencia = st.selectbox("Tipo de incidencia", db.TIPOS_INCIDENCIA)
    col3, col4, col5 = st.columns(3)
    cantidad_afectada = col3.number_input("Cantidad afectada", min_value=0.0, step=1.0)
    lote = col4.text_input("Lote (opcional)")
    fecha_vencimiento = col5.date_input("Fecha de vencimiento (opcional)", value=None)
    motivo_detalle = st.text_area("Motivo / detalle *")
    accion_tomada = st.text_input("Accion tomada (opcional)")
    if st.form_submit_button("Registrar incidencia"):
        if not producto_descripcion.strip():
            st.error("La descripcion del producto es obligatoria.")
        elif not motivo_detalle.strip():
            st.error("El motivo/detalle es obligatorio.")
        else:
            _, ok = ejecutar_con_manejo(
                db.insertar,
                "incidencia_producto",
                {
                    "documento_id": documento_id,
                    "producto_codigo": producto_codigo.strip() or None,
                    "producto_descripcion": producto_descripcion.strip(),
                    "tipo_incidencia": tipo_incidencia,
                    "cantidad_afectada": cantidad_afectada,
                    "lote": lote.strip() or None,
                    "fecha_vencimiento": str(fecha_vencimiento) if fecha_vencimiento else None,
                    "motivo_detalle": motivo_detalle.strip(),
                    "accion_tomada": accion_tomada.strip() or None,
                },
                usuario_id,
                mensaje_exito="Incidencia registrada.",
            )
            if ok:
                st.rerun()

if not incidencias.empty:
    st.markdown("**Gestionar una incidencia existente**")
    incidencia_id = seleccionar_por_id(
        "Incidencia",
        incidencias,
        formato=lambda f: f"#{f['id']} - {f['producto_descripcion']} ({f['tipo_incidencia']}, {f['estado_resolucion']})",
        key="select_incidencia_gestion",
    )
    incidencia_actual = incidencias[incidencias["id"] == incidencia_id].iloc[0]

    with st.form("form_editar_incidencia"):
        nuevo_estado_resolucion = st.selectbox(
            "Estado de resolucion",
            db.ESTADOS_INCIDENCIA,
            index=db.ESTADOS_INCIDENCIA.index(incidencia_actual["estado_resolucion"]),
        )
        accion_tomada_edit = st.text_input("Accion tomada", value=incidencia_actual["accion_tomada"] or "")
        guardar = st.form_submit_button("Guardar cambios")
        if guardar:
            _, ok = ejecutar_con_manejo(
                db.actualizar,
                "incidencia_producto",
                incidencia_id,
                {"estado_resolucion": nuevo_estado_resolucion, "accion_tomada": accion_tomada_edit.strip() or None},
                usuario_id,
                mensaje_exito="Incidencia actualizada.",
            )
            if ok:
                st.rerun()

    with st.form("form_baja_incidencia"):
        st.write("Dar de baja esta incidencia (baja logica, ej. se cargo por error)")
        motivo_baja = st.text_area("Motivo de la baja *")
        dar_baja = st.form_submit_button("Dar de baja", type="secondary")
        if dar_baja:
            if not motivo_baja.strip():
                st.error("Indica un motivo para dar de baja la incidencia.")
            else:
                _, ok = ejecutar_con_manejo(
                    db.anular,
                    "incidencia_producto",
                    incidencia_id,
                    usuario_id,
                    motivo_baja,
                    mensaje_exito="Incidencia dada de baja. No se elimino ningun dato.",
                )
                if ok:
                    st.rerun()
