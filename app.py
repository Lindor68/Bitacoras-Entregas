import streamlit as st

st.set_page_config(page_title="Bitacoras-Entregas", layout="wide")

import db
from common import seleccionar_usuario_actual

db.init_db()


def mostrar_dashboard():
    seleccionar_usuario_actual()

    st.title("Bitacoras-Entregas")
    st.caption("Seguimiento de viajes, establecimientos y documentos/folios de entrega.")

    st.divider()

    total_documentos = int(
        db.consultar("SELECT COUNT(*) AS total FROM documento WHERE estado_documento != 'Anulado'").iloc[0]["total"]
    )
    entregados = int(
        db.consultar(
            "SELECT COUNT(*) AS total FROM documento WHERE estado_documento IN "
            "('Entregado', 'Entregado con observaciones')"
        ).iloc[0]["total"]
    )
    con_incidencias = int(
        db.consultar("SELECT COUNT(DISTINCT documento_id) AS total FROM incidencia_producto WHERE activo = 1").iloc[
            0
        ]["total"]
    )
    pendientes_resolver = int(
        db.consultar(
            "SELECT COUNT(*) AS total FROM incidencia_producto WHERE activo = 1 "
            "AND estado_resolucion NOT IN ('Resuelta', 'Cerrada sin resolución')"
        ).iloc[0]["total"]
    )
    porcentaje_incidencias = (con_incidencias / total_documentos * 100) if total_documentos else 0.0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Documentos entregados", entregados)
    col2.metric("Documentos con incidencias", con_incidencias)
    col3.metric("% documentos con incidencias", f"{porcentaje_incidencias:.1f}%")
    col4.metric("Incidencias pendientes de resolver", pendientes_resolver)

    st.divider()

    documentos_por_estado = db.consultar(
        "SELECT estado_documento, COUNT(*) AS total FROM documento GROUP BY estado_documento"
    )
    incidencias_por_establecimiento = db.consultar(
        """
        SELECT e.nombre AS establecimiento, COUNT(*) AS total
        FROM incidencia_producto i
        JOIN documento d ON d.id = i.documento_id
        JOIN viaje_establecimiento ve ON ve.id = d.viaje_establecimiento_id
        JOIN establecimiento e ON e.id = ve.establecimiento_id
        WHERE i.activo = 1
        GROUP BY e.nombre
        ORDER BY total DESC
        """
    )
    incidencias_por_motivo = db.consultar(
        "SELECT tipo_incidencia, COUNT(*) AS total FROM incidencia_producto WHERE activo = 1 "
        "GROUP BY tipo_incidencia ORDER BY total DESC"
    )
    incidencias_por_producto = db.consultar(
        "SELECT producto_descripcion, COUNT(*) AS total FROM incidencia_producto WHERE activo = 1 "
        "GROUP BY producto_descripcion ORDER BY total DESC"
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Documentos por estado")
        if not documentos_por_estado.empty:
            st.bar_chart(documentos_por_estado.set_index("estado_documento"))
        st.subheader("Incidencias por establecimiento")
        if not incidencias_por_establecimiento.empty:
            st.bar_chart(incidencias_por_establecimiento.set_index("establecimiento"))
        else:
            st.caption("Sin incidencias registradas todavia.")
    with col_b:
        st.subheader("Incidencias por motivo")
        if not incidencias_por_motivo.empty:
            st.bar_chart(incidencias_por_motivo.set_index("tipo_incidencia"))
        else:
            st.caption("Sin incidencias registradas todavia.")
        st.subheader("Incidencias por producto")
        if not incidencias_por_producto.empty:
            st.bar_chart(incidencias_por_producto.set_index("producto_descripcion"))
        else:
            st.caption("Sin incidencias registradas todavia.")


dashboard = st.Page(mostrar_dashboard, title="Dashboard", default=True)
viajes = st.Page("pages/1_Viajes.py", title="Viajes")
establecimientos = st.Page("pages/2_Establecimientos.py", title="Establecimientos")
documentos = st.Page("pages/3_Documentos.py", title="Documentos")
incidencias = st.Page("pages/4_Incidencias.py", title="Incidencias")
importar_exportar = st.Page("pages/5_Importar_Exportar.py", title="Importar / Exportar")

# pages/6_Productos.py queda deliberadamente fuera de la navegacion del MVP
# (ver decision D): el catalogo de productos ya no es requisito de nada en
# el flujo principal.
pagina = st.navigation([dashboard, viajes, establecimientos, documentos, incidencias, importar_exportar])
pagina.run()
