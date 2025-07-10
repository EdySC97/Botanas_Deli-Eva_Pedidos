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

# --- Filtros ---
fecha_inicio, fecha_fin = st.date_input(
    "Selecciona rango de fechas",
    value=[date.today(), date.today()],
    key="rango_fechas"
)
if fecha_inicio > fecha_fin:
    st.error("La fecha inicio debe ser menor o igual a la fecha fin.")
    st.stop()

# Obtener estados únicos
cur.execute("SELECT DISTINCT estado FROM pedidos")
estados_disponibles = [row[0] for row in cur.fetchall()]
estado_filtro = st.selectbox("Filtrar por estado", options=["Todos"] + estados_disponibles)

# Obtener clientes únicos
cur.execute("SELECT DISTINCT nombre FROM clientes ORDER BY nombre")
clientes_disponibles = [row[0] for row in cur.fetchall()]
cliente_filtro = st.selectbox("Filtrar por cliente", options=["Todos"] + clientes_disponibles)

# --- Consulta pedidos ---
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
"""
params = [fecha_inicio, fecha_fin]

if estado_filtro != "Todos":
    query += " AND p.estado = %s"
    params.append(estado_filtro)

if cliente_filtro != "Todos":
    query += " AND c.nombre = %s"
    params.append(cliente_filtro)

query += " ORDER BY p.fecha, p.id;"
cur.execute(query, tuple(params))
pedidos = cur.fetchall()

if not pedidos:
    st.info("No se encontraron pedidos con los filtros aplicados.")
    cur.close()
    conn.close()
    st.stop()

pedido_ids = [p[0] for p in pedidos]

# --- Obtener detalle de productos ---
cur.execute("""
SELECT
    pedido_id,
    cantidad,
    unidad
FROM detalle_pedido
WHERE pedido_id = ANY(%s);
""", (pedido_ids,))
detalles = cur.fetchall()

# --- Calcular kilos por pedido ---
detalles_por_pedido = {}
for pid, cantidad, unidad in detalles:
    kg = convertir_a_kg(cantidad, unidad)
    detalles_por_pedido[pid] = detalles_por_pedido.get(pid, 0) + kg

# --- Mostrar cada pedido ---
for pedido in pedidos:
    pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido
    total_kg = detalles_por_pedido.get(pedido_id, 0)

    with st.expander(f"📄 Pedido {pedido_id} - {nombre_cliente} ({alias_cliente}) - {estado_actual}"):
        st.write(f"📆 Fecha: {fecha_local}")
        st.write(f"⚖️ Total Kilos: **{total_kg:.2f} kg**")

        # Selector de estado editable
        estados = ["en proceso", "listo", "cancelado"]
        index_estado = estados.index(estado_actual) if estado_actual in estados else 0
        nuevo_estado = st.selectbox(
            "Estado del pedido",
            options=estados,
            index=index_estado,
            key=f"estado_{pedido_id}"
        )

        if st.button(f"Guardar cambios pedido {pedido_id}", key=f"guardar_{pedido_id}"):
            try:
                cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
                conn.commit()
                st.success(f"Pedido {pedido_id} actualizado a '{nuevo_estado}'.")
            except Exception as e:
                st.error(f"Error al actualizar: {e}")

        # PDF
        if st.button(f"Generar PDF tipo ticket", key=f"pdf_{pedido_id}"):
            cur.execute("""
            SELECT pr.nombre, dp.cantidad, dp.unidad, COALESCE(dp.sabor, '')
            FROM detalle_pedido dp
            JOIN productos pr ON pr.id = dp.producto_id
            WHERE dp.pedido_id = %s;
            """, (pedido_id,))
            detalles_pedido = cur.fetchall()

            pdf = FPDF(orientation='P', unit='mm', format=(80, 297))
            pdf.set_auto_page_break(auto=True, margin=2)
            pdf.set_margins(2, 2, 2)
            pdf.add_page()

            pdf.set_font("Arial", style='B', size=11)
            pdf.cell(0, 5, f"{nombre_cliente}", ln=True)

            pdf.set_font("Arial", size=9)
            pdf.cell(0, 5, f"Alias: {alias_cliente}", ln=True)
            pdf.cell(0, 5, f"Pedido ID: {pedido_id}", ln=True)
            pdf.cell(0, 5, f"Fecha: {fecha_local}", ln=True)
            pdf.cell(0, 5, f"Estado: {nuevo_estado}", ln=True)
            pdf.ln(2)

            pdf.set_font("Arial", style='B', size=9)
            pdf.cell(30, 5, "Producto", border=1)
            pdf.cell(15, 5, "Cant.", border=1)
            pdf.cell(15, 5, "Unidad", border=1)
            pdf.cell(20, 5, "Sabor", border=1)
            pdf.ln()

            pdf.set_font("Arial", size=9)
            for nombre, cantidad, unidad, sabor in detalles_pedido:
                pdf.cell(30, 5, str(nombre), border=1)
                pdf.cell(15, 5, str(cantidad), border=1)
                pdf.cell(15, 5, str(unidad), border=1)
                pdf.cell(20, 5, str(sabor), border=1)
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
