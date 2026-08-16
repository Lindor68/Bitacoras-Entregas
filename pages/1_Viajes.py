import streamlit as st

import db
from common import ejecutar_con_manejo, seleccionar_por_id, seleccionar_usuario_actual

db.init_db()

usuario_id = seleccionar_usuario_actual()

st.title("Viajes")

filtro_estados = st.multiselect("Filtrar por estado", db.ESTADOS_VIAJE, default=[])
usuarios = db.consultar("SELECT id, nombre FROM usuario WHERE activo = 1 ORDER BY nombre")

sql = "SELECT id, codigo, estado_viaje, fecha_inicio, fecha_fin_estimada, fecha_creacion, fecha_modificacion FROM viaje"
params = ()
if filtro_estados:
    placeholders = ", ".join("?" for _ in filtro_estados)
    sql += f" WHERE estado_viaje IN ({placeholders})"
    params = tuple(filtro_estados)
sql += " ORDER BY fecha_creacion DESC"

viajes = db.consultar(sql, params)
st.dataframe(
    db.formatear_fechas_local(viajes, ["fecha_creacion", "fecha_modificacion"]),
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.subheader("Registrar nuevo viaje")

with st.form("form_nuevo_viaje", clear_on_submit=True):
    codigo = st.text_input("Codigo del viaje *")
    col1, col2 = st.columns(2)
    fecha_inicio = col1.date_input("Fecha de inicio", value=None)
    fecha_fin = col2.date_input("Fecha de fin estimada", value=None)

    ids_resp = [None] + usuarios["id"].tolist()
    etiquetas_resp = {None: "Sin asignar", **{int(f["id"]): f["nombre"] for _, f in usuarios.iterrows()}}
    responsable_id = st.selectbox("Responsable", ids_resp, format_func=lambda i: etiquetas_resp[i])

    if st.form_submit_button("Crear viaje"):
        if not codigo.strip():
            st.error("El codigo del viaje es obligatorio.")
        else:
            _, ok = ejecutar_con_manejo(
                db.insertar,
                "viaje",
                {
                    "codigo": codigo.strip(),
                    "fecha_inicio": str(fecha_inicio) if fecha_inicio else None,
                    "fecha_fin_estimada": str(fecha_fin) if fecha_fin else None,
                    "responsable_id": responsable_id,
                },
                usuario_id,
                mensaje_exito=f"Viaje '{codigo}' creado.",
            )
            if ok:
                st.rerun()

st.divider()
st.subheader("Editar / anular viaje")

if viajes.empty:
    st.info("No hay viajes registrados todavia.")
else:
    viaje_id = seleccionar_por_id(
        "Selecciona un viaje", viajes, formato=lambda f: f"#{f['id']} - {f['codigo']} ({f['estado_viaje']})"
    )
    viaje_actual = viajes[viajes["id"] == viaje_id].iloc[0]

    with st.form("form_editar_viaje"):
        nuevo_estado = st.selectbox(
            "Estado del viaje", db.ESTADOS_VIAJE, index=db.ESTADOS_VIAJE.index(viaje_actual["estado_viaje"])
        )
        guardar = st.form_submit_button("Guardar cambios")
        if guardar:
            _, ok = ejecutar_con_manejo(
                db.actualizar,
                "viaje",
                viaje_id,
                {"estado_viaje": nuevo_estado},
                usuario_id,
                mensaje_exito="Viaje actualizado.",
            )
            if ok:
                st.rerun()

    with st.form("form_anular_viaje"):
        st.write("Anular viaje (queda marcado como Cancelado, no se elimina ningun dato)")
        motivo = st.text_area("Motivo de la anulacion *")
        anular = st.form_submit_button("Anular viaje", type="secondary")
        if anular:
            if not motivo.strip():
                st.error("Indica un motivo para anular el viaje.")
            else:
                _, ok = ejecutar_con_manejo(
                    db.anular,
                    "viaje",
                    viaje_id,
                    usuario_id,
                    motivo,
                    campo_estado="estado_viaje",
                    valor_anulado="Cancelado",
                    mensaje_exito="Viaje anulado (marcado como Cancelado). No se elimino ningun dato.",
                )
                if ok:
                    st.rerun()
