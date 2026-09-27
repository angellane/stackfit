# Contributing to StackFit

Thanks for helping. The most valuable contributions, in order:

1. **A report that got something wrong.** A recommendation that ignored something
   in your repo, a stale fact, a margin that didn't add up. These are how the skill
   gets better, and they need no code. [Open one here](https://github.com/angellane/stackfit/issues/new?template=wrong-recommendation.yml).
2. **Runs on stacks we haven't tested.** Rails, Go, Laravel, Elixir, monorepos,
   mobile. Even "it worked fine on X" is useful.
3. **New or improved domain playbooks** in `references/domains/`.
4. **Script fixes and detection improvements** in `scripts/`.

## Setup

Link your clone into Claude Code's skills folder so edits take effect straight away:

```bash
git clone https://github.com/<you>/stackfit.git
cd stackfit

# macOS / Linux
ln -s "$PWD" ~/.claude/skills/stackfit
```

```powershell
# Windows (PowerShell; needs Developer Mode or an admin shell)
New-Item -ItemType SymbolicLink -Path "$HOME\.claude\skills\stackfit" -Target "$PWD"
```

Remove any other copy of StackFit from `~/.claude/skills/` first, or Claude may
load the wrong one. Start a new Claude Code session after linking.

Run the tests:

```bash
python -m unittest discover -s tests -v
```

## Ground rules

These are enforced by tests or by review:

- **Standard library only, Python 3.8+.** No dependencies. CI runs 3.8 to 3.12.
- **Deterministic.** Same repo in, identical output out. No timestamps or random
  ordering in script output.
- **Read-only and secret-safe.** Scripts never write to the analysed repo and
  never read real `.env` files, only `.env.example`-style templates, and only key
  names.
- **No hardcoded prices in playbooks.** Prices go stale; playbooks say what to
  verify, not what it costs.
- **`SKILL.md` stays under 500 lines.** Detail belongs in `references/`.

## Adding a domain playbook

1. Create `references/domains/<domain>.md` following an existing one: **Landscape**,
   **What usually decides it**, **Hidden requirements**, **Verify**.
2. Add a matching entry to `DOMAINS` in `scripts/impact_scan.py`, so the scanner
   knows what that integration touches.
3. Add `` `<domain>` `` to the playbook list in `SKILL.md`.

The tests check that all three agree.

## Changing how the skill reasons

Edits to `SKILL.md` or a playbook change Claude's behaviour, which unit tests
can't fully cover. In your pull request, include a before and after: the prompt
you ran, the repo it ran in, and the relevant part of each report.

## Pull requests

- One change per PR.
- Add a line under a new `## [Unreleased]` heading in `CHANGELOG.md`.
- Tests pass locally.
