import streamlit as st
import psycopg2
from datetime import date
import io
from fpdf import FPDF

# Función para convertir cantidades a kilos
def convertir_a_kg(cantidad, unidad):
    unidad = unidad.lower()
    if unidad == "kilo":
        return cantidad * 1
    elif unidad == "medio":
        return cantidad * 0.5
    elif unidad == "cuarto":
        return cantidad * 0.25
    elif unidad == "50 gr" or unidad == "50g":
        return cantidad * 0.05
    elif unidad == "70 gr" or unidad == "70g":
        return cantidad * 0.07
    elif unidad == "100 gr" or unidad == "100g":
        return cantidad * 0.1
    else:
        # Por si hay unidades no contempladas
        return 0

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
    for producto, cantidad, unidad, sabor in detalles:
        pdf.cell(60, 8, str(producto), border=1)
        pdf.cell(25, 8, str(cantidad), border=1)
        pdf.cell(25, 8, str(unidad), border=1)
        pdf.cell(40, 8, str(sabor), border=1)
        pdf.ln()

    total_kg = sum(convertir_a_kg(c, u) for _, c, u, _ in detalles)
    pdf.ln(5)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, f"Total kilos: {total_kg:.3f} kg", ln=True)

    pdf_bytes = pdf.output(dest='S').encode('latin1')
    return io.BytesIO(pdf_bytes)

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

# Selector de rango de fechas
fecha_inicio, fecha_fin = st.date_input(
    "Selecciona rango de fechas",
    value=[date.today(), date.today()]
)

if fecha_inicio > fecha_fin:
    st.error("La fecha de inicio no puede ser mayor que la fecha final.")
    st.stop()

# Obtener pedidos con detalles y estado para rango de fechas
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
    st.info("No hay pedidos en este rango de fechas.")
else:
    for pedido in pedidos:
        pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido

        st.subheader(f"Pedido ID: {pedido_id}")
        st.write(f"Cliente: {nombre_cliente} ({alias_cliente})")
        st.write(f"Fecha: {fecha_local}")

        # Obtener detalles del pedido
        cur.execute("""
        SELECT pr.nombre, dp.cantidad, dp.unidad, dp.sabor
        FROM detalle_pedido dp
        JOIN productos pr ON pr.id = dp.producto_id
        WHERE dp.pedido_id = %s;
        """, (pedido_id,))
        detalles = cur.fetchall()

        # Mostrar detalles en tabla
        df_detalles = []
        total_kilos = 0
        for prod, cant, uni, sabor in detalles:
            df_detalles.append({
                "Producto": prod,
                "Cantidad": cant,
                "Unidad": uni,
                "Sabor": sabor,
            })
            total_kilos += convertir_a_kg(cant, uni)

        st.table(df_detalles)
        st.write(f"**Total kilos:** {total_kilos:.3f} kg")

        # Cambio de estado
        nuevo_estado = st.selectbox(
            "Estado",
            options=["en proceso", "listo", "cancelado"],
            index=["en proceso", "listo", "cancelado"].index(estado_actual) if estado_actual in ["en proceso", "listo", "cancelado"] else 0,
            key=f"estado_{pedido_id}"
        )

        if st.button("Guardar cambios", key=f"guardar_{pedido_id}"):
            try:
                cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
                conn.commit()
                st.success(f"Pedido {pedido_id} actualizado a estado '{nuevo_estado}'.")
            except Exception as e:
                st.error(f"Error al actualizar pedido {pedido_id}: {e}")

        # Botón para descargar PDF
        if st.button("Descargar pedido PDF", key=f"pdf_{pedido_id}"):
            pdf_file = crear_pdf(pedido_id, nombre_cliente, alias_cliente, fecha_local, detalles)
            st.download_button(
                label="Descargar PDF",
                data=pdf_file,
                file_name=f"pedido_{pedido_id}.pdf",
                mime="application/pdf",
                key=f"download_pdf_{pedido_id}"
            )

        st.markdown("---")

cur.close()
conn.close()
