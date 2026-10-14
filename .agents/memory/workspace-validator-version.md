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
