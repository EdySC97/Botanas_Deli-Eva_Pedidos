import streamlit as st
import psycopg2
from datetime import date
import pandas as pd

# --- Conexión DB ---
def conectar_db():
    return psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        port=st.secrets["postgres"]["port"],
        database=st.secrets["postgres"]["database"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"],
    )

# --- Función para obtener pedidos filtrados ---
def obtener_pedidos(conn, fecha, filtro_cliente):
    with conn.cursor() as cur:
        sql = """
        SELECT
            p.id,
            c.nombre,
            c.alias,
            TO_CHAR(p.fecha AT TIME ZONE 'UTC' AT TIME ZONE 'America/Chihuahua', 'YYYY-MM-DD HH24:MI') AS fecha_local,
            p.estado
        FROM pedidos p
        JOIN clientes c ON p.cliente_id = c.id
        WHERE DATE(p.fecha AT TIME ZONE 'UTC' AT TIME ZONE 'America/Chihuahua') = %s
        """
        params = [fecha]

        if filtro_cliente:
            sql += " AND (c.nombre ILIKE %s OR c.alias ILIKE %s)"
            like_param = f"%{filtro_cliente}%"
            params.extend([like_param, like_param])

        sql += " ORDER BY p.fecha, p.id;"

        cur.execute(sql, params)
        pedidos = cur.fetchall()
    return pedidos

# --- Función para obtener detalle de pedido ---
def obtener_detalle_pedido(conn, pedido_id):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT pr.nombre, dp.cantidad, dp.unidad, dp.sabor
            FROM detalle_pedido dp
            JOIN productos pr ON pr.id = dp.producto_id
            WHERE dp.pedido_id = %s;
        """, (pedido_id,))
        detalles = cur.fetchall()
    return detalles

# --- Interfaz Streamlit ---
st.set_page_config(page_title="Revisión y Modificación de Pedidos", layout="wide")

st.title("📦 Revisión y Modificación de Pedidos")

conn = conectar_db()

# Selector de fecha
fecha = st.date_input("Selecciona la fecha", date.today())

# Buscador por cliente
filtro_cliente = st.text_input("Buscar cliente por nombre o alias (dejar vacío para mostrar todos)")

# Obtener pedidos filtrados
pedidos = obtener_pedidos(conn, fecha, filtro_cliente)

estados = ["en proceso", "listo", "cancelado"]

if not pedidos:
    st.info("No se encontraron pedidos para esa fecha y filtro.")
else:
    # Mostrar número de pedidos encontrados
    st.markdown(f"### {len(pedidos)} pedidos encontrados")

    # Usar expander para cada pedido, más organizado y limpio
    for pedido in pedidos:
        pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido

        with st.expander(f"Pedido #{pedido_id} - Cliente: {nombre_cliente} ({alias_cliente}) - {fecha_local}"):

            cols = st.columns([3, 2, 2])

            # Mostrar estado actual y selector para cambiarlo
            cols[0].write(f"Estado actual: **{estado_actual}**")

            try:
                idx = estados.index(estado_actual)
            except ValueError:
                idx = 0

            nuevo_estado = cols[1].selectbox(
                "Cambiar estado",
                options=estados,
                index=idx,
                key=f"estado_{pedido_id}"
            )

            if cols[2].button("Guardar cambios", key=f"guardar_{pedido_id}"):
                try:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
                        conn.commit()
                    st.success(f"Pedido {pedido_id} actualizado a '{nuevo_estado}'")
                except Exception as e:
                    st.error(f"Error al actualizar pedido {pedido_id}: {e}")

            # Mostrar detalle de productos del pedido en tabla
            detalles = obtener_detalle_pedido(conn, pedido_id)
            if detalles:
                df_detalle = pd.DataFrame(detalles, columns=["Producto", "Cantidad", "Unidad", "Sabor"])
                st.table(df_detalle)
            else:
                st.write("No hay detalle para este pedido.")

conn.close()
