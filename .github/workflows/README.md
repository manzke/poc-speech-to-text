# CI workflows

These GitHub Actions workflow files live here (rather than in
`.github/workflows/`) because the automation that created this branch lacks the
GitHub `workflows` permission and cannot push files under `.github/workflows/`.

**To enable CI, copy them into place and commit from a context that has the
`workflows` permission (e.g. a human push):**

```bash
mkdir -p .github/workflows
cp ci/workflows/*.yml .github/workflows/
git add .github/workflows && git commit -m "Enable CI workflows"
```

| File | Purpose |
|---|---|
| `ci.yml` | Python unit tests, web-SDK build/test, Helm lint + template |
| `license-gate.yml` | Permissive-only dependency gate (NFR-7 / ADR-009) via `scripts/check_licenses.py` |
| `build.yml` | Multi-arch image build with the model baked in; pushes to GHCR on tags |
