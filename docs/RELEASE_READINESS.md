# ReData Release and DOI Readiness

**Purpose:** A practical gate list for preparing a versioned, citable ReData release.  
**Status as of 2026-10-12:** Not yet release-ready for a research-facing claim of completed evaluation.  
**Repository:** https://github.com/theraghavraman/redata

This checklist deliberately distinguishes an archived software snapshot from evidence of research quality. A DOI makes a specific record persistently identifiable; it does not certify novelty, correctness, peer review, security, or independent reproduction.

## Gate 1 — Source and citation metadata

- [x] Public repository has a software license and a root `CITATION.cff`.
- [x] Citation metadata identifies the author and ORCID.
- [ ] Citation metadata passes automated Citation File Format validation on the release candidate.
- [ ] Select and record an explicit release version and release date.
- [ ] Verify the release archive contains the intended source and all referenced documentation, scripts, tests, and result files.
- [ ] Confirm the GitHub Pages deployment is healthy for the release candidate.

## Gate 2 — Test and benchmark evidence

- [x] A local-engine correctness suite has 16 selected regression fixtures.
- [x] CI exercises the actual local-engine HTTP API with generated data, an independent aggregate oracle, pagination checks, and authentication checks.
- [x] Historical raw benchmark JSON is preserved for 100k, 1M, and 10M-row workloads.
- [ ] Re-run the target release commit and attach its exact CI run URLs and raw artifacts.
- [ ] Add browser-only correctness tests for the operations described as browser mode.
- [ ] Expand independent reference tests for dates, cleaning, statistics, joins, connection/sync workflows, and error handling.
- [ ] Run controlled, repeated end-to-end workloads and document the hardware/runtime.
- [ ] Publish the full results table, including failures, timeouts, and limits. Keep sampled RSS clearly distinguished from true peak memory.
- [ ] Obtain an independent reproduction or clearly state that the evidence is maintainer-run only.

**Important:** Existing 10-million-row CI runs are useful engineering evidence, but they do not reproduce the README's historical 723 MB dataset and timings. Do not merge these into one claim.

## Gate 3 — Security and dependencies

- [x] `SECURITY.md` documents the security boundary and vulnerability reporting.
- [x] A workflow generates a resolved Python dependency license inventory and CycloneDX SBOM and runs `pip-audit`.
- [ ] Review the exact release candidate's SBOM and resolved license inventory manually.
- [ ] Verify browser CDN libraries, fonts, native libraries, optional extras, and transitive dependencies; confirm required notices are present.
- [ ] Investigate all actionable vulnerability findings. A passing vulnerability scan is not a complete security audit.
- [ ] Record the review date, exact commit, audit workflow URL, and reviewer decision in release notes or an auditable issue.

## Gate 4 — Research record

- [ ] Finalize `docs/TECHNICAL_REPORT_DRAFT.md` only after results are reproducible; otherwise keep it explicitly labeled as a draft.
- [ ] Replace planned or broad claims with bounded claims supported by cited artifacts.
- [ ] Ensure every reported number has its source commit, input characteristics/checksum, environment, timing boundary, repetitions, and raw result.
- [ ] Keep claims of Tableau/Power BI parity, superiority, broad scalability, or research impact out unless supported by controlled evidence.
- [ ] Make limitations and non-tested areas prominent.
- [ ] Check the report, README, benchmark protocol, claims register, licenses, and release notes for consistent terminology and numbers.

## Gate 5 — Archive a version on Zenodo

These steps require the repository owner to use the Zenodo/GitHub account UI; the repository changes alone cannot enable the integration or publish a DOI.

1. Confirm the GitHub repository is public and sign in to Zenodo with the intended account.
2. Connect GitHub to Zenodo and enable **only** `theraghavraman/redata`.
3. Review the metadata Zenodo will derive from `CITATION.cff`; do not add `.zenodo.json` unless its metadata is intentionally maintained, because Zenodo gives it priority over `CITATION.cff`.
4. Choose a version tag only after the release gates are complete. Do not label an unfinished draft as a completed research evaluation.
5. Create a GitHub release with concise notes, exact version, tested commit, test/benchmark links, limitations, and license information.
6. Confirm Zenodo successfully archived that exact release; inspect the record metadata and files before citing it.
7. Use the **version-specific DOI** when citing the exact release. Use the **concept DOI** when referring to the evolving software project as a whole.

Official guidance:
- [Zenodo GitHub integration](https://help.zenodo.org/docs/github/)
- [Zenodo software metadata and CITATION.cff](https://help.zenodo.org/docs/github/describe-software/)
- [Zenodo DOI versioning](https://zenodo.org/help/versioning)
- [GitHub citation files](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files)

Use [the release-notes template](RELEASE_NOTES_TEMPLATE.md) when preparing the GitHub release description. Fill in only values verified for the exact release candidate.

## Release decision template

Record this for each release candidate:

- **Version/tag:**
- **Exact commit SHA:**
- **Release date:**
- **CI correctness run:**
- **Benchmark run and raw artifact:**
- **Dependency audit run and reviewed SBOM:**
- **License/notice review:**
- **Known limitations and failed workloads:**
- **Independent reproduction:** yes / no / not attempted
- **Zenodo record:** pending / archived
- **Version DOI:**
- **Concept DOI:**

Do not fill in the DOI fields until Zenodo actually issues them.
