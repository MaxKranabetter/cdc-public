import streamlit as st
import plotly.graph_objects as go

def build_risk_profile_overview_section(risk_profile_data: dict[str, list[tuple[int, float]]]):
    if len(risk_profile_data) == 0:
        st.info("No risk profile data available.")
        return
    
    fig = go.Figure()
    for building_id, profile in risk_profile_data.items():
        x = [int(return_period) for return_period, _ in profile]
        y = [max(float(depth[0]), 0) for _, depth in profile]
        fig.add_trace(go.Scatter(x=x, y=y, mode='lines', line_shape='hv', name=building_id))

    fig.update_layout(
        title="Risk Profile",
        xaxis=dict(
            title="Return Period (years)",
            type="log",
            autorange="reversed"
        ),
        yaxis_title="Flood Depth (m)",
        hovermode="x unified"
    )

    st.plotly_chart(fig, width="stretch", config={"staticPlot": True})