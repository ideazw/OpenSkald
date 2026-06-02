# Security Policy

OpenViking Content Agent handles LLM and publishing credentials through environment
variables only. Do not commit secrets, cookies, access tokens, or private account IDs.

## Supported Versions

The project is currently pre-1.0. Security fixes target the latest `main` branch.

## Reporting a Vulnerability

Please report suspected vulnerabilities privately to the project maintainer. Include:

- Affected component
- Reproduction steps
- Potential impact
- Suggested fix, if known

Do not publish live credentials or exploit details in public issues.

## Live Publishing Safety

- Keep `review.require_human_approval: true` in production.
- Run `publisher-check-all` before enabling scheduled publishing.
- Use least-privilege platform tokens where the platform supports them.
- Rotate credentials after accidental disclosure or failed sandboxing.
