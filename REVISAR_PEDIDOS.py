import streamlit as st
import psycopg2
import pandas as pd
from datetime import date
from fpdf import FPDF
import tempfile
import os

# Función para convertir a kilogramos
def convertir_a_kg(cantidad, unidad):
    if not unidad or cantidad is None:
        return 0
    unidad = str(unidad).strip().lower()

    conversiones = {
        "kilo": 1,
        "kilos": 1,
        "kg": 1,
        "medio": 0.5,
        "1/2": 0.5,
        "cuarto": 0.25,
        "1/4": 0.25,
        "50 gr": 0.05,
        "50g": 0.05,
        "70 gr": 0.07,
        "70g": 0.07,
        "100 gr": 0.1,
        "100g": 0.1,
        "gramos": 0.001,
        "gr": 0.001,
        "g": 0.001
    }

    return float(cantidad) * conversiones.get(unidad, 0)

# Crear PDF
def crear_pdf(pedido_id, nombre_cliente, alias_cliente, fecha_local, detalles, total_kg):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"Pedido #{pedido_id} - {nombre_cliente} ({alias_cliente})", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 10, f"Fecha: {fecha_local}", ln=True)

    pdf.ln(5)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(60, 10, "Producto", 1)
    pdf.cell(30, 10, "Cantidad", 1)
    pdf.cell(30, 10, "Unidad", 1)
    pdf.cell(50, 10, "Sabor", 1)
    pdf.ln()

    pdf.set_font("Arial", "", 12)
    for prod, cant, uni, sabor in detalles:
        pdf.cell(60, 10, str(prod), 1)
        pdf.cell(30, 10, str(cant), 1)
        pdf.cell(30, 10, str(uni), 1)
        pdf.cell(50, 10, str(sabor), 1)
        pdf.ln()

    pdf.ln(5)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"Total en kilos: {round(total_kg, 2)} kg", ln=True)

    temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(temp_path.name)
    return temp_path.name

# Conexión a la base de datos
conn = psycopg2.connect(
    host=st.secrets["postgres"]["host"],
    port=st.secrets["postgres"]["port"],
    database=st.secrets["postgres"]["database"],
    user=st.secrets["postgres"]["user"],
    password=st.secrets["postgres"]["password"],
)
cur = conn.cursor()

st.title("📦 Revisión y Modificación de Pedidos")

# Seleccionar rango de fechas
col1, col2 = st.columns(2)
with col1:
    fecha_inicio = st.date_input("📅 Desde", date.today())
with col2:
    fecha_fin = st.date_input("📅 Hasta", date.today())

# Consulta de pedidos
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

# Mostrar pedidos
for pedido in pedidos:
    pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido
    st.markdown(f"### 🧾 Pedido #{pedido_id}")
    st.markdown(f"**Cliente:** {nombre_cliente} ({alias_cliente})  \n**Fecha:** {fecha_local}")

    # Obtener detalles del pedido
    cur.execute("""
    SELECT pr.nombre, dp.cantidad, dp.unidad, dp.sabor
    FROM detalle_pedido dp
    JOIN productos pr ON pr.id = dp.producto_id
    WHERE dp.pedido_id = %s
    """, (pedido_id,))
    detalles = cur.fetchall()

    # Mostrar tabla
    df = pd.DataFrame(detalles, columns=["Producto", "Cantidad", "Unidad", "Sabor"])
    st.dataframe(df, use_container_width=True)

    # Calcular total en kg
    total_kg = 0
    for prod, cant, uni, sabor in detalles:
        try:
            cant = float(cant)
        except:
            cant = 0
        total_kg += convertir_a_kg(cant, uni)

    st.markdown(f"**Total en kilos:** {round(total_kg, 2)} kg")

    # Estado editable
    nuevo_estado = st.selectbox(
        "Actualizar estado:",
        options=["en proceso", "listo", "cancelado"],
        index=["en proceso", "listo", "cancelado"].index(estado_actual) if estado_actual in ["en proceso", "listo", "cancelado"] else 0,
        key=f"estado_{pedido_id}"
    )

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("💾 Guardar cambios", key=f"guardar_{pedido_id}"):
            try:
                cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
                conn.commit()
                st.success(f"Pedido {pedido_id} actualizado a estado '{nuevo_estado}'.")
            except Exception as e:
                st.error(f"Error al actualizar pedido {pedido_id}: {e}")

    with col_b2:
        if st.button("🖨️ Generar PDF", key=f"pdf_{pedido_id}"):
            try:
                pdf_path = crear_pdf(pedido_id, nombre_cliente, alias_cliente, fecha_local, detalles, total_kg)
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        label="Descargar PDF",
                        data=f.read(),
                        file_name=f"pedido_{pedido_id}.pdf",
                        mime="application/pdf"
                    )
                os.remove(pdf_path)
            except Exception as e:
                st.error(f"Error al generar PDF: {e}")

cur.close()
conn.close()
