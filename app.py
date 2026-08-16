import streamlit as st

import db
from common import seleccionar_usuario_actual

st.set_page_config(page_title="Bitacoras-Entregas", layout="wide")

db.init_db()

st.title("Bitacoras-Entregas")
st.caption("Seguimiento de viajes, establecimientos, documentos y entregas.")

seleccionar_usuario_actual()

st.divider()

viajes = db.consultar("SELECT estado_viaje, COUNT(*) AS total FROM viaje GROUP BY estado_viaje")
documentos = db.consultar("SELECT estado_documento, COUNT(*) AS total FROM documento GROUP BY estado_documento")
entregas = db.consultar("SELECT estado_entrega, COUNT(*) AS total FROM documento GROUP BY estado_entrega")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Viajes por estado")
    st.metric("Total de viajes", int(viajes["total"].sum()) if not viajes.empty else 0)
    if not viajes.empty:
        st.bar_chart(viajes.set_index("estado_viaje"))

with col2:
    st.subheader("Documentos por estado")
    st.metric("Total de documentos", int(documentos["total"].sum()) if not documentos.empty else 0)
    if not documentos.empty:
        st.bar_chart(documentos.set_index("estado_documento"))

with col3:
    st.subheader("Entregas por estado")
    st.metric("Total de entregas registradas", int(entregas["total"].sum()) if not entregas.empty else 0)
    if not entregas.empty:
        st.bar_chart(entregas.set_index("estado_entrega"))

st.divider()
st.subheader("Viajes activos (no cancelados)")
st.dataframe(
    db.consultar(
        "SELECT id, codigo, estado_viaje, fecha_inicio, fecha_fin_estimada "
        "FROM viaje WHERE estado_viaje != 'Cancelado' ORDER BY fecha_creacion DESC"
    ),
    use_container_width=True,
    hide_index=True,
)
