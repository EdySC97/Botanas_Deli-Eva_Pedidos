import streamlit as st
import psycopg2
import pandas as pd
from datetime import date
from fpdf import FPDF
import io

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

st.title("📦 Revisión de Pedidos")

# --- Selección de rango de fechas ---
fecha_inicio, fecha_fin = st.date_input(
    "Selecciona rango de fechas",
    value=[date.today(), date.today()],
    key="rango_fechas"
)
if fecha_inicio > fecha_fin:
    st.error("La fecha de inicio debe ser anterior o igual a la final.")
    st.stop()

# --- Opcional: filtro por estado de pedido ---
estado_filtro = st.selectbox("Filtrar por estado", ["Todos", "en proceso", "listo", "cancelado"])

# --- Obtener lista de clientes para filtrar ---
cur.execute("SELECT DISTINCT nombre FROM clientes ORDER BY nombre")
clientes = [r[0] for r in cur.fetchall()]
cliente_filtro = st.selectbox("Filtrar por cliente", ["Todos"] + clientes)

# --- Consulta base de pedidos ---
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

query += " ORDER BY p.fecha, p.id"

cur.execute(query, params)
pedidos = cur.fetchall()

if not pedidos:
    st.info("No se encontraron pedidos con esos filtros.")
    cur.close()
    conn.close()
    st.stop()

# --- Procesar pedidos ---
pedido_ids = [p[0] for p in pedidos]

# --- Traer todos los detalles de los pedidos en lote ---
cur.execute("""
SELECT
    dp.pedido_id,
    pr.nombre,
    dp.cantidad,
    dp.unidad,
    COALESCE(dp.sabor, '') AS sabor
FROM detalle_pedido dp
JOIN productos pr ON pr.id = dp.producto_id
WHERE dp.pedido_id = ANY(%s);
""", (pedido_ids,))
detalles = cur.fetchall()

# Agrupar detalles por pedido
detalles_por_pedido = {}
total_kilos_por_pedido = {}

for pid, producto, cantidad, unidad, sabor in detalles:
    detalles_por_pedido.setdefault(pid, []).append((producto, cantidad, unidad, sabor))
    total_kilos_por_pedido[pid] = total_kilos_por_pedido.get(pid, 0) + convertir_a_kg(cantidad, unidad)

# --- Mostrar cada pedido ---
for pedido in pedidos:
    pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido
    total_kg = total_kilos_por_pedido.get(pedido_id, 0)

    with st.expander(f"📄 Pedido #{pedido_id} | Cliente: {nombre_cliente} | Estado: {estado_actual}"):
        st.markdown(f"**Alias:** {alias_cliente}")
        st.markdown(f"**Fecha:** {fecha_local}")
        st.markdown(f"**Total estimado en kilos:** {total_kg:.2f} kg")

        # Mostrar contenido en tabla
        df = pd.DataFrame(detalles_por_pedido.get(pedido_id, []),
                          columns=["Producto", "Cantidad", "Unidad", "Sabor"])
        st.table(df)

        # Cambiar estado
        estados = ["en proceso", "listo", "cancelado"]
        index_estado = estados.index(estado_actual) if estado_actual in estados else 0
        nuevo_estado = st.selectbox("Cambiar estado", estados, index=index_estado, key=f"estado_{pedido_id}")

        if st.button("Guardar estado", key=f"guardar_{pedido_id}"):
            cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
            conn.commit()
            st.success(f"Pedido {pedido_id} actualizado a '{nuevo_estado}'.")

        # Botón para descargar como PDF
        if st.button("Descargar PDF", key=f"pdf_{pedido_id}"):
            pdf = FPDF(orientation="P", unit="mm", format=(58, 210))  # formato ticket 58mm
            pdf.add_page()
            pdf.set_font("Arial", "B", 10)
            pdf.cell(0, 6, f"PEDIDO #{pedido_id}", ln=True)
            pdf.set_font("Arial", "B", 9)
            pdf.cell(0, 6, f"{nombre_cliente}", ln=True)
            pdf.set_font("Arial", "", 8)
            pdf.cell(0, 5, f"Alias: {alias_cliente}", ln=True)
            pdf.cell(0, 5, f"Fecha: {fecha_local}", ln=True)
            pdf.cell(0, 5, f"Estado: {nuevo_estado}", ln=True)
            pdf.ln(3)
            pdf.set_font("Arial", "", 7)

            for prod, cant, uni, sabor in detalles_por_pedido[pedido_id]:
                linea = f"{cant} {uni} - {prod}"
                if sabor:
                    linea += f" | Sabor: {sabor}"
                pdf.multi_cell(0, 4, linea)

            pdf.ln(3)
            pdf.set_font("Arial", "B", 8)
            pdf.cell(0, 5, f"Total estimado: {total_kg:.2f} kg", ln=True)

            pdf_output = pdf.output(dest="S").encode("latin1")
            st.download_button(
                label="📥 Descargar PDF (Ticket)",
                data=pdf_output,
                file_name=f"pedido_{pedido_id}.pdf",
                mime="application/pdf",
                key=f"dl_pdf_{pedido_id}"
            )

st.write("---")
cur.close()
conn.close()
