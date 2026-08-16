import streamlit as st

import db
from common import ejecutar_con_manejo, seleccionar_por_id, seleccionar_usuario_actual

db.init_db()

usuario_id = seleccionar_usuario_actual()

st.title("Documentos")
st.caption(
    "Jerarquia: viaje -> establecimiento visitado -> documento/folio -> resultado de entrega. "
    "El documento es la unidad principal de seguimiento; los productos solo se registran si hay "
    "una incidencia (pagina Incidencias)."
)

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
    SELECT id, tipo_documento, numero_documento, fecha_documento, estado_documento,
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
    st.write("Registrar nuevo documento/folio")
    tipo_documento = st.text_input("Tipo de documento * (remito, factura, ...)")
    numero_documento = st.text_input("Numero de documento")
    fecha_documento = st.date_input("Fecha del documento", value=None)
    if st.form_submit_button("Crear documento"):
        if not tipo_documento.strip():
            st.error("El tipo de documento es obligatorio.")
        else:
            _, ok = ejecutar_con_manejo(
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
# 3. Elegir un documento para editar su estado / anularlo
# ---------------------------------------------------------------------------

if documentos.empty:
    st.info("Registra al menos un documento.")
    st.stop()

st.divider()
documento_id = seleccionar_por_id(
    "Documento",
    documentos,
    formato=lambda f: f"#{f['id']} - {f['tipo_documento']} {f['numero_documento'] or ''} ({f['estado_documento']})".strip(),
)
documento_actual = documentos[documentos["id"] == documento_id].iloc[0]

st.subheader(f"Detalle del documento #{documento_id}")

with st.form("form_editar_documento"):
    nuevo_estado = st.selectbox(
        "Estado del documento (resultado de entrega)",
        db.ESTADOS_DOCUMENTO,
        index=db.ESTADOS_DOCUMENTO.index(documento_actual["estado_documento"]),
    )
    observacion = st.text_input(
        "Observacion del cambio (opcional, recomendable si es una correccion/reversa)"
    )
    guardar = st.form_submit_button("Guardar cambios")
    if guardar:
        _, ok = ejecutar_con_manejo(
            db.actualizar,
            "documento",
            documento_id,
            {"estado_documento": nuevo_estado},
            usuario_id,
            detalle=observacion.strip() or None,
            mensaje_exito="Documento actualizado.",
        )
        if ok:
            st.rerun()

with st.form("form_anular_documento"):
    st.write("Anular documento (baja logica, no se elimina ningun dato)")
    if documento_actual["estado_documento"] == "Entregado":
        st.warning(
            "Este documento esta 'Entregado'. No se puede anular directamente: primero registra "
            "una correccion/reversa (cambia el estado arriba, por ejemplo a 'Devuelto' o 'Rechazado')."
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

st.info("¿Detectaste una incidencia (faltante, deteriorado, vencido, etc.) en este documento? Registrala en la pagina **Incidencias**.")
