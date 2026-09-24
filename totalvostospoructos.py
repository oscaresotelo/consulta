import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="Minerva - Hoja de Costos Productivos & DSS",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS styling for metric cards, tabs, and headers
st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #1E293B; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1rem; color: #64748B; margin-bottom: 1.5rem; }
    .metric-card { background-color: #F8FAFC; border-radius: 10px; padding: 15px; border-left: 5px solid #3B82F6; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .alert-card-critical { background-color: #FEF2F2; border-left: 5px solid #EF4444; padding: 12px; border-radius: 8px; margin-bottom: 8px; }
    .alert-card-warning { background-color: #FFFBEB; border-left: 5px solid #F59E0B; padding: 12px; border-radius: 8px; margin-bottom: 8px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { height: 45px; border-radius: 6px 6px 0 0; padding-left: 16px; padding-right: 16px; background-color: #F1F5F9; }
    .stTabs [aria-selected="true"] { background-color: #3B82F6 !important; color: white !important; }
    .expense-card { background-color: #FFFFFF; padding: 18px; border-radius: 8px; border: 1px solid #E2E8F0; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

DB_PATH = "minerva.db"

def get_connection():
    """Establece la conexión con la base de datos SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db_schema():
    """Inicializa y actualiza la estructura de la BD para soportar DSS y MRP de forma segura."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Tabla de stock de materias primas si no existe
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_materias_primas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                materia_prima_id INTEGER UNIQUE,
                stock_actual REAL DEFAULT 0,
                stock_minimo REAL DEFAULT 0,
                punto_reorden REAL DEFAULT 0,
                FOREIGN KEY(materia_prima_id) REFERENCES materias_primas(id)
            )
        """)
        
        # Tabla de pedidos de producción pendientes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pedidos_produccion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receta_id INTEGER,
                cantidad REAL,
                fecha_pedido TEXT,
                estado TEXT DEFAULT 'pendiente',
                FOREIGN KEY(receta_id) REFERENCES recetas(id)
            )
        """)
        
        # Vistas analíticas para soporte a decisiones (BI)
        cursor.execute("""
            CREATE VIEW IF NOT EXISTS v_mrp_alertas_stock AS
            SELECT 
                mp.id AS materia_prima_id,
                mp.codigo,
                mp.nombre,
                COALESCE(s.stock_actual, 0) as stock_actual,
                COALESCE(s.stock_minimo, 0) as stock_minimo,
                COALESCE(s.punto_reorden, 0) as punto_reorden,
                CASE 
                    WHEN COALESCE(s.stock_actual, 0) <= COALESCE(s.stock_minimo, 0) THEN 'CRÍTICO'
                    WHEN COALESCE(s.stock_actual, 0) <= COALESCE(s.punto_reorden, 0) THEN 'REORDEN'
                    ELSE 'NORMAL'
                END AS estado_stock
            FROM materias_primas mp
            LEFT JOIN stock_materias_primas s ON mp.id = s.materia_prima_id
        """)
        
        conn.commit()
        conn.close()
    except Exception as e:
        st.warning(f"Aviso al verificar esquema BD: {e}")

# Iniciar esquema DSS
init_db_schema()

@st.cache_data(ttl=60)
def load_recetas():
    """Carga el listado de recetas disponibles y la información general asociada."""
    conn = get_connection()
    query = """
        SELECT 
            r.id, 
            r.nombre, 
            COALESCE(r.rendimiento_lote, 100.0) as rendimiento_lote, 
            COALESCE(r.unidad_lote, 'LITROS') as unidad_lote, 
            COALESCE(r.descripcion, '') as descripcion, 
            COALESCE(c.nombre, 'General / Sin asignación') as cliente_nombre, 
            COALESCE(c.margen_habitual, 35.0) as margen_habitual
        FROM recetas r
        LEFT JOIN clientes c ON r.cliente_id = c.id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

@st.cache_data(ttl=60)
def load_ingredientes_receta(receta_id):
    """Carga las materias primas necesarias para una receta con su última compra registrada."""
    conn = get_connection()
    query = """
    SELECT 
        ri.id as receta_ingrediente_id,
        mp.id as materia_prima_id,
        mp.codigo,
        mp.nombre as ingrediente,
        ri.cantidad as cantidad_base,
        ri.unidad,
        COALESCE(ri.porcentaje_merma, 0.0) as porcentaje_merma,
        mp.costo_referencia,
        (SELECT cmp.precio_unitario 
         FROM compras_materia_prima cmp 
         WHERE cmp.materia_prima_id = mp.id 
         ORDER BY cmp.fecha DESC, cmp.id DESC LIMIT 1) as costo_ultima_compra,
        (SELECT UPPER(COALESCE(cmp.moneda, 'USD'))
         FROM compras_materia_prima cmp 
         WHERE cmp.materia_prima_id = mp.id 
         ORDER BY cmp.fecha DESC, cmp.id DESC LIMIT 1) as moneda_ultima_compra,
        (SELECT cmp.costo_flete 
         FROM compras_materia_prima cmp 
         WHERE cmp.materia_prima_id = mp.id 
         ORDER BY cmp.fecha DESC, cmp.id DESC LIMIT 1) as flete_ultima_compra,
        (SELECT cmp.cantidad 
         FROM compras_materia_prima cmp 
         WHERE cmp.materia_prima_id = mp.id 
         ORDER BY cmp.fecha DESC, cmp.id DESC LIMIT 1) as cantidad_ultima_compra,
        (SELECT cmp.fecha 
         FROM compras_materia_prima cmp 
         WHERE cmp.materia_prima_id = mp.id 
         ORDER BY cmp.fecha DESC, cmp.id DESC LIMIT 1) as fecha_ultima_compra
    FROM receta_ingredientes ri
    JOIN materias_primas mp ON ri.materia_prima_id = mp.id
    WHERE ri.receta_id = ?
    """
    df = pd.read_sql_query(query, conn, params=(receta_id,))
    conn.close()
    return df

@st.cache_data(ttl=60)
def load_packaging_receta(receta_id):
    """Carga los envases asociados a una receta a través de la relación en la tabla productos."""
    conn = get_connection()
    query = """
    SELECT 
        p.id as producto_id,
        p.nombre as producto_nombre,
        e.id as packaging_id,
        e.descripcion as insumo,
        e.unidad,
        COALESCE(e.capacidad_litros, 1.0) as capacidad_litros,
        (SELECT ee.precio_unitario 
         FROM entradas_envases ee 
         WHERE ee.envase_id = e.id 
         ORDER BY ee.fecha_ingreso DESC, ee.id DESC LIMIT 1) as costo_ultima_compra_usd,
        (SELECT ee.costo_flete 
         FROM entradas_envases ee 
         WHERE ee.envase_id = e.id 
         ORDER BY ee.fecha_ingreso DESC, ee.id DESC LIMIT 1) as flete_ultima_compra,
        (SELECT ee.cantidad_ingresada 
         FROM entradas_envases ee 
         WHERE ee.envase_id = e.id 
         ORDER BY ee.fecha_ingreso DESC, ee.id DESC LIMIT 1) as cantidad_ultima_compra,
        (SELECT ee.fecha_ingreso 
         FROM entradas_envases ee 
         WHERE ee.envase_id = e.id 
         ORDER BY ee.fecha_ingreso DESC, ee.id DESC LIMIT 1) as fecha_ultima_compra
    FROM productos p
    JOIN envases e ON p.envase_id = e.id
    WHERE p.id_receta = ? AND p.activo = 1
    """
    df = pd.read_sql_query(query, conn, params=(receta_id,))
    conn.close()
    return df

@st.cache_data(ttl=60)
def load_envases_todos():
    """Carga todos los envases registrados en la base de datos con su costo más reciente."""
    conn = get_connection()
    query = """
    SELECT 
        e.id as packaging_id,
        e.descripcion as insumo,
        e.unidad,
        COALESCE(e.capacidad_litros, 1.0) as capacidad_litros,
        COALESCE((SELECT ee.precio_unitario 
         FROM entradas_envases ee 
         WHERE ee.envase_id = e.id 
         ORDER BY ee.fecha_ingreso DESC, ee.id DESC LIMIT 1), 0.0) as costo_ultima_compra_usd,
        COALESCE((SELECT ee.costo_flete 
         FROM entradas_envases ee 
         WHERE ee.envase_id = e.id 
         ORDER BY ee.fecha_ingreso DESC, ee.id DESC LIMIT 1), 0.0) as flete_ultima_compra,
        COALESCE((SELECT ee.cantidad_ingresada 
         FROM entradas_envases ee 
         WHERE ee.envase_id = e.id 
         ORDER BY ee.fecha_ingreso DESC, ee.id DESC LIMIT 1), 1.0) as cantidad_ultima_compra
    FROM envases e
    """
    try:
        df = pd.read_sql_query(query, conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

@st.cache_data(ttl=60)
def load_empleados():
    """Obtiene la nómina de empleados completa desde la base de datos."""
    conn = get_connection()
    try:
        query = """
            SELECT 
                id, 
                nombre, 
                COALESCE(puesto, 'Operario') as puesto, 
                COALESCE(sueldo_base, 0.0) as sueldo_base, 
                COALESCE(horas_jornada_diaria, 8.0) as horas_jornada_diaria, 
                COALESCE(horario_entrada, '08:00') as horario_entrada, 
                COALESCE(horario_salida, '16:00') as horario_salida, 
                COALESCE(cargas_sociales_pct, 45.0) as cargas_sociales_pct, 
                COALESCE(costo_hora, 0.0) as costo_hora 
            FROM empleados
        """
        df = pd.read_sql_query(query, conn)
    except Exception as e:
        st.warning(f"Error al cargar la tabla empleados: {e}")
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

@st.cache_data(ttl=60)
def load_gastos_mensuales():
    """Calcula la suma total mensual de gastos indirectos operativos registrados."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT SUM(importe_total) as total_gastos FROM gastos", conn)
    conn.close()
    val = df['total_gastos'].iloc[0]
    return float(val) if pd.notnull(val) else 0.0

@st.cache_data(ttl=60)
def load_detalle_gastos():
    """Carga el listado completo e individualizado de todos los gastos registrados."""
    conn = get_connection()
    query = "SELECT * FROM gastos"
    try:
        df = pd.read_sql_query(query, conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

@st.cache_data(ttl=60)
def load_alertas_mrp():
    """Consulta las alertas de reorden de materias primas desde la vista analítica BD."""
    conn = get_connection()
    try:
        query = "SELECT * FROM v_mrp_alertas_stock"
        df = pd.read_sql_query(query, conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

@st.cache_data(ttl=60)
def load_pedidos_pendientes():
    """Carga los pedidos de producción programados que están pendientes."""
    conn = get_connection()
    try:
        query = """
            SELECT pp.id, pp.receta_id, r.nombre as receta_nombre, pp.cantidad, pp.fecha_pedido, pp.estado
            FROM pedidos_produccion pp
            JOIN recetas r ON pp.receta_id = r.id
            WHERE pp.estado = 'pendiente'
        """
        df = pd.read_sql_query(query, conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

def save_gastos_to_db(df_to_save):
    """Guarda los cambios de la tabla de gastos directamente en la base de datos SQLite."""
    try:
        conn = get_connection()
        df_to_save.to_sql('gastos', conn, if_exists='replace', index=False)
        conn.close()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error al guardar los datos en la base de datos: {e}")
        return False

st.markdown("<div class='main-header'>🧪 Hoja de Costos Productivos & Decisiones DSS</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>Cálculo de Costos, Sistema MRP, Análisis What-If y Gestor Operativo (ARS / USD)</div>", unsafe_allow_html=True)

df_recetas = load_recetas()

if df_recetas.empty:
    st.warning("No hay recetas registradas en la base de datos.")
    st.stop()

with st.sidebar:
    st.header("⚙️ Parámetros Generales")
    
    receta_id_sel = st.selectbox(
        "Seleccionar Receta:",
        options=df_recetas['id'].tolist(),
        format_func=lambda x: f"[{x}] {df_recetas[df_recetas['id'] == x]['nombre'].values[0]}"
    )
    
    receta_info = df_recetas[df_recetas['id'] == receta_id_sel].iloc[0]
    
    lote_rendimiento_base = float(receta_info['rendimiento_lote'])
    unidad_medida_lote = receta_info['unidad_lote']
    
    lote_simulado = st.number_input(
        f"Lote de Producción Simulado ({unidad_medida_lote}):",
        min_value=1.0,
        value=lote_rendimiento_base if lote_rendimiento_base > 0 else 100.0,
        step=50.0
    )
    
    factor_escalado = lote_simulado / lote_rendimiento_base if lote_rendimiento_base > 0 else 1.0
    
    st.divider()
    st.header("💱 Cotización y Ajustes")
    
    tipo_cambio_usd = st.number_input(
        "Tipo de Cambio Dólar (ARS / USD):",
        min_value=1.0,
        value=1250.0,
        step=10.0,
        help="Permite convertir las Materias Primas cotizadas en Dólares (USD) a Pesos (ARS)."
    )
    
    fuente_costo_mp = st.radio(
        "Fuente de Costo Base MP:",
        options=["Última Compra", "Costo Referencia BD"],
        index=0
    )
    
    aplicar_mermas_en_costo = st.checkbox("Incluir % de merma en el cálculo de costo", value=False)
    
    margen_objetivo = st.number_input(
        "Margen Bruto Objetivo (%):",
        min_value=0.0,
        max_value=300.0,
        value=float(receta_info['margen_habitual'] or 35.0),
        step=2.5
    )

tab_mp, tab_pkg, tab_mod, tab_gif, tab_resumen, tab_mrp, tab_simulacion = st.tabs([
    "🧪 1. Materias Primas (USD)", 
    "📦 2. Packaging (ARS)", 
    "👷 3. Mano de Obra (ARS)", 
    "🏭 4. Gastos Indirectos y Detalle (ARS)", 
    "📊 5. Resumen & Costo por Litro",
    "🎯 6. Alertas MRP & Insumos",
    "🔮 7. Simulador What-If & Sensibilidad"
])

with tab_mp:
    st.subheader("Costeo de Materias Primas (Calculado en USD)")
    df_mp = load_ingredientes_receta(receta_id_sel)
    
    if not df_mp.empty:
        costos_unitarios_usd = []
        
        for idx, row in df_mp.iterrows():
            if fuente_costo_mp == "Costo Referencia BD" or pd.isnull(row['costo_ultima_compra']):
                costos_unitarios_usd.append(float(row['costo_referencia'] or 0.0))
            else:
                precio_u = float(row['costo_ultima_compra'])
                moneda = str(row['moneda_ultima_compra']).upper()
                cant_c = float(row['cantidad_ultima_compra']) if pd.notnull(row['cantidad_ultima_compra']) and float(row['cantidad_ultima_compra']) > 0 else 1.0
                flete = float(row['flete_ultima_compra']) if pd.notnull(row['flete_ultima_compra']) else 0.0
                
                flete_u = flete / cant_c
                
                if moneda == 'ARS':
                    costo_total_ars = precio_u + flete_u
                    costos_unitarios_usd.append(costo_total_ars / tipo_cambio_usd if tipo_cambio_usd > 0 else costo_total_ars)
                else:
                    costos_unitarios_usd.append(precio_u + flete_u)
                    
        df_mp['costo_unitario_usd'] = costos_unitarios_usd
        df_mp['cantidad_lote'] = df_mp['cantidad_base'] * factor_escalado
        
        if aplicar_mermas_en_costo:
            df_mp['cantidad_costeo'] = df_mp['cantidad_lote'] * (1.0 + (df_mp['porcentaje_merma'] / 100.0))
        else:
            df_mp['cantidad_costeo'] = df_mp['cantidad_lote']
            
        df_mp['subtotal_usd'] = df_mp['cantidad_costeo'] * df_mp['costo_unitario_usd']
        df_mp['subtotal_ars'] = df_mp['subtotal_usd'] * tipo_cambio_usd

        st.dataframe(
            df_mp[['codigo', 'ingrediente', 'cantidad_lote', 'unidad', 'costo_unitario_usd', 'subtotal_usd', 'subtotal_ars']],
            column_config={
                "codigo": "Código",
                "ingrediente": "Materia Prima",
                "cantidad_lote": st.column_config.NumberColumn("Cant. Lote", format="%.3f"),
                "unidad": "Unidad",
                "costo_unitario_usd": st.column_config.NumberColumn("Precio U. (USD)", format="$%.4f"),
                "subtotal_usd": st.column_config.NumberColumn("Subtotal (USD)", format="$%.2f"),
                "subtotal_ars": st.column_config.NumberColumn("Subtotal (ARS)", format="$%.2f")
            },
            hide_index=True,
            use_container_width=True
        )

        litros_totales_receta = df_mp['cantidad_lote'].sum()
        total_costo_mp_usd = df_mp['subtotal_usd'].sum()
        total_costo_mp_ars = total_costo_mp_usd * tipo_cambio_usd
        
        costo_mp_por_litro_usd = total_costo_mp_usd / litros_totales_receta if litros_totales_receta > 0 else 0.0
        costo_mp_por_litro_ars = total_costo_mp_ars / litros_totales_receta if litros_totales_receta > 0 else 0.0

        m1, m2, m3 = st.columns(3)
        m1.metric("Volumen Real Receta", f"{litros_totales_receta:,.2f} Litros")
        m2.metric("Total MP (USD)", f"USD ${total_costo_mp_usd:,.2f}")
        m3.metric("Costo MP por Litro", f"${costo_mp_por_litro_ars:,.2f} ARS", delta=f"USD ${costo_mp_por_litro_usd:,.4f}")
    else:
        st.info("No hay ingredientes registrados para esta receta.")
        litros_totales_receta = lote_simulado
        total_costo_mp_usd = 0.0
        total_costo_mp_ars = 0.0
        costo_mp_por_litro_usd = 0.0
        costo_mp_por_litro_ars = 0.0

with tab_pkg:
    st.subheader("📦 Costeo Detallado de Packing y Packaging por Envase (ARS / USD)")
    
    df_envases_todos = load_envases_todos()
    df_pkg_receta = load_packaging_receta(receta_id_sel)
    
    default_envases_ids = df_pkg_receta['packaging_id'].unique().tolist() if not df_pkg_receta.empty else []
    
    st.markdown("#### 🎯 Selección de Envases e Insumos Principales")
    
    total_costo_pkg_base_ars = 0.0
    total_costo_pkg_base_usd = 0.0

    if not df_envases_todos.empty:
        opciones_envases = df_envases_todos['packaging_id'].tolist()
        envases_seleccionados = st.multiselect(
            "Seleccionar Envase(s) a incluir en la producción:",
            options=opciones_envases,
            default=default_envases_ids,
            format_func=lambda x: f"[{x}] {df_envases_todos[df_envases_todos['packaging_id'] == x]['insumo'].values[0]} (Capacidad: {df_envases_todos[df_envases_todos['packaging_id'] == x]['capacidad_litros'].values[0]} L)"
        )
        
        if envases_seleccionados:
            df_pkg = df_envases_todos[df_envases_todos['packaging_id'].isin(envases_seleccionados)].copy()
            
            # Asignar/Editar la capacidad de caja por envase (por ejemplo 6, 12, 60 unidades por caja)
            st.markdown("##### 📦 Configuración de Capacidad por Caja según Envase")
            st.caption("Especifique cuántas unidades de cada envase contiene una caja de embalaje (ej. 6, 12, 60 unidades).")
            
            unidades_por_caja_dict = {}
            col_caps = st.columns(min(len(df_pkg), 4))
            for i, (idx, row) in enumerate(df_pkg.iterrows()):
                c_col = col_caps[i % 4]
                u_caja = c_col.number_input(
                    f"U. por caja [{row['insumo']}]:",
                    min_value=1,
                    value=12 if "ampolla" not in str(row['insumo']).lower() else 60,
                    step=1,
                    key=f"u_caja_{row['packaging_id']}"
                )
                unidades_por_caja_dict[row['packaging_id']] = u_caja
                
            df_pkg['unidades_por_caja'] = df_pkg['packaging_id'].map(unidades_por_caja_dict)

            costos_pkg_usd = []
            for idx, row in df_pkg.iterrows():
                precio_u = float(row['costo_ultima_compra_usd']) if pd.notnull(row['costo_ultima_compra_usd']) else 0.0
                cant_c = float(row['cantidad_ultima_compra']) if pd.notnull(row['cantidad_ultima_compra']) and float(row['cantidad_ultima_compra']) > 0 else 1.0
                flete = float(row['flete_ultima_compra']) if pd.notnull(row['flete_ultima_compra']) else 0.0
                flete_u = flete / cant_c
                costos_pkg_usd.append(precio_u + flete_u)
                
            df_pkg['costo_unitario_usd'] = costos_pkg_usd
            df_pkg['costo_unitario_ars'] = df_pkg['costo_unitario_usd'] * tipo_cambio_usd
            
            df_pkg['unidades_lote'] = df_pkg['capacidad_litros'].apply(lambda cap: litros_totales_receta / cap if cap > 0 else 0.0)
            df_pkg['subtotal_usd'] = df_pkg['unidades_lote'] * df_pkg['costo_unitario_usd']
            df_pkg['subtotal_ars'] = df_pkg['subtotal_usd'] * tipo_cambio_usd
            df_pkg['costo_por_litro_ars'] = df_pkg['subtotal_ars'] / litros_totales_receta if litros_totales_receta > 0 else 0.0

            total_costo_pkg_base_ars = df_pkg['subtotal_ars'].sum()
            total_costo_pkg_base_usd = df_pkg['subtotal_usd'].sum()

    st.markdown("---")
    st.markdown("#### 🎗️ Costos de Embalaje, Cinta y Gastos de Packing Secundario")
    st.caption("Configure los costos unitarios de Cajas de Cartón, Cinta Adhesiva de embalar y otros insumos directos.")

    col_emb1, col_emb2, col_emb3 = st.columns(3)
    costo_caja_unitario_ars = col_emb1.number_input("Costo Unitario de Caja de Cartón (ARS):", min_value=0.0, value=850.0, step=50.0)
    costo_rollo_cinta_ars = col_emb2.number_input("Costo Rollo de Cinta de Embalar (ARS):", min_value=0.0, value=1500.0, step=100.0)
    metros_por_rollo = col_emb2.number_input("Metros por Rollo de Cinta (m):", min_value=1.0, value=50.0, step=5.0)
    metros_cinta_por_caja = col_emb3.number_input("Metros de cinta usados por caja (m):", min_value=0.1, value=1.5, step=0.1)

    costo_metro_cinta = costo_rollo_cinta_ars / metros_por_rollo if metros_por_rollo > 0 else 0.0
    costo_cinta_por_caja = costo_metro_cinta * metros_cinta_por_caja

    st.markdown("##### 📋 Insumos Secundarios Adicionales (Etiquetas, Film Stretch, Separadores)")
    default_extra_pkg = pd.DataFrame([
        {"Insumo": "Etiquetas autoadhesivas", "Costo Unitario (ARS)": 120.0, "Cantidad por Lote": 50.0, "Tipo": "Por Lote"},
        {"Insumo": "Film Stretch (kg)", "Costo Unitario (ARS)": 3200.0, "Cantidad por Lote": 0.2, "Tipo": "Por Lote"},
    ])

    edited_extra_pkg = st.data_editor(
        default_extra_pkg,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Insumo": st.column_config.TextColumn("Descripción del Insumo", help="Ej: Etiquetas, Separadores, etc."),
            "Costo Unitario (ARS)": st.column_config.NumberColumn("Costo Unitario (ARS)", format="$%.2f", min_value=0.0),
            "Cantidad por Lote": st.column_config.NumberColumn("Cantidad", format="%.2f", min_value=0.0),
            "Tipo": st.column_config.SelectboxColumn("Criterio de Cálculo", options=["Por Lote", "Por Litro"], default="Por Lote")
        },
        key="extra_pkg_editor"
    )

    total_extra_pkg_ars = 0.0
    if not edited_extra_pkg.empty:
        for idx, row in edited_extra_pkg.iterrows():
            costo_u = float(row.get("Costo Unitario (ARS)", 0.0) or 0.0)
            cant = float(row.get("Cantidad por Lote", 0.0) or 0.0)
            tipo = row.get("Tipo", "Por Lote")
            
            if tipo == "Por Litro":
                total_extra_pkg_ars += costo_u * cant * litros_totales_receta
            else:
                total_extra_pkg_ars += costo_u * cant

    costo_pkg_adicional_litro = st.number_input("Costo Adicional General Directo por Litro (ARS):", min_value=0.0, value=0.0, step=5.0)

    # 📊 ANÁLISIS DETALLADO DEL COSTO DE PACKING POR ENVASE INDIVIDUAL
    if not df_envases_todos.empty and envases_seleccionados:
        st.markdown("---")
        st.markdown("### 📊 Desglose del Costo de Packing Unitario por Envase")
        st.caption("Detalle individualizado de cuánto cuesta empaquetar 1 solo envase (Envase + Caja Prorrateada + Cinta Prorrateada + Extras).")

        df_detalle_packing_envase = []

        for idx, row in df_pkg.iterrows():
            u_caja = row['unidades_por_caja']
            costo_envase_u = row['costo_unitario_ars']
            
            # Prorrateo de Caja y Cinta por unidad de envase
            costo_caja_por_envase = costo_caja_unitario_ars / u_caja if u_caja > 0 else 0.0
            costo_cinta_por_envase = costo_cinta_por_caja / u_caja if u_caja > 0 else 0.0
            
            # Prorrateo de Insumos Extras por unidad de envase
            total_unidades_envase_lote = row['unidades_lote']
            costo_extras_por_envase = (total_extra_pkg_ars + (costo_pkg_adicional_litro * litros_totales_receta)) / total_unidades_envase_lote if total_unidades_envase_lote > 0 else 0.0
            
            costo_packing_total_unitario = costo_envase_u + costo_caja_por_envase + costo_cinta_por_envase + costo_extras_por_envase

            df_detalle_packing_envase.append({
                "Envase / Insumo": row['insumo'],
                "Capacidad (L)": row['capacidad_litros'],
                "Unid. por Caja": u_caja,
                "Costo Envase U. (ARS)": costo_envase_u,
                "Costo Caja U. (ARS)": costo_caja_por_envase,
                "Costo Cinta U. (ARS)": costo_cinta_por_envase,
                "Costo Extras U. (ARS)": costo_extras_por_envase,
                "COSTO TOTAL PACKING / ENVASE": costo_packing_total_unitario
            })

        df_packing_resumen = pd.DataFrame(df_detalle_packing_envase)

        st.dataframe(
            df_packing_resumen,
            column_config={
                "Envase / Insumo": "Envase",
                "Capacidad (L)": st.column_config.NumberColumn("Capacidad (L)", format="%.2f L"),
                "Unid. por Caja": st.column_config.NumberColumn("Unidades / Caja", format="%d u"),
                "Costo Envase U. (ARS)": st.column_config.NumberColumn("Costo Envase U.", format="$%.2f"),
                "Costo Caja U. (ARS)": st.column_config.NumberColumn("Costo Caja / Envase", format="$%.2f"),
                "Costo Cinta U. (ARS)": st.column_config.NumberColumn("Costo Cinta / Envase", format="$%.2f"),
                "Costo Extras U. (ARS)": st.column_config.NumberColumn("Costo Extras / Envase", format="$%.2f"),
                "COSTO TOTAL PACKING / ENVASE": st.column_config.NumberColumn("COSTO PACKING / ENVASE", format="$%.2f")
            },
            hide_index=True,
            use_container_width=True
        )

        # Cálculo de totales globales para la pestaña de resumen
        cajas_totales_lote = sum([row['unidades_lote'] / row['unidades_por_caja'] for idx, row in df_pkg.iterrows() if row['unidades_por_caja'] > 0])
        costo_cajas_lote_ars = cajas_totales_lote * costo_caja_unitario_ars
        costo_cinta_lote_ars = cajas_totales_lote * costo_cinta_por_caja
        
        total_costo_pkg_ars = total_costo_pkg_base_ars + costo_cajas_lote_ars + costo_cinta_lote_ars + total_extra_pkg_ars + (costo_pkg_adicional_litro * litros_totales_receta)
        total_costo_pkg_usd_final = total_costo_pkg_ars / tipo_cambio_usd if tipo_cambio_usd > 0 else 0.0
        costo_pkg_por_litro_ars = total_costo_pkg_ars / litros_totales_receta if litros_totales_receta > 0 else 0.0

    else:
        total_costo_pkg_ars = total_extra_pkg_ars + (costo_pkg_adicional_litro * litros_totales_receta)
        total_costo_pkg_usd_final = total_costo_pkg_ars / tipo_cambio_usd if tipo_cambio_usd > 0 else 0.0
        costo_pkg_por_litro_ars = total_costo_pkg_ars / litros_totales_receta if litros_totales_receta > 0 else 0.0

    st.divider()
    p1, p2, p3 = st.columns(3)
    p1.metric("Total Packaging Lote (USD)", f"USD ${total_costo_pkg_usd_final:,.2f}")
    p2.metric("Total Packaging Lote (ARS)", f"${total_costo_pkg_ars:,.2f} ARS")
    p3.metric("Costo Packaging por Litro", f"${costo_pkg_por_litro_ars:,.2f} ARS/L")

with tab_mod:
    st.subheader("👷 3. Cálculo de Mano de Obra Directa (MOD)")
    
    st.info(
        "💡 **Cálculo automático con datos de Empleados**\n\n"
        "La **Mano de Obra Directa (MOD)** se evalúa utilizando los datos registrados en la BD:\n"
        "• **Costo Hora Base:** Derivado de `sueldo_base` y `horas_jornada_diaria` (o mediante `costo_hora` directo si está especificado).\n"
        "• **Cargas Sociales:** Aplica el porcentaje de aportes (`cargas_sociales_pct`) configurado para cada operario.\n"
        "• **Costo Hora Real:** `Costo Hora Base * (1 + % Cargas Sociales / 100)`"
    )
    
    df_emp = load_empleados()
    
    mod_c1, mod_c2 = st.columns(2)
    dias_laborales_mes = mod_c1.number_input(
        "Días laborales estimados por mes:",
        min_value=1,
        max_value=31,
        value=22,
        step=1,
        help="Permite calcular el valor de la hora de trabajo si se parte del sueldo base mensual y la jornada diaria."
    )
    
    modo_calculo_mod = st.radio(
        "Seleccionar modalidad de cálculo:",
        options=["Promedio de Nómina / Estimado Simple", "Asignación de Horas por Empleado"],
        horizontal=True
    )
    
    if not df_emp.empty:
        # Calcular los costos por hora base y real para cada empleado
        costos_hora_base = []
        costos_hora_real = []
        
        for idx, row in df_emp.iterrows():
            c_hora = float(row['costo_hora'])
            s_base = float(row['sueldo_base'])
            h_diaria = float(row['horas_jornada_diaria'])
            c_soc = float(row['cargas_sociales_pct'])
            
            if c_hora > 0:
                c_base = c_hora
            elif s_base > 0 and h_diaria > 0 and dias_laborales_mes > 0:
                c_base = s_base / (h_diaria * dias_laborales_mes)
            else:
                c_base = 0.0
                
            c_real = c_base * (1.0 + (c_soc / 100.0))
            
            costos_hora_base.append(c_base)
            costos_hora_real.append(c_real)
            
        df_emp['costo_hora_base_calculado'] = costos_hora_base
        df_emp['costo_hora_real'] = costos_hora_real

    if modo_calculo_mod == "Promedio de Nómina / Estimado Simple":
        col_h1, col_h2 = st.columns(2)
        horas_totales = col_h1.number_input(
            "Horas Hombre requeridas para el lote:", 
            min_value=0.0, 
            value=8.0, 
            step=0.5,
            help="Suma total de horas dedicadas por el personal al lote completo."
        )
        
        if not df_emp.empty:
            costo_promedio_hora = float(df_emp['costo_hora_real'].mean())
            col_h2.metric("Costo Hora Promedio Real (con Cargas Soc.)", f"${costo_promedio_hora:,.2f} ARS/hs")
            
            with st.expander("📋 Ver nómina de empleados y desglose de remuneración"):
                df_show_emp = df_emp[['nombre', 'puesto', 'sueldo_base', 'horas_jornada_diaria', 'horario_entrada', 'horario_salida', 'cargas_sociales_pct', 'costo_hora_base_calculado', 'costo_hora_real']].copy()
                st.dataframe(
                    df_show_emp,
                    column_config={
                        "nombre": "Empleado",
                        "puesto": "Puesto",
                        "sueldo_base": st.column_config.NumberColumn("Sueldo Base (ARS)", format="$%.2f"),
                        "horas_jornada_diaria": st.column_config.NumberColumn("Jornada (hs/día)", format="%.1f hs"),
                        "horario_entrada": "Entrada",
                        "horario_salida": "Salida",
                        "cargas_sociales_pct": st.column_config.NumberColumn("% Cargas Soc.", format="%.1f%%"),
                        "costo_hora_base_calculado": st.column_config.NumberColumn("Costo Hora Base", format="$%.2f"),
                        "costo_hora_real": st.column_config.NumberColumn("Costo Hora Real (ARS)", format="$%.2f")
                    },
                    hide_index=True,
                    use_container_width=True
                )
        else:
            costo_promedio_hora = st.number_input("Costo Hora Estimado de MOD (ARS):", min_value=0.0, value=3500.0, step=100.0)
            col_h2.metric("Costo Hora Estimado", f"${costo_promedio_hora:,.2f} ARS/hs")

        total_costo_mod_ars = horas_totales * costo_promedio_hora

    else:
        st.markdown("#### 👥 Asignar horas dedicadas por cada empleado al lote:")
        if not df_emp.empty:
            df_emp['horas_asignadas'] = 0.0
            
            df_emp_edited = st.data_editor(
                df_emp[['id', 'nombre', 'puesto', 'horario_entrada', 'horario_salida', 'sueldo_base', 'costo_hora_real', 'horas_asignadas']],
                column_config={
                    "id": None,
                    "nombre": "Empleado",
                    "puesto": "Puesto / Rol",
                    "horario_entrada": "Entrada",
                    "horario_salida": "Salida",
                    "sueldo_base": st.column_config.NumberColumn("Sueldo Base (ARS)", format="$%.2f", disabled=True),
                    "costo_hora_real": st.column_config.NumberColumn("Costo Hora Real (ARS)", format="$%.2f", disabled=True),
                    "horas_asignadas": st.column_config.NumberColumn("Horas dedicadas al lote", min_value=0.0, format="%.1f hs", step=0.5)
                },
                hide_index=True,
                use_container_width=True,
                key="mod_empleados_editor"
            )
            
            df_emp_edited['subtotal_emp_ars'] = df_emp_edited['costo_hora_real'] * df_emp_edited['horas_asignadas']
            total_costo_mod_ars = float(df_emp_edited['subtotal_emp_ars'].sum())
            horas_totales = float(df_emp_edited['horas_asignadas'].sum())
        else:
            st.warning("No hay empleados registrados en la base de datos para asignar horas individualmente.")
            horas_totales = 8.0
            total_costo_mod_ars = 8.0 * 3500.0

    costo_mod_por_litro_ars = total_costo_mod_ars / litros_totales_receta if litros_totales_receta > 0 else 0.0
    
    st.divider()
    m_mod1, m_mod2, m_mod3 = st.columns(3)
    m_mod1.metric("Horas Hombre Totales", f"{horas_totales:.1f} hs")
    m_mod2.metric("Costo MOD Total Lote", f"${total_costo_mod_ars:,.2f} ARS")
    m_mod3.metric("Costo MOD por Litro", f"${costo_mod_por_litro_ars:,.2f} ARS/L")

with tab_gif:
    st.subheader("🏭 Gastos Indirectos de Fabricación y Visualización de Gastos")
    
    df_gastos_raw = load_detalle_gastos()
    gastos_mensuales = load_gastos_mensuales()
    
    m_g1, m_g2, m_g3, m_g4 = st.columns(4)
    
    capacidad_planta = m_g2.number_input("Capacidad Mensual Planta (L):", min_value=1.0, value=20000.0, step=1000.0)
    tasa_gif_por_litro_ars = gastos_mensuales / capacidad_planta if capacidad_planta > 0 else 0.0
    total_costo_gif_ars = tasa_gif_por_litro_ars * litros_totales_receta

    m_g1.metric("Gastos Mensuales Totales", f"${gastos_mensuales:,.2f} ARS")
    m_g3.metric("Tasa GIF por Litro", f"${tasa_gif_por_litro_ars:,.2f} ARS/L")
    m_g4.metric("Costo GIF del Lote", f"${total_costo_gif_ars:,.2f} ARS")

    st.divider()

    st.subheader("🔍 Visualizador y Detalle Completo de Gastos")
    
    if not df_gastos_raw.empty:
        col_monto = next((c for c in df_gastos_raw.columns if 'importe' in c.lower() or 'monto' in c.lower() or 'total' in c.lower()), None)
        col_cat = next((c for c in df_gastos_raw.columns if 'cat' in c.lower() or 'tipo' in c.lower() or 'rubro' in c.lower()), None)
        col_prov = next((c for c in df_gastos_raw.columns if 'prov' in c.lower() or 'vendor' in c.lower()), None)
        col_desc = next((c for c in df_gastos_raw.columns if 'concep' in c.lower() or 'desc' in c.lower() or 'detalle' in c.lower() or 'nom' in c.lower()), None)
        col_fecha = next((c for c in df_gastos_raw.columns if 'fec' in c.lower() or 'date' in c.lower()), None)

        f_col1, f_col2, f_col3 = st.columns(3)
        
        busqueda_texto = f_col1.text_input("🔎 Buscar por concepto / proveedor:", "")
        
        categorias = ["Todas"]
        if col_cat and col_cat in df_gastos_raw.columns:
            categorias += sorted(df_gastos_raw[col_cat].dropna().unique().tolist())
        cat_seleccionada = f_col2.selectbox("Filtrar por Categoría:", categorias)

        df_filtrado = df_gastos_raw.copy()
        
        if busqueda_texto:
            mask = False
            for col_search in [col_desc, col_prov, col_cat]:
                if col_search and col_search in df_filtrado.columns:
                    mask = mask | df_filtrado[col_search].astype(str).str.contains(busqueda_texto, case=False, na=False)
            df_filtrado = df_filtrado[mask]
            
        if cat_seleccionada != "Todas" and col_cat:
            df_filtrado = df_filtrado[df_filtrado[col_cat] == cat_seleccionada]

        f_col3.metric("Gastos Filtrados", f"{len(df_filtrado)} registros", delta=f"${df_filtrado[col_monto].sum():,.2f} ARS" if col_monto else "")

        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            if col_cat and col_monto and not df_filtrado.empty:
                df_cat_summary = df_filtrado.groupby(col_cat)[col_monto].sum().reset_index()
                fig_pie = px.pie(
                    df_cat_summary, 
                    names=col_cat, 
                    values=col_monto, 
                    title="Distribución de Gastos por Categoría",
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                fig_pie.update_layout(height=380)
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Sin datos categóricos suficientes para el gráfico de torta.")

        with chart_col2:
            if col_monto and not df_filtrado.empty:
                eje_x = col_desc if col_desc else df_filtrado.columns[0]
                df_top = df_filtrado.sort_values(by=col_monto, ascending=False).head(8)
                fig_bar = px.bar(
                    df_top, 
                    x=col_monto, 
                    y=eje_x, 
                    orientation='h',
                    title="Top Gastos de Mayor Importe",
                    color=col_monto,
                    color_continuous_scale="Blues"
                )
                fig_bar.update_layout(height=380, yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("Sin datos suficientes para el gráfico de barras.")

        st.subheader("📋 Tabla Detallada de Gastos Registrados (Editable)")
        st.caption("✍️ Puedes editar importes, fechas o conceptos haciendo doble clic en las celdas, o agregar/eliminar registros. Haz clic en **Guardar Cambios** para actualizar la BD.")

        column_config_dict = {}
        if col_monto:
            column_config_dict[col_monto] = st.column_config.NumberColumn("Importe Total (ARS)", format="$%.2f", min_value=0.0)
        if col_fecha:
            column_config_dict[col_fecha] = st.column_config.TextColumn("Fecha (AAAA-MM-DD)")
            
        df_gastos_editado = st.data_editor(
            df_filtrado,
            column_config=column_config_dict,
            num_rows="dynamic",
            use_container_width=True,
            key="gastos_interactive_editor"
        )

        col_save1, col_save2 = st.columns([1, 3])
        with col_save1:
            if st.button("💾 Guardar Cambios en BD", type="primary", use_container_width=True):
                if busqueda_texto or cat_seleccionada != "Todas":
                    df_actualizado = df_gastos_raw.copy()
                    df_actualizado.update(df_gastos_editado)
                else:
                    df_actualizado = df_gastos_editado

                if save_gastos_to_db(df_actualizado):
                    st.success("✅ ¡Gastos guardados con éxito en la base de datos!")
                    st.rerun()

    else:
        st.warning("No existen registros individuales en la tabla de gastos para mostrar el detalle.")

with tab_resumen:
    st.subheader("📊 Consolidado de Costo de Producción por Litro")
    
    costo_total_litro_ars = costo_mp_por_litro_ars + costo_pkg_por_litro_ars + costo_mod_por_litro_ars + tasa_gif_por_litro_ars
    costo_total_lote_ars = costo_total_litro_ars * litros_totales_receta
    
    if margen_objetivo < 100.0:
        precio_venta_neto_litro = costo_total_litro_ars / (1.0 - (margen_objetivo / 100.0))
    else:
        precio_venta_neto_litro = costo_total_litro_ars * 2.0
        
    c1, c2, c3 = st.columns(3)
    c1.metric("COSTO TOTAL POR LITRO", f"${costo_total_litro_ars:,.2f} ARS", delta=f"USD ${(costo_total_litro_ars / tipo_cambio_usd):,.4f}")
    c2.metric("Precio Venta / Litro (Sugerido)", f"${precio_venta_neto_litro:,.2f} ARS", delta=f"Margen: {margen_objetivo}%")
    c3.metric("Costo Total Lote Simulado", f"${costo_total_lote_ars:,.2f} ARS")
    
    st.divider()

    fig_waterfall = go.Figure(go.Waterfall(
        name = "Estructura por Litro", orientation = "v",
        measure = ["relative", "relative", "relative", "relative", "total"],
        x = ["MP (USD➔ARS)", "Packaging (ARS)", "Mano Obra (ARS)", "GIF (ARS)", "TOTAL COSTO LITRO"],
        text = [
            f"${costo_mp_por_litro_ars:,.2f}", 
            f"${costo_pkg_por_litro_ars:,.2f}", 
            f"${costo_mod_por_litro_ars:,.2f}", 
            f"${tasa_gif_por_litro_ars:,.2f}", 
            f"${costo_total_litro_ars:,.2f}"
        ],
        textposition = "outside",
        y = [costo_mp_por_litro_ars, costo_pkg_por_litro_ars, costo_mod_por_litro_ars, tasa_gif_por_litro_ars, 0],
        connector = {"line": {"color": "rgb(63, 63, 63)"}}
    ))
    
    fig_waterfall.update_layout(
        title="Desglose de Costos por Litro (en Pesos ARS)",
        showlegend=False,
        height=450
    )
    
    st.plotly_chart(fig_waterfall, use_container_width=True)

with tab_mrp:
    st.subheader("🎯 6. Alertas de Reorden e Insumos Faltantes (MRP)")
    st.caption("Planificación de requerimientos de materiales para garantizar la producción y evitar quiebres de stock.")
    
    df_alertas = load_alertas_mrp()
    
    col_mrp1, col_mrp2 = st.columns(2)
    
    with col_mrp1:
        st.markdown("#### 🚨 Estado de Alerta de Materias Primas")
        if not df_alertas.empty:
            df_criticos = df_alertas[df_alertas['estado_stock'] != 'NORMAL']
            
            if not df_criticos.empty:
                for idx, row in df_criticos.iterrows():
                    cls_card = "alert-card-critical" if row['estado_stock'] == 'CRÍTICO' else "alert-card-warning"
                    st.markdown(
                        f"<div class='{cls_card}'>"
                        f"<b>[{row['estado_stock']}] {row['nombre']}</b> (Código: {row['codigo']})<br/>"
                        f"Stock Actual: <b>{row['stock_actual']}</b> | Stock Mínimo: {row['stock_minimo']} | Punto Reorden: {row['punto_reorden']}"
                        f"</div>",
                        unsafe_allow_html=True
                    )
            else:
                st.success("✅ Todas las materias primas cuentan con niveles de stock normales.")
                
            with st.expander("🔍 Ver estado completo de inventario de materias primas"):
                st.dataframe(df_alertas, use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos de stock configurados en `stock_materias_primas`.")

    with col_mrp2:
        st.markdown("#### 📦 Explosión de Insumos para la Receta Actual")
        if 'df_mp' in locals() and not df_mp.empty:
            df_mrp_receta = df_mp[['ingrediente', 'cantidad_lote', 'unidad']].copy()
            df_mrp_receta['Lote Simulado (L)'] = litros_totales_receta
            
            st.dataframe(
                df_mrp_receta,
                column_config={
                    "ingrediente": "Materia Prima",
                    "cantidad_lote": st.column_config.NumberColumn("Requerimiento Neto", format="%.3f"),
                    "unidad": "Unidad"
                },
                hide_index=True,
                use_container_width=True
            )
            
            st.download_button(
                label="📥 Descargar Plan de Compras / Solicitud de Insumos (CSV)",
                data=df_mrp_receta.to_csv(index=False).encode('utf-8'),
                file_name=f"requerimiento_insumos_receta_{receta_id_sel}.csv",
                mime="text/csv"
            )

    st.divider()
    st.markdown("#### 📋 Pedidos de Producción Pendientes y Requerimiento Consolidado")
    df_pedidos = load_pedidos_pendientes()
    
    if not df_pedidos.empty:
        st.dataframe(df_pedidos, use_container_width=True, hide_index=True)
    else:
        st.info("No hay pedidos de producción pendientes registrados actualmente en la base de datos.")

with tab_simulacion:
    st.subheader("🔮 7. Motor de Simulación What-If y Análisis de Sensibilidad")
    st.caption("Analiza el impacto de variaciones cambiarias en los costos y calcula el lote mínimo viable de producción.")
    
    sim_col1, sim_col2 = st.columns(2)
    
    with sim_col1:
        st.markdown("### 💱 Sensibilidad por Variación de Dólar")
        variacion_dolar_pct = st.slider(
            "Simular cambio porcentual en el Dólar (%):",
            min_value=-30.0,
            max_value=100.0,
            value=15.0,
            step=5.0
        )
        
        tc_simulado = tipo_cambio_usd * (1.0 + (variacion_dolar_pct / 100.0))
        costo_mp_simulado_ars = total_costo_mp_usd * tc_simulado
        costo_mp_simulado_litro_ars = costo_mp_simulado_ars / litros_totales_receta if litros_totales_receta > 0 else 0.0
        
        costo_total_litro_simulado = costo_mp_simulado_litro_ars + costo_pkg_por_litro_ars + costo_mod_por_litro_ars + tasa_gif_por_litro_ars
        incremento_costo_litro = costo_total_litro_simulado - costo_total_litro_ars
        incremento_pct = (incremento_costo_litro / costo_total_litro_ars * 100.0) if costo_total_litro_ars > 0 else 0.0
        
        st.metric("Tipo de Cambio Simulado", f"${tc_simulado:,.2f} ARS/USD", delta=f"{variacion_dolar_pct:+.1f}%")
        st.metric("Nuevo Costo Total por Litro", f"${costo_total_litro_simulado:,.2f} ARS", delta=f"+${incremento_costo_litro:,.2f} ARS ({incremento_pct:+.2f}%)")
        
        fig_sim = go.Figure()
        fig_sim.add_trace(go.Bar(
            x=["Costo Actual", "Costo Simulado"],
            y=[costo_total_litro_ars, costo_total_litro_simulado],
            marker_color=["#3B82F6", "#EF4444"],
            text=[f"${costo_total_litro_ars:,.2f}", f"${costo_total_litro_simulado:,.2f}"],
            textposition="auto"
        ))
        fig_sim.update_layout(title="Comparativa Costo por Litro ante Variación Cambiaria", height=320)
        st.plotly_chart(fig_sim, use_container_width=True)

    with sim_col2:
        st.markdown("### ⚖️ Cálculo de Lote Mínimo Viable (Punto de Equilibrio de Tirada)")
        st.caption("Calcula el volumen mínimo a producir para cubrir los gastos fijos asociados al arranque de lote.")
        
        gastos_fijos_tirada = st.number_input("Gastos Fijos Directos de Limpieza/Preparación/Tirada (ARS):", min_value=0.0, value=25000.0, step=5000.0)
        precio_objetivo_litro = st.number_input("Precio de Venta Objetivo por Litro (ARS):", min_value=0.0, value=float(precio_venta_neto_litro or 3000.0), step=100.0)
        
        costo_variable_unitario = costo_mp_por_litro_ars + costo_pkg_por_litro_ars
        margen_contribucion_unitario = precio_objetivo_litro - costo_variable_unitario
        
        if margen_contribucion_unitario > 0:
            litros_minimos_equilibrio = gastos_fijos_tirada / margen_contribucion_unitario
            st.success(f"🎯 **Lote Mínimo Viable:** **{litros_minimos_equilibrio:,.2f} Litros**")
            st.metric("Margen Contribución por Litro", f"${margen_contribucion_unitario:,.2f} ARS/L")
            st.metric("Volumen Actual Simulado", f"{litros_totales_receta:,.2f} Litros", delta=f"{litros_totales_receta - litros_minimos_equilibrio:+,.2f} L vs Equilibrio")
        else:
            st.error("⚠️ El precio objetivo ingresado no logra cubrir los costos variables por litro.")