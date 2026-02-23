# Recipe: Low-Token LLM Integration

## Recommended Sequence

1. `lookup(name=..., alias="latest")`
2. take `selected.pinned_uri`
3. `query(ref=<pinned_uri>, q=<user_question>, k=5)`

This keeps lookup ultra-light and defers payload fetch to actual query.

## Planner Sequence

1. `plan_from_intent(intent, constraints)`
2. execute first `selected` item (`query` using `args_template`)
3. if needed, run `evidence_digest` for compact context.

## Notes

- Prefer pinned digests in follow-up calls.
- Keep `k` small (3-8) to reduce response tokens.
