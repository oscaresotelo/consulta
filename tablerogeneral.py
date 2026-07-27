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
# DATOS
# ============================================================
def get_db_connection():
    return sqlite3.connect("minerva.db", check_same_thread=False)

@st.cache_data(ttl=300)
def load_data():
    conn = get_db_connection()
    query = """
    SELECT r.nombre AS Producto, e.descripcion AS Envase, SUM(s.cantidad) AS Cantidad
    FROM stock_productos_envasados s
    JOIN recetas r ON s.receta_id = r.id
    JOIN envases e ON s.envase_id = e.id
    JOIN productos p ON p.id_receta = r.id AND p.envase_id = e.id
    WHERE s.cliente_id = 6 AND p.activo = 1
    GROUP BY r.nombre, e.descripcion
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# ============================================================
# LÓGICA DE DECISIÓN
# ============================================================
def clasificar_stock(df, critico, bajo, excedente):
    def estado(cant):
        if cant < critico:
            return "Crítico"
        elif cant < bajo:
            return "Bajo"
        elif cant <= excedente:
            return "Normal"
        else:
            return "Excedente"

    def accion(cant):
        if cant < critico:
            return f"Producir urgente (faltan {int(bajo - cant)} u. para salir de zona baja)"
        elif cant < bajo:
            return f"Reponer pronto (sugerido +{int(excedente - cant)} u.)"
        elif cant <= excedente:
            return "Stock saludable, sin acción"
        else:
            return "Evaluar sobreproducción / redistribuir"

    df = df.copy()
    df["Estado"] = df["Cantidad"].apply(estado)
    df["Accion_Recomendada"] = df["Cantidad"].apply(accion)
    return df

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
# COMPONENTE HTML/JS: TABLA INTERACTIVA (orden + búsqueda instantánea)
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
      const cols = ["Producto","Envase","Cantidad","Estado","Accion_Recomendada"];
      const labels = ["Producto","Envase","Cantidad","Estado","Acción recomendada"];
      let sortCol = "Cantidad";
      let sortAsc = true;

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
        <div style="min-width:230px; background:white; border-left:6px solid {color};
             border-radius:12px; padding:14px 16px; box-shadow:0 3px 8px rgba(0,0,0,.06);">
          <div style="font-size:12px; font-weight:700; color:{color}; text-transform:uppercase;">{row['Estado']}</div>
          <div style="font-size:15px; font-weight:600; margin:4px 0;">{row['Producto']}</div>
          <div style="font-size:12px; color:#64748B;">{row['Envase']} · {row['Cantidad']} u.</div>
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
    st.title("📦 Minerva Inventory Insight")
    st.caption("Panel interactivo de stock con recomendaciones automáticas de producción/reposición")
    st.markdown("---")

    df_raw = load_data()
    if df_raw.empty:
        st.warning("No se encontraron registros activos.")
        return

    # --- Sidebar: umbrales configurables por el usuario ---
    st.sidebar.header("⚙️ Umbrales de decisión")
    critico = st.sidebar.slider("Límite Crítico (<)", 0, 50, 5)
    bajo = st.sidebar.slider("Límite Bajo (<)", critico + 1, 100, 15)
    excedente = st.sidebar.slider("Límite Excedente (>)", bajo + 1, 500, 80)
    st.sidebar.caption("Ajustá los umbrales y las recomendaciones se recalculan al instante.")

    df = clasificar_stock(df_raw, critico, bajo, excedente)
    urgentes = df[df["Estado"].isin(["Crítico", "Bajo"])].sort_values("Cantidad")

    # --- Tabla interactiva (arriba) ---
    st.markdown("## 📋 Detalle de Inventario")
    render_interactive_table(df)
    st.markdown("---")

    # --- KPIs animados ---
    render_kpi_cards(
        total_skus=len(df),
        stock_total=int(df["Cantidad"].sum()),
        criticos=len(df[df["Estado"] == "Crítico"]),
        bajos=len(df[df["Estado"] == "Bajo"]),
        excedentes=len(df[df["Estado"] == "Excedente"]),
    )

    # --- Panel de acción prioritaria ---
    st.write("### 🚨 Acción prioritaria")
    render_priority_panel(urgentes)

    st.write("## 📊 Análisis Visual")
    col_g1, col_g2 = st.columns([2, 1])

    with col_g1:
        top20 = df.sort_values("Cantidad").head(20)
        fig_bar = px.bar(
            top20, x="Cantidad", y="Producto", orientation="h",
            color="Estado", color_discrete_map=ESTADO_COLOR,
            title="Productos con menor stock (ordenados por urgencia)",
        )
        fig_bar.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_g2:
        estado_counts = df["Estado"].value_counts().reset_index()
        estado_counts.columns = ["Estado", "Cantidad_SKUs"]
        fig_pie = px.pie(
            estado_counts, values="Cantidad_SKUs", names="Estado",
            color="Estado", color_discrete_map=ESTADO_COLOR,
            hole=0.45, title="SKUs por estado de stock",
        )
        fig_pie.update_layout(margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig_pie, use_container_width=True)

    # Treemap: visión global de dónde está inmovilizado el stock
    fig_tree = px.treemap(
        df, path=["Envase", "Producto"], values="Cantidad",
        color="Estado", color_discrete_map=ESTADO_COLOR,
        title="Distribución de stock por envase y producto (tamaño = cantidad, color = estado)",
    )
    fig_tree.update_layout(margin=dict(t=40, b=0, l=0, r=0))
    st.plotly_chart(fig_tree, use_container_width=True)

    # --- Descarga de la lista de acción ---
    csv = urgentes.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Descargar lista de productos a reponer/producir",
        data=csv,
        file_name="productos_a_reponer.csv",
        mime="text/csv",
    )

if __name__ == "__main__":
    main()