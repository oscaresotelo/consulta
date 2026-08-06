import sqlite3
import json
import pandas as pd
import streamlit as st
import plotly.express as px
import streamlit.components.v1 as components

st.set_page_config(page_title="Minerva - Stock", layout="wide", page_icon="📦")

# ============================================================
# ESTILOS GLOBALES
# ============================================================
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
    </style>
""", unsafe_allow_html=True)

# ============================================================
# CARGA Y PROCESAMIENTO DE DATOS ROBUSTO
# ============================================================
def get_db_connection():
    return sqlite3.connect("minerva.db", check_same_thread=False)

@st.cache_data(ttl=300)
def load_data():
    conn = get_db_connection()
    cursor = conn.cursor()

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

    # Fecha desde la cual se analiza el historial de ventas para el promedio
    FECHA_INICIO_ANALISIS = "2026-03-01"

    # 2. Cargar ventas uniendo detalle_venta -> stock_productos_envasados
    #    (detalle_venta NO tiene FK directa a producto/receta; solo tiene
    #    stock_id, que apunta a stock_productos_envasados. De ahí se obtienen
    #    receta_id y envase_id, los mismos campos usados para armar el stock)
    query_ventas = """
    SELECT
        s.receta_id AS receta_id,
        s.envase_id AS envase_id,
        dv.cantidad AS cantidad,
        v.fecha_venta AS fecha
    FROM detalle_venta dv
    JOIN stock_productos_envasados s ON dv.stock_id = s.id
    JOIN ventas v ON dv.venta_id = v.id
    WHERE s.cliente_id = 6 AND v.estado_venta = 'activa'
      AND v.fecha_venta >= ?
    """
    try:
        df_ventas = pd.read_sql_query(query_ventas, conn, params=(FECHA_INICIO_ANALISIS,))

        if not df_ventas.empty:
            # Convertir fechas de forma flexible y asegurar tipos numéricos
            df_ventas["fecha_dt"] = pd.to_datetime(df_ventas["fecha"], errors="coerce")
            df_ventas["receta_id"] = pd.to_numeric(df_ventas["receta_id"], errors="coerce")
            df_ventas["envase_id"] = pd.to_numeric(df_ventas["envase_id"], errors="coerce")
            df_ventas["cantidad"] = pd.to_numeric(df_ventas["cantidad"], errors="coerce").fillna(0)
            df_ventas = df_ventas.dropna(subset=["fecha_dt", "receta_id", "envase_id"])

            if not df_ventas.empty:
                # ANALIZAR EL HISTORIAL COMPLETO
                df_ventas["periodo"] = df_ventas["fecha_dt"].dt.to_period("M")

                min_fecha = df_ventas["fecha_dt"].min()
                max_fecha = df_ventas["fecha_dt"].max()

                # Cantidad total de meses distintos con registros de venta
                cant_meses = max(1, df_ventas["periodo"].nunique())

                # Calcular venta mensual promedio histórica por (receta_id, envase_id)
                ventas_por_prod = (
                    df_ventas.groupby(["receta_id", "envase_id"])["cantidad"].sum() / cant_meses
                )
                dict_ventas = ventas_por_prod.to_dict()

                # Asignar promedio a la tabla de stock por la misma clave (receta, envase)
                df_stock["Venta_Mensual"] = df_stock.apply(
                    lambda row: dict_ventas.get((row["id_receta"], row["envase_id"]), 0.0),
                    axis=1,
                )

                # Guardar resumen del historial
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

# ============================================================
# LÓGICA DE DECISIÓN BASADA EN VENTAS
# ============================================================
def clasificar_stock(df, meses_critico, meses_objetivo, meses_excedente, stock_min_defecto):
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

# ============================================================
# COMPONENTE HTML/JS: KPI CARDS ANIMADAS
# ============================================================
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

# ============================================================
# COMPONENTE HTML/JS: TABLA INTERACTIVA
# ============================================================
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

# ============================================================
# COMPONENTE HTML/JS: PANEL DE ACCIÓN PRIORITARIA
# ============================================================
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

# ============================================================
# APP PRINCIPAL
# ============================================================
def main():
    st.title("📦 Minerva Consulta Comercial")
    st.caption("Panel interactivo con cálculo dinámico de stock necesario según historial de ventas por producto")
    st.markdown("---")

    df_raw = load_data()
    if df_raw.empty:
        st.warning("No se encontraron registros activos.")
        return

    # Aviso en el sidebar sobre el historial
    total_ventas_calc = df_raw["Venta_Mensual"].sum()
    info_h = st.session_state.get("historial_info", None)
    if total_ventas_calc > 0 and info_h:
        st.sidebar.success(
            f"✅ **Historial 100% Analizado**\n\n"
            f"- **Ventas analizadas:** {info_h['total_ventas']} registros\n"
            f"- **Rango:** {info_h['fecha_inicio']} a {info_h['fecha_fin']}\n"
            f"- **Meses históricos:** {info_h['cant_meses']} mes(es)\n"
            f"- **Productos con venta:** {len(df_raw[df_raw['Venta_Mensual'] > 0])} SKUs"
        )
    else:
        st.sidebar.info("ℹ️ Mostrando stock base por defecto. No se detectó coincidencia directa con la tabla de ventas.")

    # --- Sidebar: Parámetros ---
    st.sidebar.header("🎯 Cobertura de Stock por Ventas")
    meses_objetivo = st.sidebar.slider("Meses de cobertura deseados", 0.5, 6.0, 1.5, 0.5)
    meses_critico = st.sidebar.slider("Alerta Crítica (< meses)", 0.1, max(0.2, meses_objetivo - 0.1), min(0.5, meses_objetivo - 0.1), 0.1)
    meses_excedente = st.sidebar.slider("Alerta Excedente (> meses)", meses_objetivo + 0.5, 12.0, 3.0, 0.5)

    st.sidebar.markdown("---")
    stock_min_defecto = st.sidebar.number_input("Stock mín. (Productos sin venta)", min_value=0, value=10, step=5)

    # Lógica de cálculo
    df = clasificar_stock(df_raw, meses_critico, meses_objetivo, meses_excedente, stock_min_defecto)
    urgentes = df[df["Estado"].isin(["Crítico", "Bajo"])].sort_values("Cantidad_A_Producir", ascending=False)

    # --- UI Principal ---
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

    st.write("## 📊 Análisis Visual")
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

if __name__ == "__main__":
    main()