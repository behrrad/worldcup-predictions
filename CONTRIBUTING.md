# Contributing

Contributions are welcome via **pull requests**. Direct pushes to `main` are
disabled; every change lands through a reviewed PR that passes CI.

## Workflow

1. **Fork** this repository (or, if you're a collaborator, create a new branch —
   never commit to `main`).
2. Create a feature branch: `git checkout -b my-change`.
3. Make your change. Follow the conventions in **[AGENTS.md](AGENTS.md)**
   (e.g. constants/strings live in `consts.py`, not inline).
4. **Run the test gate locally** before pushing:
   ```bash
   python manage.py test --settings=config.settings_test     # backend
   cd frontend && pnpm exec tsc --noEmit                      # frontend types
   ```
   Add tests for anything you change — see **[docs/TESTING.md](docs/TESTING.md)**.
5. Push your branch and open a **pull request** against `main`.
6. CI (GitHub Actions) must be green: **Backend tests (Django)** and
   **Frontend type-check (Next.js)**.

## Review & merge

- The repository maintainer reviews and **merges** all pull requests — only the
  maintainer has merge permission.
- PRs cannot be merged until CI passes and any review conversations are resolved.

## Good first areas

- New scoring options, leaderboard views, or league settings.
- Knockout-bracket auto-advance (fill R32→Final teams as results come in).
- Tests and documentation improvements.

Thanks for contributing! 🎉
