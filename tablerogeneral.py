import sqlite3
import json
import pandas as pd
import streamlit as st
import plotly.express as px
import streamlit.components.v1 as components
from datetime import date, datetime

st.set_page_config(page_title="Minerva - Gestión Comercial & Insumos", layout="wide", page_icon="📦")

st.markdown("""
    <style>
    .stApp { background-color: #F8FAFC; }
    .metric-card {
        background: white;
        padding: 20px;
        border-radius: 16px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    .stPlotlyChart { background: white; border-radius: 16px; padding: 10px; }
    iframe { border: none !important; }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        white-space: pre-wrap;
        border-radius: 10px 10px 0px 0px;
        padding-left: 16px;
        padding-right: 16px;
        font-weight: 600;
    }
    </style>
""", unsafe_allow_html=True)

def get_db_connection():
    """Establece conexión a la base de datos SQLite."""
    return sqlite3.connect("minerva.db", check_same_thread=False)

@st.cache_data(ttl=300)
def load_data():
    """Carga y procesa el stock físico y el historial de ventas por producto."""
    conn = get_db_connection()

    # 1. Cargar Stock Físico Base
    query_stock = """
    SELECT 
        p.id AS producto_id,
        p.id_receta,
        p.envase_id,
        r.nombre AS Producto, 
        e.descripcion AS Envase, 
        SUM(s.cantidad) AS Cantidad
    FROM stock_productos_envasados s
    JOIN recetas r ON s.receta_id = r.id
    JOIN envases e ON s.envase_id = e.id
    JOIN productos p ON p.id_receta = r.id AND p.envase_id = e.id
    WHERE s.cliente_id = 6 AND p.activo = 1
    GROUP BY p.id, r.nombre, e.descripcion
    """
    try:
        df_stock = pd.read_sql_query(query_stock, conn)
    except Exception:
        query_stock_alt = """
        SELECT 
            p.id_receta,
            p.envase_id,
            r.nombre AS Producto, 
            e.descripcion AS Envase, 
            SUM(s.cantidad) AS Cantidad
        FROM stock_productos_envasados s
        JOIN recetas r ON s.receta_id = r.id
        JOIN envases e ON s.envase_id = e.id
        JOIN productos p ON p.id_receta = r.id AND p.envase_id = e.id
        WHERE s.cliente_id = 6 AND p.activo = 1
        GROUP BY r.nombre, e.descripcion
        """
        df_stock = pd.read_sql_query(query_stock_alt, conn)

    df_stock["Venta_Mensual"] = 0.0
    FECHA_INICIO_ANALISIS = "2026-03-01"

    query_ventas = """
    SELECT
        s.receta_id AS receta_id,
        s.envase_id AS envase_id,
        dv.cantidad AS cantidad,
        v.fecha_venta AS fecha
    FROM detalle_venta dv
    JOIN stock_productos_envasados s ON dv.stock_id = s.id
    JOIN ventas v ON dv.venta_id = v.id
    WHERE s.cliente_id = 6 AND LOWER(v.estado_venta) = 'activa'
      AND v.fecha_venta >= ?
    """
    try:
        df_ventas = pd.read_sql_query(query_ventas, conn, params=(FECHA_INICIO_ANALISIS,))

        if not df_ventas.empty:
            df_ventas["fecha_dt"] = pd.to_datetime(df_ventas["fecha"], errors="coerce")
            df_ventas["receta_id"] = pd.to_numeric(df_ventas["receta_id"], errors="coerce")
            df_ventas["envase_id"] = pd.to_numeric(df_ventas["envase_id"], errors="coerce")
            df_ventas["cantidad"] = pd.to_numeric(df_ventas["cantidad"], errors="coerce").fillna(0)
            df_ventas = df_ventas.dropna(subset=["fecha_dt", "receta_id", "envase_id"])

            if not df_ventas.empty:
                df_ventas["periodo"] = df_ventas["fecha_dt"].dt.to_period("M")
                min_fecha = df_ventas["fecha_dt"].min()
                max_fecha = df_ventas["fecha_dt"].max()
                cant_meses = max(1, df_ventas["periodo"].nunique())

                ventas_por_prod = (
                    df_ventas.groupby(["receta_id", "envase_id"])["cantidad"].sum() / cant_meses
                )
                dict_ventas = ventas_por_prod.to_dict()

                df_stock["Venta_Mensual"] = df_stock.apply(
                    lambda row: dict_ventas.get((row["id_receta"], row["envase_id"]), 0.0),
                    axis=1,
                )

                st.session_state["historial_info"] = {
                    "total_ventas": len(df_ventas),
                    "cant_meses": cant_meses,
                    "fecha_inicio": min_fecha.strftime("%d/%m/%Y"),
                    "fecha_fin": max_fecha.strftime("%d/%m/%Y")
                }
    except Exception as e:
        st.error(f"⚠️ Ocurrió una advertencia al procesar ventas: {e}")

    conn.close()
    df_stock["Venta_Mensual"] = df_stock["Venta_Mensual"].round(1)
    return df_stock

@st.cache_data(ttl=300)
def load_stock_materias_primas():
    """
    Carga el stock disponible actual de las materias primas desde la base de datos SQLite.
    Prioriza el campo 'cantidad_actual' para determinar el valor del stock.
    Excluye 'Agua'.
    """
    conn = get_db_connection()
    try:
        query = """
        SELECT 
            id AS materia_prima_id,
            nombre AS materia_prima,
            COALESCE(cantidad_actual, 0.0) AS stock_actual,
            COALESCE(unidad_medida, 'L') AS unidad
        FROM materias_primas
        WHERE LOWER(nombre) NOT LIKE '%agua%'
        """
        df = pd.read_sql_query(query, conn)
    except Exception:
        try:
            query_alt = """
            SELECT 
                mp.id AS materia_prima_id,
                mp.nombre AS materia_prima,
                COALESCE(SUM(s.cantidad_actual), 0.0) AS stock_actual,
                'L' AS unidad
            FROM materias_primas mp
            LEFT JOIN stock_materias_primas s ON mp.id = s.materia_prima_id
            WHERE LOWER(mp.nombre) NOT LIKE '%agua%'
            GROUP BY mp.id, mp.nombre
            """
            df = pd.read_sql_query(query_alt, conn)
        except Exception:
            try:
                query_fallback = """
                SELECT 
                    id AS materia_prima_id,
                    nombre AS materia_prima,
                    COALESCE(stock, 0.0) AS stock_actual,
                    COALESCE(unidad_medida, 'L') AS unidad
                FROM materias_primas
                WHERE LOWER(nombre) NOT LIKE '%agua%'
                """
                df = pd.read_sql_query(query_fallback, conn)
            except Exception:
                query_base = """
                SELECT id AS materia_prima_id, nombre AS materia_prima, 0.0 AS stock_actual, 'L' AS unidad
                FROM materias_primas
                WHERE LOWER(nombre) NOT LIKE '%agua%'
                """
                df = pd.read_sql_query(query_base, conn)
    finally:
        conn.close()

    df["stock_actual"] = pd.to_numeric(df["stock_actual"], errors="coerce").fillna(0.0)
    return df

@st.cache_data(ttl=300)
def load_materias_primas_consumo(fecha_inicio=None, fecha_fin=None):
    """
    Calcula el consumo real exacto de materias primas considerando:
    1. Proporción del ingrediente en la receta (ri.cantidad / total_lote)
    2. Capacidad real del envase comercializado (env.capacidad_litros)
    3. Cantidad de unidades vendidas en estado 'activa'
    
    Nota: Se excluye el 'Agua' del cálculo de insumos consumidos.
    """
    conn = get_db_connection()
    
    where_conditions = [
        "LOWER(v.estado_venta) = 'activa'",
        "LOWER(mp.nombre) NOT LIKE '%agua%'"
    ]
    params = []

    if fecha_inicio:
        where_conditions.append("v.fecha_venta >= ?")
        params.append(str(fecha_inicio))
    if fecha_fin:
        where_conditions.append("v.fecha_venta <= ?")
        params.append(str(fecha_fin))

    where_clause = " AND ".join(where_conditions)

    # Nota: Usamos (ri.cantidad * 1.0) para forzar división de punto flotante en SQLite
    query = f"""
    SELECT 
        mp.id AS materia_prima_id,
        mp.nombre AS materia_prima,
        (rec.nombre || ' - ' || env.descripcion) AS producto,
        SUM(d.cantidad) AS unidades_vendidas,
        env.capacidad_litros AS capacidad_envase_litros,
        ROUND((ri.cantidad * 1.0 / rt.total_receta) * 100, 2) AS porcentaje_en_receta,
        SUM(d.cantidad * env.capacidad_litros * (ri.cantidad * 1.0 / rt.total_receta)) AS consumo_materia_prima_litros
    FROM ventas v
    INNER JOIN detalle_venta d ON v.id = d.venta_id
    INNER JOIN stock_productos_envasados s ON s.id = d.stock_id
    INNER JOIN recetas rec ON rec.id = s.receta_id
    INNER JOIN envases env ON env.id = s.envase_id
    INNER JOIN receta_ingredientes ri ON rec.id = ri.receta_id
    INNER JOIN (
        SELECT receta_id, SUM(cantidad) AS total_receta
        FROM receta_ingredientes
        GROUP BY receta_id
    ) rt ON rt.receta_id = rec.id
    INNER JOIN materias_primas mp ON mp.id = ri.materia_prima_id
    WHERE {where_clause}
    GROUP BY mp.id, mp.nombre, s.receta_id, s.envase_id, rec.nombre, env.descripcion, env.capacidad_litros, ri.cantidad, rt.total_receta
    ORDER BY consumo_materia_prima_litros DESC
    """
    try:
        df = pd.read_sql_query(query, conn, params=params)
        df["unidades_vendidas"] = pd.to_numeric(df["unidades_vendidas"], errors="coerce").fillna(0)
        df["consumo_materia_prima_litros"] = pd.to_numeric(df["consumo_materia_prima_litros"], errors="coerce").fillna(0.0)
    except Exception as e:
        st.error(f"Error al cargar consumo de materias primas: {e}")
        df = pd.DataFrame()
    finally:
        conn.close()

    return df

def clasificar_stock(df, meses_critico, meses_objetivo, meses_excedente, stock_min_defecto):
    """Clasifica el stock actual comparándolo con la meta de ventas."""
    def evaluar_producto(row):
        cant = row["Cantidad"]
        venta_m = row["Venta_Mensual"]

        if venta_m > 0:
            s_critico = int(round(venta_m * meses_critico))
            s_necesario = int(round(venta_m * meses_objetivo))
            s_excedente = int(round(venta_m * meses_excedente))
        else:
            s_critico = int(round(stock_min_defecto * 0.5))
            s_necesario = int(stock_min_defecto)
            s_excedente = int(stock_min_defecto * 3)

        faltante = max(0, s_necesario - cant)

        if cant <= s_critico:
            estado = "Crítico"
            accion = f"Producir urgente (faltan {faltante} u. para stock necesario de {s_necesario} u.)"
        elif cant < s_necesario:
            estado = "Bajo"
            accion = f"Reponer pronto (faltan {faltante} u. para stock necesario de {s_necesario} u.)"
        elif cant <= s_excedente:
            estado = "Normal"
            accion = "Stock saludable, sin acción"
        else:
            estado = "Excedente"
            accion = f"Evaluar sobreproducción (exceso de {cant - s_excedente} u.)"

        return pd.Series([s_necesario, faltante, estado, accion])

    df_calc = df.copy()
    df_calc[["Stock_Necesario", "Cantidad_A_Producir", "Estado", "Accion_Recomendada"]] = df_calc.apply(evaluar_producto, axis=1)
    return df_calc

ESTADO_COLOR = {
    "Crítico": "#EF4444",
    "Bajo": "#F59E0B",
    "Normal": "#10B981",
    "Excedente": "#3B82F6",
}

def render_kpi_cards(total_skus, stock_total, criticos, bajos, excedentes):
    html = f"""
    <div style="font-family:'Segoe UI', sans-serif; display:flex; gap:16px; flex-wrap:wrap; margin-bottom:6px;">
      <div class="kpi" style="flex:1; min-width:150px; background:linear-gradient(135deg,#1E293B,#334155); color:white; border-radius:18px; padding:18px 20px;">
        <div style="font-size:13px; opacity:.75;">SKUs Activos</div>
        <div id="v0" style="font-size:32px; font-weight:700;">0</div>
      </div>
      <div class="kpi" style="flex:1; min-width:150px; background:linear-gradient(135deg,#0EA5E9,#0284C7); color:white; border-radius:18px; padding:18px 20px;">
        <div style="font-size:13px; opacity:.85;">Stock Total</div>
        <div id="v1" style="font-size:32px; font-weight:700;">0</div>
      </div>
      <div class="kpi" style="flex:1; min-width:150px; background:linear-gradient(135deg,#EF4444,#B91C1C); color:white; border-radius:18px; padding:18px 20px; cursor:default;">
        <div style="font-size:13px; opacity:.85;">🔴 Críticos</div>
        <div id="v2" style="font-size:32px; font-weight:700;">0</div>
      </div>
      <div class="kpi" style="flex:1; min-width:150px; background:linear-gradient(135deg,#F59E0B,#B45309); color:white; border-radius:18px; padding:18px 20px;">
        <div style="font-size:13px; opacity:.85;">🟠 Bajos</div>
        <div id="v3" style="font-size:32px; font-weight:700;">0</div>
      </div>
      <div class="kpi" style="flex:1; min-width:150px; background:linear-gradient(135deg,#3B82F6,#1D4ED8); color:white; border-radius:18px; padding:18px 20px;">
        <div style="font-size:13px; opacity:.85;">🔵 Excedentes</div>
        <div id="v4" style="font-size:32px; font-weight:700;">0</div>
      </div>
    </div>
    <style>
      .kpi {{ transition: transform .15s ease; box-shadow:0 6px 14px rgba(0,0,0,.12); }}
      .kpi:hover {{ transform: translateY(-4px); }}
    </style>
    <script>
      function animate(id, end) {{
        let el = document.getElementById(id);
        let start = 0;
        let duration = 700;
        let startTime = null;
        function step(ts) {{
          if (!startTime) startTime = ts;
          let progress = Math.min((ts - startTime) / duration, 1);
          el.textContent = Math.floor(progress * (end - start) + start).toLocaleString();
          if (progress < 1) requestAnimationFrame(step);
        }}
        requestAnimationFrame(step);
      }}
      animate("v0", {total_skus});
      animate("v1", {stock_total});
      animate("v2", {criticos});
      animate("v3", {bajos});
      animate("v4", {excedentes});
    </script>
    """
    components.html(html, height=110)

def render_interactive_table(df):
    records = df.to_dict(orient="records")
    data_json = json.dumps(records)
    color_json = json.dumps(ESTADO_COLOR)

    html = f"""
    <div style="font-family:'Segoe UI', sans-serif;">
      <input id="tableSearch" placeholder="🔍 Buscar producto o envase..."
        style="width:100%; padding:10px 14px; border-radius:10px; border:1px solid #E2E8F0;
               margin-bottom:10px; font-size:14px; outline:none; box-sizing:border-box;">
      <div style="max-height:480px; overflow-y:auto; border-radius:14px; border:1px solid #E2E8F0;">
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
          <thead style="position:sticky; top:0; background:#1E293B; color:white; z-index:1;">
            <tr id="headerRow"></tr>
          </thead>
          <tbody id="tbody"></tbody>
        </table>
      </div>
    </div>
    <script>
      const data = {data_json};
      const colors = {color_json};
      const cols = ["Producto","Envase","Cantidad","Venta_Mensual","Stock_Necesario","Cantidad_A_Producir","Estado","Accion_Recomendada"];
      const labels = ["Producto","Envase","Stock Actual","Venta Prom./Mes","Stock Necesario","A Fabricar","Estado","Acción recomendada"];
      let sortCol = "Cantidad_A_Producir";
      let sortAsc = false;

      function buildHeader() {{
        const row = document.getElementById("headerRow");
        row.innerHTML = "";
        cols.forEach((c, i) => {{
          const th = document.createElement("th");
          th.textContent = labels[i] + (sortCol === c ? (sortAsc ? " ▲" : " ▼") : "");
          th.style.padding = "10px 12px";
          th.style.textAlign = "left";
          th.style.cursor = "pointer";
          th.style.userSelect = "none";
          th.onclick = () => {{
            if (sortCol === c) sortAsc = !sortAsc; else {{ sortCol = c; sortAsc = true; }}
            render();
          }};
          row.appendChild(th);
        }});
      }}

      function render() {{
        buildHeader();
        const q = document.getElementById("tableSearch").value.toLowerCase();
        let filtered = data.filter(r =>
          r.Producto.toLowerCase().includes(q) || r.Envase.toLowerCase().includes(q)
        );
        filtered.sort((a,b) => {{
          let va = a[sortCol], vb = b[sortCol];
          if (typeof va === "number") return sortAsc ? va - vb : vb - va;
          return sortAsc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
        }});
        const tbody = document.getElementById("tbody");
        tbody.innerHTML = "";
        filtered.forEach(r => {{
          const tr = document.createElement("tr");
          tr.style.borderBottom = "1px solid #F1F5F9";
          tr.onmouseenter = () => tr.style.background = "#F8FAFC";
          tr.onmouseleave = () => tr.style.background = "white";
          cols.forEach(c => {{
            const td = document.createElement("td");
            td.style.padding = "9px 12px";
            if (c === "Estado") {{
              td.innerHTML = `<span style="background:${{colors[r[c]]}}22; color:${{colors[r[c]]}};
                padding:3px 10px; border-radius:999px; font-weight:600; font-size:12px;">${{r[c]}}</span>`;
            }} else if (c === "Cantidad_A_Producir") {{
              td.innerHTML = r[c] > 0 
                ? `<strong style="color:#DC2626;">+${{r[c]}} u.</strong>` 
                : `<span style="color:#059669;">0 u.</span>`;
            }} else {{
              td.textContent = r[c];
            }}
            tr.appendChild(td);
          }});
          tbody.appendChild(tr);
        }});
      }}
      document.getElementById("tableSearch").addEventListener("input", render);
      render();
    </script>
    """
    components.html(html, height=560, scrolling=True)

def render_priority_panel(df_urgente):
    if df_urgente.empty:
        st.success("✅ No hay productos en estado crítico o bajo. Stock bajo control.")
        return
    cards = ""
    for _, row in df_urgente.iterrows():
        color = ESTADO_COLOR[row["Estado"]]
        cards += f"""
        <div style="min-width:240px; background:white; border-left:6px solid {color};
               border-radius:12px; padding:14px 16px; box-shadow:0 3px 8px rgba(0,0,0,.06);">
          <div style="font-size:12px; font-weight:700; color:{color}; text-transform:uppercase;">{row['Estado']}</div>
          <div style="font-size:15px; font-weight:600; margin:4px 0;">{row['Producto']}</div>
          <div style="font-size:12px; color:#64748B;">{row['Envase']} · Actual: <b>{row['Cantidad']} u.</b> (Venta: <b>{row['Venta_Mensual']} u/mes</b>)</div>
          <div style="font-size:12px; margin-top:6px; color:#334155;">{row['Accion_Recomendada']}</div>
        </div>
        """
    html = f"""
    <div style="font-family:'Segoe UI', sans-serif; display:flex; gap:14px; overflow-x:auto; padding-bottom:8px;">
      {cards}
    </div>
    """
    components.html(html, height=175, scrolling=True)

def main():
    st.title("🌿 Minerva - Panel Comercial y Análisis de Insumos")
    st.caption("Sistema integral de control de stock envasado y consumo real de materias primas por ventas")
    st.markdown("---")

    # Organización principal mediante pestañas
    tab_stock, tab_materias_primas = st.tabs([
        "📦 Stock & Cobertura de Producción", 
        "🧪 Consumo Real de Materias Primas"
    ])

    with tab_stock:
        df_raw = load_data()
        if df_raw.empty:
            st.warning("No se encontraron registros activos en la base de datos.")
        else:
            # Info del historial en el Sidebar
            total_ventas_calc = df_raw["Venta_Mensual"].sum()
            info_h = st.session_state.get("historial_info", None)
            if total_ventas_calc > 0 and info_h:
                st.sidebar.success(
                    f"✅ **Historial Analizado**\n\n"
                    f"- **Ventas:** {info_h['total_ventas']} registros\n"
                    f"- **Rango:** {info_h['fecha_inicio']} a {info_h['fecha_fin']}\n"
                    f"- **Meses históricos:** {info_h['cant_meses']} mes(es)\n"
                    f"- **SKUs activos con venta:** {len(df_raw[df_raw['Venta_Mensual'] > 0])}"
                )
            else:
                st.sidebar.info("ℹ️ Mostrando stock base. No se halló historial activo de ventas.")

            st.sidebar.header("🎯 Parámetros de Cobertura de Stock")
            meses_objetivo = st.sidebar.slider("Meses de cobertura deseados", 0.5, 6.0, 1.5, 0.5)
            meses_critico = st.sidebar.slider("Alerta Crítica (< meses)", 0.1, max(0.2, meses_objetivo - 0.1), min(0.5, meses_objetivo - 0.1), 0.1)
            meses_excedente = st.sidebar.slider("Alerta Excedente (> meses)", meses_objetivo + 0.5, 12.0, 3.0, 0.5)

            st.sidebar.markdown("---")
            stock_min_defecto = st.sidebar.number_input("Stock mín. (Sin historial de venta)", min_value=0, value=10, step=5)

            df = clasificar_stock(df_raw, meses_critico, meses_objetivo, meses_excedente, stock_min_defecto)
            urgentes = df[df["Estado"].isin(["Crítico", "Bajo"])].sort_values("Cantidad_A_Producir", ascending=False)

            st.markdown(f"## 📋 Detalle de Inventario (Meta: {meses_objetivo} mes(es) de cobertura)")
            render_interactive_table(df)
            st.markdown("---")

            render_kpi_cards(
                total_skus=len(df),
                stock_total=int(df["Cantidad"].sum()),
                criticos=len(df[df["Estado"] == "Crítico"]),
                bajos=len(df[df["Estado"] == "Bajo"]),
                excedentes=len(df[df["Estado"] == "Excedente"]),
            )

            st.write("### 🚨 Acción prioritaria (Faltantes a fabricar hoy)")
            render_priority_panel(urgentes)

            st.write("## 📊 Análisis Visual de Stock")
            col_g1, col_g2 = st.columns([2, 1])

            with col_g1:
                top20 = df.sort_values("Cantidad_A_Producir", ascending=False).head(20)
                fig_bar = px.bar(
                    top20, x="Cantidad_A_Producir", y="Producto", orientation="h",
                    color="Estado", color_discrete_map=ESTADO_COLOR,
                    title="Top 20 Productos a producir (u. faltantes)",
                    hover_data=["Venta_Mensual", "Cantidad", "Stock_Necesario"]
                )
                fig_bar.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig_bar, use_container_width=True)

            with col_g2:
                estado_counts = df["Estado"].value_counts().reset_index()
                estado_counts.columns = ["Estado", "Cantidad_SKUs"]
                fig_pie = px.pie(estado_counts, values="Cantidad_SKUs", names="Estado", color="Estado", color_discrete_map=ESTADO_COLOR, hole=0.45, title="SKUs por estado")
                st.plotly_chart(fig_pie, use_container_width=True)

            fig_tree = px.treemap(df, path=["Envase", "Producto"], values="Cantidad", color="Estado", color_discrete_map=ESTADO_COLOR, title="Distribución de stock")
            st.plotly_chart(fig_tree, use_container_width=True)

            csv = urgentes.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Descargar lista de producción (CSV)", data=csv, file_name="plan_de_produccion.csv", mime="text/csv")

    with tab_materias_primas:
        st.markdown("## 🧪 Consumo Real y Stock Disponible de Materias Primas")
        st.caption("Cálculo exacto de insumos requeridos vs. Inventario disponible en depósito (excluye Agua)")

        col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
        with col_f1:
            fecha_desde = st.date_input("Fecha Desde", value=date(2026, 3, 1), key="mp_f_desde")
        with col_f2:
            fecha_hasta = st.date_input("Fecha Hasta", value=date(2026, 4, 30), key="mp_f_hasta")
        with col_f3:
            st.write("")
            st.write("")
            aplicar_filtro = st.button("🔍 Filtrar Consumo", type="primary", use_container_width=True)

        df_mp_raw = load_materias_primas_consumo(fecha_desde, fecha_hasta)
        df_stock_mp = load_stock_materias_primas()

        if df_mp_raw.empty and df_stock_mp.empty:
            st.warning("⚠️ No se registraron datos de ventas ni materias primas en la base de datos.")
        else:
            # Agrupar consumo global por Materia Prima
            if not df_mp_raw.empty:
                df_mp_ranking = df_mp_raw.groupby("materia_prima", as_index=False).agg(
                    consumo_total_litros=("consumo_materia_prima_litros", "sum"),
                    total_unidades_vendidas=("unidades_vendidas", "sum"),
                    variedad_productos=("producto", "nunique")
                )
            else:
                df_mp_ranking = pd.DataFrame(columns=["materia_prima", "consumo_total_litros", "total_unidades_vendidas", "variedad_productos"])

            # Unir con el Stock Actual Disponible
            df_insumos = pd.merge(
                df_stock_mp,
                df_mp_ranking,
                on="materia_prima",
                how="outer"
            )

            df_insumos["consumo_total_litros"] = df_insumos["consumo_total_litros"].fillna(0.0)
            df_insumos["stock_actual"] = df_insumos["stock_actual"].fillna(0.0)
            df_insumos["total_unidades_vendidas"] = df_insumos["total_unidades_vendidas"].fillna(0)
            df_insumos["variedad_productos"] = df_insumos["variedad_productos"].fillna(0)
            
            # Balance y Diagnóstico de Cobertura
            df_insumos["balance_remante"] = df_insumos["stock_actual"] - df_insumos["consumo_total_litros"]
            
            def evaluar_estado_insumo(row):
                s = row["stock_actual"]
                c = row["consumo_total_litros"]
                if c == 0:
                    return "Sin Venta"
                elif s < c:
                    return "🔴 Faltante / Comprar"
                elif s < c * 1.2:
                    return "🟠 Stock Ajustado"
                else:
                    return "🟢 Cobertura OK"

            df_insumos["Estado_Stock"] = df_insumos.apply(evaluar_estado_insumo, axis=1)
            df_insumos = df_insumos.sort_values("consumo_total_litros", ascending=False)

            total_litros_consumidos = df_insumos["consumo_total_litros"].sum()
            total_stock_disponible = df_insumos["stock_actual"].sum()
            insumos_faltantes = len(df_insumos[df_insumos["Estado_Stock"] == "🔴 Faltante / Comprar"])
            mp_top = df_insumos.iloc[0]["materia_prima"] if not df_insumos.empty else "N/A"

            c_kpi1, c_kpi2, c_kpi3, c_kpi4 = st.columns(4)
            with c_kpi1:
                st.metric("Total Stock Insumos", f"{total_stock_disponible:,.2f} L")
            with c_kpi2:
                st.metric("Total Consumo Periodo", f"{total_litros_consumidos:,.2f} L")
            with c_kpi3:
                st.metric("Insumos en Déficit", f"{insumos_faltantes} materias", delta=f"-{insumos_faltantes}" if insumos_faltantes > 0 else "OK", delta_color="inverse")
            with c_kpi4:
                st.metric("Insumo Más Requerido", mp_top)

            st.markdown("---")

            st.markdown("### 📊 Comparativo: Stock Disponible vs. Consumo Necesario (Litros)")

            col_chart1, col_chart2 = st.columns([3, 2])

            with col_chart1:
                # Preparar dataframe largo para el gráfico de barras agrupadas
                df_chart_comp = df_insumos.melt(
                    id_vars=["materia_prima"],
                    value_vars=["stock_actual", "consumo_total_litros"],
                    var_name="Tipo",
                    value_name="Litros"
                )
                df_chart_comp["Tipo"] = df_chart_comp["Tipo"].map({
                    "stock_actual": "Stock Disponible",
                    "consumo_total_litros": "Consumo Requerido"
                })

                fig_comp = px.bar(
                    df_chart_comp,
                    x="Litros",
                    y="materia_prima",
                    color="Tipo",
                    barmode="group",
                    orientation="h",
                    title="Stock Actual vs Consumo Necesario por Materia Prima",
                    color_discrete_map={"Stock Disponible": "#10B981", "Consumo Requerido": "#EF4444"}
                )
                fig_comp.update_layout(
                    yaxis=dict(autorange="reversed"),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    legend=dict(title=None, orientation="h", y=1.1)
                )
                st.plotly_chart(fig_comp, use_container_width=True)

            with col_chart2:
                fig_mp_pie = px.pie(
                    df_insumos[df_insumos["consumo_total_litros"] > 0].head(8),
                    values="consumo_total_litros",
                    names="materia_prima",
                    title="Distribución de Consumo (Top 8 Insumos)",
                    hole=0.4
                )
                st.plotly_chart(fig_mp_pie, use_container_width=True)

            st.markdown("---")

            st.markdown("### 📋 Planilla de Control: Stock Actual, Consumo y Estado")

            df_control = df_insumos[[
                "materia_prima", "stock_actual", "consumo_total_litros",
                "balance_remante", "Estado_Stock", "variedad_productos"
            ]].copy()

            df_control.columns = [
                "Materia Prima", "Stock Actual (L)", "Consumo Periodo (L)",
                "Balance / Remanente (L)", "Estado / Diagnóstico", "Productos que la usan"
            ]

            st.dataframe(
                df_control.style.format({
                    "Stock Actual (L)": "{:,.2f} L",
                    "Consumo Periodo (L)": "{:,.2f} L",
                    "Balance / Remanente (L)": "{:,.2f} L",
                    "Productos que la usan": "{:.0f}"
                }),
                use_container_width=True,
                hide_index=True
            )

            if not df_mp_raw.empty:
                st.markdown("---")
                st.markdown("### 🔎 Desglose por Producto para una Materia Prima")
                lista_mps = ["Todas las Materias Primas"] + df_insumos["materia_prima"].tolist()
                mp_seleccionada = st.selectbox("Selecciona una Materia Prima para auditar sus productos:", lista_mps)

                if mp_seleccionada != "Todas las Materias Primas":
                    df_filtrado = df_mp_raw[df_mp_raw["materia_prima"] == mp_seleccionada].copy()
                else:
                    df_filtrado = df_mp_raw.copy()

                fig_tree_mp = px.treemap(
                    df_filtrado,
                    path=["materia_prima", "producto"],
                    values="consumo_materia_prima_litros",
                    title=f"Aporte por Producto al Consumo ({mp_seleccionada})",
                    color="consumo_materia_prima_litros",
                    color_continuous_scale="Greens"
                )
                st.plotly_chart(fig_tree_mp, use_container_width=True)

            # Descargar reporte CSV
            csv_mp = df_control.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Descargar Reporte de Stock y Consumo de Insumos (CSV)",
                data=csv_mp,
                file_name=f"stock_y_consumo_materias_primas_{fecha_desde.strftime('%Y%m%d')}_{fecha_hasta.strftime('%Y%m%d')}.csv",
                mime="text/csv",
                type="primary"
            )

if __name__ == "__main__":
    main()