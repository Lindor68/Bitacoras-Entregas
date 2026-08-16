import streamlit as st

import db
from common import ejecutar_con_manejo, seleccionar_por_id, seleccionar_usuario_actual

st.set_page_config(page_title="Documentos - Bitacoras-Entregas", layout="wide")
db.init_db()

usuario_id = seleccionar_usuario_actual()

st.title("Documentos")
st.caption("Jerarquia: viaje -> establecimiento visitado -> documentos -> productos -> lotes.")

# ---------------------------------------------------------------------------
# 1. Elegir viaje
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

st.divider()
st.subheader("Establecimientos visitados en este viaje")

visitas = db.consultar(
    """
    SELECT ve.id, e.nombre AS establecimiento, ve.orden
    FROM viaje_establecimiento ve
    JOIN establecimiento e ON e.id = ve.establecimiento_id
    WHERE ve.viaje_id = ? AND ve.activo = 1
    ORDER BY ve.orden, ve.fecha_creacion
    """,
    (viaje_id,),
)
st.dataframe(visitas, use_container_width=True, hide_index=True)

establecimientos = db.consultar("SELECT id, nombre FROM establecimiento WHERE activo = 1 ORDER BY nombre")
with st.form("form_nueva_visita", clear_on_submit=True):
    st.write("Asociar establecimiento a este viaje")
    if establecimientos.empty:
        st.warning("No hay establecimientos activos. Crea uno en la pagina Establecimientos.")
        establecimiento_id = None
    else:
        ids_est = establecimientos["id"].tolist()
        etiquetas_est = {int(f["id"]): f["nombre"] for _, f in establecimientos.iterrows()}
        establecimiento_id = st.selectbox("Establecimiento", ids_est, format_func=lambda i: etiquetas_est[i])
    orden = st.number_input("Orden en el recorrido (opcional)", min_value=0, step=1, value=0)
    if st.form_submit_button("Asociar establecimiento") and establecimiento_id is not None:
        _, ok = ejecutar_con_manejo(
            db.insertar,
            "viaje_establecimiento",
            {"viaje_id": viaje_id, "establecimiento_id": establecimiento_id, "orden": orden or None},
            usuario_id,
            mensaje_exito="Establecimiento asociado al viaje.",
        )
        if ok:
            st.rerun()

# ---------------------------------------------------------------------------
# 2. Elegir la visita (viaje_establecimiento) para trabajar sus documentos
# ---------------------------------------------------------------------------

if visitas.empty:
    st.info("Asocia al menos un establecimiento a este viaje para registrar documentos.")
    st.stop()

st.divider()
visita_id = seleccionar_por_id(
    "Establecimiento sobre el que se trabaja", visitas, formato=lambda f: f"#{f['id']} - {f['establecimiento']}"
)
establecimiento_actual = visitas[visitas["id"] == visita_id].iloc[0]["establecimiento"]

st.subheader(f"Documentos en {establecimiento_actual}")

documentos = db.consultar(
    """
    SELECT id, tipo_documento, numero_documento, fecha_documento, estado_documento, estado_entrega,
           fecha_creacion, fecha_modificacion
    FROM documento
    WHERE viaje_establecimiento_id = ?
    ORDER BY fecha_creacion DESC
    """,
    (visita_id,),
)
st.dataframe(
    db.formatear_fechas_local(documentos, ["fecha_creacion", "fecha_modificacion"]),
    use_container_width=True,
    hide_index=True,
)

with st.form("form_nuevo_documento", clear_on_submit=True):
    st.write("Registrar nuevo documento")
    tipo_documento = st.text_input("Tipo de documento * (remito, factura, ...)")
    numero_documento = st.text_input("Numero de documento")
    fecha_documento = st.date_input("Fecha del documento", value=None)
    if st.form_submit_button("Crear documento"):
        if not tipo_documento.strip():
            st.error("El tipo de documento es obligatorio.")
        else:
            nuevo_id, ok = ejecutar_con_manejo(
                db.insertar,
                "documento",
                {
                    "viaje_establecimiento_id": visita_id,
                    "tipo_documento": tipo_documento.strip(),
                    "numero_documento": numero_documento.strip() or None,
                    "fecha_documento": str(fecha_documento) if fecha_documento else None,
                },
                usuario_id,
                mensaje_exito="Documento creado.",
            )
            if ok:
                st.rerun()

# ---------------------------------------------------------------------------
# 3. Elegir un documento para editar estado / gestionar sus productos y lotes
# ---------------------------------------------------------------------------

if documentos.empty:
    st.info("Registra al menos un documento para poder agregarle productos.")
    st.stop()

st.divider()
documento_id = seleccionar_por_id(
    "Documento",
    documentos,
    formato=lambda f: f"#{f['id']} - {f['tipo_documento']} {f['numero_documento'] or ''}".strip(),
)
documento_actual = documentos[documentos["id"] == documento_id].iloc[0]

st.subheader(f"Detalle del documento #{documento_id}")

with st.form("form_editar_documento"):
    col1, col2 = st.columns(2)
    nuevo_estado_documento = col1.selectbox(
        "Estado del documento",
        db.ESTADOS_DOCUMENTO,
        index=db.ESTADOS_DOCUMENTO.index(documento_actual["estado_documento"]),
    )
    nuevo_estado_entrega = col2.selectbox(
        "Estado de la entrega",
        db.ESTADOS_ENTREGA,
        index=db.ESTADOS_ENTREGA.index(documento_actual["estado_entrega"]),
    )
    guardar = st.form_submit_button("Guardar cambios")
    if guardar:
        _, ok = ejecutar_con_manejo(
            db.actualizar,
            "documento",
            documento_id,
            {"estado_documento": nuevo_estado_documento, "estado_entrega": nuevo_estado_entrega},
            usuario_id,
            mensaje_exito="Documento actualizado.",
        )
        if ok:
            st.rerun()

with st.form("form_anular_documento"):
    st.write("Anular documento (baja logica en cascada de sus productos y lotes activos)")
    if documento_actual["estado_entrega"] == "Entregado":
        st.warning(
            "Este documento tiene la entrega marcada como 'Entregado'. No se puede anular directamente: "
            "primero corrige el estado de la entrega arriba (por ejemplo a 'Devuelta' o 'Rechazado')."
        )
    motivo_anulacion_doc = st.text_area("Motivo de la anulacion *")
    anular_doc = st.form_submit_button("Anular documento", type="secondary")
    if anular_doc:
        if not motivo_anulacion_doc.strip():
            st.error("Indica un motivo para anular el documento.")
        else:
            _, ok = ejecutar_con_manejo(
                db.anular_documento,
                documento_id,
                usuario_id,
                motivo_anulacion_doc,
                mensaje_exito="Documento anulado. No se elimino ningun dato.",
            )
            if ok:
                st.rerun()

st.markdown("**Productos amparados por este documento**")

lineas = db.consultar(
    """
    SELECT dp.id, p.nombre AS producto, p.unidad,
           dp.cantidad_solicitada, dp.cantidad_despachada, dp.cantidad_entregada,
           (dp.cantidad_despachada - dp.cantidad_entregada) AS diferencia,
           dp.motivo_entrega_parcial
    FROM documento_producto dp
    JOIN producto p ON p.id = dp.producto_id
    WHERE dp.documento_id = ? AND dp.activo = 1
    ORDER BY dp.fecha_creacion
    """,
    (documento_id,),
)
st.dataframe(lineas, use_container_width=True, hide_index=True)

productos = db.consultar("SELECT id, nombre FROM producto WHERE activo = 1 ORDER BY nombre")

with st.form("form_agregar_producto", clear_on_submit=True):
    st.write("Agregar producto al documento")
    if productos.empty:
        st.warning("No hay productos activos. Crea uno en la pagina Productos.")
        producto_id = None
    else:
        ids_prod = productos["id"].tolist()
        etiquetas_prod = {int(f["id"]): f["nombre"] for _, f in productos.iterrows()}
        producto_id = st.selectbox("Producto", ids_prod, format_func=lambda i: etiquetas_prod[i])
    col1, col2, col3 = st.columns(3)
    cantidad_solicitada = col1.number_input("Cantidad solicitada", min_value=0.0, step=1.0)
    cantidad_despachada = col2.number_input("Cantidad despachada", min_value=0.0, step=1.0)
    cantidad_entregada = col3.number_input("Cantidad entregada", min_value=0.0, step=1.0)
    motivo_parcial = st.text_input("Motivo de entrega parcial (si aplica)")
    if st.form_submit_button("Agregar") and producto_id is not None:
        _, ok = ejecutar_con_manejo(
            db.insertar,
            "documento_producto",
            {
                "documento_id": documento_id,
                "producto_id": producto_id,
                "cantidad_solicitada": cantidad_solicitada,
                "cantidad_despachada": cantidad_despachada,
                "cantidad_entregada": cantidad_entregada,
                "motivo_entrega_parcial": motivo_parcial.strip() or None,
            },
            usuario_id,
            mensaje_exito="Producto agregado al documento.",
        )
        if ok:
            st.rerun()

if not lineas.empty:
    with st.form("form_baja_producto"):
        st.write("Dar de baja una linea del documento")
        linea_id = seleccionar_por_id(
            "Linea", lineas, formato=lambda f: f"#{f['id']} - {f['producto']} (entregado {f['cantidad_entregada']})"
        )
        motivo_linea = st.text_area("Motivo de la baja *")
        dar_baja_linea = st.form_submit_button("Dar de baja", type="secondary")
        if dar_baja_linea:
            if not motivo_linea.strip():
                st.error("Indica un motivo para dar de baja la linea.")
            else:
                _, ok = ejecutar_con_manejo(
                    db.anular,
                    "documento_producto",
                    linea_id,
                    usuario_id,
                    motivo_linea,
                    mensaje_exito="Linea dada de baja. No se elimino ningun dato.",
                )
                if ok:
                    st.rerun()

    # -----------------------------------------------------------------
    # 4. Lotes de una linea de producto
    # -----------------------------------------------------------------
    st.divider()
    st.markdown("**Lotes y vencimientos**")
    st.caption("El lote y el vencimiento pertenecen a la linea del documento, no al catalogo del producto.")

    dp_id = seleccionar_por_id(
        "Linea de producto", lineas, formato=lambda f: f"#{f['id']} - {f['producto']}", key="select_linea_lotes"
    )

    lotes = db.consultar(
        """
        SELECT id, lote, fecha_vencimiento, cantidad_lote
        FROM documento_producto_lote
        WHERE documento_producto_id = ? AND activo = 1
        ORDER BY fecha_vencimiento
        """,
        (dp_id,),
    )
    st.dataframe(lotes, use_container_width=True, hide_index=True)

    with st.form("form_agregar_lote", clear_on_submit=True):
        st.write("Agregar lote a esta linea")
        lote_codigo = st.text_input("Lote *")
        fecha_vencimiento = st.date_input("Fecha de vencimiento", value=None)
        cantidad_lote = st.number_input("Cantidad del lote", min_value=0.0, step=1.0)
        if st.form_submit_button("Agregar lote"):
            if not lote_codigo.strip():
                st.error("El identificador del lote es obligatorio.")
            else:
                _, ok = ejecutar_con_manejo(
                    db.insertar,
                    "documento_producto_lote",
                    {
                        "documento_producto_id": dp_id,
                        "lote": lote_codigo.strip(),
                        "fecha_vencimiento": str(fecha_vencimiento) if fecha_vencimiento else None,
                        "cantidad_lote": cantidad_lote,
                    },
                    usuario_id,
                    mensaje_exito=f"Lote '{lote_codigo}' agregado.",
                )
                if ok:
                    st.rerun()

    if not lotes.empty:
        with st.form("form_baja_lote"):
            st.write("Dar de baja un lote")
            lote_id = seleccionar_por_id("Lote", lotes, formato=lambda f: f"#{f['id']} - {f['lote']}")
            motivo_lote = st.text_area("Motivo de la baja *")
            dar_baja_lote = st.form_submit_button("Dar de baja lote", type="secondary")
            if dar_baja_lote:
                if not motivo_lote.strip():
                    st.error("Indica un motivo para dar de baja el lote.")
                else:
                    _, ok = ejecutar_con_manejo(
                        db.anular,
                        "documento_producto_lote",
                        lote_id,
                        usuario_id,
                        motivo_lote,
                        mensaje_exito="Lote dado de baja. No se elimino ningun dato.",
                    )
                    if ok:
                        st.rerun()
