import streamlit as st
import psycopg2
import pandas as pd
from datetime import date

# Función para convertir cantidades a kilogramos de forma segura
def convertir_a_kg(cantidad, unidad):
    try:
        cantidad = float(cantidad)
    except (TypeError, ValueError):
        return 0  # Si no es convertible, asumimos 0

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

# Selector de rango de fechas para filtrar pedidos
fecha_inicio, fecha_fin = st.date_input("Selecciona rango de fechas", 
                                       value=(date.today(), date.today()))

# Convertir fechas a string para SQL (yyyy-mm-dd)
fecha_inicio_str = fecha_inicio.strftime("%Y-%m-%d")
fecha_fin_str = fecha_fin.strftime("%Y-%m-%d")

# Consulta pedidos con detalles y estado en rango seleccionado
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
""", (fecha_inicio_str, fecha_fin_str))

pedidos = cur.fetchall()

if not pedidos:
    st.info("No se encontraron pedidos en el rango seleccionado.")
else:
    for pedido in pedidos:
        pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido

        # Consultar detalles para el pedido para calcular kilos totales
        cur.execute("""
        SELECT cantidad, unidad 
        FROM detalle_pedido 
        WHERE pedido_id = %s
        """, (pedido_id,))
        detalles = cur.fetchall()

        # Sumar kilos totales del pedido
        total_kg = 0
        for cantidad, unidad in detalles:
            total_kg += convertir_a_kg(cantidad, unidad)

        # Mostrar información
        st.markdown(f"### Pedido ID: {pedido_id} | Cliente: {nombre_cliente} ({alias_cliente}) | Fecha: {fecha_local}")
        st.markdown(f"**Total kilos:** {total_kg:.3f} kg")

        # Selector de estado con valor actual seleccionado
        estados = ["en proceso", "listo", "cancelado"]
        try:
            index_estado = estados.index(estado_actual)
        except ValueError:
            index_estado = 0  # Por si el estado actual no está en la lista

        nuevo_estado = st.selectbox(
            "Estado",
            options=estados,
            index=index_estado,
            key=f"estado_{pedido_id}"
        )

        # Botón para guardar cambios
        if st.button("Guardar cambios", key=f"guardar_{pedido_id}"):
            try:
                cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
                conn.commit()
                st.success(f"Pedido {pedido_id} actualizado a estado '{nuevo_estado}'.")
            except Exception as e:
                st.error(f"Error al actualizar pedido {pedido_id}: {e}")

cur.close()
conn.close()
