# Contributing to Digital Employee

First off, thanks for taking the time to contribute! 🎉

The following is a set of guidelines for contributing to Digital Employee. These are mostly
guidelines, not rules. Use your best judgment, and feel free to propose changes to this
document in a pull request.

> 📖 **TL;DR** — Fork → Branch → Commit → Push → Pull Request. PRs to `master` require
> passing review and must be merged via **Squash and merge** or **Rebase and merge**.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [I Want to Contribute](#i-want-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Your First Code Contribution](#your-first-code-contribution)
  - [Pull Requests](#pull-requests)
- [Development Setup](#development-setup)
- [Project Conventions](#project-conventions)
  - [Branch Naming](#branch-naming)
  - [Commit Messages](#commit-messages)
  - [Code Style](#code-style)
  - [Testing Requirements](#testing-requirements)
  - [Database Changes](#database-changes)
- [Branch Protection (master)](#branch-protection-master)
- [Release Process](#release-process)

---

## Code of Conduct

This project and everyone participating in it is governed by a commitment to a
harassment-free experience for everyone, regardless of age, body size, disability,
ethnicity, sex characteristics, gender identity and expression, level of experience,
education, socio-economic status, nationality, personal appearance, race, religion,
or sexual identity and orientation.

Please be kind and courteous. Disagreement is fine; disrespect is not.

---

## I Want to Contribute

### Reporting Bugs

🐛 **Before submitting a bug report:**

- Make sure you are on the latest version of `master`.
- Search the [issue tracker](../../issues) to see if the bug has already been reported.
- Collect relevant information: OS, Python/Node version, error stack trace, reproduction steps.

📝 **When submitting a bug report, include:**

- A clear, descriptive title
- Exact steps to reproduce the issue
- Expected behavior vs. actual behavior
- Screenshots or logs (if applicable)
- Environment details (OS, versions, config)

> **Security vulnerabilities** must NOT be reported via public issues.
> Please contact the maintainers privately instead.

### Suggesting Enhancements

💡 **Enhancement suggestions** are tracked as GitHub issues. When creating one:

- Use a clear, descriptive title
- Provide a detailed description of the proposed behavior
- Explain **why** this enhancement would be useful
- List any alternatives you've considered

### Your First Code Contribution

🌱 **Good first issues** are labeled `good first issue` in the issue tracker.
These are scoped to help new contributors get familiar with the codebase.

Unsure where to begin? Look for issues tagged:
- `good first issue` — small, well-defined tasks
- `help wanted` — extra attention needed
- `documentation` — improvements to docs

### Pull Requests

🔀 **The workflow:**

1. **Fork** the repository (external contributors) or create a feature branch
   (for collaborators with write access).
2. **Create a branch** from `master` (see [Branch Naming](#branch-naming)).
3. **Make your changes.** Follow the [Project Conventions](#project-conventions).
4. **Write or update tests** for your change. All PRs must pass existing tests.
5. **Run the linter and test suite locally** before pushing.
6. **Commit** with a clear message (see [Commit Messages](#commit-messages)).
7. **Push** your branch to origin.
8. **Open a Pull Request** targeting `master`.
9. **Fill in the PR template** — describe what, why, and how.
10. **Address review feedback** by pushing new commits (force-push if rebased).
11. **Wait for CI to pass** and at least one review approval.
12. Once approved, the PR is merged via **Squash and merge** or **Rebase and merge**.

📋 **PR Checklist** (will be enforced by reviewers):

- [ ] My code follows the project's style guidelines
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix/feature works
- [ ] New and existing unit tests pass locally
- [ ] Any dependent changes have been merged and published

💡 **Tips for a great PR:**

- Keep PRs **small and focused** — one logical change per PR
- Write a **descriptive title** following `type(scope): description`
- Reference related issues with `Fixes #123` or `Closes #456`
- Add **screenshots** for UI/visual changes
- Be **responsive to review feedback** — silence for >2 weeks may result in closure

---

## Development Setup

### Prerequisites

| Tool   | Version  | Notes                              |
|--------|----------|------------------------------------|
| Python | 3.10+    | Backend agent                      |
| Node   | 18+      | Frontend build (static)            |
| Go     | 1.21+    | Backend gateway (reference only)   |

### Clone & Install

```bash
git clone https://github.com/GuSheng107/digital-employee.git
cd digital-employee

# Backend agent
cd backend-agent
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
cd ..

# Frontend (only required when building)
cd frontend
npm install
npm run build               # outputs to backend-agent web dir
cd ..

# Or use Make (Linux/macOS)
make install-agent
make build-frontend
```

### Run the Project

```bash
# Linux / macOS
./scripts/start-web.sh

# Windows
scripts\start-web.cmd
```

The web console will be available at <http://localhost:8765>.

---

## Project Conventions

### Branch Naming

Use the following prefixes. Keep names short and descriptive (kebab-case after the prefix).

| Prefix       | Purpose                          | Example                          |
|--------------|----------------------------------|----------------------------------|
| `feat/`      | New feature                      | `feat/add-feishu-adapter`        |
| `fix/`       | Bug fix                          | `fix/memory-leak-on-disconnect`  |
| `refactor/`  | Code refactor (no behavior change) | `refactor/extract-platform-base` |
| `docs/`      | Documentation only               | `docs/improve-contributing`      |
| `test/`      | Add or improve tests             | `test/add-platform-conn-tests`   |
| `chore/`     | Tooling, deps, CI, misc         | `chore/bump-fastapi-version`     |
| `perf/`      | Performance improvement          | `perf/optimize-message-queue`    |
| `hotfix/`    | Urgent production fix           | `hotfix/fix-token-refresh`       |

> ❌ Avoid: `patch`, `temp`, `wip`, `my-changes`, or any name without a prefix.

### Commit Messages

We follow **Conventional Commits** with optional scope. This enables automated
changelog generation and clean history.

**Format:**

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:** `feat` · `fix` · `refactor` · `docs` · `test` · `chore` · `perf` · `ci` · `build` · `style`

**Scopes (this project):** `agent` · `gateway` · `frontend` · `platform` · `config` · `core` · `db`

**Subject rules:**

- Imperative mood: "add feature" not "added feature"
- Lowercase, no trailing period
- ≤72 characters
- No emoji in subject

**Examples:**

```text
feat(platform): add feishu websocket adapter
fix(agent): resolve memory leak in long connection
refactor(gateway): extract PlatformBase from wecom_bot
docs: update README with platform support table
chore(deps): bump fastapi to 0.115.0
```

**Breaking changes** must be noted in the footer:

```
feat(platform)!: replace webhook with grpc transport

BREAKING CHANGE: webhook platform configs must be migrated to grpc
```

### Code Style

See [`.ai-memory/code-style.md`](./.ai-memory/code-style.md) for the full guide.

Quick summary:

- **Python**: `black` + `isort` + type hints; follow PEP 8; snake_case; docstrings on public APIs
- **Vue/JS**: ESLint + Prettier; 2-space indent; single quotes; no semicolons
- **Go** (gateway): `gofmt` + `golangci-lint`; explicit error handling

### Testing Requirements

- ✅ Every new feature **must** include tests
- ✅ Every bug fix **must** include a regression test
- ✅ Tests must pass locally before opening a PR
- ✅ Aim for meaningful coverage — focus on behavior, not line count
- ❌ Do not disable or skip existing tests to make your change pass

Run the test suite before submitting:

```bash
cd backend-agent
.venv/Scripts/activate   # or source .venv/bin/activate
python -m pytest
```

### Database Changes

We deliberately **do not** use a migration framework (no Alembic).

When you need to change a database schema:

1. Write a **one-shot script** under `backend-agent/scripts/db_migrations/`
2. The script is **idempotent** (safe to run twice)
3. The script is **documented** (header comment explains what it does)
4. Old data structures are **not** preserved — clean breaks are preferred
5. The script is run once during deployment and then deleted

---

## Branch Protection (master)

The `master` branch is protected with the following rules:

| Rule                                      | Status |
|-------------------------------------------|--------|
| Require pull request before merging       | ✅      |
| Dismiss stale pull request approvals       | ✅      |
| Require approvals                          | ❌ (0 — self-review OK) |
| Require status checks to pass              | ❌ (no CI yet) |
| Require linear history                     | ❌      |
| Lock branch                                | ❌      |
| Do not allow bypassing the above settings  | ✅      |
| Allow force pushes                         | ❌      |
| Allow deletions                            | ❌      |

**Implications:**

- All changes to `master` go through a PR
- Admins **cannot** bypass the above rules
- Force-push to `master` is blocked
- `master` cannot be deleted
- New commits to a PR invalidate existing approvals

> ℹ️ When we add CI (GitHub Actions), status checks will be enabled.

---

## Release Process

(To be defined — currently single-maintainer project.)

Planned flow:

1. Bump version in `pyproject.toml` and `package.json`
2. Update `CHANGELOG.md` (generated from conventional commits)
3. Tag the release: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
4. Push tags: `git push --tags`
5. Draft GitHub release notes from the tag

---

## Questions?

- 💬 Open a [Discussion](../../discussions) for general questions
- 🐛 Open an [Issue](../../issues) for bugs and feature requests
- 📧 Contact the maintainers directly for sensitive matters

**Thank you for contributing!** 🙌
