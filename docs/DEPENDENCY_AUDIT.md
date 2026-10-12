# ReData Dependency, License, and SBOM Audit

## Purpose

ReData's dependency set includes data engines, spreadsheet readers, database drivers, cloud SDKs, and browser-loaded libraries. The repository's `THIRD_PARTY_NOTICES.md` is a maintainer inventory, not a declaration that every transitive license has already been manually approved.

The GitHub Actions workflow at [dependency-audit.yml](../.github/workflows/dependency-audit.yml) resolves the current Python requirements on an Ubuntu runner, generates a JSON license inventory and a CycloneDX SBOM, and runs `pip-audit` against the installed Python environment. It runs weekly, on relevant changes, and on manual dispatch. Its artifacts are attached to the workflow run for 90 days.

## Reproducing locally

From the repository root, use a clean virtual environment and run:

```bash
python -m venv .venv-audit
# Linux/macOS:
. .venv-audit/bin/activate
# Windows PowerShell:
# .venv-audit\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r engine/requirements.txt
python -m pip install pip-audit pip-licenses cyclonedx-bom
pip-licenses --format=json --output-file=licenses-resolved.json
cyclonedx-py environment --output-format JSON --output-file sbom.cdx.json
pip-audit
```

## How to interpret results

- The license inventory and SBOM describe the dependency environment that was actually resolved for that run; loose minimum-version requirements mean another date or platform may resolve different versions.
- A generated license identifier is a triage aid, not a substitute for reading the exact distribution's license, copyright, NOTICE, and native-library terms.
- Review licenses for direct and transitive dependencies, bundled binaries, optional extras, browser CDN assets, and fonts before packaging or redistributing an application build.
- `pip-audit` checks known Python package vulnerabilities. It does not prove the application is secure, does not audit JavaScript CDN assets, and may fail because an advisory affects a dependency. Investigate and document any failure rather than suppressing it without justification.
- Keep the raw workflow run, commit SHA, SBOM, and resolved license inventory together when preparing a release. Update `THIRD_PARTY_NOTICES.md` only after human review of the resolved evidence.

## Release gate

Do not describe the dependency review as complete until a maintainer has reviewed the exact release environment's SBOM and license inventory, addressed actionable vulnerability findings, confirmed all redistribution notices, and recorded the review in the release notes or an auditable issue. An automatically generated SBOM is evidence to review, not certification.
