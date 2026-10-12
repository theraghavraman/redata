# ReData Release Notes — Template

> Copy this file into the GitHub release description and replace every bracketed field. Remove any statement that is not supported by the final release candidate.

## ReData [VERSION]

**Release date:** [YYYY-MM-DD]  
**Source commit:** [FULL_COMMIT_SHA]  
**DOI:** [ADD ONLY AFTER ZENODO CONFIRMS ARCHIVING]

### Summary

This release archives a version of ReData, a browser-first data analytics workspace with an optional local execution engine for supported workloads.

### Verified in this release

- **Citation metadata:** [validation workflow URL and result]
- **Correctness tests:** [workflow URL, count, commit]
- **Benchmark:** [workflow URL, dataset dimensions, environment, raw artifact]
- **Dependency audit:** [workflow URL, reviewed SBOM/license inventory, review decision]
- **Deployment:** [deployment workflow URL and result]

### Benchmark interpretation

Report only results produced from this exact source revision, or clearly identify earlier runs as historical evidence. Include the dataset size and checksum, runner or hardware, dependency/runtime versions, timing boundary, repetitions, correctness oracle, and raw results. Do not present sampled process RSS as a guaranteed peak.

### Known limitations

- The release has not been independently reproduced unless an independent reproduction record is linked here.
- Browser-only and local-engine capabilities differ; describe only tested paths.
- Do not claim feature parity with Tableau, Power BI, or other products without a controlled comparative evaluation.
- The historical 10-million-row / 723 MB README result remains unreproduced unless this release includes a reproduction with the original input and conditions.
- Dependency scanning is not a complete security audit. Summarize the human review of the release's resolved dependency inventory and notices.

### Citation and licensing

Use the version-specific DOI for this exact release once it is issued by Zenodo. The concept DOI identifies the project across versions. Software source is MIT-licensed; documentation under `docs/` is CC BY 4.0 unless otherwise stated. Third-party components retain their own terms.

### Evidence links

- Citation validation: [URL]
- Correctness workflow: [URL]
- Benchmark run and raw artifact: [URL]
- Dependency audit and reviewed SBOM: [URL]
- Claims and evidence register: https://github.com/theraghavraman/redata/blob/main/docs/CLAIMS_AND_EVIDENCE.md
- Release readiness checklist: https://github.com/theraghavraman/redata/blob/main/docs/RELEASE_READINESS.md
