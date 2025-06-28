import streamlit as st
import psycopg2
import pandas as pd
from datetime import date
from fpdf import FPDF
import io

# --- Función para convertir unidades a kg ---
def convertir_a_kg(cantidad, unidad):
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
        # Si no reconocemos unidad, asumimos 0
        return 0

# --- Conexión a la base de datos ---
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
fecha_inicio, fecha_fin = st.date_input(
    "Selecciona rango de fechas",
    value=[date.today(), date.today()],
    key="rango_fechas"
)
if fecha_inicio > fecha_fin:
    st.error("La fecha inicio debe ser menor o igual a la fecha fin.")
    st.stop()

# Consulta pedidos dentro del rango
query = """
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
"""
cur.execute(query, (fecha_inicio, fecha_fin))
pedidos = cur.fetchall()

if not pedidos:
    st.info("No se encontraron pedidos en ese rango de fechas.")
    cur.close()
    conn.close()
    st.stop()

# Preparamos IDs para luego traer detalles y calcular kilos
pedido_ids = [p[0] for p in pedidos]

# Consulta detalle pedidos para todos los pedidos en rango
cur.execute("""
SELECT
    pedido_id,
    cantidad,
    unidad
FROM detalle_pedido
WHERE pedido_id = ANY(%s);
""", (pedido_ids,))
detalles = cur.fetchall()

# Organizamos detalles por pedido para calcular kilos
detalles_por_pedido = {}
for pid, cantidad, unidad in detalles:
    kg = convertir_a_kg(cantidad, unidad)
    detalles_por_pedido[pid] = detalles_por_pedido.get(pid, 0) + kg

# Mostrar tabla y controles para cada pedido
for pedido in pedidos:
    pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido
    total_kg = detalles_por_pedido.get(pedido_id, 0)

    st.markdown(f"### Pedido ID: {pedido_id}")
    st.write(f"Cliente: **{nombre_cliente}** ({alias_cliente})")
    st.write(f"Fecha: {fecha_local}")
    st.write(f"Total Kilos: **{total_kg:.2f} kg**")

    # Selector estado
    estados = ["en proceso", "listo", "cancelado"]
    try:
        index_estado = estados.index(estado_actual)
    except ValueError:
        index_estado = 0  # por defecto

    nuevo_estado = st.selectbox(
        "Estado",
        options=estados,
        index=index_estado,
        key=f"estado_{pedido_id}"
    )

    # Botón para guardar estado
    if st.button(f"Guardar cambios pedido {pedido_id}", key=f"guardar_{pedido_id}"):
        try:
            cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
            conn.commit()
            st.success(f"Pedido {pedido_id} actualizado a estado '{nuevo_estado}'.")
        except Exception as e:
            st.error(f"Error al actualizar pedido {pedido_id}: {e}")

    # Botón para generar PDF
    if st.button(f"Descargar PDF pedido {pedido_id}", key=f"pdf_{pedido_id}"):
        # Consulta detalles completos para ese pedido
        cur.execute("""
        SELECT pr.nombre, dp.cantidad, dp.unidad, dp.sabor
        FROM detalle_pedido dp
        JOIN productos pr ON pr.id = dp.producto_id
        WHERE dp.pedido_id = %s;
        """, (pedido_id,))
        detalles_pedido = cur.fetchall()

        # Crear PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, f"Pedido ID: {pedido_id}", ln=True)
        pdf.cell(0, 10, f"Cliente: {nombre_cliente} ({alias_cliente})", ln=True)
        pdf.cell(0, 10, f"Fecha: {fecha_local}", ln=True)
        pdf.cell(0, 10, f"Estado: {nuevo_estado}", ln=True)
        pdf.ln(5)

        # Tabla simple en PDF
        pdf.cell(60, 10, "Producto", border=1)
        pdf.cell(30, 10, "Cantidad", border=1)
        pdf.cell(30, 10, "Unidad", border=1)
        pdf.cell(60, 10, "Sabor", border=1)
        pdf.ln()

        for nombre_prod, cantidad, unidad, sabor in detalles_pedido:
            pdf.cell(60, 10, str(nombre_prod), border=1)
            pdf.cell(30, 10, str(cantidad), border=1)
            pdf.cell(30, 10, str(unidad), border=1)
            pdf.cell(60, 10, str(sabor), border=1)
            pdf.ln()

        pdf_output = pdf.output(dest='S').encode('latin1')

        st.download_button(
            label=f"Descargar PDF Pedido {pedido_id}",
            data=pdf_output,
            file_name=f"pedido_{pedido_id}.pdf",
            mime="application/pdf",
            key=f"download_pdf_{pedido_id}"
        )

st.write("---")

cur.close()
conn.close()

