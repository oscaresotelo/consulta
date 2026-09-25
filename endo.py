import streamlit as st
import sqlite3
import pandas as pd
import io
from datetime import datetime, date

st.set_page_config(
    page_title="EndoAssistant - Sistema Clínico de Endocrinología",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for polished medical dashboard look
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        color: #1E3A8A;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.2rem;
    }
    .stMetric {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        padding: 10px;
        border-radius: 8px;
    }
    .stButton>button {
        border-radius: 6px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

DB_NAME = "endocrinologia.db"

def get_db_connection():
    """Establece conexión con la base de datos SQLite."""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa las tablas necesarias si no existen."""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Tabla de Pacientes
    c.execute("""
        CREATE TABLE IF NOT EXISTS pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dni TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            fecha_nacimiento DATE NOT NULL,
            sexo TEXT NOT NULL,
            historial_cardiopatia INTEGER DEFAULT 0,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabla de Consultas / Controles
    c.execute("""
        CREATE TABLE IF NOT EXISTS consultas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            peso REAL,
            talla REAL,
            imc REAL,
            tsh REAL,
            t4l REAL,
            t3 REAL,
            calcio REAL,
            albumina REAL,
            hba1c REAL,
            creatinina REAL,
            tfg REAL,
            dosis_levo_rec REAL,
            notas TEXT,
            FOREIGN KEY (paciente_id) REFERENCES pacientes (id)
        )
    """)

    # Tabla de Nódulos Tiroideos (TI-RADS)
    c.execute("""
        CREATE TABLE IF NOT EXISTS nodulos_tirads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ubicacion TEXT,
            tamano_mm REAL,
            puntaje_tirads INTEGER,
            categoria_tirads TEXT,
            recomendacion TEXT,
            FOREIGN KEY (paciente_id) REFERENCES pacientes (id)
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

def add_paciente(dni, nombre, fecha_nac, sexo, cardiopatia):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO pacientes (dni, nombre, fecha_nacimiento, sexo, historial_cardiopatia)
            VALUES (?, ?, ?, ?, ?)
        """, (dni, nombre, fecha_nac, sexo, 1 if cardiopatia else 0))
        conn.commit()
        last_id = c.lastrowid
        conn.close()
        return True, last_id
    except sqlite3.IntegrityError:
        conn.close()
        return False, "El DNI ingresado ya se encuentra registrado."

def get_todos_pacientes():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM pacientes ORDER BY nombre ASC", conn)
    conn.close()
    return df

def get_paciente_by_id(paciente_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM pacientes WHERE id = ?", (paciente_id,))
    res = c.fetchone()
    conn.close()
    return res

def add_consulta(paciente_id, peso, talla, imc, tsh, t4l, t3, calcio, albumina, hba1c, creatinina, tfg, dosis_levo, notas):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO consultas 
        (paciente_id, peso, talla, imc, tsh, t4l, t3, calcio, albumina, hba1c, creatinina, tfg, dosis_levo_rec, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (paciente_id, peso, talla, imc, tsh, t4l, t3, calcio, albumina, hba1c, creatinina, tfg, dosis_levo, notas))
    conn.commit()
    conn.close()

def add_nodulo_tirads(paciente_id, ubicacion, tamano_mm, puntaje, categoria, recomendacion):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO nodulos_tirads (paciente_id, ubicacion, tamano_mm, puntaje_tirads, categoria_tirads, recomendacion)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (paciente_id, ubicacion, tamano_mm, puntaje, categoria, recomendacion))
    conn.commit()
    conn.close()

def get_historial_consultas(paciente_id):
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT fecha, peso, talla, imc, tsh, t4l, t3, calcio, albumina, hba1c, creatinina, tfg, dosis_levo_rec as dosis_levo_mcg, notas
        FROM consultas WHERE paciente_id = ? ORDER BY fecha DESC
    """, conn, params=(paciente_id,))
    conn.close()
    return df

def get_historial_nodulos(paciente_id):
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT fecha, ubicacion, tamano_mm, puntaje_tirads, categoria_tirads, recomendacion
        FROM nodulos_tirads WHERE paciente_id = ? ORDER BY fecha DESC
    """, conn, params=(paciente_id,))
    conn.close()
    return df

def calcular_edad(fecha_nac):
    if isinstance(fecha_nac, str):
        fecha_nac = datetime.strptime(fecha_nac, "%Y-%m-%d").date()
    today = date.today()
    return today.year - fecha_nac.year - ((today.month, today.day) < (fecha_nac.month, fecha_nac.day))

def calcular_imc(peso, talla_m):
    if talla_m > 0:
        return peso / (talla_m ** 2)
    return 0.0

def calcular_dosis_levo(peso, edad, tiene_cardiopatia, meta_tsh="Estándar"):
    """
    Cálculo de sustitución de Levotiroxina según peso y factores de riesgo.
    """
    if tiene_cardiopatia or edad >= 65:
        # Inicio conservador (12.5 - 25 mcg/día)
        dosis_teorica = 25.0
        criterio = "Conservador (Adulto mayor / Riesgo cardiovascular)"
    else:
        # Dosis completa de reemplazo ~1.6 mcg/kg/día
        factor = 1.6
        if meta_tsh == "Supresión Tumoral (<0.1 mUI/L)":
            factor = 1.8 - 2.0
        elif meta_tsh == "Ajuste Leve":
            factor = 1.3
        
        dosis_teorica = peso * factor
        criterio = f"Sustitución Completa (~{factor:.1f} mcg/kg/día)"

    # Redondeo a dosis comerciales disponibles
    dosis_comerciales = [25, 50, 75, 88, 100, 112, 125, 137, 150, 175, 200]
    dosis_ajustada = min(dosis_comerciales, key=lambda x: abs(x - dosis_teorica))
    
    return dosis_teorica, dosis_ajustada, criterio

def calcular_calcio_corregido(calcio_medido, albumina):
    """Fórmula: Ca Corregido = Ca Medido + 0.8 * (4.0 - Albúmina)"""
    return calcio_medido + 0.8 * (4.0 - albumina)

def calcular_tfg_ckdepi(creatinina, edad, sexo):
    """Estimación de TFG utilizando la ecuación CKD-EPI (2021)."""
    if creatinina <= 0 or edad <= 0:
        return 0.0
    
    is_female = 1 if sexo.lower() == "femenino" else 0
    kappa = 0.7 if is_female else 0.9
    alpha = -0.241 if is_female else -0.302
    
    min_scr = min(creatinina / kappa, 1.0)
    max_scr = max(creatinina / kappa, 1.0)
    
    gender_factor = 1.012 if is_female else 1.0
    
    tfg = 142 * (min_scr ** alpha) * (max_scr ** -1.200) * (0.9938 ** edad) * gender_factor
    return tfg

if 'selected_patient_id' not in st.session_state:
    st.session_state.selected_patient_id = None

st.sidebar.title("🩺 EndoAssistant")
st.sidebar.caption("Sistema de Gestión Endocrinológica")

menu = st.sidebar.radio(
    "Navegación",
    [
        "🔍 Búsqueda y Ficha de Paciente",
        "📝 Nuevo Paciente / Nueva Consulta",
        "💊 Calculadora Endocrina",
        "🔬 Evaluación TI-RADS Tiroidea",
        "📁 Importar / Exportar Datos"
    ]
)

# Patient Active Context Box in Sidebar
if st.session_state.selected_patient_id:
    p_act = get_paciente_by_id(st.session_state.selected_patient_id)
    if p_act:
        edad_act = calcular_edad(p_act['fecha_nacimiento'])
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**👤 Paciente Seleccionado:**")
        st.sidebar.markdown(f"**{p_act['nombre']}**")
        st.sidebar.markdown(f"• **DNI:** {p_act['dni']}")
        st.sidebar.markdown(f"• **Edad:** {edad_act} años | **Sexo:** {p_act['sexo']}")
        if st.sidebar.button("Cambiar / Desseleccionar", use_container_width=True):
            st.session_state.selected_patient_id = None
            st.rerun()

if menu == "🔍 Búsqueda y Ficha de Paciente":
    st.markdown('<div class="main-header">Búsqueda y Ficha Clínica del Paciente</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Consulte la historia clínica, controles anteriores y evolución de nódulos.</div>', unsafe_allow_html=True)

    df_pacientes = get_todos_pacientes()
    
    if df_pacientes.empty:
        st.info("No hay pacientes registrados en el sistema. Vaya a 'Nuevo Paciente / Nueva Consulta' para comenzar.")
    else:
        search_query = st.text_input("🔎 Buscar por DNI o Nombre:", "")
        
        if search_query:
            df_filtered = df_pacientes[
                df_pacientes['nombre'].str.contains(search_query, case=False) |
                df_pacientes['dni'].str.contains(search_query, case=False)
            ]
        else:
            df_filtered = df_pacientes

        st.dataframe(df_filtered[['dni', 'nombre', 'fecha_nacimiento', 'sexo']], use_container_width=True)

        patient_options = {row['id']: f"{row['nombre']} (DNI: {row['dni']})" for _, row in df_filtered.iterrows()}
        
        if patient_options:
            selected_id = st.selectbox(
                "Seleccionar paciente para ver ficha completa:",
                options=list(patient_options.keys()),
                format_func=lambda x: patient_options[x]
            )
            
            if st.button("Abrir Ficha Clínica"):
                st.session_state.selected_patient_id = selected_id
                st.rerun()

    # If a patient is selected, display complete clinical record
    if st.session_state.selected_patient_id:
        st.markdown("---")
        p_act = get_paciente_by_id(st.session_state.selected_patient_id)
        edad = calcular_edad(p_act['fecha_nacimiento'])
        
        st.subheader(f"📋 Ficha Clínica: {p_act['nombre']}")
        
        col_inf1, col_inf2, col_inf3, col_inf4 = st.columns(4)
        col_inf1.metric("DNI", p_act['dni'])
        col_inf2.metric("Edad", f"{edad} años")
        col_inf3.metric("Sexo Biológico", p_act['sexo'])
        col_inf4.metric("Riesgo Cardiovascular", "Sí" if p_act['historial_cardiopatia'] else "No")

        tab_consultas, tab_nodulos = st.tabs(["📊 Historial de Consultas y Laboratorios", "🔬 Historial Ecográfico (TI-RADS)"])
        
        with tab_consultas:
            df_c = get_historial_consultas(p_act['id'])
            if not df_c.empty:
                st.dataframe(df_c, use_container_width=True)
            else:
                st.info("El paciente aún no registra consultas guardadas.")

        with tab_nodulos:
            df_n = get_historial_nodulos(p_act['id'])
            if not df_n.empty:
                st.dataframe(df_n, use_container_width=True)
            else:
                st.info("El paciente no registra evaluaciones de nódulos tiroideos.")

elif menu == "📝 Nuevo Paciente / Nueva Consulta":
    st.markdown('<div class="main-header">Registro Clínico</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Dé de alta un nuevo paciente o agregue un control de laboratorio a un paciente existente.</div>', unsafe_allow_html=True)

    tab_nuevo_p, tab_nueva_c = st.tabs(["👤 Alta de Nuevo Paciente", "🩺 Registrar Nueva Consulta / Control"])

    with tab_nuevo_p:
        with st.form("form_nuevo_paciente", clear_on_submit=True):
            st.subheader("Datos Demográficos")
            col1, col2 = st.columns(2)
            with col1:
                dni = st.text_input("DNI / Documento Identificador *")
                nombre = st.text_input("Nombre Completo *")
                fecha_nac = st.date_input("Fecha de Nacimiento *", value=date(1985, 1, 1), min_value=date(1920, 1, 1))
            with col2:
                sexo = st.selectbox("Sexo Biológico *", ["Femenino", "Masculino"])
                cardiopatia = st.checkbox("Antecedente de Cardiopatía Isquémica / Arritmias / >65 años")

            btn_save_p = st.form_submit_button("Guardar Paciente")
            
            if btn_save_p:
                if not dni or not nombre:
                    st.error("Por favor complete los campos obligatorios (*).")
                else:
                    success, res = add_paciente(dni, nombre, fecha_nac.strftime("%Y-%m-%d"), sexo, cardiopatia)
                    if success:
                        st.success(f"Paciente {nombre} creado correctamente.")
                        st.session_state.selected_patient_id = res
                        st.rerun()
                    else:
                        st.error(res)

    with tab_nueva_c:
        if not st.session_state.selected_patient_id:
            st.warning("⚠️ Primero debe seleccionar o registrar un paciente para agregar una consulta.")
        else:
            p_act = get_paciente_by_id(st.session_state.selected_patient_id)
            st.info(f"Registrando consulta para: **{p_act['nombre']}** (DNI: {p_act['dni']})")

            with st.form("form_nueva_consulta", clear_on_submit=True):
                st.subheader("1. Antropometría")
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    peso = st.number_input("Peso (kg)", min_value=0.0, value=70.0, step=0.1)
                with col_a2:
                    talla = st.number_input("Talla (m)", min_value=0.0, value=1.65, step=0.01)

                st.subheader("2. Perfil Tiroideo y Calcio")
                col_b1, col_b2, col_b3, col_b4 = st.columns(4)
                with col_b1:
                    tsh = st.number_input("TSH (mUI/L)", min_value=0.0, value=2.5, step=0.1)
                with col_b2:
                    t4l = st.number_input("T4 Libre (ng/dL)", min_value=0.0, value=1.2, step=0.05)
                with col_b3:
                    t3 = st.number_input("T3 Total (ng/dL)", min_value=0.0, value=100.0, step=1.0)
                with col_b4:
                    calcio = st.number_input("Calcio Sérico (mg/dL)", min_value=0.0, value=9.2, step=0.1)

                st.subheader("3. Función Renal y Metabolismo")
                col_c1, col_c2, col_c3 = st.columns(3)
                with col_c1:
                    albumina = st.number_input("Albúmina (g/dL)", min_value=0.0, value=4.0, step=0.1)
                with col_c2:
                    hba1c = st.number_input("HbA1c (%)", min_value=0.0, value=5.6, step=0.1)
                with col_c3:
                    creatinina = st.number_input("Creatinina (mg/dL)", min_value=0.0, value=0.9, step=0.05)

                dosis_levo = st.number_input("Dosis Levotiroxina Actual/Prescripta (mcg/día)", min_value=0.0, value=0.0, step=12.5)
                notas = st.text_area("Observaciones Clínicas / Indicaciones", "")

                btn_save_c = st.form_submit_button("Guardar Consulta")

                if btn_save_c:
                    imc_calc = calcular_imc(peso, talla)
                    edad_p = calcular_edad(p_act['fecha_nacimiento'])
                    tfg_calc = calcular_tfg_ckdepi(creatinina, edad_p, p_act['sexo'])
                    
                    add_consulta(
                        p_act['id'], peso, talla, imc_calc, tsh, t4l, t3, 
                        calcio, albumina, hba1c, creatinina, tfg_calc, dosis_levo, notas
                    )
                    st.success("Consulta guardada exitosamente en el historial del paciente.")

elif menu == "💊 Calculadora Endocrina":
    st.markdown('<div class="main-header">Calculadoras Clínico-Endocrinas</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Herramientas de ajuste de Levotiroxina, corrección de Calcio y estimación de TFG.</div>', unsafe_allow_html=True)

    # Defaults
    peso_c = 70.0
    edad_c = 45
    sexo_c = "Femenino"
    cardio_c = False

    if st.session_state.selected_patient_id:
        p_act = get_paciente_by_id(st.session_state.selected_patient_id)
        edad_c = calcular_edad(p_act['fecha_nacimiento'])
        sexo_c = p_act['sexo']
        cardio_c = bool(p_act['historial_cardiopatia'])
        st.info(f"Cargando parámetros para: **{p_act['nombre']}** | Edad: {edad_c} años | Sexo: {sexo_c}")

    col_calc1, col_calc2 = st.columns(2)

    with col_calc1:
        st.subheader("1. Ajuste de Dosis de Levotiroxina")
        peso_input = st.number_input("Peso Corporal del Paciente (kg)", min_value=10.0, value=peso_c, step=0.5)
        edad_input = st.number_input("Edad del Paciente", min_value=1, value=edad_c)
        meta_tsh = st.selectbox("Meta TSH", ["Estándar (0.4 - 4.0 mUI/L)", "Supresión Tumoral (<0.1 mUI/L)", "Ajuste Leve"])
        cardio_input = st.checkbox("Riesgo Cardiovascular o Adulto Mayor (>65 años)", value=cardio_c)

        teorica, comercial, criterio = calcular_dosis_levo(peso_input, edad_input, cardio_input, meta_tsh)

        st.markdown("---")
        st.write(f"**Criterio Clínico:** {criterio}")
        st.write(f"**Dosis exacta teórica:** `{teorica:.1f} mcg/día`")
        st.metric("Dosis Comercial Recomendada", f"{comercial} mcg/día")

    with col_calc2:
        st.subheader("2. Calcio Corregido por Albúmina")
        ca_med = st.number_input("Calcio Total Sérico (mg/dL)", min_value=0.0, value=8.4, step=0.1)
        alb_med = st.number_input("Albúmina Sérica (g/dL)", min_value=0.0, value=3.2, step=0.1)

        ca_corr = calcular_calcio_corregido(ca_med, alb_med)
        st.metric("Calcio Corregido", f"{ca_corr:.2f} mg/dL")

        if ca_corr < 8.5:
            st.warning("⚠️ Hipocalcemia (Corregido < 8.5 mg/dL). Evaluar PTH / Vitamina D.")
        elif ca_corr > 10.5:
            st.error("🚨 Hipercalcemia (Corregido > 10.5 mg/dL). Evaluar Hiperparatiroidismo Primario.")
        else:
            st.success("✅ Calcio corregido en rango normal (8.5 - 10.5 mg/dL).")

        st.markdown("---")
        st.subheader("3. Estimación de TFG (CKD-EPI 2021)")
        cr_med = st.number_input("Creatinina Sérica (mg/dL)", min_value=0.0, value=1.0, step=0.05)
        
        tfg_val = calcular_tfg_ckdepi(cr_med, edad_input, sexo_c)
        st.metric("Tasa de Filtrado Glomerular (TFG)", f"{tfg_val:.1f} mL/min/1.73m²")

elif menu == "🔬 Evaluación TI-RADS Tiroidea":
    st.markdown('<div class="main-header">Estratificación TI-RADS Tiroidea (ACR)</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Evaluación de riesgo e indicación de BAPAF (Punción-Aspiración con Aguja Fina) según el American College of Radiology.</div>', unsafe_allow_html=True)

    if st.session_state.selected_patient_id:
        p_act = get_paciente_by_id(st.session_state.selected_patient_id)
        st.info(f"Evaluando nódulo para: **{p_act['nombre']}** (DNI: {p_act['dni']})")

    col_t1, col_t2 = st.columns([1, 1])

    with col_t1:
        st.subheader("Criterios Ultrasonográficos")
        
        ubicacion = st.text_input("Ubicación del Nódulo (ej. Lóbulo Derecho, Istmo)", "Lóbulo Derecho")
        tamano_mm = st.number_input("Tamaño Máximo del Nódulo (en mm)", min_value=1.0, value=12.0, step=1.0)

        # 1. Composición
        comp = st.radio("1. Composición", [
            ("Quístico / Casi completamente quístico", 0),
            ("Espongiforme", 0),
            ("Mixto quístico y sólido", 1),
            ("Sólido / Casi completamente sólido", 2)
        ], format_func=lambda x: f"{x[0]} (+{x[1]} pts)")

        # 2. Ecogenicidad
        eco = st.radio("2. Ecogenicidad", [
            ("Anecogénico", 0),
            ("Hiperecogénico o Isoecogénico", 1),
            ("Hipoecogénico", 2),
            ("Muy hipoecogénico", 3)
        ], format_func=lambda x: f"{x[0]} (+{x[1]} pts)")

        # 3. Forma
        forma = st.radio("3. Forma", [
            ("Más ancho que alto", 0),
            ("Más alto que ancho", 3)
        ], format_func=lambda x: f"{x[0]} (+{x[1]} pts)")

        # 4. Márgenes
        margen = st.radio("4. Márgenes", [
            ("Liso", 0),
            ("Indefinido", 0),
            ("Lobulado e irregular", 2),
            ("Extensión extratiroidea", 3)
        ], format_func=lambda x: f"{x[0]} (+{x[1]} pts)")

        # 5. Focos Ecogénicos
        st.write("5. Focos Ecogénicos")
        f_ninguno = st.checkbox("Ninguno / Cola de cometa (+0 pts)", value=True)
        f_macro = st.checkbox("Macrocalcificaciones (+1 pt)")
        f_periferico = st.checkbox("Calcificaciones periféricas en cáscara (+2 pts)")
        f_punteado = st.checkbox("Focos ecogénicos punteados / Microcalcificaciones (+3 pts)")

    with col_t2:
        st.subheader("Resultado de la Clasificación")

        # Total points calculation
        puntos = comp[1] + eco[1] + forma[1] + margen[1]
        if not f_ninguno:
            if f_macro: puntos += 1
            if f_periferico: puntos += 2
            if f_punteado: puntos += 3

        st.metric("Puntaje Total ACR TI-RADS", f"{puntos} Puntos")

        # Categorization logic
        if puntos == 0:
            cat = "TR1 - Benigno"
            riesgo = "< 2%"
            rec = "No requiere PAA (Biopsia)."
        elif puntos == 2:
            cat = "TR2 - No Sospechoso"
            riesgo = "< 2%"
            rec = "No requiere PAA."
        elif puntos == 3:
            cat = "TR3 - Levemente Sospechoso"
            riesgo = "~ 5%"
            if tamano_mm >= 25:
                rec = "⚠️ Indicar PAA (Nódulo ≥ 25 mm)."
            elif tamano_mm >= 15:
                rec = "🔄 Seguimiento ecográfico recomendado (Nódulo ≥ 15 mm)."
            else:
                rec = "✅ Sin indicación de PAA o seguimiento inmediato (<15 mm)."
        elif 4 <= puntos <= 6:
            cat = "TR4 - Moderadamente Sospechoso"
            riesgo = "5% - 20%"
            if tamano_mm >= 15:
                rec = "🚨 Indicar PAA (Nódulo ≥ 15 mm)."
            elif tamano_mm >= 10:
                rec = "🔄 Seguimiento ecográfico recomendado (Nódulo ≥ 10 mm)."
            else:
                rec = "✅ Sin indicación de PAA o seguimiento inmediato (<10 mm)."
        else:
            cat = "TR5 - Altamente Sospechoso"
            riesgo = "> 20%"
            if tamano_mm >= 10:
                rec = "🚨 Indicar PAA (Nódulo ≥ 10 mm)."
            elif tamano_mm >= 5:
                rec = "🔄 Seguimiento ecográfico recomendado (Nódulo ≥ 5 mm)."
            else:
                rec = "✅ Control ecográfico periódico (<5 mm)."

        st.markdown(f"### Categoria: **{cat}**")
        st.write(f"**Riesgo de malignidad:** {riesgo}")
        st.info(f"**Indicación Clínica:** {rec}")

        if st.session_state.selected_patient_id:
            if st.button("💾 Guardar Evaluación TI-RADS en la Ficha del Paciente"):
                add_nodulo_tirads(
                    st.session_state.selected_patient_id,
                    ubicacion,
                    tamano_mm,
                    puntos,
                    cat,
                    rec
                )
                st.success("Evaluación de nódulo tiroideo guardada en el historial.")

elif menu == "📁 Importar / Exportar Datos":
    st.markdown('<div class="main-header">Gestión de Datos</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Carga masiva de pacientes desde planillas Excel/CSV o exportación completa de la base de datos.</div>', unsafe_allow_html=True)

    tab_imp, tab_exp = st.tabs(["📥 Importación Masiva (CSV / Excel)", "📤 Exportar Base de Datos"])

    with tab_imp:
        file_up = st.file_uploader("Seleccione un archivo CSV o Excel", type=["csv", "xlsx"])
        if file_up:
            try:
                if file_up.name.endswith(".csv"):
                    df_imp = pd.read_csv(file_up)
                else:
                    df_imp = pd.read_excel(file_up)

                st.write("Vista previa del archivo:")
                st.dataframe(df_imp.head())

                req_cols = ["dni", "nombre", "fecha_nacimiento", "sexo"]
                missing = [c for c in req_cols if c not in df_imp.columns]

                if missing:
                    st.error(f"Faltan columnas requeridas en el archivo: {missing}")
                else:
                    if st.button("Confirmar e Importar Pacientes"):
                        conn = get_db_connection()
                        c = conn.cursor()
                        exitos = 0
                        fallos = 0

                        for _, r in df_imp.iterrows():
                            try:
                                c.execute("""
                                    INSERT INTO pacientes (dni, nombre, fecha_nacimiento, sexo)
                                    VALUES (?, ?, ?, ?)
                                """, (str(r['dni']), str(r['nombre']), str(r['fecha_nacimiento']), str(r['sexo'])))
                                exitos += 1
                            except Exception:
                                fallos += 1

                        conn.commit()
                        conn.close()
                        st.success(f"Proceso finalizado. {exitos} pacientes importados con éxito. ({fallos} omitidos por DNI duplicado).")

            except Exception as e:
                st.error(f"Error al leer el archivo: {e}")

    with tab_exp:
        st.subheader("Exportar Tablas a Excel")
        conn = get_db_connection()
        
        df_p = pd.read_sql_query("SELECT * FROM pacientes", conn)
        df_c = pd.read_sql_query("SELECT * FROM consultas", conn)
        df_n = pd.read_sql_query("SELECT * FROM nodulos_tirads", conn)
        conn.close()

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_p.to_excel(writer, sheet_name='Pacientes', index=False)
            df_c.to_excel(writer, sheet_name='Consultas', index=False)
            df_n.to_excel(writer, sheet_name='Nodulos_TIRADS', index=False)

        st.download_button(
            label="💾 Descargar Base de Datos Completa (Excel)",
            data=buffer.getvalue(),
            file_name=f"Base_Datos_Endocrinologia_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )