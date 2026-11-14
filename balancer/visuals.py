"""Presentation shared by the Streamlit pages."""
from html import escape

import plotly.graph_objects as go
import streamlit as st

from balancer.config import LEVEL_COLORS


def theme() -> None:
    st.html(
        """
<style>
:root { --gold: #e4ba70; --muted: #a9a6b2; }
[data-testid="stMainBlockContainer"] {
    max-width: 1220px; padding: 2.25rem 3rem 4rem; margin-inline: auto;
}
[data-testid="stHeader"] { background: #111216; }
[data-testid="stAppDeployButton"] { display: none; }
[data-testid="stFileUploaderDropzoneInstructions"] { display: none; }
[data-testid="stFileUploaderDropzone"] button { font-size: 0; }
[data-testid="stFileUploaderDropzone"] button::after { content: "Parcourir…"; font-size: .94rem; }
[data-testid="stSidebar"] { background: #17181e; border-right: 1px solid #292933; }
[data-testid="stSidebarContent"] { padding-top: 1.2rem; }
[data-testid="stSidebar"] [data-testid="stRadio"] label { padding: .35rem 0; }
[data-testid="stSidebar"] hr { margin: 1.4rem 0; }
h1, h2, h3 { letter-spacing: -.035em; }
h1 { font-weight: 730; font-size: clamp(2.15rem, 4vw, 3.32rem); }
[data-testid="stCaptionContainer"] p { color: var(--muted); }
[data-testid="stText"], [data-testid="stText"] pre {
    font-family: inherit; white-space: pre-wrap; overflow-wrap: anywhere;
}
[data-testid="stMetric"] {
    border: 1px solid #36343c; padding: .85rem 1rem; border-radius: 10px; background: #191b21;
}
[data-testid="stMetricValue"] { color: #f8eee0; font-weight: 650; }
[data-testid="stMetricLabel"] p { color: #bfbac6; }
[data-testid="stVerticalBlockBorderWrapper"] { border-color: #393640; }
.brand { display: flex; align-items: center; gap: .7rem; padding: .4rem 0 1.3rem; }
.brand-mark { color: var(--gold); font: 700 1.85rem Georgia, serif; line-height: 1; }
.brand-title { color: #f5f0e8; font-weight: 800; letter-spacing: .13em; font-size: .85rem; }
.brand-subtitle { color: var(--muted); font-size: .82rem; margin-top: .28rem; }
.section-label { color: var(--gold); text-transform: uppercase; font-size: .75rem;
    letter-spacing: .16em; font-weight: 750; margin: .2rem 0 -.65rem; }
@media (max-width: 800px) {
    [data-testid="stMainBlockContainer"] { padding: 2.5rem 1.1rem; }
}
</style>
        """
    )


def title(label: str, heading: str, note: str) -> None:
    st.html(f'<p class="section-label">{label}</p>')
    st.title(heading)
    st.caption(note)


def level_chart(stats: dict) -> go.Figure:
    levels = stats["levels"][:20]
    flagged = {entry["level"] for entry in stats["findings"]}
    labels = [escape(row["level"]) for row in levels]
    rates = [row["success_rate"] for row in levels]
    figure = go.Figure(
        go.Bar(
            x=rates,
            y=labels,
            orientation="h",
            text=[f"{rate:.1f} %".replace(".", ",") for rate in rates],
            textposition="outside",
            customdata=[[row["n"], row["avg_attempts"]] for row in levels],
            marker={"color": [
                LEVEL_COLORS["accent"] if row["level"] in flagged else LEVEL_COLORS["context"]
                for row in levels
            ]},
            hovertemplate="%{y}<br>%{x:.1f} % de réussite<br>%{customdata[0]} observations"
                          "<br>%{customdata[1]:.2f} tentatives en moyenne<extra></extra>",
        )
    )
    figure.update_layout(height=min(710, max(285, 38 * len(levels) + 65)), bargap=0.38)
    figure.update_xaxes(range=[0, 114], tickvals=[0, 25, 50, 75, 100], ticktext=["0 %", "25 %", "50 %", "75 %", "100 %"])
    figure.update_yaxes(autorange="reversed", automargin=True, showgrid=False)
    return style_chart(figure)


def trend_chart(trend: list[dict]) -> go.Figure:
    figure = go.Figure(go.Scatter(
        x=[item["period"] for item in trend],
        y=[item["success_rate"] for item in trend],
        customdata=[item["n"] for item in trend],
        mode="lines+markers",
        line={"color": LEVEL_COLORS["accent"], "width": 3},
        marker={"size": 7},
        hovertemplate="%{x|%d/%m/%Y}<br>%{y:.1f} % de réussite<br>%{customdata} observations<extra></extra>",
    ))
    figure.update_layout(height=320)
    figure.update_xaxes(type="date", tickformat="%d/%m", showgrid=False)
    figure.update_yaxes(range=[0, 100], ticksuffix=" %")
    return style_chart(figure)


def style_chart(figure: go.Figure) -> go.Figure:
    figure.update_layout(
        template="plotly_dark", paper_bgcolor="#111216", plot_bgcolor="#111216",
        font={"color": "#eee9e4", "size": 13}, separators=", ",
        margin={"t": 12, "r": 24, "b": 38, "l": 8},
    )
    figure.update_xaxes(gridcolor="#34323d", zeroline=False)
    figure.update_yaxes(gridcolor="#34323d", zeroline=False)
    return figure
