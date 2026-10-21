# Contributing

Start with a reproducible problem and a small fixture. Useful first
contributions include new synthetic support scenarios, retrieval evaluation
cases, installation fixes, and clearer setup instructions.

1. Install with `uv sync --extra dev --locked`.
2. Run `uv run --extra dev pytest -q` and `uv run --extra dev ruff check .`.
   For frontend changes, use Node.js 20+ and run `npm ci` then `npm test`.
3. Explain the problem, resulting behavior, and verification in your pull request.
4. Keep generated reports, `.env`, credentials, customer data, and model files
   out of commits.

For retrieval changes, compare keyword/vector/hybrid results using the same
inputs. Add regression coverage when changing snapshot activation, source
attribution, permission boundaries, or data handling.

Do not add a hosted service, telemetry, external model dependency, or data
upload to the default workflow without explaining the user-visible behavior
and cost. Bug reports should use fictional data and sanitized errors.
