# Security Policy

## Supported version

Security fixes are developed against the current default branch. There is no separate long-term-support release line at this time.

## Reporting a vulnerability

Please do not publish an unpatched, exploitable vulnerability in a public issue. Use GitHub's **Report a vulnerability** / private vulnerability reporting option for this repository if it is enabled. If it is unavailable, contact the repository maintainer privately through GitHub before disclosing technical details publicly. Include the affected commit or version, impact, reproduction steps, and any practical mitigation. Do not include real credentials, private datasets, or other sensitive information in a report.

## Security boundaries and limitations

- The local engine binds to `127.0.0.1`, uses a random per-run token, checks the `Host` header against the expected local hostnames, and requires the token for API operations.
- Do not expose the engine port to a LAN, public interface, reverse proxy, or tunnel. The loopback binding and token checks are defense-in-depth, not a guarantee against malware or a compromised local account.
- Treat imported files, SQL text, URLs, connection metadata, and remote database/API responses as untrusted input. Keep the engine and dependencies updated.
- The SQL lab is designed to allow read-only query statements; this is not a general-purpose SQL sandbox for arbitrary hostile code.
- Data imported for local-engine analysis is stored in the local workspace. Connections deliberately communicate with the external database, file service, bucket, or API that the user configures. Browser-only mode loads some libraries and fonts from third-party CDNs, as documented in the README.
- Before sharing diagnostic logs, review them for local file paths, server addresses, dataset names, query text, and other sensitive metadata.

## Verification

The CI smoke benchmark checks that unauthenticated API requests are rejected. It also checks that an unapproved `Host` header is rejected even when a valid token is supplied. These are regression checks for specific controls, not a complete security audit or penetration test. See the benchmark workflow and [dependency audit procedure](docs/DEPENDENCY_AUDIT.md) for additional automated checks.
