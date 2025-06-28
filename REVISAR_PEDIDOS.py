import streamlit as st
import psycopg2
import pandas as pd
from datetime import date, timedelta
from fpdf import FPDF
import tempfile
import os

# --- Función para convertir unidades a kilogramos ---
def convertir_a_kg(cantidad, unidad):
    unidad = unidad.lower()
    try:
        if unidad in ["kg", "kilo", "kilos"]:
            return cantidad
        elif unidad in ["medio", "1/2"]:
            return cantidad * 0.5
        elif unidad in ["cuarto", "1/4"]:
            return cantidad * 0.25
        elif "100 g" in unidad or "100g" in unidad:
            return cantidad * 0.1
        elif "70 gr" in unidad:
            return cantidad * 0.07
        elif "50 gr" in unidad:
            return cantidad * 0.05
        elif "5kg" in unidad:
            return cantidad * 5
        elif "10kg" in unidad:
            return cantidad * 10
        elif "20kg" in unidad:
            return cantidad * 20
    except:
        return 0
    return 0

# --- Función para generar PDF ---
def generar_pdf(cliente, alias, fecha, detalles, total_kg):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"Pedido - {cliente} ({alias})", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 10, f"Fecha: {fecha}", ln=True)
    pdf.ln(5)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(60, 8, "Producto", 1)
    pdf.cell(30, 8, "Cantidad", 1)
    pdf.cell(30, 8, "Unidad", 1)
    pdf.cell(40, 8, "Sabor", 1)
    pdf.cell(30, 8, "Kg Est.", 1)
    pdf.ln()

    pdf.set_font("Arial", "", 11)
    for fila in detalles:
        producto, cantidad, unidad, sabor = fila
        kg = convertir_a_kg(cantidad, unidad)
        pdf.cell(60, 8, producto, 1)
        pdf.cell(30, 8, str(cantidad), 1)
        pdf.cell(30, 8, unidad, 1)
        pdf.cell(40, 8, sabor or "-", 1)
        pdf.cell(30, 8, f"{kg:.2f}", 1)
        pdf.ln()

    pdf.ln(5)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"Total estimado: {total_kg:.2f} kg", ln=True)

    # Guardar temporalmente
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(tmp_file.name)
    return tmp_file.name

# --- Conexión a la base de datos ---
conn = psycopg2.connect(
    host=st.secrets["postgres"]["host"],
    port=st.secrets["postgres"]["port"],
    database=st.secrets["postgres"]["database"],
    user=st.secrets["postgres"]["user"],
    password=st.secrets["postgres"]["password"],
)
cur = conn.cursor()

st.title("📦 Revisión de Pedidos + PDF")

# --- Limpiar estados inválidos ---
cur.execute("""
    UPDATE pedidos
    SET estado = 'en proceso'
    WHERE estado IS NULL OR TRIM(estado) = '' OR estado NOT IN ('en proceso', 'listo', 'cancelado')
""")
conn.commit()

# --- Selector de fecha ---
col1, col2 = st.columns(2)
fecha_inicio = col1.date_input("📅 Desde", date.today() - timedelta(days=7))
fecha_fin = col2.date_input("📅 Hasta", date.today())

# --- Obtener pedidos ---
cur.execute("""
SELECT
    p.id,
    c.nombre,
    c.alias,
    TO_CHAR(p.fecha AT TIME ZONE 'UTC' AT TIME ZONE 'America/Chihuahua', 'YYYY-MM-DD HH24:MI') AS fecha_local,
    p.estado
FROM pedidos p
JOIN clientes c ON p.cliente_id = c.id
WHERE DATE(p.fecha AT TIME ZONE 'UTC' AT TIME ZONE 'America/Chihuahua') BETWEEN %s AND %s
ORDER BY p.fecha, p.id;
""", (fecha_inicio, fecha_fin))
pedidos = cur.fetchall()

if not pedidos:
    st.warning("No hay pedidos en el rango seleccionado.")
else:
    for pedido in pedidos:
        pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido
        st.markdown(f"### Pedido ID: `{pedido_id}`")
        st.write(f"📌 Cliente: **{nombre_cliente}** ({alias_cliente}) | Fecha: {fecha_local} | Estado: `{estado_actual}`")

        # --- Obtener detalles del pedido ---
        cur.execute("""
            SELECT pr.nombre, dp.cantidad, dp.unidad, dp.sabor
            FROM detalle_pedido dp
            JOIN productos pr ON pr.id = dp.producto_id
            WHERE dp.pedido_id = %s;
        """, (pedido_id,))
        detalles = cur.fetchall()

        df = pd.DataFrame(detalles, columns=["Producto", "Cantidad", "Unidad", "Sabor"])
        df["Kg Estimado"] = df.apply(lambda row: convertir_a_kg(row["Cantidad"], row["Unidad"]), axis=1)
        total_kg = df["Kg Estimado"].sum()

        st.dataframe(df, use_container_width=True)
        st.success(f"Total estimado: {total_kg:.2f} kg")

        # --- Botón para generar PDF ---
        if st.button("🖨 Generar PDF", key=f"pdf_{pedido_id}"):
            ruta_pdf = generar_pdf(nombre_cliente, alias_cliente, fecha_local, detalles, total_kg)
            with open(ruta_pdf, "rb") as f:
                st.download_button("📥 Descargar Pedido en PDF", f, file_name=f"pedido_{pedido_id}.pdf")
            os.remove(ruta_pdf)

cur.close()
conn.close()
