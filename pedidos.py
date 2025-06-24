import streamlit as st
import psycopg2
import pandas as pd
import os

os.environ["PGCLIENTENCODING"] = "latin1"

st.title("Captura de Pedido")

# Credenciales desde .streamlit/secrets.toml
host = st.secrets["postgres"]["host"]
port = st.secrets["postgres"]["port"]
database = st.secrets["postgres"]["database"]
user = st.secrets["postgres"]["user"]
password = st.secrets["postgres"]["password"]
pool_mode = st.secrets["postgres"].get("pool_mode", "session")  # opcional, si usas pool_mode

# Estado inicial en session_state
if "carrito" not in st.session_state:
    st.session_state.carrito = []

if "confirmacion_pendiente" not in st.session_state:
    st.session_state.confirmacion_pendiente = False

if "pedido_guardado" not in st.session_state:
    st.session_state.pedido_guardado = False

# -------------------- CONEXIÓN --------------------
def conectar_db():
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
        )
        return conn
    except Exception as e:
        st.error(f"Error al conectar con la base de datos: {e}")
        return None

conn = conectar_db()
if conn is None:
    st.stop()
cur = conn.cursor()

# -------------------- CLIENTES Y PRODUCTOS --------------------
cur.execute("SELECT id, nombre FROM clientes ORDER BY nombre")
clientes = cur.fetchall()
cliente_dict = {nombre: id_ for id_, nombre in clientes}
cliente_nombre = st.selectbox("Selecciona cliente", list(cliente_dict.keys()))

cur.execute("SELECT id, nombre, unidad_base FROM productos ORDER BY nombre")
productos = cur.fetchall()
producto_opciones = [f"{nombre} ({unidad})" for _, nombre, unidad in productos]
producto_seleccionado = st.selectbox("Producto", producto_opciones)

cantidad = st.number_input("Cantidad", min_value=0.0, step=1.0)

unidades = [
    "Kg", "Medio", "Cuarto", "Pieza",
    "bulto 5kg", "bulto 10kg", "bulto 20kg", "Tubitos 1kg"
]
unidad = st.selectbox("Unidades", unidades)

# -------------------- AGREGAR AL PEDIDO --------------------
if st.button("Agregar al pedido"):
    if cantidad <= 0:
        st.warning("La cantidad debe ser mayor que cero")
    else:
        idx = producto_opciones.index(producto_seleccionado)
        producto_id = productos[idx][0]
        producto_nombre = productos[idx][1]
        st.session_state.carrito.append({
            "producto_id": producto_id,
            "producto": producto_nombre,
            "cantidad": cantidad,
            "unidad": unidad,
        })
        st.success(f"Producto '{producto_nombre}' agregado.")

# -------------------- EDITAR CARRITO --------------------
if st.session_state.carrito:
    st.subheader("Editar productos en el carrito")
    eliminar_indices = []
    for i, item in enumerate(st.session_state.carrito):
        cols = st.columns([4, 2, 2, 2])
        cols[0].write(item["producto"])
        nueva_cantidad = cols[1].number_input(
            f"Cantidad {i}", value=item["cantidad"], step=1.0, key=f"cant_{i}"
        )
        nueva_unidad = cols[2].selectbox(
            f"Unidad {i}", unidades, index=unidades.index(item["unidad"]), key=f"uni_{i}"
        )
        if cols[3].button("Eliminar", key=f"del_{i}"):
            eliminar_indices.append(i)

        st.session_state.carrito[i]["cantidad"] = nueva_cantidad
        st.session_state.carrito[i]["unidad"] = nueva_unidad

    for idx in sorted(eliminar_indices, reverse=True):
        st.session_state.carrito.pop(idx)
    if eliminar_indices:
        st.success("Producto(s) eliminado(s)")

    # -------------------- RESUMEN --------------------
    df = pd.DataFrame(st.session_state.carrito)
    if not df.empty and all(col in df.columns for col in ["producto", "unidad", "cantidad"]):
        resumen_pivot = df.pivot_table(
            index="producto", columns="unidad", values="cantidad", aggfunc="sum", fill_value=0
        ).reset_index()
        st.subheader("Resumen del pedido")
        st.table(resumen_pivot)
    else:
        st.info("No hay productos para mostrar en el resumen")

    # -------------------- FLUJO DE GUARDADO --------------------
    if not st.session_state.confirmacion_pendiente and not st.session_state.pedido_guardado:
        if st.button("Guardar pedido"):
            st.session_state.confirmacion_pendiente = True
            st.experimental_rerun()

    if st.session_state.confirmacion_pendiente and not st.session_state.pedido_guardado:
        st.warning("¿Estás seguro de guardar este pedido?")
        if st.button("✅ Confirmar y guardar"):
            try:
                cur.execute(
                    "INSERT INTO pedidos (cliente_id) VALUES (%s) RETURNING id",
                    (cliente_dict[cliente_nombre],)
                )
                pedido_id = cur.fetchone()[0]

                for item in st.session_state.carrito:
                    cur.execute(
                        "INSERT INTO detalle_pedido (pedido_id, producto_id, cantidad, unidad) VALUES (%s, %s, %s, %s)",
                        (pedido_id, item["producto_id"], item["cantidad"], item["unidad"])
                    )
                conn.commit()

                st.success("✅ Pedido guardado correctamente.")
                st.session_state.carrito = []
                st.session_state.pedido_guardado = True
                st.session_state.confirmacion_pendiente = False
                st.experimental_rerun()

            except Exception as e:
                st.error(f"❌ Error al guardar el pedido: {e}")

else:
    st.info("Agrega productos al carrito para iniciar un pedido.")

cur.close()
conn.close()
