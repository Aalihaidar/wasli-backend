# Security Policy

## Reporting a vulnerability

Report security issues privately: never in a public issue or pull request, and
never with the secret itself in the message.

- **Preferred:** GitHub's private report form, **Security → Advisories → Report
  a vulnerability**, when the repository offers it.
- **Otherwise** (the form is not offered, for example while the repository is
  private): contact the repository owner directly through their GitHub profile,
  [@Aalihaidar](https://github.com/Aalihaidar).

We aim to acknowledge a report within 3 business days and to agree a disclosure
timeline with you.

The repository can be public or private at different times, and GitHub offers
different security features in each case. The steps for switching are in
[`docs/github-setup.md`](../docs/github-setup.md).

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
