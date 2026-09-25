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
    page_title="EndoSuite Pro - CDSS Endocrinología",
    layout="wide",
    page_icon="🩺",
)

# Inicializar Base de Datos SQLite
db.init_db()

# --- ESTADO DE SESIÓN (Paciente Activo) ---
if "paciente_activo" not in st.session_state:
    st.session_state.paciente_activo = None

st.sidebar.title("🩺 EndoSuite Pro v2.0")

# --- BARRA LATERAL: Gestión y Selección de Paciente ---
st.sidebar.header("Paciente Activo")
lista_pacientes = db.obtener_pacientes()

if lista_pacientes:
    opciones_pacientes = {
        f"{p[1]} (DNI: {p[0]})": {
            "dni": p[0],
            "nombre": p[1],
            "nac": p[2],
            "sexo": p[3],
        }
        for p in lista_pacientes
    }
    seleccion = st.sidebar.selectbox(
        "Buscar / Seleccionar Paciente",
        ["-- Ninguno --"] + list(opciones_pacientes.keys()),
    )

    if seleccion != "-- Ninguno --":
        st.session_state.paciente_activo = opciones_pacientes[seleccion]
    else:
        st.session_state.paciente_activo = None
else:
    st.sidebar.info("No hay pacientes registrados.")

with st.sidebar.expander("➕ Dar de alta nuevo paciente"):
    with st.form("form_nuevo_paciente", clear_on_submit=True):
        nuevo_dni = st.text_input("DNI / Identificador")
        nuevo_nombre = st.text_input("Nombre Completo")
        nueva_fecha = st.date_input(
            "Fecha Nacimiento", min_value=datetime.date(1920, 1, 1)
        )
        nuevo_sexo = st.selectbox("Sexo", ["Femenino", "Masculino"])

        if st.form_submit_button("Guardar Paciente"):
            if nuevo_dni and nuevo_nombre:
                if db.guardar_paciente(
                    nuevo_dni, nuevo_nombre, str(nueva_fecha), nuevo_sexo
                ):
                    st.success("Paciente guardado correctamente.")
                    st.rerun()
                else:
                    st.error("El DNI ya se encuentra registrado.")
            else:
                st.warning("DNI y Nombre son obligatorios.")

# Display visual del Paciente Activo
st.markdown("---")
if st.session_state.paciente_activo:
    p = st.session_state.paciente_activo
    st.info(
        f"👤 **Paciente Activo:** {p['nombre']} | **DNI:** {p['dni']} | **Sexo:** {p['sexo']} | **F. Nacimiento:** {p['nac']}"
    )
else:
    st.warning(
        "⚠️ Modo rápido sin guardar datos. Seleccioná un paciente en la barra lateral para registrar consultas en su historial."
    )

# --- NAVEGACIÓN PRINCIPAL ---
st.sidebar.markdown("---")
modulo_seleccionado = st.sidebar.radio(
    "Navegación de Módulos",
    [
        "Evolución y Registro Longitudinal",
        "Patología Tiroidea",
        "Diabetes y Riesgo Cardio-Renal",
        "Simulador AGP (Glucemia 24h)",
        "Calcio, PTH y Osteoporosis",
        "Emergencias y Pruebas Especiales",
    ],
)

# --- RENDERIZADO DE MÓDULOS ---

# 1. MÓDULO EVOLUCIÓN LONGITUDINAL
if modulo_seleccionado == "Evolución y Registro Longitudinal":
    st.header("📈 Evolución Temporal y Controles del Paciente")

    if not st.session_state.paciente_activo:
        st.info(
            "Seleccioná un paciente en el panel lateral para ver o agregar datos a su historia clínica."
        )
    else:
        dni_p = st.session_state.paciente_activo["dni"]

        # Formulario para agregar nuevo control
        with st.expander("📝 Cargar nuevo control de laboratorio"):
            with st.form("form_control", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                fecha_ctrl = c1.date_input("Fecha del Control", datetime.date.today())
                peso_ctrl = c2.number_input("Peso (kg)", min_value=20.0, max_value=250.0, value=70.0)
                altura_ctrl = c3.number_input("Altura (m)", min_value=1.0, max_value=2.30, value=1.70)

                c4, c5, c6, c7 = st.columns(4)
                hba1c_ctrl = c4.number_input("HbA1c (%)", min_value=3.0, max_value=20.0, value=7.0)
                tsh_ctrl = c5.number_input("TSH (mUI/L)", min_value=0.0, max_value=150.0, value=2.5)
                t4l_ctrl = c6.number_input("T4 Libre (ng/dL)", min_value=0.0, max_value=10.0, value=1.2)
                vfg_ctrl = c7.number_input("eGFR (mL/min)", min_value=0.0, max_value=150.0, value=90.0)

                if st.form_submit_button("Guardar Registro de Consulta"):
                    db.guardar_control(
                        dni_p,
                        str(fecha_ctrl),
                        peso_ctrl,
                        altura_ctrl,
                        hba1c_ctrl,
                        tsh_ctrl,
                        t4l_ctrl,
                        vfg_ctrl,
                    )
                    st.success("Registro añadido a la base de datos.")
                    st.rerun()

        # Mostrar gráficos dinámicos del historial
        controles = db.obtener_historial_controles(dni_p)
        if controles:
            df = pd.DataFrame(
                controles,
                columns=["Fecha", "Peso", "HbA1c", "TSH", "T4L", "eGFR"],
            )
            df["Fecha"] = pd.to_datetime(df["Fecha"])

            st.markdown("### Gráficos de Tendencia")
            col_g1, col_g2 = st.columns(2)

            with col_g1:
                fig_hba1c = px.line(
                    df,
                    x="Fecha",
                    y="HbA1c",
                    markers=True,
                    title="Evolución de Hemoglobina Glicosilada (%)",
                )
                fig_hba1c.add_hline(
                    y=7.0,
                    line_dash="dash",
                    line_color="red",
                    annotation_text="Meta Estándar ADA (7.0%)",
                )
                st.plotly_chart(fig_hba1c, use_container_width=True)

            with col_g2:
                fig_tsh = px.line(
                    df,
                    x="Fecha",
                    y="TSH",
                    markers=True,
                    title="Evolución de TSH (mUI/L)",
                )
                fig_tsh.add_hline(y=0.4, line_dash="dot", line_color="green")
                fig_tsh.add_hline(
                    y=4.5,
                    line_dash="dot",
                    line_color="green",
                    annotation_text="Rango Referencia (0.4 - 4.5)",
                )
                st.plotly_chart(fig_tsh, use_container_width=True)

            st.markdown("### Tabla de Consultas Previas")
            st.dataframe(
                df.sort_values(by="Fecha", ascending=False),
                use_container_width=True,
            )
        else:
            st.info("El paciente seleccionado aún no posee controles registrados.")

# 2. MÓDULO PATOLOGÍA TIROIDEA
elif modulo_seleccionado == "Patología Tiroidea":
    render_modulo_tiroides(st.session_state.paciente_activo)

# 3. MÓDULO DIABETES Y RIESGO CARDIO-RENAL
elif modulo_seleccionado == "Diabetes y Riesgo Cardio-Renal":
    render_modulo_diabetes(st.session_state.paciente_activo)

# 4. MÓDULO SIMULADOR AGP INTERACTIVO
elif modulo_seleccionado == "Simulador AGP (Glucemia 24h)":
    render_simulador_agp()

# 5. MÓDULO CALCIO, PTH Y OSTEOPOROSIS
elif modulo_seleccionado == "Calcio, PTH y Osteoporosis":
    render_calcio_osteoporosis()

# 6. MÓDULO EMERGENCIAS Y PRUEBAS ESPECIALES
elif modulo_seleccionado == "Emergencias y Pruebas Especiales":
    render_modulo_emergencias()