"""Orchestration d'un modèle local et vérification de ses recommandations."""

import json
import math
import time

from .ollama import OllamaError

MAX_LEVELS = 8
MAX_TOOL_ROUNDS = 5
MAX_TOOL_CALLS = 10
TIME_BUDGET_S = 200

# Label and unit are owned by the application. Model output carries references only.
METRICS = {
    "n": ("Observations", ""),
    "success_n": ("Réussites", ""),
    "failure_n": ("Échecs", ""),
    "success_rate": ("Taux de réussite", "%"),
    "avg_attempts": ("Tentatives moyennes", ""),
    "success_ci_low": ("Borne basse de l’intervalle de confiance", "%"),
    "success_ci_high": ("Borne haute de l’intervalle de confiance", "%"),
    "peer_n": ("Observations sur les autres niveaux", ""),
    "peer_success_rate": ("Taux de réussite sur les autres niveaux", "%"),
    "peer_gap": ("Écart de réussite avec les autres niveaux", "points de %"),
    "timing_accuracy_n": ("Mesures de précision du timing", ""),
    "avg_timing_accuracy_pct": ("Précision moyenne du timing", "%"),
    "avg_reaction_ms": ("Temps de réaction moyen", "ms"),
    "success_timing_n": ("Mesures de timing en cas de réussite", ""),
    "failure_timing_n": ("Mesures de timing en cas d’échec", ""),
    "success_avg_timing_accuracy_pct": ("Précision moyenne en cas de réussite", "%"),
    "failure_avg_timing_accuracy_pct": ("Précision moyenne en cas d’échec", "%"),
    "timing_gap_pct_points": ("Écart de précision entre réussites et échecs", "points de %"),
}

LEVEL_FIELDS = (
    "n",
    "success_n",
    "failure_n",
    "success_rate",
    "avg_attempts",
    "success_ci_low",
    "success_ci_high",
    "timing_accuracy_n",
)
TIMING_FIELDS = (
    "timing_accuracy_n",
    "avg_timing_accuracy_pct",
    "avg_reaction_ms",
    "success_timing_n",
    "failure_timing_n",
    "success_avg_timing_accuracy_pct",
    "failure_avg_timing_accuracy_pct",
    "timing_gap_pct_points",
)

ACTIONS = {
    "widen_window": {
        "hypothesis": "La tolérance de la fenêtre de timing pourrait contribuer aux échecs.",
        "proposal": "Tester une fenêtre de timing élargie de 10 % par rapport à sa valeur actuelle.",
        "rationale": "Comparer le taux de réussite et les tentatives moyennes entre la version actuelle et la variante, avec des groupes de joueurs comparables.",
        "limitations": "La différence de précision est une association. Le réglage actuel et l'effet de la variante restent à mesurer.",
    },
    "timing_cue": {
        "hypothesis": "Le signal qui annonce le bon moment d’action pourrait manquer de lisibilité.",
        "proposal": "Tester un repère visuel indiquant quand la fenêtre de timing s’ouvre.",
        "rationale": "Comparer la précision et les réussites avec et sans ce repère en conservant la même fenêtre.",
        "limitations": "La télémétrie ne décrit pas le signal vu par les joueurs. Le repère proposé doit être testé en jeu.",
    },
    "practice_transition": {
        "hypothesis": "La transition pourrait exiger un geste que les joueurs n’ont pas encore suffisamment pratiqué.",
        "proposal": "Ajouter une occasion de pratiquer le geste juste avant cette transition et tester la variante.",
        "rationale": "Mesurer le taux de réussite et les tentatives sur la transition après le passage d’entraînement.",
        "limitations": "Les données agrégées ne renseignent pas sur l’expérience préalable ni sur le chemin exact de chaque joueur.",
    },
    "inspect_failures": {
        "hypothesis": "Une contrainte propre au niveau pourrait expliquer la difficulté observée.",
        "proposal": "Observer des essais du niveau et classer les échecs par cause observable avant de modifier le réglage.",
        "rationale": "Le taux de réussite oriente la recherche vers ce niveau. L’observation du jeu sert à isoler les causes.",
        "limitations": "L’écart entre niveaux peut également refléter des différences de joueurs ou de progression.",
    },
    "collect_samples": {
        "hypothesis": "Le taux observé pourrait varier fortement avec de nouvelles sessions.",
        "proposal": "Collecter davantage de sessions avec les mêmes règles de mesure avant de modifier ce niveau.",
        "rationale": "Un petit nombre d’observations limite la précision de l’estimation de réussite.",
        "limitations": "La confiance porte sur le constat statistique. Aucune cause n’est établie.",
    },
}

SYSTEM_PROMPT = """Tu es l’agent d’analyse d’un prototype de jeu de précision.
L’application exécute des outils de calcul en lecture seule. Les niveaux portent
des identifiants techniques N1, N2, etc. Utilise exclusivement ces identifiants.

Procédure dans cet ordre :
- Appelle inspect_level pour établir le constat d’un niveau prioritaire.
- Après son résultat, appelle compare_level ou inspect_timing selon le constat,
  ou les deux si nécessaire, sur le même niveau. Si le niveau présente une
  réussite faible et que timing_n est positif, appelle inspect_timing sur
  ce niveau avant d’examiner un autre niveau.
- Si aucun autre appel ne paraît utile, réponds simplement « Analyse terminée ».
Le rapport structuré sera demandé dans une étape séparée. Les statistiques sont
des observations et ne démontrent aucune cause ni aucun effet futur."""


class AgentError(RuntimeError):
    """L’investigation n’a pas donné de rapport validable."""


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _evidence(token, values):
    items = []
    for metric, value in values.items():
        if _number(value):
            label, unit = METRICS[metric]
            items.append({"reference": f"{token}.{metric}", "label": label, "value": value, "unit": unit})
    return items


def _level_sort_key(level, flagged):
    rate = level.get("success_rate")
    return (
        level["level"] not in flagged,
        level.get("n", 0) < 20,
        rate if _number(rate) else 101,
        -level.get("n", 0),
        level["level"],
    )


TOOL_DESCRIPTIONS = {
    "inspect_level": "Obtenir effectif, réussite, tentatives et intervalle de confiance d'un niveau.",
    "compare_level": "Comparer un niveau aux autres niveaux pondérés par leur effectif.",
    "inspect_timing": "Comparer les mesures de précision du timing entre réussites et échecs.",
}


class _Investigation:
    def __init__(self, stats):
        self.stats = stats
        self.levels = stats.get("levels", [])
        if not self.levels:
            raise AgentError("Importez au moins un niveau valide avant d’interroger l’agent.")
        self.flagged = {finding["level"] for finding in stats.get("findings", [])}
        ordered = sorted(self.levels, key=lambda level: _level_sort_key(level, self.flagged))
        self.candidates = {f"N{index}": level for index, level in enumerate(ordered[:MAX_LEVELS], 1)}
        self.trace = []
        self.observations = {}
        self.completed = set()

    def tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": {"level": {"type": "string", "enum": list(self.candidates)}},
                        "required": ["level"],
                        "additionalProperties": False,
                    },
                },
            }
            for name, description in TOOL_DESCRIPTIONS.items()
        ]

    def brief(self):
        return [
            {
                "level": token,
                "signal_statistique": level["level"] in self.flagged,
                "n": level["n"],
                "success_rate": level["success_rate"],
                "timing_n": level.get("timing_accuracy_n", 0),
            }
            for token, level in self.candidates.items()
        ]

    def _comparison(self, level):
        total = self.stats["overview"]
        peer_n = total["rows"] - level["n"]
        if peer_n <= 0:
            return {"peer_n": 0}
        success_total = total.get("success_n")
        success_level = level.get("success_n")
        if not _number(success_total) or not _number(success_level):
            return {"peer_n": peer_n}
        peer_rate = (success_total - success_level) / peer_n * 100
        return {
            "peer_n": peer_n,
            "peer_success_rate": round(peer_rate, 2),
            "peer_gap": round(success_level / level["n"] * 100 - peer_rate, 2),
        }

    def _values(self, tool, level):
        if tool == "compare_level":
            return self._comparison(level)
        fields = LEVEL_FIELDS if tool == "inspect_level" else TIMING_FIELDS
        return {field: level.get(field) for field in fields}

    def call(self, call, already_inspected):
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict):
            return None, {"error": "Appel invalide. Utilise la définition d’un outil."}
        tool, args = function.get("name"), function.get("arguments")
        if not isinstance(tool, str) or tool not in TOOL_DESCRIPTIONS:
            return None, {"error": "Nom d’outil invalide."}
        if not isinstance(args, dict) or set(args) != {"level"}:
            return tool, {"error": "Fournis uniquement l’identifiant du niveau."}
        token = args["level"]
        if not isinstance(token, str) or token not in self.candidates:
            return tool, {"error": "Identifiant de niveau invalide."}
        if tool != "inspect_level" and ("inspect_level", token) not in already_inspected:
            return tool, {"error": "Appelle cet outil après avoir reçu le résultat de inspect_level."}
        if (tool, token) in self.completed:
            return tool, {"error": "Ce résultat est déjà disponible."}
        if len(self.trace) >= MAX_TOOL_CALLS:
            return tool, {"error": "Budget d’appels atteint."}

        level = self.candidates[token]
        evidence = _evidence(token, self._values(tool, level))
        self.completed.add((tool, token))
        self.observations.update({row["reference"]: row for row in evidence})
        result = {"level": token, "evidence": evidence}
        self.trace.append(
            {
                "step": len(self.trace) + 1,
                "tool": tool,
                "args": {"level": token},
                "level": level["level"],
                "result": result,
            }
        )
        return tool, result

    def examined(self, token):
        return any((tool, token) in self.completed for tool in ("compare_level", "inspect_timing"))

    def choices(self):
        """Limit model-selected actions to observations it actually requested."""
        choices = {}
        for token in self.candidates:
            if not self.examined(token):
                continue
            metrics = {
                reference.partition(".")[2]: row["value"]
                for reference, row in self.observations.items()
                if reference.startswith(f"{token}.")
            }
            n = metrics.get("n", 0)
            success_rate = metrics.get("success_rate", 100)
            gap = metrics.get("peer_gap", 0)
            peer_signal = metrics.get("peer_n", 0) >= 20 and gap <= -15
            low_rate = success_rate <= 55 or peer_signal
            timing_support = (
                metrics.get("success_timing_n", 0) >= 8
                and metrics.get("failure_timing_n", 0) >= 8
                and metrics.get("timing_gap_pct_points", 0) >= 10
            )
            if n < 20:
                choices[token] = {"collect_samples": ("n", "success_rate")}
                continue
            if not low_rate:
                continue
            actions = {"inspect_failures": ("n", "success_rate")}
            if peer_signal:
                actions["inspect_failures"] += ("peer_gap",)
            if metrics.get("avg_attempts", 0) >= 2:
                actions["practice_transition"] = ("n", "success_rate", "avg_attempts")
            if timing_support:
                timing_keys = (
                    "n", "success_rate", "success_timing_n", "failure_timing_n", "timing_gap_pct_points"
                )
                actions.update(widen_window=timing_keys, timing_cue=timing_keys)
            choices[token] = actions
        return choices


def _report_schema(selections, references):
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["recommendations"],
        "properties": {
            "recommendations": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["selection", "evidence"],
                    "properties": {
                        "selection": {"type": "string", "enum": selections},
                        "evidence": {
                            "type": "array",
                            "maxItems": 3,
                            "items": {"type": "string", "enum": references},
                        },
                    },
                },
            }
        },
    }


def _display_value(value):
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _validate_report(content, investigation, choices):
    try:
        report = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise AgentError("Le modèle a renvoyé un rapport JSON illisible.") from exc
    recommendations = report.get("recommendations") if isinstance(report, dict) else None
    if not isinstance(recommendations, list) or set(report) != {"recommendations"} or not 1 <= len(recommendations) <= 3:
        raise AgentError("Le modèle n’a pas renvoyé de recommandation structurée.")

    accepted = []
    used_actions = set()
    for item in recommendations:
        if (
            not isinstance(item, dict)
            or set(item) != {"selection", "evidence"}
            or not isinstance(item["selection"], str)
        ):
            raise AgentError("Le format d’une recommandation est invalide.")
        token, _, action = item["selection"].partition(":")
        references = item["evidence"]
        if (
            (token, action) in used_actions
            or token not in choices
            or action not in choices[token]
        ):
            raise AgentError("Une recommandation ne correspond pas aux observations de son niveau.")
        if not isinstance(references, list) or len(references) > 3 or any(
            not isinstance(reference, str)
            or not reference.startswith(f"{token}.")
            or reference not in investigation.observations
            for reference in references
        ):
            raise AgentError("Le modèle a cité une mesure absente ou issue d’un autre niveau.")

        required = [f"{token}.{metric}" for metric in choices[token][action]]
        evidence = [investigation.observations[ref].copy() for ref in dict.fromkeys(required + references)]
        indicators = [f"{row['label']} · {_display_value(row['value'])} {row['unit']}".rstrip() for row in evidence]
        rate = investigation.observations[f"{token}.success_rate"]["value"]
        n = investigation.observations[f"{token}.n"]["value"]
        level = investigation.candidates[token]["level"]
        problem = f"Taux de réussite de {_display_value(rate)} % sur {n} observations."
        if action == "collect_samples":
            problem = f"Effectif limité à {n} observations pour estimer la difficulté."
        accepted.append(
            {
                "id": f"R{len(accepted) + 1}",
                "level": level,
                "problem": problem,
                **ACTIONS[action],
                "indicators": indicators,
                "evidence": evidence,
                "confidence": "Limitée" if n < 40 or action == "collect_samples" else "Modérée",
                "status": "pending",
                "action": action,
            }
        )
        used_actions.add((token, action))

    return accepted


def _remaining(deadline, client):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AgentError("L’analyse a atteint son délai maximum.")
    return min(remaining, client.timeout)


def _notify(callback, stage, message, **details):
    if callback is not None:
        callback({"stage": stage, "message": message, **details})


def _explore(client, investigation, deadline, on_event):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Analyse les niveaux candidats ci-dessous. Commence par un appel inspect_level.\n"
            + json.dumps(investigation.brief(), ensure_ascii=False),
        },
    ]
    turns = 0
    for round_number in range(1, MAX_TOOL_ROUNDS + 1):
        _notify(on_event, "model", f"Étape d’investigation {round_number}…")
        reply = client.chat(messages, tools=investigation.tools(), timeout=_remaining(deadline, client))
        turns += 1
        calls = reply.get("tool_calls")
        if not isinstance(calls, list) or not calls:
            has_two_tools = any(investigation.examined(token) for token in investigation.candidates)
            if has_two_tools:
                break
            needed = (
                "Appelle inspect_level sur un niveau proposé."
                if not investigation.trace
                else "Appelle inspect_timing ou compare_level sur le niveau déjà examiné."
            )
            messages.extend(
                (
                    {"role": "assistant", "content": str(reply.get("content", ""))[:500]},
                    {"role": "user", "content": needed},
                )
            )
            continue

        if len(calls) > MAX_TOOL_CALLS:
            raise AgentError("Le modèle a demandé trop d’appels d’outils en une seule étape.")
        messages.append({"role": "assistant", "content": "", "tool_calls": calls})
        already_inspected = investigation.completed.copy()
        for call in calls:
            tool, result = investigation.call(call, already_inspected)
            if "evidence" in result:
                _notify(
                    on_event,
                    "tool",
                    f"Outil exécuté · {tool}",
                    step=len(investigation.trace),
                    tool=tool,
                )
            message = {"role": "tool", "content": json.dumps(result, ensure_ascii=False)}
            if tool:
                message["tool_name"] = tool
            messages.append(message)
        if len(investigation.trace) >= MAX_TOOL_CALLS:
            break

    if not investigation.trace:
        raise AgentError("Le modèle n’a exécuté aucun outil. Réessayez avec Qwen3 8B.")
    return turns


def _synthesize(client, investigation, choices, deadline, on_event):
    available = {
        token: [row for ref, row in investigation.observations.items() if ref.startswith(f"{token}.")]
        for token in choices
    }
    references = [row["reference"] for rows in available.values() for row in rows]
    selections = [f"{token}:{action}" for token, actions in choices.items() for action in actions]
    schema = _report_schema(selections, references)
    prompt = {
        "selections_permises": selections,
        "signification_des_actions": {code: action["hypothesis"] for code, action in ACTIONS.items()},
        "preuves_observees": available,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "Sélectionne et classe de une à trois recommandations distinctes. "
                "Copie la clé de sélection exacte niveau:action dans le champ selection. "
                "Privilégie un test ciblé de timing si la comparaison de timing le permet. "
                "L’application joint les preuves obligatoires. Le champ evidence contient au plus "
                "trois références complémentaires du même niveau et peut rester vide. "
                "Réponds uniquement avec l’objet JSON conforme au schéma."
            ),
        },
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
    ]
    last_error = None
    for attempt in range(1, 3):
        _notify(on_event, "synthesis", "Validation du rapport de l’agent…")
        reply = client.chat(messages, schema=schema, timeout=_remaining(deadline, client))
        try:
            return _validate_report(reply.get("content"), investigation, choices), attempt
        except AgentError as exc:
            last_error = exc
            messages.append(
                {"role": "user", "content": f"{exc} Regénère un objet conforme à partir des preuves fournies."}
            )
    raise last_error


def run_analysis(client, stats, frame=None, on_event=None):
    """Exécute une exploration locale avec outils et retourne un rapport vérifié.

    Le paramètre optionnel frame est réservé aux intégrations. Le rapport se fonde
    sur les agrégats persistés, y compris lorsqu'une analyse est rouverte.
    """
    del frame
    start = time.monotonic()
    deadline = start + TIME_BUDGET_S
    investigation = _Investigation(stats)
    _notify(on_event, "connection", "Vérification du modèle local…")
    state = client.status()
    if not state["available"]:
        raise AgentError(state["message"])

    try:
        turns = _explore(client, investigation, deadline, on_event)
        choices = investigation.choices()
        if choices:
            recommendations, synthesis_turns = _synthesize(client, investigation, choices, deadline, on_event)
            turns += synthesis_turns
            summary = f"Rapport vérifié. {len(recommendations)} proposition(s) à examiner."
        else:
            complete = any(investigation.examined(token) for token in investigation.candidates)
            if not complete:
                raise AgentError("L’investigation a besoin d’un second outil sur un même niveau.")
            recommendations = []
            summary = "Aucune proposition retenue pour les niveaux examinés par l’agent."
    except OllamaError as exc:
        raise AgentError(str(exc)) from exc

    _notify(on_event, "done", "Rapport vérifié.")
    return {
        "model": client.model,
        "summary": summary,
        "recommendations": recommendations,
        "trace": investigation.trace,
        "metadata": {
            "model_turns": turns,
            "tool_calls": len(investigation.trace),
            "candidate_levels": len(investigation.candidates),
            "total_levels": len(investigation.levels),
            "elapsed_s": round(time.monotonic() - start, 2),
            "model_digest": state.get("digest"),
            "ollama_version": state.get("version"),
            "runtime": client.runtime(),
        },
    }
