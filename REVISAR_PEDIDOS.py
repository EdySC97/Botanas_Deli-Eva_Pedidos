import streamlit as st
import psycopg2
import pandas as pd
from datetime import date
from fpdf import FPDF
import io

def convertir_a_kg(cantidad, unidad):
    try:
        cantidad = float(cantidad)
    except (TypeError, ValueError):
        return 0

    unidad = unidad.lower().strip()
    if unidad in ['kilo', 'kilos', 'kg']:
        return cantidad * 1
    elif unidad == 'medio':
        return cantidad * 0.5
    elif unidad == 'cuarto':
        return cantidad * 0.25
    elif unidad in ['50 gr', '50g', '50 gramos']:
        return cantidad * 0.05
    elif unidad in ['100 gr', '100g', '100 gramos']:
        return cantidad * 0.10
    elif unidad in ['70 gr', '70g', '70 gramos']:
        return cantidad * 0.07
    else:
        return 0

# Función para crear PDF de pedido
def crear_pdf(pedido_id, cliente, alias, fecha_local, detalles):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"Pedido ID: {pedido_id}", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"Cliente: {cliente} ({alias})", ln=True)
    pdf.cell(0, 8, f"Fecha: {fecha_local}", ln=True)
    pdf.ln(10)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(60, 8, "Producto", border=1)
    pdf.cell(25, 8, "Cantidad", border=1)
    pdf.cell(25, 8, "Unidad", border=1)
    pdf.cell(40, 8, "Sabor", border=1)
    pdf.ln()

    pdf.set_font("Arial", "", 12)
    for det in detalles:
        producto, cantidad, unidad, sabor = det
        pdf.cell(60, 8, str(producto), border=1)
        pdf.cell(25, 8, str(cantidad), border=1)
        pdf.cell(25, 8, str(unidad), border=1)
        pdf.cell(40, 8, str(sabor), border=1)
        pdf.ln()

    # Total kilos
    total_kg = sum(convertir_a_kg(c, u) for _, c, u, _ in detalles)
    pdf.ln(5)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, f"Total kilos: {total_kg:.3f} kg", ln=True)

    # Guardar PDF en memoria
    pdf_output = io.BytesIO()
    pdf.output(pdf_output)
    pdf_output.seek(0)
    return pdf_output

# --- CONEXIÓN A BD ---
conn = psycopg2.connect(
    host=st.secrets["postgres"]["host"],
    port=st.secrets["postgres"]["port"],
    database=st.secrets["postgres"]["database"],
    user=st.secrets["postgres"]["user"],
    password=st.secrets["postgres"]["password"],
)
cur = conn.cursor()

st.title("📦 Revisión y Modificación de Pedidos")

# Selector rango fechas
fecha_inicio, fecha_fin = st.date_input("Selecciona rango de fechas", 
                                       value=(date.today(), date.today()))

fecha_inicio_str = fecha_inicio.strftime("%Y-%m-%d")
fecha_fin_str = fecha_fin.strftime("%Y-%m-%d")

# Consulta pedidos
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
""", (fecha_inicio_str, fecha_fin_str))

pedidos = cur.fetchall()

if not pedidos:
    st.info("No se encontraron pedidos en el rango seleccionado.")
else:
    for pedido in pedidos:
        pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido

        # Obtener detalles del pedido para kilos y mostrar tabla
        cur.execute("""
        SELECT pr.nombre, dp.cantidad, dp.unidad, dp.sabor
        FROM detalle_pedido dp
        JOIN productos pr ON pr.id = dp.producto_id
        WHERE dp.pedido_id = %s
        """, (pedido_id,))
        detalles = cur.fetchall()

        # Calcular kilos totales
        total_kg = sum(convertir_a_kg(c, u) for _, c, u, _ in detalles)

        # Mostrar info pedido
        st.markdown(f"### Pedido ID: {pedido_id} | Cliente: {nombre_cliente} ({alias_cliente}) | Fecha: {fecha_local}")
        st.markdown(f"**Total kilos:** {total_kg:.3f} kg")

        # Mostrar tabla detalle
        df_detalles = pd.DataFrame(detalles, columns=["Producto", "Cantidad", "Unidad", "Sabor"])
        st.dataframe(df_detalles)

        # Selector estado
        estados = ["en proceso", "listo", "cancelado"]
        try:
            index_estado = estados.index(estado_actual)
        except ValueError:
            index_estado = 0

        nuevo_estado = st.selectbox(
            "Estado",
            options=estados,
            index=index_estado,
            key=f"estado_{pedido_id}"
        )

        if st.button("Guardar cambios", key=f"guardar_{pedido_id}"):
            try:
                cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
                conn.commit()
                st.success(f"Pedido {pedido_id} actualizado a estado '{nuevo_estado}'.")
            except Exception as e:
                st.error(f"Error al actualizar pedido {pedido_id}: {e}")

        # Botón para generar PDF y descargar
        if st.button("Descargar pedido PDF", key=f"pdf_{pedido_id}"):
            pdf_file = crear_pdf(pedido_id, nombre_cliente, alias_cliente, fecha_local, detalles)
            st.download_button(
                label="Descargar PDF",
                data=pdf_file,
                file_name=f"pedido_{pedido_id}.pdf",
                mime='application/pdf'
            )

cur.close()
conn.close()
