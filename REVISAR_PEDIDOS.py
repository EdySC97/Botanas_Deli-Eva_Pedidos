import streamlit as st
import psycopg2
import pandas as pd
from datetime import date
from fpdf import FPDF
import io

# --- Función para convertir unidades a kg ---
def convertir_a_kg(cantidad, unidad):
    if cantidad is None or unidad is None:
        return 0
    try:
        cantidad = float(cantidad)
    except ValueError:
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

# --- Consulta lista de clientes ---
cur.execute("SELECT DISTINCT nombre FROM clientes ORDER BY nombre;")
clientes = [row[0] for row in cur.fetchall()]
cliente_filtro = st.selectbox("Filtrar por cliente (opcional)", ["Todos"] + clientes)

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

# Filtrar por cliente si se seleccionó uno
if cliente_filtro != "Todos":
    pedidos = [p for p in pedidos if p[1] == cliente_filtro]

# Obtener IDs para consultar detalles
pedido_ids = [p[0] for p in pedidos]
if not pedido_ids:
    st.warning("No hay pedidos para el cliente seleccionado.")
    cur.close()
    conn.close()
    st.stop()

# Consulta detalles para todos los pedidos del rango
cur.execute("""
SELECT
    pedido_id,
    cantidad,
    unidad
FROM detalle_pedido
WHERE pedido_id = ANY(%s);
""", (pedido_ids,))
detalles = cur.fetchall()

# Calcular total de kilos por pedido
detalles_por_pedido = {}
for pid, cantidad, unidad in detalles:
    kg = convertir_a_kg(cantidad, unidad)
    detalles_por_pedido[pid] = detalles_por_pedido.get(pid, 0) + kg

# Mostrar pedidos con expansión
for pedido in pedidos:
    pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido
    total_kg = detalles_por_pedido.get(pedido_id, 0)

    with st.expander(f"📋 Pedido ID {pedido_id} | {nombre_cliente} | {fecha_local}"):
        st.write(f"Alias: **{alias_cliente}**")
        st.write(f"Total Kilos: **{total_kg:.2f} kg**")

        estados = ["en proceso", "listo", "cancelado"]
        try:
            index_estado = estados.index(estado_actual)
        except ValueError:
            index_estado = 0

        nuevo_estado = st.selectbox(
            "Estado del pedido",
            options=estados,
            index=index_estado,
            key=f"estado_{pedido_id}"
        )

        # Botón guardar
        if st.button(f"💾 Guardar estado pedido {pedido_id}", key=f"guardar_{pedido_id}"):
            try:
                cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
                conn.commit()
                st.success(f"Estado del pedido {pedido_id} actualizado a '{nuevo_estado}'.")
            except Exception as e:
                st.error(f"Error al actualizar pedido {pedido_id}: {e}")

        # Consulta detalles específicos para este pedido
        cur.execute("""
        SELECT pr.nombre, dp.cantidad, dp.unidad, dp.sabor
        FROM detalle_pedido dp
        JOIN productos pr ON pr.id = dp.producto_id
        WHERE dp.pedido_id = %s;
        """, (pedido_id,))
        detalles_pedido = cur.fetchall()

        # Mostrar tabla
        df_detalle = pd.DataFrame(detalles_pedido, columns=["Producto", "Cantidad", "Unidad", "Sabor"])
        st.dataframe(df_detalle)

        # Generar PDF tipo ticket
        if st.button(f"📄 Generar Ticket Pedido {pedido_id}", key=f"pdf_{pedido_id}"):
            pdf = FPDF(orientation='P', unit='mm', format=(80, 200))
            pdf.add_page()
            pdf.set_margins(5, 5, 5)
            pdf.set_font("Arial", size=6)
            pdf.cell(0, 6, f"Pedido ID: {pedido_id}", ln=True)
            pdf.set_font("Arial", "B", 6)
            pdf.cell(0, 6, f"Cliente: {nombre_cliente}", ln=True)
            pdf.set_font("Arial", "B", 6)
            pdf.cell(0,6, f"Alias: {alias_cliente}", ln=True)
            pdf.set_font("Arial", "B", 6)
            pdf.cell(0, 6, f"Fecha: {fecha_local}", ln=True)
            pdf.set_font("Arial", "B", 6)
            pdf.cell(0, 6, f"Estado: {nuevo_estado}", ln=True)
            pdf.set_font("Arial", "", 6)
            pdf.ln(4)
        
            pdf.set_font("Arial", "B", 6)
            pdf.cell(0, 6, "Detalles del pedido:", ln=True)
            pdf.set_font("Arial", size=6)
        
            for nombre_prod, cantidad, unidad, sabor in detalles_pedido:
                pdf.set_font("Arial", "B", 6)
                pdf.cell(0, 6, f"{nombre_prod}", ln=True)
                pdf.set_font("Arial", "", 6)
                pdf.cell(0, 6, f"{cantidad} {unidad} | Sabor: {sabor}", ln=True)
                pdf.ln(1)
        
            pdf_output = pdf.output(dest='S').encode('latin1')
            st.download_button(
                label=f"⬇️ Descargar Ticket PDF Pedido {pedido_id}",
                data=pdf_output,
                file_name=f"ticket_pedido_{pedido_id}.pdf",
                mime="application/pdf",
                key=f"ticket_pdf_{pedido_id}"
            )


st.write("---")
cur.close()
conn.close()
