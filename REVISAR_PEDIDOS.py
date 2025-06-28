import streamlit as st
import psycopg2
import pandas as pd
from datetime import date, timedelta

# Función para convertir unidades a kilogramos
def convertir_a_kg(cantidad, unidad):
    unidad = unidad.lower()
    if unidad in ["kg", "kilo", "kilos"]:
        return cantidad
    elif unidad in ["medio", "1/2"]:
        return cantidad * 0.5
    elif unidad in ["cuarto", "1/4"]:
        return cantidad * 0.25
    elif unidad == "100 g":
        return cantidad * 0.1
    elif unidad == "70 gr":
        return cantidad * 0.07
    elif unidad == "50 gr":
        return cantidad * 0.05
    elif "bulto 5kg" in unidad.lower():
        return cantidad * 5
    elif "bulto 10kg" in unidad.lower():
        return cantidad * 10
    elif "bulto 20kg" in unidad.lower():
        return cantidad * 20
    else:
        return 0  # Si no sabemos convertir

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

# ✅ Limpiar estados inválidos
cur.execute("""
    UPDATE pedidos
    SET estado = 'en proceso'
    WHERE estado IS NULL OR TRIM(estado) = '' OR estado NOT IN ('en proceso', 'listo', 'cancelado')
""")
conn.commit()

# 📅 Selector de rango de fechas
col1, col2 = st.columns(2)
fecha_inicio = col1.date_input("📅 Desde", date.today() - timedelta(days=7))
fecha_fin = col2.date_input("📅 Hasta", date.today())

# Obtener pedidos en rango de fechas
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
    st.warning("No hay pedidos en el rango de fechas seleccionado.")
else:
    for pedido in pedidos:
        pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido
        st.markdown(f"### Pedido ID: `{pedido_id}`")
        st.write(f"📌 Cliente: **{nombre_cliente}** ({alias_cliente}) | 📆 Fecha: {fecha_local}")

        # Obtener detalle del pedido
        cur.execute("""
            SELECT pr.nombre, dp.cantidad, dp.unidad, dp.sabor
            FROM detalle_pedido dp
            JOIN productos pr ON pr.id = dp.producto_id
            WHERE dp.pedido_id = %s;
        """, (pedido_id,))
        detalles = cur.fetchall()

        total_kg = 0
        for producto, cantidad, unidad, sabor in detalles:
            kg = convertir_a_kg(cantidad, unidad)
            total_kg += kg
            st.write(f"- 🛒 {cantidad} {unidad} de {producto} {'(' + sabor + ')' if sabor else ''} → {kg:.2f} kg")

        st.success(f"**Total estimado: {total_kg:.2f} kg**")

        nuevo_estado = st.selectbox(
            "🛠 Cambiar estado:",
            options=["en proceso", "listo", "cancelado"],
            index=["en proceso", "listo", "cancelado"].index(estado_actual),
            key=f"estado_{pedido_id}"
        )

        col_guardar, col_imprimir = st.columns(2)

        if col_guardar.button("💾 Guardar cambios", key=f"guardar_{pedido_id}"):
            try:
                cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
                conn.commit()
                st.success(f"✅ Pedido {pedido_id} actualizado a '{nuevo_estado}'.")
            except Exception as e:
                st.error(f"❌ Error al actualizar pedido {pedido_id}: {e}")

        if col_imprimir.button("🖨 Imprimir pedido", key=f"print_{pedido_id}"):
            st.info(f"🖨 Pedido {pedido_id} enviado a impresión (simulado).")

cur.close()
conn.close()
