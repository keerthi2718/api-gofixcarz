---
name: Workspace validator generation
description: Generator dependency inference can disagree with the consuming Zod package.
---

Generate validators for the consuming package's Zod major version, not whichever
version the generator infers from the root workspace.

**Why:** Exporting the Python customer's UUID contracts caused Orval to emit
Zod 4-style UUID validators even though the consumer used Zod 3. Generated code
was syntactically valid but failed TypeScript compilation.

**How to apply:** Keep the generator's version selection explicit and aligned
with the consumer; reassess it when deliberately upgrading the consumer.
Do not hand-edit generated validators or replace the consumer library just to
work around inference.

Orval also emits some query names as both a TypeScript type and a Zod value.
When both generated barrels are re-exported, explicitly select the original
type and expose the validator under a separate Schema alias.

**Why:** Wildcard exports alone produce ambiguous duplicate exports and break
the shared-library build when adding a query endpoint.

**How to apply:** Resolve collisions in the handwritten public barrel, not
generated output, and run the consuming TypeScript build after generation.
