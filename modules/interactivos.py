import numpy as np
import plotly.graph_objects as go
import streamlit as st


def render_simulador_agp():
    st.header("📊 Simulador de Perfil Ambulatorio de Glucosa (AGP)")
    st.caption(
        "Ajustá los parámetros interactivos para simular el impacto en la curva"
        " de 24 horas, el Tiempo en Rango (TIR) y el riesgo de hipoglucemias."
    )

    col_ctrl, col_graf = st.columns([1, 2])

    with col_ctrl:
        st.subheader("Parámetros de Entrada")
        basal = st.slider("Insulina Basal (UI/día)", 10, 60, 24)
        carbos_almuerzo = st.slider("Carbohidratos Almuerzo (g)", 10, 120, 60)
        sensibilidad = st.slider(
            "Factor de Sensibilidad (ISF)",
            15,
            80,
            40,
            help="mg/dL que reduce 1 UI de insulina",
        )
        actividad = st.select_slider(
            "Actividad Física Tarde",
            options=["Reposo", "Caminata Leve", "Ejercicio Moderado"],
            value="Reposo",
        )

    # Factor de reducción por actividad
    factor_act = 0.0
    if actividad == "Caminata Leve":
        factor_act = 15.0
    elif actividad == "Ejercicio Moderado":
        factor_act = 35.0

    # Simulación de curva glucémica
    horas = np.linspace(0, 24, 144)  # Muestra cada 10 min
    base_glu = 160 - (basal * 1.8)
    pico_almuerzo = (carbos_almuerzo * 1.6) * np.exp(
        -(((horas - 14) / 1.8) ** 2)
    )
    pico_cena = (carbos_almuerzo * 1.1) * np.exp(-(((horas - 21) / 1.8) ** 2))
    caida_ejercicio = factor_act * np.exp(-(((horas - 17) / 2.0) ** 2))

    glucemia = np.clip(
        base_glu + pico_almuerzo + pico_cena - caida_ejercicio, 40, 350
    )

    # Cálculo de métricas CGM
    tir = np.sum((glucemia >= 70) & (glucemia <= 180)) / len(glucemia) * 100
    tar = np.sum(glucemia > 180) / len(glucemia) * 100
    tbr = np.sum(glucemia < 70) / len(glucemia) * 100

    with col_graf:
        fig = go.Figure()

        # Zonas objetivo
        fig.add_hrect(
            y0=70,
            y1=180,
            fillcolor="rgba(46, 204, 113, 0.15)",
            line_width=0,
            annotation_text="Rango Objetivo (70-180 mg/dL)",
        )
        fig.add_hrect(
            y0=0,
            y1=70,
            fillcolor="rgba(231, 76, 60, 0.15)",
            line_width=0,
            annotation_text="Hipoglucemia (< 70 mg/dL)",
        )
        fig.add_hrect(
            y0=180,
            y1=350,
            fillcolor="rgba(241, 196, 15, 0.10)",
            line_width=0,
            annotation_text="Hiperglucemia (> 180 mg/dL)",
        )

        fig.add_trace(
            go.Scatter(
                x=horas,
                y=glucemia,
                mode="lines",
                name="Glucemia Estimada",
                line=dict(color="#2980b9", width=3),
            )
        )

        fig.update_layout(
            title="Curva Glucémica Proyectada (24 Horas)",
            xaxis_title="Hora del Día",
            yaxis_title="Glucemia (mg/dL)",
            yaxis=dict(range=[30, 360]),
            height=380,
        )

        st.plotly_chart(fig, use_container_width=True)

        m1, m2, m3 = st.columns(3)
        m1.metric("Tiempo en Rango (TIR)", f"{tir:.1f} %", delta="Meta ≥ 70%")
        m2.metric("Tiempo Alto (TAR)", f"{tar:.1f} %", delta="Meta ≤ 25%")
        m3.metric(
            "Tiempo Bajo (TBR)",
            f"{tbr:.1f} %",
            delta="- Riesgo" if tbr > 4 else "Normal",
            delta_color="inverse",
        )


def render_calcio_osteoporosis():
    st.header("🦴 Metabolismo Cánhico y Osteoporosis")

    tab1, tab2 = st.tabs(
        ["Calcio Corregido y Eje PTH", "Clasificación DMO y Riesgo FRAX®"]
    )

    with tab1:
        st.subheader("Ajuste de Calcemia y Diagnóstico de Eje")

        c1, c2, c3 = st.columns(3)
        calcio = c1.number_input("Calcio Total (mg/dL)", value=9.2, step=0.1)
        albumina = c2.number_input("Albúmina Sérica (g/dL)", value=4.0, step=0.1)
        pth = c3.number_input(
            "PTH Intacta (pg/mL)",
            value=35.0,
            step=1.0,
            help="Valor normal: 15-65 pg/mL",
        )

        calcio_corregido = calcio + 0.8 * (4.0 - albumina)

        st.markdown("---")
        col_res1, col_res2 = st.columns(2)

        with col_res1:
            st.metric(
                "Calcio Corregido por Albúmina", f"{calcio_corregido:.2f} mg/dL"
            )
            if calcio_corregido < 8.5:
                st.warning("⚠️ Hipocalcemia")
            elif 8.5 <= calcio_corregido <= 10.2:
                st.success("✅ Calcemia dentro del rango normal")
            else:
                st.error("🚨 Hipercalcemia")

        with col_res2:
            st.subheader("Interpretación Clinico-Laboratorial")
            if calcio_corregido > 10.2 and pth > 65:
                st.error(
                    "Sugerente de **Hiperparatiroidismo Primario (HPTP)**."
                )
            elif calcio_corregido < 8.5 and pth > 65:
                st.warning(
                    "Sugerente de **Hiperparatiroidismo Secundario**"
                    " (Deficit Vit D / ERC)."
                )
            elif calcio_corregido < 8.5 and pth < 15:
                st.error("Sugerente de **Hipoparatiroidismo**.")
            else:
                st.info("Eje Calcio/PTH sin alteración evidente.")

    with tab2:
        st.subheader("Evaluación de Densitometría Ósea (DMO)")

        col_dmo1, col_dmo2 = st.columns(2)
        with col_dmo1:
            t_score_lumbar = st.number_input(
                "T-Score Columna Lumbar (L1-L4)", value=-1.8, step=0.1
            )
            t_score_femor = st.number_input(
                "T-Score Cuello Femoral", value=-2.6, step=0.1
            )

        with col_dmo2:
            st.write("**Factores de Riesgo Clínico (FRAX Simplificado):**")
            fx_previa = st.checkbox("Fractura por fragilidad previa")
            corticoides = st.checkbox("Uso prolongado de glucocorticoides")
            fumador = st.checkbox("Tabaquismo activo")

        peor_t_score = min(t_score_lumbar, t_score_femor)

        st.markdown("---")
        st.subheader("Diagnóstico OMS")

        if peor_t_score >= -1.0:
            st.success(
                f"**Masa Ósea Normal** (Peor T-Score: {peor_t_score:.1f})"
            )
        elif -2.5 < peor_t_score < -1.0:
            st.warning(f"**Osteopenia** (Peor T-Score: {peor_t_score:.1f})")
            if fx_previa or corticoides:
                st.error(
                    "⚠️ Osteopenia con factor de alto riesgo: Considerar"
                    " inicio de tratamiento farmacológico (Bisfosfonatos /"
                    " Denosumab)."
                )
        else:
            if fx_previa:
                st.error(
                    f"**Osteoporosis Severa / Establecida** (T-Score:"
                    f" {peor_t_score:.1f} + Fractura)"
                )
            else:
                st.error(
                    f"**Osteoporosis** (Peor T-Score: {peor_t_score:.1f})"
                )