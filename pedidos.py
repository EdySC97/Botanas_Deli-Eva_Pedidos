import os
import psycopg2
import streamlit as st
import pandas as pd

os.environ["PGCLIENTENCODING"] = "latin1"

st.title("Captura de Pedido")
contra = "naIm0bybuWEMwlxG"

def conectar_db():
    return psycopg2.connect(
        host="aws-0-us-east-2.pooler.supabase.com",
        port=5432,
        database="postgres",
        user="postgres.yccoxeoxdogrpgxjitzp",  # o el usuario correcto que tengas
        password=contra,
    )


conn = conectar_db()
cur = conn.cursor()

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
    "Kg",
    "Medio",
    "Cuarto",
    "Pieza",
    "bulto 5kg",
    "bulto 10kg",
    "bulto 20kg",
    "Tubitos 1kg",
]
unidad = st.selectbox("Unidades", unidades)

if "carrito" not in st.session_state:
    st.session_state.carrito = []

if st.button("Agregar al pedido"):
    if cantidad <= 0:
        st.warning("La cantidad debe ser mayor que cero")
    else:
        producto_idx = producto_opciones.index(producto_seleccionado)
        producto_id = productos[producto_idx][0]
        producto_nombre = productos[producto_idx][1]
        st.session_state.carrito.append(
            {
                "producto_id": producto_id,
                "producto": producto_nombre,
                "cantidad": cantidad,
                "unidad": unidad,
            }
        )

st.subheader("Editar productos en el carrito")

if st.session_state.carrito:
    cols = st.columns([4, 2, 2, 2])
    cols[0].write("Producto")
    cols[1].write("Cantidad")
    cols[2].write("Unidad")
    cols[3].write("Eliminar")

    eliminar_indices = []
    for i, item in enumerate(st.session_state.carrito):
        cols = st.columns([4, 2, 2, 2])
        cols[0].write(item["producto"])
        nueva_cantidad = cols[1].number_input(
            f"Cantidad {i}",
            min_value=0.0,
            value=item["cantidad"],
            step=1.0,
            key=f"cant_{i}",
        )
        nueva_unidad = cols[2].selectbox(
            f"Unidad {i}",
            unidades,
            index=unidades.index(item["unidad"]),
            key=f"uni_{i}",
        )
        if cols[3].button("Eliminar", key=f"del_{i}"):
            eliminar_indices.append(i)

        st.session_state.carrito[i]["cantidad"] = nueva_cantidad
        st.session_state.carrito[i]["unidad"] = nueva_unidad

    if eliminar_indices:
        for idx in sorted(eliminar_indices, reverse=True):
            st.session_state.carrito.pop(idx)
        st.success("Producto(s) eliminado(s)")

    st.subheader("Resumen del pedido")

    # Crear DataFrame para pivotear
    df = pd.DataFrame(st.session_state.carrito)

    # Pivotear para que las unidades sean columnas y cantidades los valores
    resumen_pivot = df.pivot_table(
        index="producto",
        columns="unidad",
        values="cantidad",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()

    st.table(resumen_pivot)

    if st.button("Guardar pedido"):
        cur.execute(
            "INSERT INTO pedidos (cliente_id) VALUES (%s) RETURNING id",
            (cliente_dict[cliente_nombre],),
        )
        pedido_id = cur.fetchone()[0]

        for item in st.session_state.carrito:
            cur.execute(
                "INSERT INTO detalle_pedido (pedido_id, producto_id, cantidad, unidad) VALUES (%s, %s, %s, %s)",
                (pedido_id, item["producto_id"], item["cantidad"], item["unidad"]),
            )
        conn.commit()
        st.success("Pedido guardado correctamente")
        st.session_state.carrito = []
else:
    st.info("No hay productos en el carrito")

cur.close()
conn.close()
