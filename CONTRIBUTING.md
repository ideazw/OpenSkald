# Contributing

Thanks for helping improve OpenViking Content Agent.

## Local Setup

```bash
uv sync --extra dev
bash scripts/check.sh
```

`scripts/check.sh` uses a temporary demo configuration by default. It does not require
LLM or publisher credentials and does not contact external publishing platforms.

## Development Rules

- Keep changes configuration-driven where possible.
- Do not hardcode API keys, model names, account IDs, or platform credentials.
- Add or update tests for behavior changes.
- Keep publisher integrations behind plugin classes in `backend/app/publishers/`.
- Keep prompt skills declarative in `backend/app/skills/<skill_name>/skill.yaml`.
- Generated or proposed skills must remain human-gated and disabled until reviewed.

## Before Opening a Pull Request

```bash
bash scripts/check.sh
```

For changes that affect Docker deployment, also run this on a machine with Docker:

```bash
docker compose config
docker compose up --build
```

## Real Platform Credentials

Never commit real credentials. Use environment variables referenced by `config.yaml`.
When testing live publishing, use a private config file and keep human approval enabled.
