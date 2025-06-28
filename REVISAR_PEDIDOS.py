import streamlit as st
import psycopg2
import pandas as pd
from datetime import date
from fpdf import FPDF

# --- Función para convertir unidades a kg ---
def convertir_a_kg(cantidad, unidad):
    if not unidad:
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

# --- Selección de rango de fechas ---
fecha_inicio, fecha_fin = st.date_input(
    "Selecciona rango de fechas",
    value=[date.today(), date.today()],
    key="rango_fechas"
)
if fecha_inicio > fecha_fin:
    st.error("La fecha inicio debe ser menor o igual a la fecha fin.")
    st.stop()

# --- Filtro por cliente ---
cur.execute("SELECT id, nombre || ' (' || alias || ')' FROM clientes ORDER BY nombre;")
clientes = cur.fetchall()
clientes_dict = {nombre: id_ for id_, nombre in clientes}
cliente_sel = st.selectbox("🔍 Filtrar por cliente", ["Todos"] + list(clientes_dict.keys()))

# --- Consulta principal de pedidos ---
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

if cliente_sel != "Todos":
    query += " AND c.id = %s"
    params.append(clientes_dict[cliente_sel])

query += " ORDER BY p.fecha, p.id;"
cur.execute(query, params)
pedidos = cur.fetchall()

if not pedidos:
    st.info("No se encontraron pedidos.")
    cur.close()
    conn.close()
    st.stop()

pedido_ids = [p[0] for p in pedidos]

# --- Consulta detalles para calcular kilos ---
cur.execute("""
SELECT pedido_id, cantidad, unidad
FROM detalle_pedido
WHERE pedido_id = ANY(%s);
""", (pedido_ids,))
detalles = cur.fetchall()

# --- Agrupamos para sumar kg ---
detalles_por_pedido = {}
for pid, cantidad, unidad in detalles:
    kg = convertir_a_kg(cantidad, unidad)
    detalles_por_pedido[pid] = detalles_por_pedido.get(pid, 0) + kg

# --- Mostrar cada pedido como sección expandible ---
for pedido in pedidos:
    pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido
    total_kg = detalles_por_pedido.get(pedido_id, 0)

    with st.expander(f"🧾 Pedido #{pedido_id} | {nombre_cliente} ({alias_cliente}) | {fecha_local} | Estado: {estado_actual}"):
        st.write(f"**Fecha:** {fecha_local}")
        st.write(f"**Cliente:** {nombre_cliente} ({alias_cliente})")
        st.write(f"**Total en kilos:** {total_kg:.2f} kg")

        estados = ["en proceso", "listo", "cancelado"]
        index_estado = estados.index(estado_actual) if estado_actual in estados else 0
        nuevo_estado = st.selectbox(
            "🛠 Cambiar estado",
            options=estados,
            index=index_estado,
            key=f"estado_{pedido_id}"
        )

        col1, col2 = st.columns(2)

        # Botón para guardar
        with col1:
            if st.button("💾 Guardar cambios", key=f"guardar_{pedido_id}"):
                try:
                    cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
                    conn.commit()
                    st.success(f"Pedido {pedido_id} actualizado a '{nuevo_estado}'")
                except Exception as e:
                    st.error(f"Error al guardar: {e}")

        # Botón para exportar PDF
        with col2:
            if st.button("🖨️ Descargar PDF", key=f"pdf_{pedido_id}"):
                cur.execute("""
                SELECT pr.nombre, dp.cantidad, dp.unidad, dp.sabor
                FROM detalle_pedido dp
                JOIN productos pr ON pr.id = dp.producto_id
                WHERE dp.pedido_id = %s;
                """, (pedido_id,))
                detalles_pedido = cur.fetchall()

                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", size=12)
                pdf.cell(0, 10, f"Pedido #{pedido_id}", ln=True)
                pdf.cell(0, 10, f"Cliente: {nombre_cliente} ({alias_cliente})", ln=True)
                pdf.cell(0, 10, f"Fecha: {fecha_local}", ln=True)
                pdf.cell(0, 10, f"Estado: {nuevo_estado}", ln=True)
                pdf.cell(0, 10, f"Total en kilos: {total_kg:.2f} kg", ln=True)
                pdf.ln(5)

                # Encabezados
                pdf.set_font("Arial", "B", 11)
                pdf.cell(60, 10, "Producto", border=1)
                pdf.cell(30, 10, "Cantidad", border=1)
                pdf.cell(30, 10, "Unidad", border=1)
                pdf.cell(60, 10, "Sabor", border=1)
                pdf.ln()

                # Detalles
                pdf.set_font("Arial", size=10)
                for nombre_prod, cantidad, unidad, sabor in detalles_pedido:
                    pdf.cell(60, 10, str(nombre_prod), border=1)
                    pdf.cell(30, 10, str(cantidad), border=1)
                    pdf.cell(30, 10, str(unidad), border=1)
                    pdf.cell(60, 10, str(sabor), border=1)
                    pdf.ln()

                pdf_output = pdf.output(dest='S').encode('latin1')
                st.download_button(
                    label=f"📥 Descargar Pedido {pedido_id}.pdf",
                    data=pdf_output,
                    file_name=f"pedido_{pedido_id}.pdf",
                    mime="application/pdf",
                    key=f"descarga_{pedido_id}"
                )

cur.close()
conn.close()
