"""Recreate demo.csv from a fixed seed using only the Python standard library."""

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random


FIELDS = (
    "session_id", "level", "success", "attempts", "reaction_ms", "timing_accuracy_pct",
    "duration_s", "progress_pct", "played_at",
)
LEVELS = (
    ("Mise en orbite", 90, 65, 17),
    ("Transfert lunaire", 83, 70, 23),
    ("Périgée", 73, 82, 29),
    ("Arc de Saturne", 82, 71, 25),
    ("Échappée stellaire", 80, 71, 31),
)


def make_rows():
    rng = Random(280421)
    start = datetime(2026, 10, 20, 15, tzinfo=UTC)
    for index in range(150):
        day = index // 15
        played_at = start + timedelta(days=day, minutes=17 * (index % 15))
        precision = rng.gauss(0, 7) + 0.5 * day
        progress = 0
        for position, (level, mean, threshold, base_duration) in enumerate(LEVELS, start=1):
            timing = min(100, max(0, rng.gauss(mean + precision, 8)))
            missed = timing + rng.gauss(0, 9) < threshold
            min_attempts = 2 if missed else 1
            attempts = min(8, min_attempts + round(abs(rng.gauss(0, 0.9 + max(0, threshold - timing) / 13))))
            reaction = max(100, rng.gauss(330 - precision * 3, 43))
            duration = round(base_duration + attempts * 5 + rng.uniform(0, 10), 1)
            played_at += timedelta(seconds=duration)
            if not missed:
                progress = position * 100 // len(LEVELS)
            yield (
                f"SIM-{index + 1:03}", level, int(not missed), attempts,
                round(reaction, 1) if rng.random() > 0.035 else "",
                round(timing, 1) if rng.random() > 0.025 else "",
                duration, progress, played_at.isoformat(timespec="seconds"),
            )
            if missed or rng.random() < 0.035:
                break


if __name__ == "__main__":
    with Path(__file__).with_name("demo.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        writer.writerows(make_rows())
