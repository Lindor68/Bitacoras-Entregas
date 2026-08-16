import io

import pandas as pd
import streamlit as st

import db
from common import ejecutar_con_manejo, seleccionar_usuario_actual

st.set_page_config(page_title="Importar/Exportar - Bitacoras-Entregas", layout="wide")
db.init_db()

usuario_id = seleccionar_usuario_actual()

st.title("Importar / Exportar")

st.subheader("Exportar bitacora consolidada")

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
        d.estado_entrega,
        p.nombre AS producto,
        dp.cantidad_solicitada,
        dp.cantidad_despachada,
        dp.cantidad_entregada,
        (dp.cantidad_despachada - dp.cantidad_entregada) AS diferencia,
        dp.motivo_entrega_parcial,
        p.unidad,
        l.lote,
        l.fecha_vencimiento,
        l.cantidad_lote
    FROM documento d
    JOIN viaje_establecimiento ve ON ve.id = d.viaje_establecimiento_id
    JOIN viaje v ON v.id = ve.viaje_id
    JOIN establecimiento e ON e.id = ve.establecimiento_id
    LEFT JOIN documento_producto dp ON dp.documento_id = d.id AND dp.activo = 1
    LEFT JOIN producto p ON p.id = dp.producto_id
    LEFT JOIN documento_producto_lote l ON l.documento_producto_id = dp.id AND l.activo = 1
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
st.subheader("Importar catalogo desde CSV")

catalogo = st.selectbox("Catalogo a importar", ["establecimiento", "producto"])
columnas_por_catalogo = {
    "establecimiento": ["codigo", "nombre", "tipo", "direccion"],
    "producto": ["nombre", "sku", "unidad"],
}
columnas_esperadas = columnas_por_catalogo[catalogo]
st.caption(f"El CSV debe tener las columnas: {', '.join(columnas_esperadas)} (solo 'nombre' es obligatoria).")

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
            if st.button(f"Importar {len(df_importar)} filas a {catalogo}"):
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
                    _, ok = ejecutar_con_manejo(db.insertar, catalogo, datos, usuario_id)
                    if ok:
                        creados += 1
                    else:
                        omitidos.append(f"fila {numero_fila + 2} ('{nombre}')")
                st.success(f"Se importaron {creados} de {len(df_importar)} filas a {catalogo}.")
                if omitidos:
                    st.warning("Se omitieron por error de integridad (ej. codigo/SKU duplicado): " + ", ".join(omitidos))
                st.rerun()
