#!/usr/bin/env python3
"""
github_probe.py - Measure SDK health instead of guessing it.

Two rubric criteria, sdk_quality and ecosystem_maturity, are usually scored from
vague impressions. This turns them into measurements: is the package deprecated,
when was it last published, is the repo archived, how recently was it pushed.
It also finds real integrations on GitHub to copy patterns from.

Sources, in order of reliability under rate limits:
  1. Package registries (npm, PyPI) - generous limits, and the only place that
     reports deprecation, which is the single most decisive fact about an SDK.
  2. GitHub REST API - richer, but 60 requests/hour unauthenticated and shared
     across everyone on an IP. Set GITHUB_TOKEN (or have `gh` logged in) for
     5000/hour. When the quota is gone the probe degrades to registry data and
     says so rather than failing.

Usage:
    python3 github_probe.py probe stripe @paddle/paddle-js --ecosystem npm
    python3 github_probe.py probe django-allauth --ecosystem pypi --format json
    python3 github_probe.py probe stripe/stripe-node
    python3 github_probe.py find "nextjs stripe subscription" --language TypeScript

Exit codes: 0 ok (including partial results), 2 bad arguments.
Never exits non-zero for network failure - partial data beats no answer.
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.github.com"
UA = "stackfit-skill"
TIMEOUT = 15

# Maintenance bands in days since the last sign of life. Chosen so that a normal
# quarterly release cycle still reads as active, and so "abandoned" means a full
# year of silence rather than a slow month.
ACTIVE_DAYS = 120
SLOWING_DAYS = 365
STALE_DAYS = 730


class RateLimited(Exception):
    pass


def utcnow():
    """UTC now as a naive datetime, without the 3.12 deprecation on utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _allow_piping():
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def github_token():
    """Env var first, then the gh CLI if the developer is already logged in."""
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(key):
            return os.environ[key]
    try:
        proc = subprocess.run(["gh", "auth", "token"], capture_output=True,
                              text=True, timeout=5)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def fetch_json(url, token=None, accept="application/json"):
    headers = {"User-Agent": UA, "Accept": accept}
    if token and url.startswith(API):
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        remaining = exc.headers.get("x-ratelimit-remaining") if exc.headers else None
        if exc.code in (403, 429) and remaining == "0":
            reset = exc.headers.get("x-ratelimit-reset")
            raise RateLimited(_reset_message(reset))
        if exc.code == 404:
            return None
        raise
    except (urllib.error.URLError, ValueError, OSError) as exc:
        raise RateLimited("network unavailable ({})".format(exc))


def _reset_message(reset):
    try:
        when = datetime(1970, 1, 1) + timedelta(seconds=int(reset))
        return "GitHub rate limit exhausted, resets at {} UTC. Set GITHUB_TOKEN for 5000/hour.".format(
            when.strftime("%H:%M"))
    except (TypeError, ValueError):
        return "GitHub rate limit exhausted. Set GITHUB_TOKEN for 5000/hour."


# ---------------------------------------------------------------- pure parsing

def github_slug(url):
    """Extract owner/repo from any of the URL shapes registries use."""
    if not url or not isinstance(url, str):
        return None
    match = re.search(r"github\.com[:/]+([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", url)
    if not match:
        return None
    owner, repo = match.group(1), re.sub(r"\.git$", "", match.group(2))
    if not owner or not repo or owner in {"sponsors", "orgs"}:
        return None
    return "{}/{}".format(owner, repo)


def parse_npm(doc):
    """Pull the decisive facts out of an npm registry document."""
    if not isinstance(doc, dict):
        return {}
    latest = (doc.get("dist-tags") or {}).get("latest")
    versions = doc.get("versions") or {}
    version_doc = versions.get(latest) or {}
    times = doc.get("time") or {}
    repo = doc.get("repository")
    repo_url = repo.get("url") if isinstance(repo, dict) else repo
    # Deprecation can sit on the whole package or just the current version.
    deprecated = version_doc.get("deprecated") or doc.get("deprecated")
    return {
        "registry": "npm",
        "name": doc.get("name"),
        "latest_version": latest,
        "last_published": times.get(latest) or times.get("modified"),
        "deprecated": bool(deprecated),
        "deprecation_message": deprecated if isinstance(deprecated, str) else None,
        "license": version_doc.get("license") or doc.get("license"),
        "typescript_types": bool(version_doc.get("types") or version_doc.get("typings")),
        "repo": github_slug(repo_url) or github_slug(doc.get("homepage")),
        "version_count": len(versions),
    }


def parse_pypi(doc):
    if not isinstance(doc, dict):
        return {}
    info = doc.get("info") or {}
    releases = doc.get("releases") or {}
    version = info.get("version")
    last_published = None
    for entry in (releases.get(version) or []):
        if entry.get("upload_time_iso_8601"):
            last_published = entry["upload_time_iso_8601"]
            break
    urls = info.get("project_urls") or {}
    candidates = [info.get("home_page")] + [v for v in urls.values() if isinstance(v, str)]
    repo = next((github_slug(u) for u in candidates if github_slug(u)), None)
    classifiers = info.get("classifiers") or []
    return {
        "registry": "pypi",
        "name": info.get("name"),
        "latest_version": version,
        "last_published": last_published,
        "deprecated": any("Inactive" in c for c in classifiers),
        "deprecation_message": None,
        "license": info.get("license") or None,
        "typescript_types": False,
        "repo": repo,
        "version_count": len(releases),
    }


def parse_date(value):
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:26] if "." in text else text, fmt)
        except ValueError:
            continue
    return None


def days_since(value, now=None):
    parsed = parse_date(value)
    if not parsed:
        return None
    return ((now or utcnow()) - parsed).days


def derive_maintenance(signals, now=None):
    """Turn raw dates into a maintenance verdict with the reason attached."""
    now = now or utcnow()
    if signals.get("archived"):
        return "archived", "repository is archived - read-only, no further releases"
    if signals.get("deprecated"):
        message = signals.get("deprecation_message") or "marked deprecated by its publisher"
        return "deprecated", message
    ages = [d for d in (days_since(signals.get("last_published"), now),
                        days_since(signals.get("pushed_at"), now)) if d is not None]
    if not ages:
        return "unknown", "no publish or push date available"
    age = min(ages)
    if age <= ACTIVE_DAYS:
        return "active", "last activity {} days ago".format(age)
    if age <= SLOWING_DAYS:
        return "slowing", "last activity {} days ago".format(age)
    if age <= STALE_DAYS:
        return "stale", "no activity for {} days".format(age)
    return "dormant", "no activity for {} days - treat as unmaintained".format(age)


def suggest_anchors(signals, status):
    """Map measurements onto rubric bands. Suggestions, not verdicts.

    Stars measure popularity, not quality - an official vendor SDK with 400 stars
    can be better maintained than a community wrapper with 4000. The caller is
    expected to read the rubric anchors and decide.
    """
    if status in ("archived", "deprecated"):
        return {"sdk_quality": "0-1", "ecosystem_maturity": "0-1",
                "note": "disqualify unless a maintained fork is the real candidate"}
    if status == "dormant":
        return {"sdk_quality": "1-2", "ecosystem_maturity": "1-2",
                "note": "unmaintained; confirm before recommending"}
    if status == "stale":
        return {"sdk_quality": "2-3", "ecosystem_maturity": "2-3", "note": None}

    stars = signals.get("stars") or 0
    if status == "active" and stars >= 2000:
        sdk, eco = "4-5", "4-5"
    elif status == "active":
        sdk, eco = "4-5", "3-4"
    else:  # slowing
        sdk, eco = "3-4", "3-4"
    if signals.get("typescript_types"):
        note = "ships type definitions"
    else:
        note = None
    return {"sdk_quality": sdk, "ecosystem_maturity": eco, "note": note}


# -------------------------------------------------------------------- fetching

def registry_url(package, ecosystem):
    if ecosystem == "npm":
        return "https://registry.npmjs.org/" + urllib.parse.quote(package, safe="@")
    return "https://pypi.org/pypi/{}/json".format(urllib.parse.quote(package))


def guess_ecosystem(package):
    if package.startswith("@") or "/" not in package:
        return "npm"
    return None


def probe_one(package, ecosystem, token, now=None):
    """Registry first, GitHub as enrichment. Partial results are expected."""
    result = {"query": package, "sources": [], "warnings": []}
    slug = None

    if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", package) and not package.startswith("@"):
        slug = package  # already an owner/repo
    else:
        order = [ecosystem] if ecosystem and ecosystem != "auto" else ["npm", "pypi"]
        for eco in order:
            try:
                doc = fetch_json(registry_url(package, eco))
            except RateLimited as exc:
                result["warnings"].append("{}: {}".format(eco, exc))
                continue
            if not doc:
                continue
            parsed = parse_npm(doc) if eco == "npm" else parse_pypi(doc)
            if parsed.get("name"):
                result.update(parsed)
                result["sources"].append(eco)
                slug = parsed.get("repo")
                break

    if slug:
        result["repo"] = slug
        try:
            repo = fetch_json(API + "/repos/" + slug, token,
                              "application/vnd.github+json")
            if repo:
                result.update({
                    "stars": repo.get("stargazers_count"),
                    "forks": repo.get("forks_count"),
                    "open_issues": repo.get("open_issues_count"),
                    "archived": repo.get("archived"),
                    "pushed_at": repo.get("pushed_at"),
                    "language": repo.get("language"),
                    "repo_license": (repo.get("license") or {}).get("spdx_id"),
                    "description": repo.get("description"),
                })
                result["sources"].append("github")
        except RateLimited as exc:
            result["warnings"].append(str(exc))
        except urllib.error.HTTPError as exc:
            result["warnings"].append("github: HTTP {}".format(exc.code))

    if not result["sources"]:
        result["warnings"].append(
            "no data found - check the package name, or the SDK may not be public")

    status, reason = derive_maintenance(result, now)
    result["maintenance"] = status
    result["maintenance_reason"] = reason
    result["suggested_anchors"] = suggest_anchors(result, status)
    return result


def find_repos(query, token, language=None, limit=5):
    terms = query
    if language:
        terms += " language:" + language
    url = "{}/search/repositories?q={}&sort=stars&order=desc&per_page={}".format(
        API, urllib.parse.quote(terms), max(1, min(limit, 20)))
    try:
        doc = fetch_json(url, token, "application/vnd.github+json")
    except (RateLimited, urllib.error.HTTPError) as exc:
        return {"query": terms, "results": [], "warnings": [str(exc)]}
    items = (doc or {}).get("items") or []
    return {
        "query": terms,
        "total": (doc or {}).get("total_count", 0),
        "results": [{
            "repo": item.get("full_name"),
            "stars": item.get("stargazers_count"),
            "pushed_at": (item.get("pushed_at") or "")[:10],
            "language": item.get("language"),
            "description": (item.get("description") or "")[:120],
            "url": item.get("html_url"),
        } for item in items],
        "warnings": [],
    }


# ------------------------------------------------------------------- rendering

def render_probe(results):
    lines = ["SDK HEALTH", ""]
    lines.append("{:<26}{:<12}{:<10}{:<12}{}".format(
        "package", "status", "stars", "version", "last activity"))
    lines.append("-" * 78)
    for item in results:
        lines.append("{:<26}{:<12}{:<10}{:<12}{}".format(
            str(item.get("query"))[:25],
            item.get("maintenance", "?"),
            str(item.get("stars") if item.get("stars") is not None else "-"),
            str(item.get("latest_version") or "-")[:11],
            (item.get("last_published") or item.get("pushed_at") or "-")[:10]))
    for item in results:
        lines.append("")
        lines.append("{} ({})".format(item.get("query"), item.get("repo") or "no repo found"))
        lines.append("  {}: {}".format(item.get("maintenance"), item.get("maintenance_reason")))
        if item.get("deprecated"):
            lines.append("  DEPRECATED: {}".format(
                item.get("deprecation_message") or "publisher marked this deprecated"))
        anchors = item.get("suggested_anchors") or {}
        suffix = " ({})".format(anchors["note"]) if anchors.get("note") else ""
        lines.append("  suggested anchors: sdk_quality {}, ecosystem_maturity {}{}".format(
            anchors.get("sdk_quality", "?"), anchors.get("ecosystem_maturity", "?"), suffix))
        if item.get("open_issues") is not None:
            lines.append("  open issues: {} | license: {} | sources: {}".format(
                item["open_issues"], item.get("repo_license") or item.get("license") or "?",
                ", ".join(item.get("sources") or ["none"])))
        for warning in item.get("warnings") or []:
            lines.append("  ! " + warning)
    lines.append("")
    lines.append("Stars measure popularity, not maintenance or fit. Confirm against the "
                 "rubric anchors before scoring.")
    return "\n".join(lines)


def render_find(found):
    lines = ["EXISTING IMPLEMENTATIONS: {}".format(found["query"])]
    if not found["results"]:
        lines.append("  no results" + (" ({})".format(found["warnings"][0])
                                       if found.get("warnings") else ""))
        return "\n".join(lines)
    lines.append("  {} matching repositories, top {} by stars".format(
        found.get("total", 0), len(found["results"])))
    lines.append("")
    for item in found["results"]:
        lines.append("  {} ({} stars, pushed {})".format(
            item["repo"], item["stars"], item["pushed_at"]))
        if item["description"]:
            lines.append("      " + item["description"])
        lines.append("      " + item["url"])
    lines.append("")
    lines.append("Read these for integration patterns, not as endorsements - popular "
                 "example repos are often outdated or written for a different stack.")
    return "\n".join(lines)


def main(argv=None):
    _allow_piping()
    parser = argparse.ArgumentParser(description="Probe SDK health and find real integrations.")
    sub = parser.add_subparsers(dest="command")

    probe = sub.add_parser("probe", help="health of one or more SDKs")
    probe.add_argument("packages", nargs="+", help="package names or owner/repo")
    probe.add_argument("--ecosystem", choices=["npm", "pypi", "auto"], default="auto")
    probe.add_argument("--format", choices=["text", "json"], default="text")

    find = sub.add_parser("find", help="find existing integrations on GitHub")
    find.add_argument("query")
    find.add_argument("--language")
    find.add_argument("--limit", type=int, default=5)
    find.add_argument("--format", choices=["text", "json"], default="text")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2

    token = github_token()
    if args.command == "probe":
        results = [probe_one(pkg, args.ecosystem, token) for pkg in args.packages]
        print(json.dumps(results, indent=2, sort_keys=True) if args.format == "json"
              else render_probe(results))
    else:
        found = find_repos(args.query, token, args.language, args.limit)
        print(json.dumps(found, indent=2, sort_keys=True) if args.format == "json"
              else render_find(found))
    return 0


if __name__ == "__main__":
    sys.exit(main())
