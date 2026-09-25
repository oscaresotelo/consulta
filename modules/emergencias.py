import streamlit as st

def render_modulo_emergencias():
    st.header("⚡ Emergencias y Pruebas Especiales")
    
    tab1, tab2, tab3 = st.tabs(["Tormenta Tiroidea (Burch-Wartofsky)", "Washout TAC Suprarrenal", "Equivalencia Steroidea"])
    
    with tab1:
        st.subheader("Escala de Burch-Wartofsky (BWPS)")
        
        pts_temp = st.selectbox("Temperatura Corporal (°C)", [
            ("< 37.7 °C (0 pts)", 0),
            ("37.8 - 38.2 °C (5 pts)", 5),
            ("38.3 - 38.8 °C (10 pts)", 10),
            ("38.9 - 39.4 °C (15 pts)", 15),
            ("39.5 - 39.9 °C (20 pts)", 20),
            ("≥ 40.0 °C (30 pts)", 30)
        ], format_func=lambda x: x[0])[1]
        
        pts_cns = st.selectbox("Efectos en Sistema Nervioso Central", [
            ("Ausente (0 pts)", 0),
            ("Leve: Agitación (10 pts)", 10),
            ("Moderado: Delirio, psicosis, letargia (20 pts)", 20),
            ("Grave: Coma, convulsiones (30 pts)", 30)
        ], format_func=lambda x: x[0])[1]
        
        pts_gi = st.selectbox("Disfunción Gastrointestinal / Hepática", [
            ("Ausente (0 pts)", 0),
            ("Moderada: Diarrea, náuseas, vómitos, dolor (10 pts)", 10),
            ("Grave: Ictericia no explicada (20 pts)", 20)
        ], format_func=lambda x: x[0])[1]
        
        pts_cv = st.selectbox("Taquicardia (LPM)", [
            ("< 110 LPM (0 pts)", 0),
            ("110 - 119 LPM (5 pts)", 5),
            ("120 - 129 LPM (10 pts)", 10),
            ("130 - 139 LPM (15 pts)", 15),
            ("≥ 140 LPM (25 pts)", 25)
        ], format_func=lambda x: x[0])[1]
        
        bwps_total = pts_temp + pts_cns + pts_gi + pts_cv
        st.write(f"**Puntaje Total BWPS:** `{bwps_total} puntos`")
        
        if bwps_total >= 45:
            st.error("🚨 Altamente sugestivo de Tormenta Tiroidea. Iniciar tratamiento agresivo inmediato.")
        elif 25 <= bwps_total < 45:
            st.warning("⚠️ Impending Storm (Amenaza de Tormenta Tiroidea). Evaluar manejo intensivo.")
        else:
            st.success("Improbable Tormenta Tiroidea.")

    with tab2:
        st.subheader("Cálculo de Lavamiento (Washout) de Adenoma Suprarrenal")
        st.caption("Requiere Tomografía de 3 fases: Sin contraste (NC), Fase Portal (1 min) y Fase Tardía (15 min).")
        
        hu_nc = st.number_input("Atenuación Sin Contraste (HU_NC)", value=12.0)
        hu_venosa = st.number_input("Atenuación Fase Portal/Venosa (HU_V)", value=65.0)
        hu_tardia = st.number_input("Atenuación Fase Tardía a 15 min (HU_T)", value=28.0)
        
        if hu_venosa > hu_nc and hu_venosa > hu_tardia:
            apw = ((hu_venosa - hu_tardia) / (hu_venosa - hu_nc)) * 100
            rpw = ((hu_venosa - hu_tardia) / hu_venosa) * 100
            
            col1, col2 = st.columns(2)
            col1.metric("Washout Absoluto (APW)", f"{apw:.1f} %")
            col2.metric("Washout Relativo (RPW)", f"{rpw:.1f} %")
            
            if apw >= 60 or rpw >= 40:
                st.success("Patrón compatible con **Adenoma Benigno** (Washout Rápido).")
            else:
                st.warning("Patrón **Atípico / Indeterminado** (Bajo Washout). Considerar resonancia o biopsia.")

    with tab3:
        st.subheader("Equivalencia de Glucocorticoides")
        dosis_ref = st.number_input("Dosis de Hidrocortisona (mg)", min_value=1.0, value=20.0)
        
        st.write("Dosis equivalentes en otros corticoides:")
        st.write(f"* **Prednisona / Meprednisona:** {dosis_ref * (5/20):.2f} mg")
        st.write(f"* **Metilprednisolona:** {dosis_ref * (4/20):.2f} mg")
        st.write(f"* **Dexametasona:** {dosis_ref * (0.75/20):.2f} mg")
        st.write(f"* **Deflazacort:** {dosis_ref * (6/20):.2f} mg")