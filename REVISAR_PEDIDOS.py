import streamlit as st
import psycopg2
import pandas as pd
from datetime import date

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

# Seleccionar fecha para filtrar pedidos
fecha = st.date_input("Selecciona la fecha", date.today())

# Obtener pedidos con detalles y estado
cur.execute("""
SELECT
    p.id,
    c.nombre,
    c.alias,
    TO_CHAR(p.fecha AT TIME ZONE 'UTC' AT TIME ZONE 'America/Chihuahua', 'YYYY-MM-DD HH24:MI') AS fecha_local,
    p.estado
FROM pedidos p
JOIN clientes c ON p.cliente_id = c.id
WHERE DATE(p.fecha AT TIME ZONE 'UTC' AT TIME ZONE 'America/Chihuahua') = %s
ORDER BY p.fecha, p.id;
""", (fecha,))
pedidos = cur.fetchall()

estados = ["en proceso", "listo", "cancelado"]

# Mostrar y editar estados
for pedido in pedidos:
    pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido
    st.write(f"Pedido ID: {pedido_id} | Cliente: {nombre_cliente} ({alias_cliente}) | Fecha: {fecha_local}")

    try:
        idx = estados.index(estado_actual)
    except ValueError:
        idx = 0

    nuevo_estado = st.selectbox(
        "Estado",
        options=estados,
        index=idx,
        key=f"estado_{pedido_id}"
    )

    if st.button("Guardar cambios", key=f"guardar_{pedido_id}"):
        try:
            cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
            conn.commit()
            st.success(f"Pedido {pedido_id} actualizado a estado '{nuevo_estado}'.")
        except Exception as e:
            st.error(f"Error al actualizar pedido {pedido_id}: {e}")

cur.close()
conn.close()
