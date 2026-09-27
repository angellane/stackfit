# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.1] - 2026-09-27

### Fixed
- Reports must state the scorer's numeric margin, call "interchangeable" options a
  tie, and say "not scored" when scoring didn't run, instead of asserting a margin.
- Scripts now run on Windows: fall back from `python3` to `python` / `py -3`, and
  write scratch files to the system temp directory instead of `/tmp`.
- Payments playbook: compare fees per transaction at the real price point, since
  fixed fees dominate low-priced plans.
- Payments playbook: use OSS rather than the retired VAT MOSS, and distinguish
  domestic, cross-border B2C and reverse-charged B2B VAT.

## [1.0.0] - 2026-09-15

Initial release.

### Added
- `SKILL.md` workflow: depth calibration, repository analysis, decision framing,
  shortlisting, fact verification, scoring, impact analysis, report.
- `scripts/analyze_stack.py` — detects languages, frameworks, data layer, existing
  vendors, deployment target, runtime model, capabilities and constraints across
  JavaScript/TypeScript, Python, Ruby, Go, Rust, Java, PHP, Elixir and Dart manifests.
- `scripts/score_candidates.py` — weighted scoring across ten uniformly-oriented
  criteria, with margin analysis, cross-profile sensitivity and an evidence audit.
  Five weight profiles plus per-criterion overrides.
- `scripts/impact_scan.py` — domain-aware touchpoint scanning for ten feature
  domains, infrastructure readiness checks from both paths and dependencies, and a
  transparent effort band.
- References: anchored scoring rubric, per-domain playbooks, impact analysis guide,
  migration analysis guide, ADR template.
- `assets/report-template.md` — fillable report skeleton.
- 62-test suite covering detection, arithmetic, validation, CLI contracts,
  determinism, secret safety and skill-format integrity.
- GitHub Actions CI across Python 3.8–3.12.

### Security
- Real `.env` files are never read. Only `.env.example`-style templates are parsed,
  and only for key names. Asserted by test.

## [1.1.0] - 2026-09-15

### Added
- `scripts/github_probe.py` — measures SDK health instead of recalling it. `probe`
  reports deprecation, last publish, archived status, stars and push recency from
  npm/PyPI and the GitHub API, and suggests rubric anchor bands. `find` locates real
  integrations on GitHub to read for patterns. Uses `GITHUB_TOKEN` or the `gh` CLI
  when available; degrades to registry data when the GitHub quota is exhausted.
- Output economy rules in `SKILL.md` governing the response the developer reads:
  lead with the decision, no process narration, no repeated facts, no closing
  summary, with rough word budgets.
- Tests for registry parsing, maintenance banding, rate-limit degradation and
  domain-playbook integrity (79 total, up from 62).

### Changed
- `references/domains.md` split into `references/domains/<domain>.md`, so a lookup
  loads one playbook (~604 tokens) instead of all eleven (~4,556).
- `SKILL.md` and `references/scoring-rubric.md` compressed without dropping guidance.
  A typical full evaluation now loads ~5,800 tokens of skill context, down from
  ~10,600, despite the added capability.
- `sdk_quality` and `ecosystem_maturity` anchors now reference measured signals, and
  a deprecated or archived SDK is called out as disqualifier territory.

## [1.2.0] - 2026-09-15

### Fixed
- `jobs` had a domain playbook and was advertised in `SKILL.md`, but
  `impact_scan.py` had no such domain and exited 2 — a dead end mid-task. A test
  now asserts playbooks, scanner domains and `SKILL.md` agree in both directions.

### Added
- Impact-scan domains for `jobs`, `sms`, `feature-flags`, `cms`, `observability`,
  `i18n`, `documents`, `maps` and `video` (20 total, including `generic`).
- Domain playbooks for `sms`, `feature-flags`, `cms` and `observability` (15 total).
- `generic` profile and free-text domain resolution: `--domain "e-signature for
  contracts"` resolves to `documents`; unrecognised features fall back to the
  generic profile with a note rather than exiting non-zero.
- `SKILL.md` guidance for features with no playbook — derive the landscape,
  deciding factors, hidden requirements and volatile facts, and say that no
  playbook was used.

### Changed
- Unknown `--domain` values no longer exit 2. Erroring stranded the user for the
  common case of a feature outside the curated list.

## [1.3.0] - 2026-09-15

### Changed
- Renamed the skill from `integration-architect` to `stackfit`. The name states the
  differentiator: the right answer depends on your stack. Skill `name` frontmatter,
  directory, docs, eval set and the integrity test were all updated together, since
  a mismatch between the directory and the `name` field breaks installation.
