# Third-Party Notices and License Inventory

This file records third-party software and assets that are explicitly referenced by the current repository documentation or runtime configuration. It is an initial direct-dependency inventory, **not yet a complete software bill of materials (SBOM)**. Python dependency ranges are not fully locked, and their transitive dependency set can vary by platform and installation date. Before distributing a packaged build, generate and review a version-resolved SBOM and verify every bundled asset's license and required notices.

## Repository-owned materials

- Original ReData software source: MIT; see [LICENSE](LICENSE).
- Original documentation and report prose under `docs/`: CC BY 4.0 unless a file states otherwise; see [docs/LICENSE](docs/LICENSE).
- Third-party materials retain their own licenses. The repository license does not override those terms.

## Browser-loaded libraries and assets

| Component | Version / use observed in repository | License | Required notice / source |
|---|---|---|---|
| SheetJS Community Edition (`xlsx`) | CDN reference `xlsx@0.18.5` in `index.html` | Apache-2.0 | Preserve license and copyright notices; include the attribution below. [Official license guidance](https://docs.sheetjs.com/docs/miscellany/license/) |
| sql.js | CDN reference `sql.js/1.8.0` in `index.html` | MIT | Preserve the upstream copyright and license notice. [Upstream license](https://github.com/sql-js/sql.js/blob/master/LICENSE) |
| DM Sans, DM Mono, Manrope | Loaded from Google Fonts CSS | SIL Open Font License 1.1 (verify the exact served font files/versions when packaging) | Font files and any bundled copies must retain their own OFL license and reserved-font-name terms where applicable. [Google Fonts](https://fonts.google.com/) |

### SheetJS Community Edition attribution

SheetJS Community Edition — https://sheetjs.com/  
Copyright (C) 2012-present SheetJS LLC  
Licensed under the Apache License, Version 2.0. You may obtain a copy at https://www.apache.org/licenses/LICENSE-2.0. The software is distributed on an "AS IS" basis, without warranties or conditions of any kind.

## Python dependencies declared in `engine/requirements.txt`

The file currently declares these direct packages with minimum-version constraints. Confirm the license against the exact installed version and its distribution metadata when producing a release.

| Package | Declared requirement | Commonly published license identifier / family | Upstream metadata |
|---|---|---|---|
| DuckDB | `duckdb>=1.1.0` | MIT | https://github.com/duckdb/duckdb |
| openpyxl | `openpyxl>=3.1.0` | MIT | https://foss.heptapod.net/openpyxl/openpyxl |
| xlrd | `xlrd>=2.0.1` | BSD-3-Clause | https://github.com/python-excel/xlrd |
| PyArrow | `pyarrow>=14.0` | Apache-2.0 | https://github.com/apache/arrow |
| Psycopg (binary extra) | `psycopg[binary]>=3.1` | LGPL-3.0 (review packaging and binary distribution terms for the selected extra/version) | https://github.com/psycopg/psycopg |
| PyMySQL | `PyMySQL>=1.1` | MIT | https://github.com/PyMySQL/PyMySQL |
| pymssql | `pymssql>=2.3` | LGPL-2.1-or-later (verify selected release and bundled FreeTDS details) | https://github.com/pymssql/pymssql |
| Snowflake Connector for Python | `snowflake-connector-python>=3.12` | Apache-2.0 | https://github.com/snowflakedb/snowflake-connector-python |
| Boto3 | `boto3>=1.34` | Apache-2.0 | https://github.com/boto/boto3 |

These entries are a starting point, not a substitute for checking the license metadata and bundled notices of the exact versions installed in the release environment. Some dependencies bring additional transitive packages and native components with separate notices.

## Maintainer release checklist

- [ ] Generate a version-resolved SBOM (for example, SPDX or CycloneDX) from the release environment.
- [ ] Audit direct and transitive dependencies, including native libraries and optional extras.
- [ ] Preserve all required copyright, license, NOTICE, and attribution files for redistributed components.
- [ ] Check font and other asset licenses for files actually bundled with the release.
- [ ] Verify compatibility before copying or modifying third-party source.
- [ ] Re-run the inventory when dependency versions or runtime assets change.
