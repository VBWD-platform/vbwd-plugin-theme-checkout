# vbwd-plugin-theme-checkout

`theme_checkout` is the theme adapter for the fe-user `checkout` plugin and the fe-user payment-provider plugins: it renders `/checkout`, `/checkout/confirmation` and the `/pay/<provider>` pages (`…/success`, `…/cancel`) server-side through the theme platform. It renders only when the backend runs with
`VBWD_FRONTEND_MODE=theme`; in the default `vue` mode it mounts no page routes and the
Vue SPA keeps serving everything. Dependencies: `theme>=1.0`, `theme_cms`, `checkout`.

Payment pages only exist after a checkout, so they live here (sub-package `theme_checkout/payment/`):
one declarative `PaymentFlowDescriptor` per provider (stripe, paypal) yields its pages, htmx fragments
and checkout redirect, each owned by the provider's fe-user plugin (`stripe-payment`, `paypal-payment`)
so a disabled provider answers 404. token-payment has no page: it is an instant-pay checkout method.
Further providers (S153) land as further descriptors in `theme_checkout/payment/flow_descriptors.py`.

Design and roadmap: sprint S152 (`docs/dev_log/20260930/sprints/S152_twig_theme_platform_server_rendered_surfaces.md` in the vbwd-sdk workspace).

## Pre-commit

`bin/pre-commit-check.sh` is this repo's gate (the same file in all seven theme repos; the plugin
name comes from the repo directory, `theme_checkout` or `vbwd-plugin-theme-checkout`):

```bash
bin/pre-commit-check.sh             # = --full: lint + unit + integration
bin/pre-commit-check.sh --quick     # lint + unit
bin/pre-commit-check.sh --lint      # / --unit / --integration: one part only
bin/pre-commit-check.sh --e2e       # the walkthrough tests/e2e/walkthrough-theme_checkout.spec.ts (@theme_checkout)
bin/pre-commit-check.sh --help
```

- Inside an SDK checkout (`vbwd-backend/plugins/theme_checkout`) lint, unit and integration run through
  `vbwd-backend/bin/pre-commit-check.sh --plugin theme_checkout` (docker test services, shared test DB),
  plus Black and Flake8 over this repo's files (the backend gate's Black cannot see gitignored
  plugin dirs) and `node --test` on each `tests/js/*.test.mjs`.
- A standalone clone needs `VBWD_BACKEND_DIR=/path/to/vbwd-backend` (with the plugins this one
  depends on in its `plugins/`); the gate symlinks this repo in as `plugins/theme_checkout` and mounts it
  into the test containers. Without it, the gate prints the setup steps and exits 2.
- `--e2e` needs a `vbwd-fe-user` checkout (`VBWD_FE_USER_DIR`, default the SDK sibling) and a stack
  in theme mode at `E2E_BASE_URL` (default `http://localhost:8080`); it warns when
  `/_render/_theme/mode` does not answer 200. See `docs/architecture/frontend-modes.md` in the
  vbwd-sdk workspace.
- Exit codes: 0 ok · 1 static analysis · 2 unit tests or setup · 3 integration · 4 e2e.
