#!/usr/bin/env python3
"""
Test suite for the StackFit scripts.

Standard library only - run with:
    python3 -m unittest discover -s tests -v
    python3 tests/test_scripts.py

Fixtures are built in temp directories so the tests are hermetic and can run
anywhere without network access.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import analyze_stack  # noqa: E402
import github_probe  # noqa: E402
import impact_scan  # noqa: E402
import score_candidates  # noqa: E402


def write(root, rel, content=""):
    path = os.path.join(root, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def make_next_repo(root):
    """A Next.js + Prisma + Postgres app on Vercel with auth but no billing."""
    write(root, "package.json", json.dumps({
        "name": "acme", "type": "module",
        "scripts": {"dev": "next dev", "test": "vitest"},
        "dependencies": {
            "next": "14.2.3", "react": "18.3.1", "next-auth": "^4.24.7",
            "@prisma/client": "^5.14.0", "pg": "^8.11.5", "resend": "^3.2.0",
            "@sentry/nextjs": "^8.7.0",
        },
        "devDependencies": {"prisma": "^5.14.0", "vitest": "^1.6.0"},
    }))
    write(root, "vercel.json", '{"framework":"nextjs"}')
    write(root, "prisma/schema.prisma",
          "model User {\n  id String @id\n  email String @unique\n}\n")
    write(root, "prisma/migrations/20240101_init/migration.sql", "CREATE TABLE users();")
    write(root, "app/api/auth/route.ts", 'import NextAuth from "next-auth";')
    write(root, "lib/session.ts",
          'import { getServerSession } from "next-auth";\n'
          'export async function requireAuth() { return getServerSession(); }\n')
    write(root, "app/dashboard.tsx",
          'export default function D() { const isPro = false; return isPro; }')
    write(root, ".env.example", "DATABASE_URL=postgres://x\nNEXTAUTH_SECRET=y\n")
    write(root, ".env", "DATABASE_URL=postgres://REAL_SECRET_VALUE\n")
    write(root, "tests/app.test.ts", "import { test } from 'vitest';")
    write(root, "node_modules/leftpad/index.js", "module.exports = 1;")
    write(root, "node_modules/leftpad/package.json",
          '{"dependencies":{"stripe":"^15.0.0"}}')
    return root


def make_django_repo(root):
    """Django + Celery + Docker: long-running runtime, job runner present."""
    write(root, "requirements.txt",
          "Django==5.0.4\npsycopg2-binary==2.9.9\ncelery[redis]==5.4.0\n"
          "redis==5.0.4\nboto3==1.34.100\npytest==8.2.0\n")
    write(root, "Dockerfile", "FROM python:3.12\n")
    write(root, "users/models.py",
          "from django.db import models\n"
          "class User(models.Model):\n    email = models.EmailField()\n")
    write(root, "users/migrations/0001_initial.py", "")
    write(root, "api/urls.py", "from django.urls import path\nurlpatterns = []\n")
    write(root, "api/views.py",
          "from django.contrib.auth.decorators import login_required\n"
          "@login_required\ndef dashboard(request): return request.user\n")
    write(root, "worker/tasks.py",
          "from celery import shared_task\n@shared_task\ndef t(): pass\n")
    write(root, "tests/test_api.py", "def test_x(): assert True\n")
    return root


def base_scores(value=3):
    return {key: value for key in score_candidates.CRITERION_KEYS}


def candidate(name, value=3, **overrides):
    scores = base_scores(value)
    scores.update(overrides)
    return {
        "name": name,
        "scores": scores,
        "evidence": {key: "reason for " + key for key in score_candidates.CRITERION_KEYS},
        "facts": [{"claim": "price", "source": "https://x", "verified": True}],
    }


class TempRepoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# ---------------------------------------------------------------- analyze_stack

class TestAnalyzeStack(TempRepoTest):
    def test_detects_javascript_stack(self):
        result = analyze_stack.analyze(make_next_repo(self.tmp))
        names = {item["name"] for items in result["stack"].values() for item in items}
        for expected in ("Next.js", "React", "Prisma", "PostgreSQL",
                         "NextAuth / Auth.js", "Resend", "Sentry"):
            self.assertIn(expected, names, "missing " + expected)
        self.assertEqual(result["stack"]["framework"][0]["name"], "Next.js")

    def test_detects_python_stack(self):
        result = analyze_stack.analyze(make_django_repo(self.tmp))
        names = {item["name"] for items in result["stack"].values() for item in items}
        self.assertIn("Django", names)
        self.assertIn("Celery", names)
        self.assertIn("PostgreSQL", names)
        self.assertIn("AWS SDK (boto3)", names)

    def test_skips_node_modules(self):
        """Vendored dependencies must not be mistaken for the project's own stack."""
        result = analyze_stack.analyze(make_next_repo(self.tmp))
        names = {item["name"] for items in result["stack"].values() for item in items}
        self.assertNotIn("Stripe", names,
                         "stripe from node_modules leaked into the detected stack")
        self.assertNotIn("node_modules", json.dumps(result["manifests"]))

    def test_never_reads_real_env_files(self):
        """Secrets must never reach the output, even as a side effect."""
        result = analyze_stack.analyze(make_next_repo(self.tmp))
        blob = json.dumps(result)
        self.assertNotIn("REAL_SECRET_VALUE", blob)
        self.assertIn("DATABASE_URL", result["env"]["keys"])
        self.assertEqual(result["env"]["sources"], [".env.example"])

    def test_runtime_model_inference(self):
        serverless = analyze_stack.analyze(make_next_repo(self.tmp))
        self.assertEqual(serverless["deployment"]["runtime_model"], "serverless")
        other = tempfile.mkdtemp()
        try:
            longrunning = analyze_stack.analyze(make_django_repo(other))
            self.assertEqual(longrunning["deployment"]["runtime_model"], "long-running")
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_capabilities(self):
        result = analyze_stack.analyze(make_next_repo(self.tmp))
        caps = result["capabilities"]
        self.assertTrue(caps["can_receive_webhooks"])
        self.assertTrue(caps["has_database"])
        self.assertTrue(caps["has_migrations"])
        self.assertTrue(caps["has_tests"])
        self.assertFalse(caps["has_background_jobs"])

    def test_serverless_without_jobs_raises_constraint(self):
        """The constraint that most often invalidates a recommendation."""
        result = analyze_stack.analyze(make_next_repo(self.tmp))
        self.assertTrue(any("job runner" in c.lower() for c in result["constraints"]))

    def test_existing_vendors_surfaced(self):
        result = analyze_stack.analyze(make_next_repo(self.tmp))
        self.assertIn("Resend", result["existing_vendors"])
        self.assertIn("NextAuth / Auth.js", result["existing_vendors"])

    def test_empty_repo_is_not_an_error(self):
        result = analyze_stack.analyze(self.tmp)
        self.assertEqual(result["file_count"], 0)
        self.assertEqual(result["stack"], {})
        self.assertIn("greenfield", analyze_stack.render_text(result).lower())

    def test_deterministic_output(self):
        make_next_repo(self.tmp)
        first = json.dumps(analyze_stack.analyze(self.tmp), sort_keys=True)
        second = json.dumps(analyze_stack.analyze(self.tmp), sort_keys=True)
        self.assertEqual(first, second)

    def test_truncation_flagged(self):
        make_next_repo(self.tmp)
        result = analyze_stack.analyze(self.tmp, max_files=2)
        self.assertTrue(result["truncated"])
        self.assertTrue(any("max-files" in c for c in result["constraints"]))

    def test_scoped_package_prefix_matching(self):
        write(self.tmp, "package.json",
              json.dumps({"dependencies": {"@aws-sdk/client-s3": "3.0.0",
                                           "@clerk/nextjs": "5.0.0"}}))
        result = analyze_stack.analyze(self.tmp)
        names = {item["name"] for items in result["stack"].values() for item in items}
        self.assertIn("AWS S3", names)
        self.assertIn("Clerk", names)

    def test_malformed_manifest_does_not_crash(self):
        write(self.tmp, "package.json", "{not valid json at all")
        result = analyze_stack.analyze(self.tmp)
        self.assertEqual(len(result["manifests"]), 1)
        self.assertEqual(result["manifests"][0]["dependency_count"], 0)

    def test_text_renderer_runs_on_both_fixtures(self):
        for maker in (make_next_repo, make_django_repo):
            root = tempfile.mkdtemp()
            try:
                text = analyze_stack.render_text(analyze_stack.analyze(maker(root)))
                self.assertIn("STACK ANALYSIS", text)
            finally:
                shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------ score_candidates

class TestScoring(unittest.TestCase):
    def test_perfect_and_zero_scores(self):
        data = {"candidates": [candidate("Max", 5), candidate("Min", 0)]}
        result = score_candidates.build_result(data, "default", None)
        totals = {row["name"]: row["total"] for row in result["ranking"]}
        self.assertEqual(totals["Max"], 100.0)
        self.assertEqual(totals["Min"], 0.0)

    def test_weighted_arithmetic_is_correct(self):
        """Hand-checked: 5/5 on an 18-weight criterion contributes exactly 18."""
        data = {"candidates": [candidate("A", 0, architecture_fit=5)]}
        result = score_candidates.build_result(data, "default", None)
        row = result["ranking"][0]
        self.assertEqual(row["contributions"]["architecture_fit"], 18.0)
        self.assertEqual(row["total"], 18.0)

    def test_all_profiles_sum_to_100(self):
        for name, weights in score_candidates.PROFILES.items():
            self.assertEqual(sum(weights.values()), 100, name + " weights must total 100")
            self.assertEqual(sorted(weights), sorted(score_candidates.CRITERION_KEYS),
                             name + " must score every criterion")

    def test_ranking_order_and_determinism(self):
        data = {"candidates": [candidate("Low", 2), candidate("High", 5),
                               candidate("Mid", 3)]}
        first = score_candidates.build_result(data, "default", None)
        second = score_candidates.build_result(data, "default", None)
        self.assertEqual([r["name"] for r in first["ranking"]], ["High", "Mid", "Low"])
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_ties_break_alphabetically(self):
        data = {"candidates": [candidate("Zeta", 3), candidate("Alpha", 3)]}
        result = score_candidates.build_result(data, "default", None)
        self.assertEqual([r["name"] for r in result["ranking"]], ["Alpha", "Zeta"])

    def test_close_call_detected(self):
        data = {"candidates": [candidate("A", 3), candidate("B", 3, sdk_quality=4)]}
        result = score_candidates.build_result(data, "default", None)
        self.assertTrue(result["close_call"])
        self.assertLess(result["margin_to_runner_up"], score_candidates.CLOSE_CALL_MARGIN)

    def test_clear_winner_is_not_a_close_call(self):
        data = {"candidates": [candidate("A", 5), candidate("B", 1)]}
        result = score_candidates.build_result(data, "default", None)
        self.assertFalse(result["close_call"])

    def test_sensitivity_flags_profile_dependent_winner(self):
        """A cheap-but-slow option vs a fast-but-costly one should flip by profile."""
        cheap = candidate("Cheap", 2, cost_efficiency=5, operational_simplicity=5,
                          portability=5)
        fast = candidate("Fast", 2, implementation_speed=5, documentation_quality=5,
                         sdk_quality=5, architecture_fit=5)
        result = score_candidates.build_result({"candidates": [cheap, fast]}, "default", None)
        winners = set(result["sensitivity"]["winner_by_profile"].values())
        self.assertGreater(len(winners), 1, "expected the winner to change by profile")
        self.assertFalse(result["sensitivity"]["robust"])

    def test_sensitivity_robust_when_one_option_dominates(self):
        data = {"candidates": [candidate("Best", 5), candidate("Rest", 2)]}
        result = score_candidates.build_result(data, "default", None)
        self.assertTrue(result["sensitivity"]["robust"])

    def test_disqualified_option_cannot_be_recommended(self):
        blocked = candidate("Blocked", 5)
        blocked["disqualifiers"] = ["no SOC 2 report"]
        data = {"candidates": [blocked, candidate("Allowed", 2)]}
        result = score_candidates.build_result(data, "default", None)
        self.assertEqual(result["recommendation"], "Allowed")
        self.assertEqual(result["ranking"][-1]["name"], "Blocked")
        self.assertTrue(result["ranking"][-1]["excluded"])

    def test_weights_override(self):
        data = {"candidates": [candidate("A", 0, cost_efficiency=5)]}
        result = score_candidates.build_result(data, "default", {"cost_efficiency": 50})
        self.assertEqual(result["weights"]["cost_efficiency"], 50)
        # 50 of 138 total weight, all of it earned
        self.assertAlmostEqual(result["ranking"][0]["total"], round(50 * 100.0 / 138, 1), places=1)

    def test_profile_selection_from_file(self):
        data = {"profile": "ship-fast", "candidates": [candidate("A", 3)]}
        result = score_candidates.build_result(data, None, None)
        self.assertEqual(result["profile"], "ship-fast")

    def test_audit_flags_missing_evidence(self):
        bare = {"name": "Bare", "scores": base_scores(3)}
        result = score_candidates.build_result({"candidates": [bare]}, "default", None)
        self.assertTrue(any("without evidence" in f for f in result["audit"]))

    def test_audit_flags_unverified_facts(self):
        shaky = candidate("Shaky")
        shaky["facts"] = [{"claim": "$99/mo", "source": "memory", "verified": False}]
        result = score_candidates.build_result({"candidates": [shaky]}, "default", None)
        self.assertTrue(any("unverified" in f for f in result["audit"]))

    def test_clean_candidate_has_no_audit_findings(self):
        result = score_candidates.build_result({"candidates": [candidate("Clean")]},
                                               "default", None)
        self.assertEqual(result["audit"], [])

    def test_validation_rejects_out_of_range(self):
        data = {"candidates": [candidate("A", 3, architecture_fit=9)]}
        with self.assertRaises(score_candidates.CandidateError):
            score_candidates.build_result(data, "default", None)

    def test_validation_rejects_missing_criteria(self):
        with self.assertRaises(score_candidates.CandidateError):
            score_candidates.build_result(
                {"candidates": [{"name": "A", "scores": {"architecture_fit": 3}}]},
                "default", None)

    def test_validation_rejects_unknown_criteria(self):
        bad = candidate("A")
        bad["scores"]["vibes"] = 5
        with self.assertRaises(score_candidates.CandidateError):
            score_candidates.build_result({"candidates": [bad]}, "default", None)

    def test_validation_rejects_duplicates_and_empties(self):
        for payload in (
            {"candidates": [candidate("A"), candidate("A")]},
            {"candidates": []},
            {"candidates": [candidate("X") for _ in range(9)]},
            {"candidates": "not a list"},
        ):
            with self.assertRaises(score_candidates.CandidateError):
                score_candidates.build_result(payload, "default", None)

    def test_validation_rejects_boolean_scores(self):
        bad = candidate("A")
        bad["scores"]["architecture_fit"] = True
        with self.assertRaises(score_candidates.CandidateError):
            score_candidates.build_result({"candidates": [bad]}, "default", None)

    def test_unknown_profile_rejected(self):
        with self.assertRaises(score_candidates.CandidateError):
            score_candidates.build_result({"candidates": [candidate("A")]}, "turbo", None)

    def test_template_is_valid_input(self):
        """The starter file must round-trip through the scorer without editing."""
        result = score_candidates.build_result(
            json.loads(json.dumps(score_candidates.TEMPLATE)), None, None)
        self.assertEqual(result["recommendation"], "Example Provider")

    def test_renderers_produce_output(self):
        data = {"feature": "billing", "candidates": [candidate("A", 4), candidate("B", 2)]}
        result = score_candidates.build_result(data, "default", None)
        self.assertIn("SENSITIVITY", score_candidates.render_text(result))
        markdown = score_candidates.render_markdown(result)
        self.assertIn("| # | Option | Score |", markdown)
        self.assertIn("Sensitivity check", markdown)


# --------------------------------------------------------------- impact_scan

class TestImpactScan(TempRepoTest):
    def test_payments_touchpoints_found(self):
        result = impact_scan.scan(make_next_repo(self.tmp), "payments")
        self.assertGreater(result["total_files_touched"], 0)
        files = [f for role in result["touchpoints"].values() for f in role["files"]]
        self.assertTrue(any("schema.prisma" in f for f in files))

    def test_infrastructure_detected_from_paths(self):
        result = impact_scan.scan(make_next_repo(self.tmp), "payments")
        self.assertTrue(result["infrastructure"]["http_endpoint"]["present"])
        self.assertTrue(result["infrastructure"]["migrations"]["present"])
        self.assertTrue(result["infrastructure"]["tests"]["present"])
        self.assertFalse(result["infrastructure"]["background_jobs"]["present"])

    def test_infrastructure_detected_from_dependencies(self):
        """Celery in requirements means a job runner exists even with no matching path.

        Without this, impact_scan would contradict analyze_stack, which reads
        manifests - two tools disagreeing is worse than either being silent.
        """
        root = os.path.join(self.tmp, "dj")
        os.makedirs(root)
        write(root, "requirements.txt", "Django==5.0\ncelery==5.4.0\n")
        write(root, "app.py", "x = 1\n")
        result = impact_scan.scan(root, "payments")
        jobs = result["infrastructure"]["background_jobs"]
        self.assertTrue(jobs["present"])
        self.assertTrue(jobs["from_dependency_only"])
        self.assertTrue(any("celery" in e for e in jobs["examples"]))

    def test_dependency_markers_avoid_substring_false_positives(self):
        write(self.tmp, "package.json",
              json.dumps({"dependencies": {"bulldozer-ui": "1.0.0", "nextra": "2.0.0"}}))
        write(self.tmp, "index.js", "console.log(1);")
        result = impact_scan.scan(self.tmp, "payments")
        self.assertFalse(result["infrastructure"]["background_jobs"]["present"],
                         "'bulldozer-ui' must not register as the 'bull' job runner")

    def test_missing_infrastructure_increases_effort(self):
        bare = os.path.join(self.tmp, "bare")
        os.makedirs(bare)
        write(bare, "index.js", "console.log('hi');")
        rich = make_next_repo(os.path.join(self.tmp, "rich"))
        bare_effort = impact_scan.scan(bare, "payments")["effort_estimate"]
        rich_effort = impact_scan.scan(rich, "payments")["effort_estimate"]
        self.assertGreater(bare_effort["inputs"]["penalty_days"],
                           rich_effort["inputs"]["penalty_days"])
        self.assertTrue(bare_effort["inputs"]["penalties"])

    def test_effort_band_is_ordered_and_positive(self):
        for domain in impact_scan.DOMAINS:
            effort = impact_scan.scan(make_next_repo(self.tmp), domain)["effort_estimate"]
            self.assertGreater(effort["low_days"], 0, domain)
            self.assertGreaterEqual(effort["high_days"], effort["low_days"], domain)

    def test_every_domain_runs_clean(self):
        root = make_django_repo(self.tmp)
        for domain in impact_scan.DOMAINS:
            result = impact_scan.scan(root, domain)
            self.assertEqual(result["domain"], domain)
            self.assertIn("required_capabilities", result)
            self.assertTrue(impact_scan.render_text(result))

    def test_domain_aliases_resolve(self):
        for alias, target in impact_scan.DOMAIN_ALIASES.items():
            self.assertIn(target, impact_scan.DOMAINS,
                          "alias {} points at unknown domain {}".format(alias, target))

    def test_empty_repo_is_not_an_error(self):
        result = impact_scan.scan(self.tmp, "auth")
        self.assertEqual(result["total_files_touched"], 0)
        self.assertIn("No matching files", impact_scan.render_text(result))

    def test_deterministic_output(self):
        make_next_repo(self.tmp)
        first = json.dumps(impact_scan.scan(self.tmp, "payments"), sort_keys=True)
        second = json.dumps(impact_scan.scan(self.tmp, "payments"), sort_keys=True)
        self.assertEqual(first, second)


# ----------------------------------------------------------------------- CLI

class TestCommandLine(TempRepoTest):
    def run_script(self, name, args):
        return subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, name)] + args,
            capture_output=True, text=True)

    def test_analyze_stack_cli_json(self):
        make_next_repo(self.tmp)
        proc = self.run_script("analyze_stack.py", [self.tmp, "--format", "json"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["schema_version"], 1)

    def test_analyze_stack_cli_bad_path(self):
        proc = self.run_script("analyze_stack.py", [os.path.join(self.tmp, "nope")])
        self.assertEqual(proc.returncode, 2)

    def test_impact_scan_cli_alias(self):
        make_next_repo(self.tmp)
        proc = self.run_script("impact_scan.py",
                               [self.tmp, "--domain", "subscriptions", "--format", "json"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["domain"], "payments")

    def test_impact_scan_cli_falls_back_on_unknown_domain(self):
        """Unrecognised features get the generic profile, not an error.

        Erroring here would strand the user mid-task for the common case of a
        feature outside the curated domain list.
        """
        proc = self.run_script("impact_scan.py",
                               [self.tmp, "--domain", "telepathy", "--format", "json"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["domain"], "generic")
        self.assertIn("no specific playbook", proc.stderr)

    def test_impact_scan_requires_domain(self):
        proc = self.run_script("impact_scan.py", [self.tmp])
        self.assertEqual(proc.returncode, 2)

    def test_score_cli_template_round_trip(self):
        proc = self.run_script("score_candidates.py", ["--template"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        path = os.path.join(self.tmp, "c.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(proc.stdout)
        scored = self.run_script("score_candidates.py", [path, "--format", "json"])
        self.assertEqual(scored.returncode, 0, scored.stderr)
        self.assertEqual(json.loads(scored.stdout)["recommendation"], "Example Provider")

    def test_score_cli_rejects_bad_json(self):
        path = os.path.join(self.tmp, "bad.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        proc = self.run_script("score_candidates.py", [path])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not valid JSON", proc.stderr)

    def test_score_cli_missing_file_argument(self):
        proc = self.run_script("score_candidates.py", [])
        self.assertEqual(proc.returncode, 2)

    def test_score_cli_list_profiles(self):
        proc = self.run_script("score_candidates.py", ["--list-profiles"])
        self.assertEqual(proc.returncode, 0)
        for name in score_candidates.PROFILES:
            self.assertIn(name, proc.stdout)

    def test_piping_to_head_does_not_traceback(self):
        """`analyze_stack.py . | head` is normal usage and must not look like a crash."""
        make_next_repo(self.tmp)
        for name, args in (
            ("analyze_stack.py", [self.tmp]),
            ("impact_scan.py", [self.tmp, "--domain", "payments"]),
        ):
            script = os.path.join(SCRIPTS_DIR, name)
            proc = subprocess.run(
                "{} {} {} | head -2".format(
                    sys.executable, script, " ".join(args)),
                shell=True, capture_output=True, text=True)
            self.assertNotIn("BrokenPipeError", proc.stderr, name + " leaked a traceback")
            self.assertNotIn("Traceback", proc.stderr, name + " leaked a traceback")

    def test_help_available_on_every_script(self):
        for name in ("analyze_stack.py", "score_candidates.py", "impact_scan.py"):
            proc = self.run_script(name, ["--help"])
            self.assertEqual(proc.returncode, 0, name + " --help failed")
            self.assertIn("usage", proc.stdout.lower())


# ------------------------------------------------------------------ packaging

class TestGithubProbe(unittest.TestCase):
    """All offline - the network layer is stubbed so tests never hit GitHub."""

    NOW = datetime(2026, 9, 15)

    def test_github_slug_from_registry_url_shapes(self):
        cases = {
            "git+https://github.com/stripe/stripe-node.git": "stripe/stripe-node",
            "https://github.com/getsentry/sentry-python": "getsentry/sentry-python",
            "git@github.com:vercel/next.js.git": "vercel/next.js",
            "https://github.com/psf/requests/issues": "psf/requests",
        }
        for url, expected in cases.items():
            self.assertEqual(github_probe.github_slug(url), expected, url)
        for bad in (None, "", "https://gitlab.com/a/b", "not a url", 42):
            self.assertIsNone(github_probe.github_slug(bad))

    def test_parse_npm_extracts_decisive_facts(self):
        doc = {
            "name": "stripe", "dist-tags": {"latest": "15.0.0"},
            "versions": {"15.0.0": {"types": "types/index.d.ts", "license": "MIT"}},
            "time": {"15.0.0": "2026-09-09T10:00:00.000Z"},
            "repository": {"url": "git+https://github.com/stripe/stripe-node.git"},
        }
        parsed = github_probe.parse_npm(doc)
        self.assertEqual(parsed["latest_version"], "15.0.0")
        self.assertEqual(parsed["repo"], "stripe/stripe-node")
        self.assertTrue(parsed["typescript_types"])
        self.assertFalse(parsed["deprecated"])

    def test_parse_npm_detects_version_level_deprecation(self):
        """Deprecation is the single most decisive fact about an SDK."""
        doc = {
            "name": "old-sdk", "dist-tags": {"latest": "2.0.0"},
            "versions": {"2.0.0": {"deprecated": "use new-sdk instead"}},
            "time": {"2.0.0": "2026-01-01T00:00:00.000Z"},
        }
        parsed = github_probe.parse_npm(doc)
        self.assertTrue(parsed["deprecated"])
        self.assertIn("new-sdk", parsed["deprecation_message"])

    def test_parse_pypi(self):
        doc = {
            "info": {"name": "django-allauth", "version": "0.63.0",
                     "project_urls": {"Source": "https://github.com/pennersr/django-allauth"},
                     "classifiers": ["Development Status :: 5 - Production/Stable"]},
            "releases": {"0.63.0": [{"upload_time_iso_8601": "2026-08-01T00:00:00.000Z"}]},
        }
        parsed = github_probe.parse_pypi(doc)
        self.assertEqual(parsed["repo"], "pennersr/django-allauth")
        self.assertEqual(parsed["latest_version"], "0.63.0")
        self.assertFalse(parsed["deprecated"])

    def test_parse_handles_garbage_without_crashing(self):
        for junk in (None, [], "string", {}):
            self.assertIsInstance(github_probe.parse_npm(junk), dict)
            self.assertIsInstance(github_probe.parse_pypi(junk), dict)

    def test_maintenance_bands(self):
        def status(days=None, **kw):
            signals = dict(kw)
            if days is not None:
                signals["last_published"] = (
                    self.NOW - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
            return github_probe.derive_maintenance(signals, self.NOW)[0]

        self.assertEqual(status(5), "active")
        self.assertEqual(status(200), "slowing")
        self.assertEqual(status(500), "stale")
        self.assertEqual(status(1200), "dormant")
        self.assertEqual(status(5, archived=True), "archived")
        self.assertEqual(status(5, deprecated=True), "deprecated")
        self.assertEqual(status(), "unknown")

    def test_archived_beats_recent_activity(self):
        """An archived repo is dead regardless of a recent final commit."""
        signals = {"archived": True,
                   "last_published": self.NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}
        status, reason = github_probe.derive_maintenance(signals, self.NOW)
        self.assertEqual(status, "archived")
        self.assertIn("archived", reason)

    def test_suggested_anchors_track_status(self):
        for status in ("archived", "deprecated"):
            anchors = github_probe.suggest_anchors({}, status)
            self.assertEqual(anchors["sdk_quality"], "0-1")
            self.assertIn("disqualify", anchors["note"])
        healthy = github_probe.suggest_anchors({"stars": 5000}, "active")
        self.assertEqual(healthy["sdk_quality"], "4-5")

    def test_registry_url_encodes_scoped_packages(self):
        url = github_probe.registry_url("@paddle/paddle-js", "npm")
        self.assertIn("@paddle", url)
        self.assertNotIn(" ", url)
        self.assertIn("pypi.org", github_probe.registry_url("requests", "pypi"))

    def test_probe_degrades_when_github_is_rate_limited(self):
        """Partial registry data beats failing - the common real-world case."""
        npm_doc = {
            "name": "stripe", "dist-tags": {"latest": "15.0.0"},
            "versions": {"15.0.0": {}},
            "time": {"15.0.0": "2026-09-09T10:00:00.000Z"},
            "repository": {"url": "https://github.com/stripe/stripe-node"},
        }

        def fake_fetch(url, token=None, accept="application/json"):
            if "registry.npmjs.org" in url:
                return npm_doc
            raise github_probe.RateLimited("GitHub rate limit exhausted")

        with mock.patch.object(github_probe, "fetch_json", fake_fetch):
            result = github_probe.probe_one("stripe", "npm", None, self.NOW)
        self.assertEqual(result["latest_version"], "15.0.0")
        self.assertEqual(result["repo"], "stripe/stripe-node")
        self.assertEqual(result["maintenance"], "active")
        self.assertTrue(any("rate limit" in w for w in result["warnings"]))
        self.assertNotIn("github", result["sources"])

    def test_probe_reports_when_nothing_is_found(self):
        with mock.patch.object(github_probe, "fetch_json",
                               lambda *a, **k: None):
            result = github_probe.probe_one("nonexistent-xyz", "auto", None, self.NOW)
        self.assertEqual(result["sources"], [])
        self.assertTrue(any("no data found" in w for w in result["warnings"]))
        self.assertEqual(result["maintenance"], "unknown")

    def test_probe_accepts_owner_repo_directly(self):
        def fake_fetch(url, token=None, accept="application/json"):
            self.assertIn("api.github.com/repos/stripe/stripe-node", url)
            return {"stargazers_count": 4000, "archived": False,
                    "pushed_at": "2026-09-10T00:00:00Z", "open_issues_count": 20}

        with mock.patch.object(github_probe, "fetch_json", fake_fetch):
            result = github_probe.probe_one("stripe/stripe-node", "auto", None, self.NOW)
        self.assertEqual(result["stars"], 4000)
        self.assertEqual(result["maintenance"], "active")

    def test_find_returns_empty_on_rate_limit(self):
        def fake_fetch(*args, **kwargs):
            raise github_probe.RateLimited("limited")
        with mock.patch.object(github_probe, "fetch_json", fake_fetch):
            found = github_probe.find_repos("anything", None)
        self.assertEqual(found["results"], [])
        self.assertTrue(found["warnings"])
        self.assertIn("no results", github_probe.render_find(found))

    def test_renderers_run(self):
        sample = [{"query": "stripe", "maintenance": "active",
                   "maintenance_reason": "last activity 5 days ago",
                   "latest_version": "15.0.0", "repo": "stripe/stripe-node",
                   "suggested_anchors": {"sdk_quality": "4-5",
                                         "ecosystem_maturity": "4-5", "note": None},
                   "sources": ["npm"], "warnings": []}]
        text = github_probe.render_probe(sample)
        self.assertIn("SDK HEALTH", text)
        self.assertIn("stripe", text)
        self.assertIn("popularity, not maintenance", text)

    def test_no_deprecation_warnings_on_modern_python(self):
        proc = subprocess.run(
            [sys.executable, "-W", "error::DeprecationWarning",
             os.path.join(SCRIPTS_DIR, "github_probe.py")],
            capture_output=True, text=True)
        self.assertNotIn("DeprecationWarning", proc.stderr)


class TestSkillIntegrity(unittest.TestCase):
    """The checks a skill has to pass to install and load correctly."""

    def test_skill_md_frontmatter(self):
        with open(os.path.join(REPO_ROOT, "SKILL.md"), encoding="utf-8") as fh:
            content = fh.read()
        self.assertTrue(content.startswith("---\n"))
        frontmatter = content.split("---", 2)[1]
        fields = {}
        for line in frontmatter.strip().splitlines():
            if ":" in line and not line.startswith(" "):
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
        self.assertEqual(fields.get("name"), "stackfit")
        description = fields.get("description", "")
        self.assertTrue(description)
        self.assertLessEqual(len(description), 1024,
                             "description exceeds the 1024-character limit")
        self.assertNotIn("<", description, "angle brackets are rejected in descriptions")
        self.assertNotIn(">", description)

    def test_skill_md_length_is_reasonable(self):
        with open(os.path.join(REPO_ROOT, "SKILL.md"), encoding="utf-8") as fh:
            lines = fh.readlines()
        self.assertLess(len(lines), 500,
                        "SKILL.md should stay under 500 lines; move detail to references/")

    def test_referenced_files_exist(self):
        for rel in ("references/scoring-rubric.md", "references/impact-analysis.md",
                    "references/migration-analysis.md", "references/adr-template.md",
                    "assets/report-template.md", "scripts/analyze_stack.py",
                    "scripts/score_candidates.py", "scripts/impact_scan.py",
                    "scripts/github_probe.py"):
            self.assertTrue(os.path.exists(os.path.join(REPO_ROOT, rel)), rel + " is missing")

    def test_playbooks_scanner_and_skill_md_agree(self):
        """A playbook the scanner rejects is a dead end for the user mid-task.

        This exact drift shipped once: `jobs` had a playbook and was advertised in
        SKILL.md, but impact_scan.py had no such domain and exited 2.
        """
        with open(os.path.join(REPO_ROOT, "SKILL.md"), encoding="utf-8") as fh:
            skill = fh.read()
        folder = os.path.join(REPO_ROOT, "references", "domains")
        playbooks = sorted(f[:-3] for f in os.listdir(folder) if f.endswith(".md"))
        self.assertGreaterEqual(len(playbooks), 15)
        for domain in playbooks:
            self.assertIn(domain, impact_scan.DOMAINS,
                          "playbook '{}' has no impact_scan domain".format(domain))
            self.assertIn("`" + domain + "`", skill,
                          "playbook '{}' is not advertised in SKILL.md".format(domain))

    def test_generic_fallback_exists_for_unlisted_features(self):
        """The skill must work for any feature, not only curated domains."""
        self.assertIn("generic", impact_scan.DOMAINS)
        self.assertIsNone(impact_scan.resolve_domain("quantum teleportation"))
        self.assertEqual(impact_scan.resolve_domain("e-signature for contracts"),
                         "documents")
        self.assertEqual(impact_scan.resolve_domain("add stripe billing"), "payments")
        self.assertEqual(impact_scan.resolve_domain("subscriptions"), "payments")


    def test_domain_playbooks_carry_no_hardcoded_pricing(self):
        """Prices go stale and quietly embarrass every recommendation built on them."""
        import re as _re
        folder = os.path.join(REPO_ROOT, "references", "domains")
        for name in sorted(os.listdir(folder)):
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                body = fh.read()
            self.assertIsNone(_re.search(r"\$\d", body),
                              name + " contains a hardcoded price")

    def test_only_one_skill_md(self):
        found = []
        for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
            dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__"}]
            if "SKILL.md" in filenames:
                found.append(dirpath)
        self.assertEqual(len(found), 1, "exactly one SKILL.md is allowed: " + str(found))


if __name__ == "__main__":
    unittest.main(verbosity=2)
