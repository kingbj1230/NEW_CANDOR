# Role-Based Structure Rules

This repository follows domain + role separation:

- `routes/`: HTTP route handlers and request/response shaping only.
- `services/`: core business logic and orchestration.
- `utils/`: shared pure helper functions and normalization logic.
- `templates/` and `static/`: UI assets and rendering resources.

## Guardrails

1. Do not add new feature modules at the project root.
2. Keep route logic thin; move reusable logic into `services/`.
3. Keep utility functions framework-agnostic in `utils/`.
4. Keep legacy compatibility shims removed unless an explicit external compatibility requirement appears.

## Dead-Code Cleanup Baseline

- Legacy shim modules were removed from root-level routing/service utilities.
- Internal imports should reference `routes/*`, `services/*`, and `utils/*` directly.
- Static assets must remain only if referenced by templates or frontend scripts.
