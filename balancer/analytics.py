"""CSV schema and deterministic session-level game balance statistics."""

import csv
from decimal import Decimal, InvalidOperation
from io import StringIO
from math import sqrt

import numpy as np
import pandas as pd


MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 100_000
MAX_LEVELS = 250
REQUIRED = ("session_id", "level", "success", "attempts")
OPTIONAL_NUMERIC = {
    "reaction_ms": 1_000_000_000,
    "timing_accuracy_pct": 100,
    "duration_s": 1_000_000_000,
    "progress_pct": 100,
}
OPTIONAL = (*OPTIONAL_NUMERIC, "played_at")
MISSING_CODES = {"", "na", "n/a", "nan", "null"}
OUTCOMES = {
    **dict.fromkeys(("1", "true", "vrai", "oui", "yes", "success", "réussite", "reussite"), True),
    **dict.fromkeys(("0", "false", "faux", "non", "no", "failure", "échec", "echec"), False),
}
MIN_FINDING_ROWS = 20
MIN_FINDING_GAP = 15


class CsvError(ValueError):
    """An error that a CSV author can correct."""


def _line_error(column: str, mask: pd.Series, lines: list[int], detail: str) -> None:
    examples = [lines[index] for index in mask[mask].index[:5]]
    if examples:
        locations = ", ".join(str(line) for line in examples)
        raise CsvError(f"Colonne « {column} », ligne(s) {locations}. {detail}")


def _read_rows(source: str) -> tuple[pd.DataFrame, list[int], list[str]]:
    readers = []
    for delimiter in (",", ";"):
        candidate = csv.reader(StringIO(source, newline=""), delimiter=delimiter, strict=True)
        try:
            header = [name.strip().lower() for name in next(candidate, [])]
        except csv.Error:
            continue
        required_count = sum(field in header for field in REQUIRED)
        readers.append((required_count, len(header), header, candidate))
    if not readers:
        raise CsvError("En-tête CSV invalide. Vérifiez le séparateur et les guillemets.")
    _, _, header, reader = max(readers, key=lambda entry: entry[:2])
    try:
        if not header:
            raise CsvError("Le fichier CSV est vide.")
        if "" in header or len(set(header)) != len(header):
            raise CsvError("Chaque colonne doit porter un nom distinct et non vide.")
        missing = [column for column in REQUIRED if column not in header]
        if missing:
            raise CsvError(f"Colonnes obligatoires manquantes ({', '.join(missing)}).")
        known = [column for column in header if column in (*REQUIRED, *OPTIONAL)]
        indices = [header.index(column) for column in known]
        records, lines = [], []
        for record in reader:
            if not record:
                continue
            if len(record) != len(header):
                raise CsvError(f"La ligne {reader.line_num} contient {len(record)} champ(s), contre {len(header)} dans l’en-tête.")
            if len(records) == MAX_ROWS:
                raise CsvError("Le fichier dépasse la limite de 100 000 lignes de données.")
            records.append([record[index].strip() for index in indices])
            lines.append(reader.line_num)
    except csv.Error as error:
        raise CsvError(f"Format CSV invalide à la ligne {reader.line_num}. Vérifiez le séparateur et les guillemets.") from error
    if not records:
        raise CsvError("Le fichier doit contenir au moins une ligne de données.")
    return pd.DataFrame(records, columns=known), lines, [column for column in header if column not in known]


def _numbers(
    series: pd.Series, lines: list[int], minimum: int, maximum: int, *, required: bool = False,
) -> pd.Series:
    missing = series.str.lower().isin(MISSING_CODES)
    values = pd.to_numeric(series.mask(missing).str.replace(",", ".", regex=False), errors="coerce")
    invalid = ~missing & (~np.isfinite(values) | (values < minimum) | (values > maximum))
    if required:
        invalid = invalid | missing | values.mod(1).ne(0)
        candidates = ~invalid & ~series.str.fullmatch(r"[+-]?[0-9]+")
        exact = series.loc[candidates].map(
            lambda value: _is_exact_integer(value.replace(",", "."), minimum, maximum)
        ).astype(bool)
        invalid.loc[candidates] = ~exact
        message = f"Indiquez un entier compris entre {minimum} et {maximum}."
    else:
        message = f"Indiquez un nombre compris entre {minimum} et {maximum} ou laissez la cellule vide."
    _line_error(str(series.name), invalid, lines, message)
    return values.astype("int64" if required else "float64")


def _is_exact_integer(value: str, minimum: int, maximum: int) -> bool:
    try:
        number = Decimal(value)
        return minimum <= number <= maximum and number == number.to_integral_value()
    except InvalidOperation:
        return False


def load_csv(data: bytes) -> tuple[pd.DataFrame, list[str]]:
    """Load and validate one row per session and level; unknown columns are ignored."""
    if len(data) > MAX_BYTES:
        raise CsvError("Le fichier dépasse la taille maximale de 20 Mio.")
    warnings = []
    try:
        source = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            source = data.decode("cp1252")
        except UnicodeDecodeError as error:
            raise CsvError("Encodage illisible. Enregistrez le fichier au format CSV UTF-8.") from error
        warnings.append("Le fichier a été lu avec l’encodage Windows-1252. UTF-8 est recommandé pour les prochains exports.")

    frame, lines, ignored = _read_rows(source)
    if ignored:
        warnings.append(f"{len(ignored)} colonne(s) hors schéma ignorée(s).")

    for field in ("session_id", "level"):
        invalid = frame[field].eq("") | (frame[field].str.len() > 128) | frame[field].str.contains(r"[\x00-\x1f\x7f]", regex=True)
        _line_error(field, invalid, lines, "Indiquez un texte de 1 à 128 caractères sans saut de ligne ni caractère de contrôle.")
    if frame["level"].nunique() > MAX_LEVELS:
        raise CsvError(f"Le fichier contient plus de {MAX_LEVELS} niveaux distincts.")
    _line_error("session_id / level", frame.duplicated(["session_id", "level"]), lines,
                "Conservez une ligne par paire session et niveau. Regroupez les essais dans la colonne « attempts ».")

    successes = frame["success"].str.lower().map(OUTCOMES)
    _line_error("success", successes.isna(), lines, "Utilisez 1/0, oui/non ou réussite/échec.")
    frame["success"] = successes.astype(bool)
    frame["attempts"] = _numbers(frame["attempts"], lines, 1, 1_000_000_000, required=True)

    missing_columns = [field for field in OPTIONAL if field not in frame]
    if missing_columns:
        warnings.append(f"Colonnes facultatives absentes ({', '.join(missing_columns)}). Les indicateurs concernés sont indisponibles.")
    for field, maximum in OPTIONAL_NUMERIC.items():
        frame[field] = _numbers(frame[field], lines, 0, maximum) if field in frame else np.nan
    if "played_at" in frame:
        source_dates = frame["played_at"]
        missing = source_dates.str.lower().isin(MISSING_CODES)
        complete = source_dates.str.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[Tt ].+)?")
        dates = pd.to_datetime(source_dates.mask(missing), format="ISO8601", utc=True, errors="coerce")
        _line_error("played_at", ~missing & (~complete | dates.isna()), lines,
                    "Utilisez une date ISO (AAAA-MM-JJ) ou une date-heure ISO 8601.")
        frame["played_at"] = dates
    else:
        frame["played_at"] = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")

    incomplete = {field: int(frame[field].isna().sum()) for field in OPTIONAL if field not in missing_columns}
    missing_values = ", ".join(f"{field} ({count}/{len(frame)})" for field, count in incomplete.items() if count)
    if missing_values:
        warnings.append(f"Valeurs facultatives manquantes dans {missing_values}. Chaque indicateur utilise les observations disponibles.")
    return frame[[*REQUIRED, *OPTIONAL]], warnings


def _average(values: pd.Series) -> float | None:
    average = values.mean()
    return round(float(average), 2) if pd.notna(average) else None


def _metrics(group: pd.DataFrame) -> dict:
    n = len(group)
    successes = int(group["success"].sum())
    return {
        "n": n,
        "success_n": successes,
        "failure_n": n - successes,
        "success_rate": round(100 * successes / n, 2),
        "failure_rate": round(100 * (n - successes) / n, 2),
        "avg_attempts": _average(group["attempts"]),
        **{f"avg_{field}": _average(group[field]) for field in OPTIONAL_NUMERIC},
        "timing_accuracy_n": int(group["timing_accuracy_pct"].count()),
    }


def _wilson(successes: int, n: int) -> tuple[float, float]:
    """Two-sided 95% Wilson interval for a binomial success rate, in percent."""
    z = 1.959963984540054
    fraction = successes / n
    denominator = 1 + z**2 / n
    center = (fraction + z**2 / (2 * n)) / denominator
    half = z * sqrt(fraction * (1 - fraction) / n + z**2 / (4 * n**2)) / denominator
    return round(100 * max(0, center - half), 2), round(100 * min(1, center + half), 2)


def _level_metrics(level: str, group: pd.DataFrame) -> dict:
    row = {"level": level, **_metrics(group)}
    successes = group.loc[group["success"], "timing_accuracy_pct"].dropna()
    failures = group.loc[~group["success"], "timing_accuracy_pct"].dropna()
    gap = round(float(successes.mean() - failures.mean()), 2) if len(successes) and len(failures) else None
    ci_low, ci_high = _wilson(row["success_n"], row["n"])
    row.update(
        success_ci_low=ci_low,
        success_ci_high=ci_high,
        success_timing_n=len(successes),
        failure_timing_n=len(failures),
        success_avg_timing_accuracy_pct=_average(successes),
        failure_avg_timing_accuracy_pct=_average(failures),
        timing_gap_pct_points=gap,
    )
    return row


def _findings(levels: list[dict], rows: int, successes: int) -> list[dict]:
    findings = []
    for level in levels:
        other_rows = rows - level["n"]
        if min(level["n"], other_rows) < MIN_FINDING_ROWS:
            continue
        other_successes = successes - level["success_n"]
        other_rate = 100 * other_successes / other_rows
        # Compare proportions exactly so an observation at the threshold is included.
        gap_numerator = 100 * (other_successes * level["n"] - level["success_n"] * other_rows)
        gap_denominator = other_rows * level["n"]
        if gap_numerator >= MIN_FINDING_GAP * gap_denominator:
            findings.append({
                "level": level["level"],
                "reason": "Taux de réussite inférieur d’au moins 15 points à celui des autres niveaux regroupés.",
                "metrics": {
                    "n": level["n"],
                    "success_rate": level["success_rate"],
                    "other_n": other_rows,
                    "other_success_rate": round(other_rate, 2),
                    "gap_pct_points": round(gap_numerator / gap_denominator, 2),
                    "timing_gap_pct_points": level["timing_gap_pct_points"],
                },
            })
    return sorted(findings, key=lambda item: -item["metrics"]["gap_pct_points"])


def _trend(frame: pd.DataFrame) -> tuple[list[dict], int]:
    dated = frame.dropna(subset=["played_at"])
    days = dated["played_at"].dt.strftime("%Y-%m-%d")
    daily = dated.groupby(days, sort=True).agg(n=("success", "size"),
                                              success_rate=("success", "mean"),
                                              avg_attempts=("attempts", "mean"))
    trend = [
        {"period": period, "n": int(n),
         "success_rate": round(100 * rate, 2), "avg_attempts": round(attempts, 2)}
        for period, n, rate, attempts in daily.itertuples(name=None)
    ]
    return trend, len(dated)


def analyze(frame: pd.DataFrame) -> dict:
    """Compute JSON-native statistics from a validated frame with no model calls."""
    overview = {**_metrics(frame), "sessions": int(frame["session_id"].nunique()),
                "rows": len(frame), "levels": int(frame["level"].nunique())}
    levels = [_level_metrics(level, group) for level, group in frame.groupby("level", sort=False)]
    trend, trend_coverage_n = _trend(frame)
    return {
        "overview": overview,
        "levels": levels,
        "trend": trend,
        "trend_coverage_n": trend_coverage_n,
        "findings": _findings(levels, len(frame), overview["success_n"]),
        "findings_method": (
            "Alerte descriptive à partir de 20 observations dans le niveau et 20 dans les autres niveaux regroupés, "
            "avec au moins 15 points de pourcentage d’écart. Chaque observation correspond à un couple session-niveau."
        ),
    }
