"""Streamlit entry point for local game-balance analysis."""
import logging
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from balancer.agent import AgentError, run_analysis
from balancer.analytics import analyze, load_csv
from balancer.config import DATABASE, DEMO, MODEL_CHOICES, STATUS_LABELS, app_logger
from balancer.ollama import OllamaClient, OllamaError
from balancer.storage import Store, export_html, export_recommendations
from balancer.visuals import level_chart, theme, title, trend_chart

PAGE_NAMES = ("Analyse", "Agent local", "Recommandations", "Historique")
SIMULATION_LABEL = "Simulation · Gravity Chain"


def number(value: float | None, digits: int = 1, unit: str = "") -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",") + unit


def record_label(record: dict) -> str:
    origin = " · Simulation" if record["is_demo"] else ""
    stamp = record["created_at"][:16].replace("T", " ")
    return f"#{record['id']}  {record['name']} · {stamp} UTC{origin}"


def open_page(page: str) -> None:
    st.session_state.page = page


def load_analysis(store: Store, data: bytes, name: str, is_demo: bool) -> None:
    try:
        frame, warnings = load_csv(data)
        stats = analyze(frame)
        st.session_state.pending_analysis_id = store.save_analysis(name, is_demo, stats, warnings)
    except ValueError as exc:
        st.error(str(exc))
        return
    except (OSError, sqlite3.Error):
        app_logger().exception("Impossible d'enregistrer une analyse")
        st.error("Impossible d’enregistrer cette analyse. Vérifiez l’espace disque et l’accès au dossier.")
        return
    st.rerun()


def select_analysis(analyses: list[dict]) -> dict | None:
    if not analyses:
        return None
    by_id = {record["id"]: record for record in analyses}
    pending = st.session_state.pop("pending_analysis_id", None)
    if pending in by_id:
        st.session_state.analysis_id = pending
    if st.session_state.get("analysis_id") not in by_id:
        st.session_state.analysis_id = analyses[0]["id"]
    st.sidebar.selectbox(
        "Analyse active", list(by_id),
        format_func=lambda value: record_label(by_id[value]),
        key="analysis_id",
    )
    return by_id[st.session_state.analysis_id]


def import_section(store: Store, record: dict | None) -> None:
    with st.expander("Ajouter des données", expanded=record is None):
        st.caption("Un fichier CSV ou le jeu d’essai fictif fourni avec l’application.")
        left, right = st.columns([3, 2], gap="large")
        with left:
            with st.form("csv_upload"):
                file = st.file_uploader("Fichier de sessions (CSV, 20 Mio maximum)", type=["csv"])
                submit = st.form_submit_button("Analyser le CSV", width="stretch")
            if submit:
                if file is None:
                    st.warning("Choisissez un fichier CSV à analyser.")
                else:
                    name = Path(file.name).name[:120]
                    data = file.getvalue()
                    load_analysis(store, data, name, data == DEMO.read_bytes())
        with right:
            st.markdown("**Jeu de démonstration**")
            st.caption("Sessions synthétiques avec une étape de timing volontairement difficile.")
            if st.button("Charger la simulation", type="primary", width="stretch"):
                load_analysis(store, DEMO.read_bytes(), SIMULATION_LABEL, True)
            st.download_button(
                "Télécharger le CSV de démo", DEMO.read_bytes(), "gravity-chain-demo.csv",
                "text/csv", width="stretch",
            )


def show_summary(record: dict) -> None:
    stats = record["stats"]
    overview = stats["overview"]
    if record["is_demo"]:
        st.info("Simulation · Ces données ont été générées pour la démonstration.")
    warnings = record["warnings"]
    if warnings:
        warning_label = "point à lire" if len(warnings) == 1 else "points à lire"
        with st.expander(f"Qualité de l’import · {len(warnings)} {warning_label}"):
            for warning in warnings:
                st.text(warning)
    cards = st.columns(4)
    cards[0].metric("Sessions", number(overview["sessions"], 0))
    cards[1].metric("Étapes", number(overview["levels"], 0))
    cards[2].metric(
        "Réussite", number(overview["success_rate"], 1, " %"),
        help=f"Sur {overview['rows']} observations session-étape.",
    )
    cards[3].metric("Tentatives moyennes", number(overview["avg_attempts"], 2))
    st.subheader("Difficulté par étape")
    st.caption("Taux de réussite par observation. En doré, les étapes signalées par les règles d’analyse.")
    st.plotly_chart(level_chart(stats), config={"displayModeBar": False, "responsive": True})
    if len(stats["levels"]) > 20:
        st.caption("Les vingt premières étapes sont affichées ici. Le tableau couvre toutes les étapes.")
    findings = stats["findings"]
    if findings:
        st.subheader("Étapes à examiner")
        for entry in findings[:8]:
            with st.container(border=True):
                st.text(entry["level"])
                st.text(entry["reason"])
        if len(findings) > 8:
            st.caption(f"{len(findings)} étapes signalées au total. Le rapport HTML contient l’analyse.")
    else:
        st.caption("Aucune étape n’atteint les seuils de signalement sur cet import.")
    st.button("Examiner avec l’agent", on_click=open_page, args=("Agent local",), type="primary")
    with st.expander("Mesures par étape"):
        st.caption(stats["findings_method"])
        rows = [{
            "Étape": row["level"], "Observations": row["n"],
            "Réussite (%)": row["success_rate"], "Échec (%)": row["failure_rate"],
            "Tentatives": row["avg_attempts"], "Réaction (ms)": row["avg_reaction_ms"],
            "Précision (%)": row["avg_timing_accuracy_pct"], "Durée (s)": row["avg_duration_s"],
            "Progression (%)": row["avg_progress_pct"],
            "IC bas (%)": row["success_ci_low"], "IC haut (%)": row["success_ci_high"],
        } for row in stats["levels"]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Intervalles de Wilson à 95 %. Une cellule vide indique une mesure absente.")
    st.subheader("Évolution des performances")
    if stats["trend"]:
        st.caption("Résultats par jour UTC, pour les lignes datées. La composition des étapes peut varier.")
        st.plotly_chart(trend_chart(stats["trend"]), config={"displayModeBar": False})
    else:
        st.caption("Ajoutez des dates au champ played_at pour calculer l’évolution.")


def show_agent(store: Store, record: dict | None) -> None:
    title("Inférence sur ce PC", "Agent local", "Le modèle choisit des outils statistiques puis présente ses hypothèses et ses propositions.")
    model = st.selectbox("Modèle Ollama", MODEL_CHOICES)
    client = OllamaClient(model=model)
    state = client.status()
    if state["available"]:
        st.success(f"{model} disponible sur Ollama {state.get('version') or ''}".strip())
    else:
        st.warning(str(state["message"]))
        st.caption("Démarrez Ollama, téléchargez le modèle sélectionné, puis vérifiez à nouveau.")
        st.code(f"ollama pull {model}", language="powershell")
    if st.button("Vérifier la disponibilité"):
        st.rerun()
    if record is None:
        st.info("Chargez d’abord un CSV ou la simulation dans Analyse.")
        return
    if record["is_demo"]:
        st.info("Simulation · L’agent analyse le jeu de données fictif avec le modèle local.")
    previous = record.get("agent")
    if previous:
        st.subheader("Analyse IA enregistrée")
        st.text(previous["summary"])
        show_trace(previous)
        st.button("Ouvrir les recommandations", on_click=open_page, args=("Recommandations",), type="primary")
        st.caption("Chargez une nouvelle analyse si vous souhaitez conserver deux exécutions du modèle.")
        return
    if st.button("Lancer l’agent", disabled=not state["available"], type="primary"):
        with st.status("Analyse locale en cours…", expanded=True) as progress:
            def on_event(event: dict) -> None:
                st.text(str(event.get("message", "Traitement local")))
            try:
                result = run_analysis(client, record["stats"], on_event=on_event)
                store.save_agent(record["id"], result)
            except (AgentError, OllamaError) as exc:
                app_logger().warning("Analyse IA interrompue (%s)", type(exc).__name__)
                progress.update(label="Analyse locale interrompue", state="error")
                st.error(str(exc))
                return
            except ValueError as exc:
                progress.update(label="Rapport déjà enregistré", state="error")
                st.error(str(exc))
                return
            except (OSError, sqlite3.Error):
                app_logger().exception("Sauvegarde du rapport IA impossible")
                progress.update(label="Rapport non enregistré", state="error")
                st.error("Impossible d’enregistrer le rapport. Réessayez après avoir vérifié l’accès au dossier.")
                return
            progress.update(label="Analyse locale enregistrée", state="complete")
        st.rerun()


def show_trace(result: dict) -> None:
    st.caption(f"Modèle {result['model']} · {len(result['trace'])} appels d’outils enregistrés")
    runtime = result.get("metadata", {}).get("runtime", {})
    if runtime.get("running"):
        amount = number(runtime["vram_bytes"] / 1024**3, 2, " Gio") if runtime.get("vram_bytes") else "0 Gio"
        st.caption(f"Mesure pendant l’analyse · {runtime['device']} · VRAM du modèle {amount}")
    with st.expander("Consulter les appels d’outils"):
        for step in result["trace"]:
            st.text(f"{step['step']}. {step['tool']}")
            st.json({"arguments": step["args"], "résultat": step["result"]}, expanded=False)
        metadata = result.get("metadata")
        if metadata:
            st.json(metadata, expanded=False)


def show_recommendations(store: Store, record: dict | None) -> None:
    title("Validation humaine", "Recommandations", "Les décisions sont enregistrées dans l’historique de cette analyse.")
    result = record.get("agent") if record is not None else None
    if result is None:
        st.info("Lancez une analyse avec l’agent local pour obtenir des recommandations.")
        return
    if record["is_demo"]:
        st.info("Simulation · Ces propositions concernent les données fictives.")
    st.text(result["summary"])
    recommendations = result["recommendations"]
    if not recommendations:
        st.info("L’agent a terminé sans recommander de modification.")
    for rec in recommendations:
        with st.container(border=True):
            st.text(rec["level"])
            proposal, observations = st.columns([3, 2], gap="large")
            with proposal:
                st.markdown("**Modification à tester**")
                st.text(rec["proposal"])
                st.markdown("**Hypothèse**")
                st.text(rec["hypothesis"])
                st.markdown("**Justification**")
                st.text(rec["rationale"])
                st.markdown("**Confiance et limites**")
                st.text(f"{rec['confidence']} · {rec['limitations']}")
            with observations:
                st.markdown("**Problème observé**")
                st.text(rec["problem"])
                st.markdown("**Indicateurs vérifiables**")
                st.text("\n".join(rec["indicators"]))
            status_key = f"status_{record['id']}_{rec['id']}"
            chosen = st.selectbox(
                "Statut de la recommandation", list(STATUS_LABELS),
                index=list(STATUS_LABELS).index(rec["status"]),
                format_func=STATUS_LABELS.__getitem__, key=status_key,
            )
            if st.button("Enregistrer la décision", key=f"save_{status_key}", disabled=chosen == rec["status"]):
                try:
                    store.set_status(record["id"], rec["id"], chosen)
                except (OSError, sqlite3.Error):
                    app_logger().exception("Impossible d’enregistrer la décision")
                    st.error("La décision n’a pas pu être enregistrée. Réessayez.")
                else:
                    st.rerun()
    show_exports(record)


def show_exports(record: dict) -> None:
    st.subheader("Exporter l’analyse")
    prefix = f"gravity-chain-{record['id']}"
    columns = st.columns(3)
    columns[0].download_button(
        "Rapport HTML", export_html(record), f"{prefix}.html", "text/html", width="stretch",
    )
    if record.get("agent"):
        columns[1].download_button(
            "Recommandations JSON", export_recommendations(record, "json"),
            f"{prefix}-recommandations.json", "application/json", width="stretch",
        )
        columns[2].download_button(
            "Recommandations CSV", export_recommendations(record, "csv"),
            f"{prefix}-recommandations.csv", "text/csv", width="stretch",
        )


def show_history(record: dict | None, analyses: list[dict]) -> None:
    title("Résultats enregistrés sur ce PC", "Historique", "Comparez les imports et retrouvez leurs rapports et décisions.")
    if not record:
        st.info("Aucune analyse enregistrée.")
        return
    rows = [{
        "Analyse": row["id"],
        "Source": row["name"],
        "Origine": "Simulation" if row["is_demo"] else "Import",
        "Date (UTC)": row["created_at"][:16].replace("T", " "),
        "Sessions": row["stats"]["overview"]["sessions"],
        "Réussite (%)": row["stats"]["overview"]["success_rate"],
    } for row in analyses]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    alternatives = {row["id"]: row for row in analyses if row["id"] != record["id"]}
    if alternatives:
        other_id = st.selectbox(
            "Comparer l’analyse active avec", list(alternatives),
            format_func=lambda option: record_label(alternatives[option]),
        )
        comparison(record, alternatives[other_id])
    show_exports(record)


def comparison(record: dict, other: dict) -> None:
    if record["is_demo"] != other["is_demo"]:
        st.info("La comparaison inclut une simulation. Les écarts sont descriptifs.")
    left = {row["level"]: row["success_rate"] for row in record["stats"]["levels"]}
    right = {row["level"]: row["success_rate"] for row in other["stats"]["levels"]}
    levels = list(dict.fromkeys([*left, *right]))
    st.dataframe(pd.DataFrame([
        {
            "Étape": level, "Active (%)": left.get(level), "Comparée (%)": right.get(level),
            "Écart (points)": round(left[level] - right[level], 2) if level in left and level in right else None,
        }
        for level in levels
    ]), hide_index=True, width="stretch")
    st.caption("L’écart est calculé sur les étapes communes. Les populations peuvent différer.")


def main() -> None:
    st.set_page_config(page_title="Gravity Chain · AI Game Balancer", layout="wide", initial_sidebar_state="expanded")
    theme()
    app_logger()
    store = Store(DATABASE)
    analyses = store.list_analyses()
    with st.sidebar:
        st.html("""<div class="brand"><span class="brand-mark" aria-hidden="true">◈</span>
<div><div class="brand-title">GRAVITY CHAIN</div><div class="brand-subtitle">AI Game Balancer</div></div></div>""")
        page = st.radio("Navigation", PAGE_NAMES, key="page", label_visibility="collapsed")
        st.divider()
    active = select_analysis(analyses)
    record = store.get_analysis(active["id"]) if active else None
    if page == "Analyse":
        title("Télémétrie de jeu", "Équilibrage des étapes", "Repérez les ruptures de difficulté à partir des sessions de jeu.")
        import_section(store, record)
        if record is not None:
            show_summary(record)
    elif page == "Agent local":
        show_agent(store, record)
    elif page == "Recommandations":
        show_recommendations(store, record)
    else:
        show_history(record, analyses)


if __name__ == "__main__":
    try:
        main()
    except (OSError, sqlite3.Error):
        logging.getLogger("gravity-chain").exception("Application locale indisponible")
        st.error("Impossible d’accéder aux fichiers locaux. Vérifiez les droits sur le dossier et l’espace disque.")
