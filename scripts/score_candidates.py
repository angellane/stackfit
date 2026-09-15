#!/usr/bin/env python3
"""
score_candidates.py - Transparent weighted scoring for StackFit.

Takes a candidates file (JSON) with per-criterion scores and produces a ranking
with the arithmetic shown, plus three honesty checks that stop a recommendation
from looking more certain than it is:

  1. Margin analysis  - flags when the top two options are close enough that the
                        ranking is really a tie and a human tiebreaker matters.
  2. Sensitivity      - re-runs the ranking under every weight profile and
                        reports whether the winner survives. A winner that only
                        wins under one profile is a preference, not a verdict.
  3. Evidence audit   - flags criteria scored without evidence and volatile
                        facts (pricing, limits) that were never verified.

All criteria are oriented so that 5 is always the favourable end. That removes
the classic sign error where "cost" and "effort" get added the wrong way round.

Usage:
    python3 score_candidates.py candidates.json
    python3 score_candidates.py candidates.json --profile ship-fast --format markdown
    python3 score_candidates.py --template > candidates.json
    python3 score_candidates.py --list-profiles

Exit codes: 0 ok, 1 invalid candidates file, 2 bad arguments.
"""

import argparse
import json
import signal
import sys

CRITERIA = [
    ("architecture_fit", "How naturally it fits the existing framework, data layer and runtime"),
    ("implementation_speed", "How quickly a working integration lands (5 = fastest)"),
    ("migration_ease", "How little rework of existing code/data is required (5 = least)"),
    ("documentation_quality", "Accuracy and completeness of official docs"),
    ("sdk_quality", "Idiomatic SDK for this language, typed, maintained"),
    ("operational_simplicity", "How little ongoing ops burden it adds (5 = least)"),
    ("cost_efficiency", "Cost at this project's realistic scale (5 = cheapest)"),
    ("scalability_headroom", "Room to grow before re-architecting"),
    ("ecosystem_maturity", "Adoption, community answers, third-party examples"),
    ("portability", "How cheaply you could leave later (5 = least lock-in)"),
]
CRITERION_KEYS = [key for key, _ in CRITERIA]

PROFILES = {
    "default": {
        "architecture_fit": 18, "implementation_speed": 12, "migration_ease": 8,
        "documentation_quality": 8, "sdk_quality": 10, "operational_simplicity": 10,
        "cost_efficiency": 12, "scalability_headroom": 8, "ecosystem_maturity": 6,
        "portability": 8,
    },
    "ship-fast": {
        "architecture_fit": 18, "implementation_speed": 22, "migration_ease": 6,
        "documentation_quality": 12, "sdk_quality": 12, "operational_simplicity": 12,
        "cost_efficiency": 10, "scalability_headroom": 3, "ecosystem_maturity": 3,
        "portability": 2,
    },
    "enterprise": {
        "architecture_fit": 16, "implementation_speed": 6, "migration_ease": 6,
        "documentation_quality": 8, "sdk_quality": 10, "operational_simplicity": 10,
        "cost_efficiency": 8, "scalability_headroom": 14, "ecosystem_maturity": 8,
        "portability": 14,
    },
    "cost-sensitive": {
        "architecture_fit": 14, "implementation_speed": 10, "migration_ease": 3,
        "documentation_quality": 6, "sdk_quality": 8, "operational_simplicity": 12,
        "cost_efficiency": 28, "scalability_headroom": 6, "ecosystem_maturity": 3,
        "portability": 10,
    },
    "long-haul": {
        "architecture_fit": 14, "implementation_speed": 3, "migration_ease": 3,
        "documentation_quality": 10, "sdk_quality": 12, "operational_simplicity": 16,
        "cost_efficiency": 6, "scalability_headroom": 10, "ecosystem_maturity": 8,
        "portability": 18,
    },
}

CLOSE_CALL_MARGIN = 5.0  # points out of 100
MAX_SCORE = 5


class CandidateError(Exception):
    pass


def resolve_weights(profile_name, override):
    if profile_name not in PROFILES:
        raise CandidateError(
            "unknown profile '{}'. Available: {}".format(
                profile_name, ", ".join(sorted(PROFILES))))
    weights = dict(PROFILES[profile_name])
    if override:
        unknown = sorted(set(override) - set(CRITERION_KEYS))
        if unknown:
            raise CandidateError("unknown criteria in weights override: " + ", ".join(unknown))
        for key, value in override.items():
            if not isinstance(value, (int, float)) or value < 0:
                raise CandidateError("weight for '{}' must be a non-negative number".format(key))
            weights[key] = float(value)
    total = sum(weights.values())
    if total <= 0:
        raise CandidateError("weights sum to zero")
    return weights, total


def validate(data):
    if not isinstance(data, dict):
        raise CandidateError("top level of the candidates file must be an object")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise CandidateError("'candidates' must be a non-empty list")
    if len(candidates) > 8:
        raise CandidateError(
            "{} candidates supplied. Shortlist to 5 or fewer before scoring - "
            "a long list signals the research step was not narrowed down."
            .format(len(candidates)))
    names = []
    for index, candidate in enumerate(candidates):
        where = "candidate[{}]".format(index)
        if not isinstance(candidate, dict):
            raise CandidateError(where + " must be an object")
        name = candidate.get("name")
        if not isinstance(name, str) or not name.strip():
            raise CandidateError(where + " needs a non-empty 'name'")
        if name in names:
            raise CandidateError("duplicate candidate name: " + name)
        names.append(name)
        scores = candidate.get("scores")
        if not isinstance(scores, dict):
            raise CandidateError("{} ('{}') needs a 'scores' object".format(where, name))
        missing = [key for key in CRITERION_KEYS if key not in scores]
        if missing:
            raise CandidateError(
                "{} ('{}') is missing scores for: {}".format(where, name, ", ".join(missing)))
        unknown = sorted(set(scores) - set(CRITERION_KEYS))
        if unknown:
            raise CandidateError(
                "{} ('{}') has unknown criteria: {}".format(where, name, ", ".join(unknown)))
        for key, value in scores.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise CandidateError(
                    "{} ('{}') score for '{}' must be a number 0-5".format(where, name, key))
            if not 0 <= value <= MAX_SCORE:
                raise CandidateError(
                    "{} ('{}') score for '{}' is {} - must be between 0 and 5"
                    .format(where, name, key, value))
    return candidates


def score_one(candidate, weights, weight_total):
    scores = candidate["scores"]
    contributions = {}
    total = 0.0
    for key in CRITERION_KEYS:
        weight = weights[key]
        contribution = (float(scores[key]) / MAX_SCORE) * weight
        contributions[key] = round(contribution, 2)
        total += contribution
    normalized = total * (100.0 / weight_total)
    return round(normalized, 1), contributions


def rank(candidates, weights, weight_total):
    rows = []
    for candidate in candidates:
        total, contributions = score_one(candidate, weights, weight_total)
        disqualifiers = candidate.get("disqualifiers") or []
        rows.append({
            "name": candidate["name"],
            "total": total,
            "contributions": contributions,
            "scores": dict(candidate["scores"]),
            "excluded": bool(disqualifiers),
            "disqualifiers": list(disqualifiers),
            "summary": candidate.get("summary", ""),
        })
    # Deterministic: score desc, then name asc. Excluded options sink to the bottom.
    rows.sort(key=lambda r: (r["excluded"], -r["total"], r["name"]))
    for position, row in enumerate(rows, start=1):
        row["rank"] = position
    return rows


def sensitivity(candidates):
    """Winner under each profile - shows whether the result is robust."""
    winners = {}
    for profile_name in sorted(PROFILES):
        weights, total = resolve_weights(profile_name, None)
        rows = [row for row in rank(candidates, weights, total) if not row["excluded"]]
        winners[profile_name] = rows[0]["name"] if rows else None
    return winners


def audit(candidates):
    """Surface the places where a confident-looking number has nothing behind it."""
    findings = []
    for candidate in candidates:
        name = candidate["name"]
        evidence = candidate.get("evidence") or {}
        if not isinstance(evidence, dict):
            findings.append("{}: 'evidence' should be an object keyed by criterion".format(name))
            evidence = {}
        unsupported = [
            key for key in CRITERION_KEYS
            if not str(evidence.get(key, "")).strip()
        ]
        if unsupported:
            findings.append(
                "{}: scored without evidence on {} criteria ({}). A score with no "
                "repo-specific or documented reason behind it is a guess wearing a number."
                .format(name, len(unsupported), ", ".join(unsupported[:4])
                        + ("..." if len(unsupported) > 4 else "")))
        facts = candidate.get("facts") or []
        if isinstance(facts, list):
            unverified = [
                fact.get("claim", "(unnamed claim)")
                for fact in facts
                if isinstance(fact, dict) and not fact.get("verified")
            ]
            if unverified:
                findings.append(
                    "{}: {} unverified fact(s) - {}. Pricing and quota figures move; "
                    "label these as unverified in the report or check the vendor page."
                    .format(name, len(unverified), "; ".join(str(u) for u in unverified[:2])))
            if not facts:
                findings.append(
                    "{}: no 'facts' recorded. Cost and limit claims in the write-up will "
                    "have no source attached.".format(name))
    return findings


def build_result(data, profile_name, weights_override):
    candidates = validate(data)
    profile_name = profile_name or data.get("profile") or "default"
    override = weights_override or data.get("weights_override")
    weights, weight_total = resolve_weights(profile_name, override)
    rows = rank(candidates, weights, weight_total)
    active = [row for row in rows if not row["excluded"]]

    margin = None
    close_call = False
    if len(active) >= 2:
        margin = round(active[0]["total"] - active[1]["total"], 1)
        close_call = margin < CLOSE_CALL_MARGIN

    winners = sensitivity(candidates)
    top_name = active[0]["name"] if active else None
    robust = bool(top_name) and all(w == top_name for w in winners.values())

    return {
        "schema_version": 1,
        "feature": data.get("feature", ""),
        "profile": profile_name,
        "weights": weights,
        "ranking": rows,
        "recommendation": top_name,
        "margin_to_runner_up": margin,
        "close_call": close_call,
        "sensitivity": {"winner_by_profile": winners, "robust": robust},
        "audit": audit(candidates),
    }


def render_text(result):
    lines = []
    add = lines.append
    add("SCORING: {}".format(result["feature"] or "(feature not named)"))
    add("profile: {} (weights shown below, normalised to 100)".format(result["profile"]))
    add("")
    add("{:<4}{:<28}{:>7}  {}".format("#", "candidate", "score", "status"))
    add("-" * 72)
    for row in result["ranking"]:
        status = "EXCLUDED: " + "; ".join(row["disqualifiers"]) if row["excluded"] else ""
        add("{:<4}{:<28}{:>7.1f}  {}".format(row["rank"], row["name"][:27], row["total"], status))
    add("")
    add("PER-CRITERION CONTRIBUTION (points of the 100 available)")
    header = "{:<24}".format("criterion") + "".join(
        "{:>13}".format(row["name"][:12]) for row in result["ranking"][:5])
    add(header)
    add("-" * len(header))
    for key in CRITERION_KEYS:
        row_text = "{:<24}".format("{} (w{})".format(key[:16], int(result["weights"][key])))
        for row in result["ranking"][:5]:
            row_text += "{:>13}".format("{:.1f} ({})".format(
                row["contributions"][key], int(row["scores"][key])))
        add(row_text)
    add("")
    if result["margin_to_runner_up"] is not None:
        add("MARGIN: {} points over the runner-up.".format(result["margin_to_runner_up"]))
        if result["close_call"]:
            add("  This is inside the noise floor. Present the top two as near-equivalent "
                "and decide on a concrete tiebreaker, not the decimal.")
    sens = result["sensitivity"]
    add("SENSITIVITY: " + ("winner holds under every weight profile."
                           if sens["robust"] else "winner changes with priorities."))
    for profile_name, winner in sorted(sens["winner_by_profile"].items()):
        add("  {:<16} -> {}".format(profile_name, winner))
    if result["audit"]:
        add("")
        add("EVIDENCE AUDIT")
        for finding in result["audit"]:
            add("  - " + finding)
    return "\n".join(lines)


def render_markdown(result):
    lines = []
    add = lines.append
    add("### Weighted comparison ({} profile)".format(result["profile"]))
    add("")
    add("| # | Option | Score | Notes |")
    add("|---|--------|-------|-------|")
    for row in result["ranking"]:
        note = ("**Excluded** - " + "; ".join(row["disqualifiers"])) if row["excluded"] else row["summary"]
        add("| {} | {} | **{:.1f}** | {} |".format(row["rank"], row["name"], row["total"], note))
    add("")
    add("| Criterion | Weight | " + " | ".join(r["name"] for r in result["ranking"][:5]) + " |")
    add("|---|---|" + "---|" * len(result["ranking"][:5]))
    for key in CRITERION_KEYS:
        cells = " | ".join("{}/5".format(int(r["scores"][key])) for r in result["ranking"][:5])
        add("| {} | {} | {} |".format(key.replace("_", " "), int(result["weights"][key]), cells))
    add("")
    if result["close_call"]:
        add("> Margin over the runner-up is {} points - close enough to treat as a tie. "
            "The decision should turn on a concrete tiebreaker rather than the score."
            .format(result["margin_to_runner_up"]))
    elif result["margin_to_runner_up"] is not None:
        add("> Margin over the runner-up: {} points.".format(result["margin_to_runner_up"]))
    sens = result["sensitivity"]
    if sens["robust"]:
        add(">")
        add("> Sensitivity check: the same option wins under every weight profile "
            "(ship-fast, cost-sensitive, enterprise, long-haul), so the result does not "
            "hinge on how the criteria were weighted.")
    else:
        flips = ", ".join("{} -> {}".format(k, v) for k, v in sorted(sens["winner_by_profile"].items()))
        add(">")
        add("> Sensitivity check: the winner changes with priorities ({}). "
            "Confirm the priority before treating this as settled.".format(flips))
    return "\n".join(lines)


TEMPLATE = {
    "feature": "subscription billing",
    "profile": "default",
    "candidates": [
        {
            "name": "Example Provider",
            "summary": "One line on what this option actually is.",
            "scores": {key: 3 for key in CRITERION_KEYS},
            "evidence": {
                key: "Why this score, citing a repo path or a doc." for key in CRITERION_KEYS
            },
            "facts": [
                {"claim": "pricing or quota figure", "source": "https://vendor.example/pricing",
                 "verified": False}
            ],
            "disqualifiers": [],
        }
    ],
}


def _allow_piping():
    """Exit quietly when output is piped into something like `head`.

    Without this, `analyze_stack.py . | head` prints a BrokenPipeError
    traceback, which looks like a crash in what is a completely normal usage.
    """
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def main(argv=None):
    _allow_piping()
    parser = argparse.ArgumentParser(description="Score integration candidates.")
    parser.add_argument("candidates", nargs="?", help="path to candidates JSON ('-' for stdin)")
    parser.add_argument("--profile", choices=sorted(PROFILES), help="weight profile")
    parser.add_argument("--weights", help="JSON object overriding individual weights")
    parser.add_argument("--format", choices=["text", "json", "markdown"], default="text")
    parser.add_argument("--template", action="store_true", help="print a starter candidates file")
    parser.add_argument("--list-profiles", action="store_true")
    args = parser.parse_args(argv)

    if args.template:
        print(json.dumps(TEMPLATE, indent=2))
        return 0
    if args.list_profiles:
        for name in sorted(PROFILES):
            print("{}:".format(name))
            for key in CRITERION_KEYS:
                print("  {:<24} {}".format(key, PROFILES[name][key]))
        return 0
    if not args.candidates:
        parser.print_usage(sys.stderr)
        sys.stderr.write("error: candidates file required (or use --template)\n")
        return 2

    try:
        raw = sys.stdin.read() if args.candidates == "-" else open(
            args.candidates, "r", encoding="utf-8").read()
        data = json.loads(raw)
    except OSError as exc:
        sys.stderr.write("error: cannot read candidates file: {}\n".format(exc))
        return 1
    except ValueError as exc:
        sys.stderr.write("error: candidates file is not valid JSON: {}\n".format(exc))
        return 1

    override = None
    if args.weights:
        try:
            override = json.loads(args.weights)
        except ValueError as exc:
            sys.stderr.write("error: --weights is not valid JSON: {}\n".format(exc))
            return 2

    try:
        result = build_result(data, args.profile, override)
    except CandidateError as exc:
        sys.stderr.write("error: {}\n".format(exc))
        return 1

    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    elif args.format == "markdown":
        print(render_markdown(result))
    else:
        print(render_text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
