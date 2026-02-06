import streamlit as st
import psycopg2
import pandas as pd
import os
st.set_page_config(
    page_title="Tienda online Botanas Deli-Eva",
    page_icon="🏠",
    layout="centered",
    initial_sidebar_state="expanded",
)
os.environ["PGCLIENTENCODING"] = "latin1"

st.title("Captura de Pedido")

# Credenciales desde .streamlit/secrets.toml
host = st.secrets["postgres"]["host"]
port = st.secrets["postgres"]["port"]
database = st.secrets["postgres"]["database"]
user = st.secrets["postgres"]["user"]
password = st.secrets["postgres"]["password"]
pool_mode = st.secrets["postgres"].get("pool_mode", "session")  # opcional

# Estado inicial en session_state
if "carrito" not in st.session_state:
    st.session_state.carrito = []

if "confirmacion_pendiente" not in st.session_state:
    st.session_state.confirmacion_pendiente = False

if "pedido_guardado" not in st.session_state:
    st.session_state.pedido_guardado = False


# Conexión a la base de datos
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

# Obtener clientes
cur.execute("SELECT id, alias FROM clientes ORDER BY nombre")
clientes = cur.fetchall()
cliente_dict = {nombre: id_ for id_, nombre in clientes}
cliente_nombre = st.selectbox("Selecciona cliente", list(cliente_dict.keys()))

# Obtener productos
cur.execute("SELECT id, nombre, unidad_base FROM productos ORDER BY nombre")
productos = cur.fetchall()
producto_opciones = [f"{nombre} ({unidad})" for _, nombre, unidad in productos]
producto_seleccionado = st.selectbox("Producto", producto_opciones)

# Mapear producto seleccionado a su id y nombre real
producto_idx = producto_opciones.index(producto_seleccionado)
producto_id = productos[producto_idx][0]
producto_nombre = productos[producto_idx][1]

# Definir unidades y sabores para Palomitas y Chips
unidades_palomitas = ["50 gr", "70 gr", "Medio kilo", "Kilo"]
sabores_palomitas = ["Escolar", "Queso", "Flaming Hot", "Queso Jalapeño", "Mantequilla"]

#Definir unidades de crema de cacahuate

unidades_crema_cacahuate=["Litro (1 Kg)","Medio litro (Medio kilo)","Cuarto de litro (Cuarto de kilo)"]
sabor_crema=["Con zúcar","Sin azúcar"]

unidades_chips = ["100 g", "200 g", "Medio kilo", "Bulto 5kg", "Bulto 10kg"]
sabores_chips = ["Adobada", "Queso Jalapeño", "Salsa Negra", "Naturales (Camote)"]

# Definir unidades para ajo salado

unidades_ajo_salado = ["100 g", "50 g"]
sabores_ajo_salado = ["Natural"]

# Definir carne seca

unidades_carne_seca = ["100 g", "50 g", "Medio kilo", "Kilo"]
sabores_carne_seca = ["Natural", "Chipotle", "Pimienta limón", "Mango habanero"]

# Unidades generales para otros productos
unidades_generales = [
    "Kg",
    "Medio",
    "Cuarto",
    "Pieza",
    "Bulto 5kg",
    "Bulto 10kg",
    "Bulto 20kg",
    "Tubitos 1kg",
]

# Lógica para asignar unidades y sabores según la primera palabra del producto
producto_raiz = producto_nombre.lower().split()[0]

if producto_raiz == "palomita":
    unidades = unidades_palomitas
    sabores = sabores_palomitas
elif producto_raiz == "chips":
    unidades = unidades_chips
    sabores = sabores_chips
elif producto_raiz == "ajo":
    unidades = unidades_ajo_salado
    sabores = sabores_ajo_salado
elif producto_raiz == "carne":
    unidades = unidades_carne_seca
    sabores = sabores_carne_seca
elif producto_raiz=="crema":
    unidades= unidades_crema_cacahuate
    sabores=sabor_crema

else:
    unidades = unidades_generales
    sabores = ["N/A"]  # Para productos sin sabores

cantidad = st.number_input("Cantidad", min_value=0.0, step=1.0)

unidad = st.selectbox("Unidades", unidades)

# Mostrar selector de sabores solo si tiene sabores definidos (no "N/A")
if sabores != ["N/A"]:
    sabor = st.selectbox("Sabor", sabores)
else:
    sabor = None

# Botón para agregar al pedido
if st.button("Agregar al pedido"):
    if cantidad <= 0:
        st.warning("La cantidad debe ser mayor que cero")
    else:
        st.session_state.carrito.append(
            {
                "producto_id": producto_id,
                "producto": producto_nombre,
                "cantidad": cantidad,
                "unidad": unidad,
                "sabor": sabor if sabor else "",
            }
        )
        st.success(f"Producto '{producto_nombre}' agregado.")

# Editar carrito
if st.session_state.carrito:
    st.subheader("Editar productos en el carrito")
    eliminar_indices = []
    for i, item in enumerate(st.session_state.carrito):
        cols = st.columns([4, 2, 2, 3, 2])
        cols[0].write(item["producto"])
        nueva_cantidad = cols[1].number_input(
            f"Cantidad {i}", value=item["cantidad"], step=1.0, key=f"cant_{i}"
        )

        nombre_raiz = item["producto"].lower().split()[0]

        if nombre_raiz == "palomita":
            unidades_item = unidades_palomitas
            sabores_item = sabores_palomitas
        elif nombre_raiz == "chips":
            unidades_item = unidades_chips
            sabores_item = sabores_chips
        else:
            unidades_item = unidades_generales
            sabores_item = ["N/A"]

        unidad_idx = (
            unidades_item.index(item["unidad"])
            if item["unidad"] in unidades_item
            else 0
        )
        nueva_unidad = cols[2].selectbox(
            f"Unidad {i}", unidades_item, index=unidad_idx, key=f"uni_{i}"
        )

        if sabores_item != ["N/A"]:
            sabor_idx = (
                sabores_item.index(item["sabor"])
                if item["sabor"] in sabores_item
                else 0
            )
            nuevo_sabor = cols[3].selectbox(
                f"Sabor {i}", sabores_item, index=sabor_idx, key=f"sabor_{i}"
            )
        else:
            nuevo_sabor = ""

        if cols[4].button("Eliminar", key=f"del_{i}"):
            eliminar_indices.append(i)

        st.session_state.carrito[i]["cantidad"] = nueva_cantidad
        st.session_state.carrito[i]["unidad"] = nueva_unidad
        st.session_state.carrito[i]["sabor"] = nuevo_sabor

    # Eliminar items seleccionados
    for idx_del in sorted(eliminar_indices, reverse=True):
        st.session_state.carrito.pop(idx_del)
    if eliminar_indices:
        st.success("Producto(s) eliminado(s)")

    # Mostrar resumen del pedido
    df = pd.DataFrame(st.session_state.carrito)
    if not df.empty and all(
        col in df.columns for col in ["producto", "unidad", "cantidad"]
    ):
        resumen_pivot = df.pivot_table(
            index="producto",
            columns="unidad",
            values="cantidad",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        st.subheader("Resumen del pedido")
        st.table(resumen_pivot)
    else:
        st.info("No hay productos para mostrar en el resumen")

    # Guardar pedido
    if (
        not st.session_state.confirmacion_pendiente
        and not st.session_state.pedido_guardado
    ):
        if st.button("Guardar pedido"):
            st.session_state.confirmacion_pendiente = True
            st.rerun()

    if st.session_state.confirmacion_pendiente and not st.session_state.pedido_guardado:
        st.warning("¿Estás seguro de guardar este pedido?")
        if st.button("✅ Confirmar y guardar"):
            try:
                cur.execute(
                    "INSERT INTO pedidos (cliente_id) VALUES (%s) RETURNING id",
                    (cliente_dict[cliente_nombre],),
                )
                pedido_id = cur.fetchone()[0]

                for item in st.session_state.carrito:
                    cur.execute(
                        "INSERT INTO detalle_pedido (pedido_id, producto_id, cantidad, unidad, sabor) VALUES (%s, %s, %s, %s, %s)",
                        (
                            pedido_id,
                            item["producto_id"],
                            item["cantidad"],
                            item["unidad"],
                            item["sabor"],
                        ),
                    )
                conn.commit()

                st.success("✅ Pedido guardado correctamente.")
                st.session_state.carrito = []
                st.session_state.pedido_guardado = True
                st.session_state.confirmacion_pendiente = False
                st.rerun()

            except Exception as e:
                st.error(f"❌ Error al guardar el pedido: {e}")

else:
    st.info("Agrega productos al carrito para iniciar un pedido.")

cur.close()
conn.close()





