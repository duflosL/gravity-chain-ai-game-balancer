"""Local archive and portable exports for game balance reviews."""

from contextlib import contextmanager
import csv
from datetime import UTC, datetime
from html import escape
from io import StringIO
import json
from pathlib import Path
import sqlite3


STATUS_LABELS = {"pending": "En attente", "accepted": "Acceptée", "rejected": "Rejetée"}


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Store:
    """Store aggregate evidence and decisions without saving imported CSV rows."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    is_demo INTEGER NOT NULL CHECK (is_demo IN (0, 1)),
                    created_at TEXT NOT NULL,
                    stats TEXT NOT NULL,
                    warnings TEXT NOT NULL,
                    agent TEXT
                )
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_analysis(self, name: str, is_demo: bool, stats: dict, warnings: list[str]) -> int:
        created = datetime.now(UTC).isoformat(timespec="seconds")
        with self._connect() as db:
            result = db.execute(
                "INSERT INTO analyses (name, is_demo, created_at, stats, warnings) VALUES (?, ?, ?, ?, ?)",
                (name, int(is_demo), created, _dump(stats), _dump(warnings)),
            )
            return result.lastrowid

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict:
        values = dict(row)
        values["is_demo"] = bool(values["is_demo"])
        for key in ("stats", "warnings", "agent"):
            values[key] = json.loads(values[key]) if values[key] is not None else None
        return values

    def get_analysis(self, analysis_id: int) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
            if row is None:
                raise KeyError(f"Analyse {analysis_id} introuvable.")
            return self._decode(row)

    def list_analyses(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM analyses ORDER BY id DESC").fetchall()
            return [self._decode(row) for row in rows]

    def save_agent(self, analysis_id: int, result: dict) -> None:
        with self._connect() as db:
            changed = db.execute("UPDATE analyses SET agent = ? WHERE id = ? AND agent IS NULL",
                                 (_dump(result), analysis_id)).rowcount
            if changed == 0:
                exists = db.execute("SELECT 1 FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
                if exists is None:
                    raise KeyError(f"Analyse {analysis_id} introuvable.")
                raise ValueError("Cette analyse possède déjà un rapport IA. Créez une nouvelle analyse pour lancer une autre revue.")

    def set_status(self, analysis_id: int, recommendation_id: str, status: str) -> None:
        if status not in STATUS_LABELS:
            raise ValueError("Statut de recommandation invalide.")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT agent FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
            if row is None:
                raise KeyError(f"Analyse {analysis_id} introuvable.")
            agent = json.loads(row["agent"]) if row["agent"] else {}
            for recommendation in agent.get("recommendations", []):
                if recommendation["id"] == recommendation_id:
                    recommendation["status"] = status
                    db.execute("UPDATE analyses SET agent = ? WHERE id = ?", (_dump(agent), analysis_id))
                    return
            raise KeyError(f"Recommandation {recommendation_id} introuvable.")


CSV_FIELDS = {
    "id": "identifiant",
    "level": "niveau",
    "problem": "problème",
    "hypothesis": "hypothèse",
    "indicators": "indicateurs",
    "proposal": "modification_proposée",
    "rationale": "justification",
    "confidence": "confiance",
    "limitations": "limites",
    "status": "statut",
}


def _csv_safe(value: str) -> str:
    """Prevent spreadsheet formula interpretation of imported or generated text."""
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def export_recommendations(record: dict, kind: str) -> bytes:
    agent = record.get("agent") or {}
    recommendations = agent.get("recommendations", [])
    if kind == "json":
        payload = {
            "schema_version": 1,
            "analysis_id": record["id"],
            "name": record["name"],
            "is_demo": record["is_demo"],
            "created_at": record["created_at"],
            "model": agent.get("model"),
            "recommendations": recommendations,
        }
        return (json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    if kind != "csv":
        raise ValueError("Format d’export de recommandations inconnu.")
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["analyse", "source", "modèle", *CSV_FIELDS.values()])
    for recommendation in recommendations:
        values = [record["name"], "Simulation" if record["is_demo"] else "CSV importé", agent.get("model") or ""]
        for key in CSV_FIELDS:
            value = recommendation.get(key, "")
            if key == "status":
                value = STATUS_LABELS.get(value, value)
            if isinstance(value, list):
                value = " | ".join(value)
            values.append(str(value))
        writer.writerow([_csv_safe(value) for value in values])
    return buffer.getvalue().encode("utf-8-sig")


def _html(value) -> str:
    return escape(str(value)) if value is not None else "—"


def _table(headers: tuple[str, ...], rows) -> str:
    table_header = "".join(f'<th scope="col">{_html(label)}</th>' for label in headers)
    table_body = "".join("<tr>" + "".join(f"<td>{_html(value)}</td>" for value in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{table_header}</tr></thead><tbody>{table_body}</tbody></table></div>'


def _recommendation_html(recommendation: dict) -> str:
    detail = (
        ("Hypothèse", recommendation.get("hypothesis")),
        ("Indicateurs", " · ".join(recommendation.get("indicators", []))),
        ("Modification proposée", recommendation.get("proposal")),
        ("Justification", recommendation.get("rationale")),
        ("Confiance", recommendation.get("confidence")),
        ("Limites", recommendation.get("limitations")),
    )
    fields = "".join(f"<dt>{label}</dt><dd>{_html(text)}</dd>" for label, text in detail)
    status = recommendation.get("status", "pending")
    return (
        f'<article><p class="label">{_html(recommendation.get("level"))} · {_html(STATUS_LABELS.get(status, status))}</p>'
        f'<h3>{_html(recommendation.get("problem"))}</h3><dl>{fields}</dl></article>'
    )


def export_html(record: dict) -> bytes:
    stats = record["stats"]
    overview = stats["overview"]
    agent = record.get("agent")
    levels = _table(("Niveau", "Observations", "Réussite (%)", "Échec (%)", "Tentatives moy.", "Précision moy. (%)"), (
        (row["level"], row["n"], row["success_rate"], row["failure_rate"], row["avg_attempts"],
         row["avg_timing_accuracy_pct"])
        for row in stats["levels"]
    ))
    trend = stats["trend"]
    trend_section = "<p>Aucune date disponible.</p>"
    if trend:
        trend_section = _table(("Jour UTC", "Observations", "Réussite (%)", "Tentatives moy."), (
            (row["period"], row["n"], row["success_rate"], row["avg_attempts"]) for row in trend
        ))
    findings = "".join(
        f'<li><strong>{_html(row["level"])}</strong> · {_html(row["reason"])} '
        f'Écart de {_html(row["metrics"]["gap_pct_points"])} points.</li>' for row in stats["findings"]
    )
    warnings = "".join(f"<li>{_html(warning)}</li>" for warning in record["warnings"])
    finding_list = f"<ul>{findings}</ul>" if findings else "<p>Aucun signalement selon ces seuils.</p>"
    warning_list = f"<ul>{warnings}</ul>" if warnings else ""
    review = "<p>Analyse statistique disponible. La revue par le modèle local reste à lancer.</p>"
    if agent:
        recommendations = "".join(_recommendation_html(item) for item in agent["recommendations"])
        if not recommendations:
            recommendations = "<p>Le modèle a terminé sa revue sans proposer de modification.</p>"
        review = (f'<p class="label">Modèle local · {_html(agent["model"])}</p>'
                  f'<p>{_html(agent["summary"])}</p>{recommendations}')
    source = "Simulation · données fictives" if record["is_demo"] else "Données importées"
    html = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gravity Chain · Rapport d’équilibrage</title>
<style>
:root {{ color-scheme: dark; background: #101113; color: #f2eee8; font: 16px/1.55 system-ui, sans-serif; }}
body {{ margin: 2rem auto; padding: 0 1.25rem; max-width: 66rem; }}
header, section {{ margin-bottom: 2rem; }} h1, h2, h3 {{ line-height: 1.2; }}
.label {{ color: #e5c481; font-size: .85rem; font-weight: 700; letter-spacing: .04em; }}
.table-wrap {{ overflow: auto; }} table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: left; padding: .6rem; border-bottom: 1px solid #404044; }}
article {{ padding: 1rem 1.25rem; border-left: 2px solid #e5c481; background: #1a1c20; margin: 1rem 0; }}
dt {{ font-weight: 700; margin-top: .5rem; }} dd {{ margin: 0; overflow-wrap: anywhere; }}
@media print {{ :root {{ color-scheme: light; background: white; color: #111; }} .label {{ color: #654b1c; }} article {{ background: #f3f3f3; }} }}
</style></head><body>
<header><p class="label">GRAVITY CHAIN · AI GAME BALANCER</p><h1>{_html(record["name"])}</h1>
<p>{source} · Analyse {_html(record["id"])} · {_html(record["created_at"])}</p></header>
<section><h2>Synthèse</h2><p>{_html(overview["sessions"])} sessions et {_html(overview["rows"])} observations sur
{_html(overview["levels"])} niveaux. Taux de réussite {_html(overview["success_rate"])} %.</p>
{warning_list}</section>
<section><h2>Résultats par niveau</h2>{levels}</section>
<section><h2>Évolution</h2>{trend_section}</section>
<section><h2>Niveaux à surveiller</h2><p>{_html(stats["findings_method"])}</p>{finding_list}</section>
<section><h2>Revue et décisions</h2>{review}</section>
</body></html>"""
    return html.encode("utf-8")
