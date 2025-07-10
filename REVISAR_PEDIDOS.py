import streamlit as st
import psycopg2
import pandas as pd
from datetime import date
from fpdf import FPDF
import io

# --- Función para convertir unidades a kg ---
def convertir_a_kg(cantidad, unidad):
    if cantidad is None:
        return 0
    try:
        cantidad = float(cantidad)
    except:
        return 0

    if unidad is None:
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

# --- Conexión a la base de datos ---
conn = psycopg2.connect(
    host=st.secrets["postgres"]["host"],
    port=st.secrets["postgres"]["port"],
    database=st.secrets["postgres"]["database"],
    user=st.secrets["postgres"]["user"],
    password=st.secrets["postgres"]["password"],
)
cur = conn.cursor()

st.set_page_config(layout="wide")
st.title("📦 Revisión y Modificación de Pedidos")

# --- Filtros ---
fecha_inicio, fecha_fin = st.date_input(
    "📅 Selecciona rango de fechas",
    value=[date.today(), date.today()],
    key="rango_fechas"
)
if fecha_inicio > fecha_fin:
    st.error("La fecha inicio debe ser menor o igual a la fecha fin.")
    st.stop()

# Obtener lista de clientes
cur.execute("SELECT DISTINCT c.nombre FROM pedidos p JOIN clientes c ON c.id = p.cliente_id")
clientes_opciones = [r[0] for r in cur.fetchall()]
cliente_filtro = st.selectbox("👤 Filtrar por cliente (opcional)", ["Todos"] + clientes_opciones)

estado_filtro = st.selectbox("📦 Filtrar por estado", ["Todos", "en proceso", "listo", "cancelado"])

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

if cliente_filtro != "Todos":
    query += " AND c.nombre = %s"
    params.append(cliente_filtro)

if estado_filtro != "Todos":
    query += " AND p.estado = %s"
    params.append(estado_filtro)

query += " ORDER BY p.fecha, p.id"
cur.execute(query, tuple(params))
pedidos = cur.fetchall()

if not pedidos:
    st.info("No se encontraron pedidos.")
    cur.close()
    conn.close()
    st.stop()

# Obtener IDs de pedidos para detalles
pedido_ids = [p[0] for p in pedidos]

# --- Consulta detalles ---
cur.execute("""
SELECT pedido_id, cantidad, unidad
FROM detalle_pedido
WHERE pedido_id = ANY(%s);
""", (pedido_ids,))
detalles = cur.fetchall()

# Sumar kilos por pedido
detalles_por_pedido = {}
for pid, cantidad, unidad in detalles:
    kg = convertir_a_kg(cantidad, unidad)
    detalles_por_pedido[pid] = detalles_por_pedido.get(pid, 0) + kg

# --- Mostrar pedidos ---
for pedido in pedidos:
    pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido
    total_kg = detalles_por_pedido.get(pedido_id, 0)

    with st.expander(f"🧾 Pedido ID {pedido_id} - {nombre_cliente} ({alias_cliente})"):
        st.write(f"🕒 Fecha: {fecha_local}")
        st.write(f"⚖️ Total Kilos: **{total_kg:.2f} kg**")

        # Estado editable
        estados = ["en proceso", "listo", "cancelado"]
        index_estado = estados.index(estado_actual) if estado_actual in estados else 0
        nuevo_estado = st.selectbox(
            "📌 Estado",
            options=estados,
            index=index_estado,
            key=f"estado_{pedido_id}"
        )

        if st.button(f"💾 Guardar cambios (Pedido {pedido_id})", key=f"guardar_{pedido_id}"):
            try:
                cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
                conn.commit()
                st.success("✅ Estado actualizado.")
            except Exception as e:
                st.error(f"❌ Error al actualizar: {e}")

        # Generar PDF ticket
        if st.button(f"🖨️ Descargar ticket (Pedido {pedido_id})", key=f"pdf_{pedido_id}"):
            cur.execute("""
            SELECT pr.nombre, dp.cantidad, dp.unidad,
                   COALESCE(dp.sabor, '') as sabor
            FROM detalle_pedido dp
            JOIN productos pr ON pr.id = dp.producto_id
            WHERE dp.pedido_id = %s;
            """, (pedido_id,))
            detalles_pedido = cur.fetchall()

            pdf = FPDF(format=(80, 297))  # Ticket width
            pdf.add_page()
            pdf.set_font("Arial", size=9)
            pdf.multi_cell(0, 5, f"PEDIDO #{pedido_id}", align="C")
            pdf.set_font("Arial", "B", size=9)
            pdf.cell(0, 5, f"{nombre_cliente}", ln=True)
            pdf.set_font("Arial", size=9)
            pdf.cell(0, 5, f"Alias: {alias_cliente}", ln=True)
            pdf.cell(0, 5, f"Fecha: {fecha_local}", ln=True)
            pdf.cell(0, 5, f"Estado: {nuevo_estado}", ln=True)
            pdf.cell(0, 5, "-"*32, ln=True)

            for nombre_prod, cantidad, unidad, sabor in detalles_pedido:
                pdf.multi_cell(0, 5, f"{cantidad:.2f} {unidad} | {nombre_prod}")
                if sabor:
                    pdf.multi_cell(0, 5, f"Sabor: {sabor}")

            pdf.cell(0, 5, "-"*32, ln=True)
            pdf.cell(0, 5, f"Total Kg: {total_kg:.2f}", ln=True)

            pdf_output = pdf.output(dest='S').encode('latin1')
            st.download_button(
                label="⬇️ Descargar Ticket",
                data=pdf_output,
                file_name=f"pedido_{pedido_id}.pdf",
                mime="application/pdf",
                key=f"download_pdf_{pedido_id}"
            )

st.write("---")
cur.close()
conn.close()
