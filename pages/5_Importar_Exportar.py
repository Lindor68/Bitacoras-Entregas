import io

import pandas as pd
import streamlit as st

import db
from common import ejecutar_con_manejo, seleccionar_usuario_actual

db.init_db()

usuario_id = seleccionar_usuario_actual()

st.title("Importar / Exportar")

st.subheader("Exportar bitacora consolidada")
st.caption("Un documento sin incidencias aparece una sola vez; uno con varias aparece repetido, una fila por incidencia.")

consolidado = db.consultar(
    """
    SELECT
        v.codigo AS viaje,
        v.estado_viaje,
        e.nombre AS establecimiento,
        d.tipo_documento,
        d.numero_documento,
        d.fecha_documento,
        d.estado_documento,
        i.producto_codigo,
        i.producto_descripcion,
        i.tipo_incidencia,
        i.cantidad_afectada,
        i.lote,
        i.fecha_vencimiento,
        i.motivo_detalle,
        i.accion_tomada,
        i.estado_resolucion
    FROM documento d
    JOIN viaje_establecimiento ve ON ve.id = d.viaje_establecimiento_id
    JOIN viaje v ON v.id = ve.viaje_id
    JOIN establecimiento e ON e.id = ve.establecimiento_id
    LEFT JOIN incidencia_producto i ON i.documento_id = d.id AND i.activo = 1
    ORDER BY v.codigo, e.nombre, d.fecha_creacion
    """
)

st.dataframe(consolidado, use_container_width=True, hide_index=True)

col1, col2 = st.columns(2)

csv_bytes = consolidado.to_csv(index=False).encode("utf-8")
col1.download_button("Descargar CSV", csv_bytes, file_name="bitacora_entregas.csv", mime="text/csv")

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    consolidado.to_excel(writer, index=False, sheet_name="Bitacora")
col2.download_button(
    "Descargar Excel",
    excel_buffer.getvalue(),
    file_name="bitacora_entregas.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.divider()
st.subheader("Importar establecimientos desde CSV")
st.caption("El CSV debe tener las columnas: codigo, nombre, tipo, direccion (solo 'nombre' es obligatoria).")

archivo = st.file_uploader("Archivo CSV", type=["csv"])
if archivo is not None:
    try:
        df_importar = pd.read_csv(archivo)
    except Exception as exc:
        st.error(f"No se pudo leer el CSV: {exc}")
    else:
        if "nombre" not in df_importar.columns:
            st.error("El CSV debe tener una columna 'nombre'.")
        else:
            st.dataframe(df_importar, use_container_width=True, hide_index=True)
            if st.button(f"Importar {len(df_importar)} filas a establecimiento"):
                columnas_esperadas = ["codigo", "nombre", "tipo", "direccion"]
                creados = 0
                omitidos = []
                for numero_fila, fila in df_importar.iterrows():
                    nombre = str(fila.get("nombre", "")).strip()
                    if not nombre or nombre.lower() == "nan":
                        continue
                    datos = {"nombre": nombre}
                    for col in columnas_esperadas:
                        if col == "nombre":
                            continue
                        valor = fila.get(col)
                        datos[col] = None if pd.isna(valor) else str(valor).strip()
                    _, ok = ejecutar_con_manejo(db.insertar, "establecimiento", datos, usuario_id)
                    if ok:
                        creados += 1
                    else:
                        omitidos.append(f"fila {numero_fila + 2} ('{nombre}')")
                st.success(f"Se importaron {creados} de {len(df_importar)} filas a establecimiento.")
                if omitidos:
                    st.warning("Se omitieron por error de integridad (ej. codigo duplicado): " + ", ".join(omitidos))
                st.rerun()
