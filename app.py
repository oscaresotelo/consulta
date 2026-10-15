import datetime
import pandas as pd
import plotly.express as px
import streamlit as st

import database as db
from modules.diabetes import render_modulo_diabetes
from modules.emergencias import render_modulo_emergencias
from modules.interactivos import render_calcio_osteoporosis, render_simulador_agp
from modules.tiroides import render_modulo_tiroides

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Gestión Minerva - Control de Materia Prima",
    layout="wide",
    page_icon="📦",
)

# Inicializar Base de Datos SQLite (Asegurate que tu base soporte clientes y materia prima)
db.init_db()

# --- ESTADO DE SESIÓN (Cliente Activo) ---
if "cliente_activo" not in st.session_state:
    st.session_state.cliente_activo = None

st.sidebar.title("🧪 Minerva - Producción")

# --- BARRA LATERAL: Gestión y Selección de Cliente ---
st.sidebar.header("Cliente / Proveedor Activo")
lista_clientes = db.obtener_pacientes()  # Puedes renombrar la función en tu DB a obtener_clientes()

if lista_clientes:
    opciones_clientes = {
        f"{c[1]} (ID/DNI: {c[0]})": {
            "dni": c[0],
            "nombre": c[1],
            "nac": c[2],
            "sexo": c[3],
        }
        for c in lista_clientes
    }
    seleccion = st.sidebar.selectbox(
        "Buscar / Seleccionar Cliente",
        ["-- Todos los Clientes (General) --"] + list(opciones_clientes.keys()),
    )

    if seleccion != "-- Todos los Clientes (General) --":
        st.session_state.cliente_activo = opciones_clientes[seleccion]
    else:
        st.session_state.cliente_activo = None
else:
    st.sidebar.info("No hay clientes registrados.")

with st.sidebar.expander("➕ Dar de alta nuevo cliente"):
    with st.form("form_nuevo_cliente", clear_on_submit=True):
        nuevo_dni = st.text_input("Identificador / CUIT / DNI")
        nuevo_nombre = st.text_input("Razón Social / Nombre Completo")
        nueva_fecha = st.date_input(
            "Fecha de Registro", min_value=datetime.date(2020, 1, 1)
        )
        nuevo_sexo = st.selectbox("Tipo", ["Cliente Mayorista", "Cliente Minorista", "Proveedor"])

        if st.form_submit_button("Guardar Cliente"):
            if nuevo_dni and nuevo_nombre:
                if db.guardar_paciente(  # Cambiar por guardar_cliente en tu backend si corresponde
                    nuevo_dni, nuevo_nombre, str(nueva_fecha), nuevo_sexo
                ):
                    st.success("Cliente guardado correctamente.")
                    st.rerun()
                else:
                    st.error("El identificador ya se encuentra registrado.")
            else:
                st.warning("Identificador y Nombre son obligatorios.")

# Display visual del Cliente Activo o Vista General
st.markdown("---")
if st.session_state.cliente_activo:
    c = st.session_state.cliente_activo
    st.info(
        f"🏢 **Cliente Seleccionado:** {c['nombre']} | **ID:** {c['dni']} | **Tipo:** {c['sexo']} | **F. Registro:** {c['nac']}"
    )
else:
    st.warning(
        "🌐 **Vista General:** Mostrando datos y materia prima de **todos los clientes**. Seleccioná un cliente específico en la barra lateral para filtrar."
    )

# --- NAVEGACIÓN PRINCIPAL ---
st.sidebar.markdown("---")
modulo_seleccionado = st.sidebar.radio(
    "Navegación de Módulos",
    [
        "Control de Materia Prima y Lotes",
        "Patología Tiroidea",
        "Diabetes y Riesgo Cardio-Renal",
        "Simulador AGP (Glucemia 24h)",
        "Calcio, PTH y Osteoporosis",
        "Emergencias y Pruebas Especiales",
    ],
)

# --- RENDERIZADO DE MÓDULOS ---

# 1. MÓDULO MATERIA PRIMA Y CONTROL LONGITUDINAL
if modulo_seleccionado == "Control de Materia Prima y Lotes":
    st.header("📦 Control de Materia Prima por Cliente")

    # Formulario para registrar uso/ingreso de materia prima
    with st.expander("📝 Registrar Movimiento / Lote de Materia Prima"):
        with st.form("form_materia_prima", clear_on_submit=True):
            # Si hay un cliente activo, lo asignamos por defecto, sino permitimos elegir o registrar general
            c1, c2, c3 = st.columns(3)
            fecha_ctrl = c1.date_input("Fecha de Operación", datetime.date.today())
            
            # Selector de cliente dentro del formulario si no hay uno activo en la barra lateral
            if not st.session_state.cliente_activo and lista_clientes:
                nombres_clientes_form = [p[1] for p in lista_clientes]
                cliente_elegido_form = c2.selectbox("Cliente Asociado", nombres_clientes_form)
                # Buscar el DNI correspondiente
                dni_p = next(p[0] for p in lista_clientes if p[1] == cliente_elegido_form)
            elif st.session_state.cliente_activo:
                dni_p = st.session_state.cliente_activo["dni"]
                c2.info(f"Cliente: {st.session_state.cliente_activo['nombre']}")
            else:
                dni_p = "GENERAL"
                c2.info("Registro General (Sin cliente específico)")

            materia_prima = c3.selectbox(
                "Materia Prima / Insumo", 
                ["LESS (Lauril Éter Sulfato)", "CTAC 50%", "Alcohol Cetílico", "Genamin", "Ciclometicona", "Glicerina", "Otro"]
            )

            c4, c5, c6, c7 = st.columns(4)
            cantidad_ctrl = c4.number_input("Cantidad / Volumen (kg o L)", min_value=0.1, max_value=5000.0, value=10.0)
            viscosidad_ctrl = c5.number_input("Viscosidad (cP - Viscometro)", min_value=0.0, max_value=50000.0, value=2500.0)
            ph_ctrl = c6.number_input("Nivel de pH", min_value=0.0, max_value=14.0, value=6.0)
            costo_ctrl = c7.number_input("Costo Lote ($)", min_value=0.0, max_value=1000000.0, value=5000.0)

            if st.form_submit_button("Guardar Registro de Materia Prima"):
                # Adaptamos la función de guardado (puedes rutearla en tu base de datos)
                db.guardar_control(
                    dni_p,
                    str(fecha_ctrl),
                    cantidad_ctrl,
                    viscosidad_ctrl,
                    costo_ctrl, 
                    ph_ctrl,
                    0.0,
                    0.0,
                )
                st.success("Registro de materia prima guardado correctamente.")
                st.rerun()

    # Filtrado de datos según la selección de la barra lateral
    if st.session_state.cliente_activo:
        dni_p = st.session_state.cliente_activo["dni"]
        controles = db.obtener_historial_controles(dni_p)
        st.subheader(f"Historial de Materia Prima para: {st.session_state.cliente_activo['nombre']}")
    else:
        controles = []
        if lista_clientes:
            for c in lista_clientes:
                hist_cliente = db.obtener_historial_controles(c[0])
                if hist_cliente:
                    for h in hist_cliente:
                        controles.append((c[1],) + h)
        st.subheader("📊 Historial General de Materia Prima (Todos los Clientes)")

    if controles:
        if not st.session_state.cliente_activo:
            df = pd.DataFrame(
                controles,
                columns=["Cliente", "Fecha", "Cantidad", "Viscosidad", "Costo", "pH", "Extra1", "Extra2"],
            )
        else:
            df = pd.DataFrame(
                controles,
                columns=["Fecha", "Cantidad", "Viscosidad", "Costo", "pH", "Extra1", "Extra2"],
            )
        
        df["Fecha"] = pd.to_datetime(df["Fecha"])

        if not st.session_state.cliente_activo and "Cliente" in df.columns:
            clientes_unicos = df["Cliente"].unique().tolist()
            filtro_cliente = st.multiselect("Filtrar por Clientes específicos en la vista:", clientes_unicos, default=clientes_unicos)
            df = df[df["Cliente"].isin(filtro_cliente)]

        st.markdown("### Gráficos de Tendencia de Insumos")
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            if not df.empty:
                fig_cant = px.line(
                    df,
                    x="Fecha",
                    y="Cantidad",
                    color="Cliente" if "Cliente" in df.columns else None,
                    markers=True,
                    title="Volumen / Cantidad de Materia Prima Utilizada",
                )
                st.plotly_chart(fig_cant, use_container_width=True)

        with col_g2:
            if not df.empty:
                fig_visc = px.line(
                    df,
                    x="Fecha",
                    y="Viscosidad",
                    color="Cliente" if "Cliente" in df.columns else None,
                    markers=True,
                    title="Control de Viscosidad (cP) en Lotes",
                )
                st.plotly_chart(fig_visc, use_container_width=True)

        st.markdown("### Tabla Detallada de Movimientos")
        st.dataframe(
            df.sort_values(by="Fecha", ascending=False),
            use_container_width=True,
        )
    else:
        st.info("No hay registros de materia prima disponibles para mostrar.")

# 2. Resto de módulos originales
elif modulo_seleccionado == "Patología Tiroidea":
    render_modulo_tiroides(st.session_state.cliente_activo)

elif modulo_seleccionado == "Diabetes y Riesgo Cardio-Renal":
    render_modulo_diabetes(st.session_state.cliente_activo)

elif modulo_seleccionado == "Simulador AGP (Glucemia 24h)":
    render_simulador_agp()

elif modulo_seleccionado == "Calcio, PTH y Osteoporosis":
    render_calcio_osteoporosis()

elif modulo_seleccionado == "Emergencias y Pruebas Especiales":
    render_modulo_emergencias()