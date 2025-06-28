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

st.set_page_config(page_title="Revisión de Pedidos", layout="wide")
st.title("📦 Revisión y Modificación de Pedidos")

# ---------- Funciones auxiliares ----------
def convertir_a_kg(cantidad, unidad):
    unidad = unidad.lower()
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

def obtener_detalle_pedido(conn, pedido_id):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT pr.nombre, dp.cantidad, dp.unidad, dp.sabor
            FROM detalle_pedido dp
            JOIN productos pr ON pr.id = dp.producto_id
            WHERE dp.pedido_id = %s;
        """, (pedido_id,))
        return cur.fetchall()

# ---------- Selección de fecha ----------
fecha = st.date_input("📅 Selecciona la fecha", date.today())

# ---------- Consulta de pedidos ----------
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

if not pedidos:
    st.info("No hay pedidos para la fecha seleccionada.")
else:
    for pedido in pedidos:
        pedido_id, nombre_cliente, alias_cliente, fecha_local, estado_actual = pedido
        st.subheader(f"📦 Pedido #{pedido_id} - {nombre_cliente} ({alias_cliente}) - {fecha_local}")

        detalles = obtener_detalle_pedido(conn, pedido_id)
        total_kg = 0
        filas = []

        for nombre, cantidad, unidad, sabor in detalles:
            kg = convertir_a_kg(cantidad, unidad)
            total_kg += kg
            filas.append({
                "Producto": nombre,
                "Cantidad": cantidad,
                "Unidad": unidad,
                "Sabor": sabor,
                "Equiv. KG": round(kg, 2)
            })

        df = pd.DataFrame(filas)
        st.dataframe(df, use_container_width=True)
        st.markdown(f"**🔢 Total en kilogramos estimados:** `{round(total_kg, 2)} kg`")

        # Cambiar estado y exportar
        nuevo_estado = st.selectbox(
            "🛠 Cambiar estado",
            options=["en proceso", "listo", "cancelado"],
            index=["en proceso", "listo", "cancelado"].index(estado_actual),
            key=f"estado_{pedido_id}"
        )

        cols = st.columns([1, 1])
        if cols[0].button("Guardar cambios", key=f"guardar_{pedido_id}"):
            try:
                cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (nuevo_estado, pedido_id))
                conn.commit()
                st.success(f"✅ Pedido {pedido_id} actualizado.")
            except Exception as e:
                st.error(f"❌ Error al actualizar pedido {pedido_id}: {e}")

        # Descargar como CSV
        csv = df.to_csv(index=False).encode("utf-8")
        cols[1].download_button(
            label="📄 Descargar pedido (CSV)",
            data=csv,
            file_name=f"pedido_{pedido_id}.csv",
            mime="text/csv",
            key=f"descargar_{pedido_id}"
        )

        st.markdown("---")

cur.close()
conn.close()
