# ReData Release and DOI Readiness

**Purpose:** A practical gate list for preparing a versioned, citable ReData release.  
**Status as of 2026-10-12:** ReData v0.1.0 is already published and the owner has confirmed a Zenodo DOI in the UI. A post-release audit found that the v0.1.0 tag uses a vulnerable SheetJS version; main has been patched, and this checklist now governs a possible v0.1.1 patch release. Do not create the patch tag until all checks pass on one exact candidate commit. Research-evaluation claims remain incomplete.  
**Repository:** https://github.com/theraghavraman/redata

This checklist deliberately distinguishes an archived software snapshot from evidence of research quality. A DOI makes a specific record persistently identifiable; it does not certify novelty, correctness, peer review, security, or independent reproduction.

## Gate 1 — Source and citation metadata

- [x] Public repository has a software license and a root `CITATION.cff`.
- [x] Citation metadata identifies the author and ORCID.
- [x] Citation metadata passed automated Citation File Format validation on the v0.1.0 release commit ([run](https://github.com/theraghavraman/redata/actions/runs/38235506081)); rerun on the patch candidate before tagging.
- [x] v0.1.0 version and release date were recorded. The patch candidate's version/date remain unselected until all gates pass.
- [x] The v0.1.0 tag points to the reviewed source commit; its repository tree contains no bundled wheel, shared-library, DLL, executable, ZIP, or tarball files. Repeat this check for the patch archive.
- [x] GitHub Pages deployment passed for v0.1.0 ([run](https://github.com/theraghavraman/redata/actions/runs/38234294941)); rerun for the patch candidate.

## Gate 2 — Test and benchmark evidence

- [x] A local-engine correctness suite has 16 selected regression fixtures.
- [x] CI exercises the actual local-engine HTTP API with generated data, an independent aggregate oracle, pagination checks, and authentication checks.
- [x] Historical raw benchmark JSON is preserved for 100k, 1M, and 10M-row workloads.
- [x] v0.1.0's exact commit was tested; correctness, generator, and 1M-row smoke benchmark passed, and raw evidence is linked in the [post-release audit](audits/v0.1.0-post-release-audit.md). Repeat on the patch candidate.
- [ ] Add browser-only correctness tests for the operations described as browser mode.
- [ ] Expand independent reference tests for dates, cleaning, statistics, joins, connection/sync workflows, and error handling.
- [ ] Run controlled, repeated end-to-end workloads and document the hardware/runtime.
- [ ] Publish the full results table, including failures, timeouts, and limits. Keep sampled RSS clearly distinguished from true peak memory.
- [x] Release notes clearly state that independent reproduction and comprehensive performance evaluation have not been established. No independent reproduction has been performed.

**Important:** Existing 10-million-row CI runs are useful engineering evidence, but they do not reproduce the README's historical 723 MB dataset and timings. Do not merge these into one claim.

## Gate 3 — Security and dependencies

- [x] `SECURITY.md` documents the security boundary and vulnerability reporting.
- [x] A workflow generates a resolved Python dependency license inventory and CycloneDX SBOM and runs `pip-audit`.
- [x] Manually reviewed v0.1.0's exact SBOM and license inventory; findings and caveats are recorded in the [post-release audit](audits/v0.1.0-post-release-audit.md). Review the patch candidate's exact artifacts before tagging.
- [x] Reviewed v0.1.0's browser CDN references, fonts, Python dependency inventory, and source-archive contents. This review found CVE-2023-30533 in the released SheetJS 0.18.5 reference; main now pins SheetJS 0.20.3 and SQL.js 1.14.2. The old tag is unchanged.
- [x] Python `pip-audit` found no known vulnerabilities for the v0.1.0 resolved environment. Manual browser review found CVE-2023-30533 in v0.1.0; the main branch fix has passed browser dependency checks. The patch candidate must pass the full suite before release.
- [x] Recorded the review date, release SHA, audit run, artifact checksums, license findings, and decision in the [post-release audit record](audits/v0.1.0-post-release-audit.md).

## Gate 4 — Research record

- [ ] Finalize `docs/TECHNICAL_REPORT_DRAFT.md` only after results are reproducible; otherwise keep it explicitly labeled as a draft.
- [ ] Replace planned or broad claims with bounded claims supported by cited artifacts.
- [ ] Ensure every reported number has its source commit, input characteristics/checksum, environment, timing boundary, repetitions, and raw result.
- [ ] Keep claims of Tableau/Power BI parity, superiority, broad scalability, or research impact out unless supported by controlled evidence.
- [ ] Make limitations and non-tested areas prominent.
- [ ] Check the report, README, benchmark protocol, claims register, licenses, and release notes for consistent terminology and numbers.

## Gate 5 — Archive a version on Zenodo

The repository owner confirmed in the Zenodo account UI on 2026-10-12 that `theraghavraman/redata` is enabled. The v0.1.0 GitHub release already exists; for the next patch release, verify the candidate commit, create a new versioned GitHub release only after all gates pass, then verify the resulting Zenodo record.

The v0.1.0 GitHub release already exists, and the owner supplied a screenshot showing DOI `10.5281/zenodo.23314956`. The record's metadata and archived file listing were not independently retrieved in this audit; inspect those directly before treating archive contents as verified. A future patch release needs its own version-specific DOI.

1. Confirm the GitHub repository is public and sign in to Zenodo with the intended account.
2. [x] Connect GitHub to Zenodo and enable **only** `theraghavraman/redata` (confirmed by repository owner on 2026-10-12).
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
