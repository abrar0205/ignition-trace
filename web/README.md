# IgnitionTrace workbench

Interactive trace investigation with local browser analysis. The root repository contains the Python service, Android recorder, shared fixtures and complete documentation.

Use Node 22.13+ and pnpm 11.25.0:

```sh
pnpm install --frozen-lockfile
pnpm test
pnpm typecheck
pnpm build:static
```

Serve `out/` with the root Python application for the local archive. A plain static host supports scenario generation, imports, replay, comparison and report export without a backend. Set `NEXT_PUBLIC_BASE_PATH=/ignition-trace` when building for GitHub Pages.

`pnpm build` produces the alternate Sites deployment. The hosting manifest contains public configuration only; credentials are never stored here.
