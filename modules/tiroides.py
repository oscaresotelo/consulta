import math
import streamlit as st

def render_modulo_tiroides(paciente_activo: dict):
    st.header("🩺 Módulo de Patología Tiroidea")
    
    tab1, tab2, tab3 = st.tabs(["Estratificación ACR TI-RADS", "Cálculo Volumétrico (3D)", "Dosis de Levotiroxina"])
    
    with tab1:
        st.subheader("Clasificación Ecográfica ACR TI-RADS")
        
        col1, col2 = st.columns(2)
        with col1:
            composicion = st.selectbox("Composición", [
                ("Quístico / Casi completamente quístico (0 pts)", 0),
                ("Espongiforme (0 pts)", 0),
                ("Misto quístico y sólido (1 pt)", 1),
                ("Sólido / Casi completamente sólido (2 pts)", 2)
            ], format_func=lambda x: x[0])
            
            ecogenicidad = st.selectbox("Ecogenicidad", [
                ("Anecoico (0 pts)", 0),
                ("Hiperecoico / Isoecoico (1 pt)", 1),
                ("Hipoecoico (2 pts)", 2),
                ("Muy hipoecoico (3 pts)", 3)
            ], format_func=lambda x: x[0])
            
            forma = st.selectbox("Forma", [
                ("Más ancho que alto (0 pts)", 0),
                ("Más alto que ancho (1 pt)", 1)
            ], format_func=lambda x: x[0])
            
        with col2:
            margen = st.selectbox("Márgenes", [
                ("Liso (0 pts)", 0),
                ("Mal definido (0 pts)", 0),
                ("Lobulado / Irregular (2 pts)", 2),
                ("Extensión extratiroidea (3 pts)", 3)
            ], format_func=lambda x: x[0])
            
            focos = st.multiselect("Focos Ecogénicos", [
                ("Sin focos / Sombra acústica posterior (0 pts)", 0),
                ("Grandes artefactos en cola de cometa (0 pts)", 0),
                ("Macrocalcificaciones (1 pt)", 1),
                ("Calcificaciones periféricas / en cáscara (2 pts)", 2),
                ("Puntos ecogénicos punctiformes / Microcalcificaciones (3 pts)", 3)
            ], format_func=lambda x: x[0])
            
        puntos_focos = sum([f[1] for f in focos])
        puntaje_total = composicion[1] + ecogenicidad[1] + forma[1] + margen[1] + puntos_focos
        
        st.markdown("---")
        st.write(f"**Puntaje TI-RADS Acumulado:** `{puntaje_total} puntos`")
        
        if puntaje_total == 0:
            st.success("TR1 - Benigno (Riesgo < 2%). No requiere PAA.")
        elif puntaje_total == 2:
            st.success("TR2 - No Sospechoso (Riesgo < 2%). No requiere PAA.")
        elif puntaje_total == 3:
            st.info("TR3 - Levemente Sospechoso (Riesgo ~5%). PAA si es ≥ 2.5 cm. Seguimiento si es ≥ 1.5 cm.")
        elif 4 <= puntaje_total <= 6:
            st.warning("TR4 - Moderadamente Sospechoso (Riesgo 5-20%). PAA si es ≥ 1.5 cm. Seguimiento si es ≥ 1.0 cm.")
        else:
            st.error("TR5 - Altamente Sospechoso (Riesgo > 20%). PAA si es ≥ 1.0 cm. Seguimiento si es ≥ 0.5 cm.")

    with tab2:
        st.subheader("Cálculo Volumétrico de Nódulo y Tasa de Crecimiento")
        c1, c2, c3 = st.columns(3)
        d1 = c1.number_input("Diámetro 1 (mm)", min_value=0.0, value=12.0)
        d2 = c2.number_input("Diámetro 2 (mm)", min_value=0.0, value=15.0)
        d3 = c3.number_input("Diámetro 3 (mm)", min_value=0.0, value=10.0)
        
        # Volumen elipsoide: D1 * D2 * D3 * (pi / 6)
        volumen_ml = (d1 * d2 * d3 * math.pi) / 6000.0
        st.metric("Volumen Estimado del Nódulo", f"{volumen_ml:.2f} mL / cm³")

    with tab3:
        st.subheader("Ajuste de Dosis de Levotiroxina (LT4)")
        peso = st.number_input("Peso Actual del Paciente (kg)", min_value=30.0, max_value=200.0, value=70.0)
        objetivo = st.radio("Objetivo Terapéutico", ["Sustitución Estándar (Hipotiroidismo)", "Supresión CDT (Cáncer Diferenciado de Tiroides)"])
        
        if objetivo == "Sustitución Estándar (Hipotiroidismo)":
            dosis_mcg = peso * 1.6
            st.info(f"Dosis teórica estimada (1.6 mcg/kg/día): **{dosis_mcg:.0f} mcg/día**")
        else:
            dosis_mcg = peso * 2.1
            st.warning(f"Dosis de supresión estimada (2.0 - 2.2 mcg/kg/día): **{dosis_mcg:.0f} mcg/día**")
            
        comerciales = [25, 50, 75, 88, 100, 112, 125, 137, 150, 175, 200]
        cercana = min(comerciales, key=lambda x: abs(x - dosis_mcg))
        st.success(f"Dosis comercial recomendada más cercana: **{cercana} mcg/día**")