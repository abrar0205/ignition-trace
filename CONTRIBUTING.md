# Contributing

Start with a reproducible recording containing synthetic or explicitly shareable data. Describe the expected measurement and the evidence IDs that demonstrate the problem.

Run `pytest -q`, then `pnpm test` and `pnpm typecheck` in `web/`. Detector or generator changes must update Python and TypeScript together. Regenerate the corpus with `python scripts/export_fixtures.py` and inspect the changed expectations. Do not change expected results solely to make a failing check pass.

Keep measurements distinct from inference. New adapters must document their source clock, units, capture scope and missing-data behavior. Maintain keyboard access and responsive layouts in the workbench. Android changes must pass the JVM recorder tests and APK build; report target-device tests separately.

Submit a pull request describing the problem, resulting behavior and validation. Keep private recordings and credentials outside the repository.

