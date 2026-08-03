# Aevrin UI Content Guide

## Voice

- Calm
- Direct
- Operational
- Transparent about limits

## Prefer

- “Scan an MCP server”
- “Partial scan coverage”
- “Review urgent findings”
- “The score reflects only completed checks”
- “Copy this secret now”
- “No automatic renewal”

## Avoid

- “Everything is safe”
- “Military-grade”
- “Complete protection”
- “No issues” when stages failed
- “False positive” suppression without an auditable reason

## Product Language

- Use `GitHub repository`, `Live MCP server`, and `Pasted configuration`.
- Use `Complete`, `Partial`, `Failed`, `Queued`, and `Running` for scan state.
- Use `Critical`, `High`, `Medium`, `Low`, and `Info` for severity.
- Use `Limitations` for not-tested coverage notes, not `findings`.

## Error Pattern

Every user-visible error should answer:

1. What failed
2. Why, when known
3. What the user can do next
4. Whether any partial data is still valid

## Empty States

- First run: explain the product in one sentence and present one primary CTA.
- No findings: remind the user that clean completed checks are not the same as complete coverage.
- No API keys: explain when a key is necessary.
- No billing data: explain the current plan path instead of showing blank cards.
