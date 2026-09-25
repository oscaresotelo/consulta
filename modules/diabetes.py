import streamlit as st

def render_modulo_diabetes(paciente_activo: dict):
    st.header("🩸 Módulo de Diabetología y Riesgo Renal")
    
    tab1, tab2 = st.tabs(["Insulinoterapia (Basal-Bolo / ICR / ISF)", "Estimación TFG (CKD-EPI 2021)"])
    
    with tab1:
        st.subheader("Parámetros de Corrección e Ingesta")
        
        peso = st.number_input("Peso Paciente (kg)", min_value=40.0, value=70.0, key="diab_peso")
        tdi = st.number_input("Dosis Diaria Total de Insulina (TDI en Unidades)", min_value=5.0, value=peso * 0.5)
        
        col1, col2 = st.columns(2)
        with col1:
            icr = 500 / tdi if tdi > 0 else 0
            st.metric("Ratio Insulina / Carbohidratos (ICR)", f"1 UI por {icr:.1f} g HC", delta="Regla de los 500")
            
        with col2:
            isf = 1800 / tdi if tdi > 0 else 0
            st.metric("Factor de Sensibilidad (ISF)", f"{isf:.1f} mg/dL por 1 UI", delta="Regla de los 1800 (Análogos)")
            
        st.markdown("---")
        st.subheader("Calculadora de Bolo Corrector + Comida")
        c1, c2 = st.columns(2)
        glu_actual = c1.number_input("Glucemia Actual (mg/dL)", value=180)
        glu_objetivo = c2.number_input("Glucemia Objetivo (mg/dL)", value=100)
        hc_consumir = st.number_input("Carbohidratos a Consumir (g)", value=45)
        
        if isf > 0 and icr > 0:
            bolo_correccion = max(0.0, (glu_actual - glu_objetivo) / isf)
            bolo_comida = hc_consumir / icr
            bolo_total = bolo_correccion + bolo_comida
            
            st.success(f"**Bolo Sugerido:** {bolo_total:.1f} UI "
                       f"({bolo_comida:.1f} UI por alimentos + {bolo_correccion:.1f} UI por corrección)")

    with tab2:
        st.subheader("Estimación de Función Renal (CKD-EPI 2021 sin raza)")
        
        creat = st.number_input("Creatinina Sérica (mg/dL)", min_value=0.2, value=1.0, step=0.1)
        edad = st.number_input("Edad del Paciente", min_value=18, max_value=110, value=50)
        sexo = st.radio("Sexo Biológico", ["Femenino", "Masculino"])
        
        # Fórmula CKD-EPI 2021
        is_female = (sexo == "Femenino")
        kappa = 0.7 if is_female else 0.9
        alpha = -0.241 if is_female else -0.302
        gender_mult = 1.012 if is_female else 1.0
        
        scr_k = creat / kappa
        vfg = 142 * (min(scr_k, 1.0) ** alpha) * (max(scr_k, 1.0) ** -1.200) * (0.9938 ** edad) * gender_mult
        
        st.metric("Tasa de Filtración Glomerular (eGFR)", f"{vfg:.1f} mL/min/1.73m²")
        
        if vfg >= 90:
            st.success("G1: Función renal normal o elevada.")
        elif vfg >= 60:
            st.info("G2: Levemente disminuida.")
        elif vfg >= 45:
            st.warning("G3a: Disminuida de leve a moderada.")
        elif vfg >= 30:
            st.warning("G3b: Disminuida de moderada a grave.")
        elif vfg >= 15:
            st.error("G4: Gravemente disminuida.")
        else:
            st.error("G5: Fallo renal.")