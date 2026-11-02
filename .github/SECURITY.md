# Security Policy

## Reporting a vulnerability

This repository is private. Report security issues **directly to the
repository owner**, never in an issue or pull request, and never with the
secret itself in the message. We aim to acknowledge a report within 3 business
days and to agree a disclosure timeline with you.

If the repository is ever made public, enable **Settings → Advanced Security →
Private vulnerability reporting** and point this section at the
**Security → Advisories → Report a vulnerability** form.

## Supported versions

Only the latest release on `main` is supported.

| Version | Supported |
| --- | --- |
| `main` (latest release) | ✅ |
| older releases / tags | ❌ — upgrade to the latest release |

## Scope notes

- The development stack (`docker-compose.yml`, the dev container) is for local
  use only: its default credentials and `DEBUG=True` are intentional there and
  are not vulnerabilities.
- Dependency and container-image CVEs are tracked automatically by Dependabot,
  `pip-audit` in CI, and the Trivy scan of each published image (Security →
  Code scanning). File those only with a working exploit path.
- Never attach `.env` contents, tokens, or other credentials to a report.
