import streamlit as st
import psycopg2
import pandas as pd
from datetime import date

st.set_page_config(page_title="Revisión de Pedidos", layout="wide")

# --- Función para convertir unidades a kilogramos ---
def convertir_a_kg(cantidad, unidad):
    try:
        cantidad = float(cantidad)
    except (TypeError, ValueError):
        return 0

    unidad = unidad.lower() if unidad else ""

    if "medio" in unidad:
        return cantidad * 0.5
    elif "cuarto" in unidad:
        return cantidad * 0.25
    elif "kilo" in unidad or "kg" in unidad:
        return cantidad * 1
    elif "50" in unidad:
        return cantidad * 0.05
    elif "70" in unidad:
        return cantidad * 0.07
    elif "100" in unidad:
        return cantidad * 0.1
    elif "200" in unidad:
        return cantidad * 0.2
    elif "bulto" in unidad and "5" in unidad:
        return cantidad * 5
    elif "bulto" in unidad and "10" in unidad:
        return cantidad * 10
    elif "bulto" in unidad and "20" in unidad:
        return cantidad * 20
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
col1, col2 = st.columns(2)
with col1:
    fecha_inicio = st.date_input("📅 Fecha inicio", date.today())
with col2:
    fecha_fin = st.date_input("📅 Fecha fin", date.today())

# --- Obtener pedidos con detalles ---
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
    st.info("No hay pedidos para este rango de fechas.")
else:
    for pedido in pedidos:
        pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido

        # --- Mostrar resumen del pedido ---
        st.markdown(f"### Pedido #{pedido_id} - {nombre_cliente} ({alias_cliente})")
        st.markdown(f"🕒 Fecha: {fecha_local}")

        # --- Obtener detalles del pedido ---
        cur.execute("""
        SELECT dp.cantidad, dp.unidad, dp.sabor, pr.nombre
        FROM detalle_pedido dp
        JOIN productos pr ON dp.producto_id = pr.id
        WHERE dp.pedido_id = %s
        """, (pedido_id,))
        detalles = cur.fetchall()

        total_kg = sum([convertir_a_kg(c, u) for c, u, _, _ in detalles])

        df = pd.DataFrame(detalles, columns=["Cantidad", "Unidad", "Sabor", "Producto"])
        df["Kg estimados"] = [convertir_a_kg(c, u) for c, u, _, _ in detalles]
        st.dataframe(df, use_container_width=True)
        st.success(f"🔢 Total estimado en kg: **{round(total_kg, 2)} kg**")

        # --- Cambiar estado del pedido ---
        nuevo_estado = st.selectbox(
            "Cambiar estado:",
            options=["en proceso", "listo", "cancelado"],
            index=["en proceso", "listo", "cancelado"].index(estado_actual),
            key=f"estado_{pedido_id}"
        )

        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("💾 Guardar", key=f"guardar_{pedido_id}"):
                try:
                    cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
                    conn.commit()
                    st.success(f"✅ Pedido {pedido_id} actualizado.")
                except Exception as e:
                    st.error(f"❌ Error: {e}")

        with col2:
            # Simulación de impresión
            texto = f"Pedido #{pedido_id}\nCliente: {nombre_cliente} ({alias_cliente})\nFecha: {fecha_local}\nEstado: {nuevo_estado}\n\nProductos:\n"
            for c, u, s, p in detalles:
                texto += f"- {p}: {c} {u} ({s})\n"
            texto += f"\nTotal estimado: {round(total_kg, 2)} kg"

            st.download_button(
                label="🖨️ Imprimir pedido",
                data=texto,
                file_name=f"pedido_{pedido_id}.txt",
                mime="text/plain",
                key=f"descargar_{pedido_id}"
            )

cur.close()
conn.close()
