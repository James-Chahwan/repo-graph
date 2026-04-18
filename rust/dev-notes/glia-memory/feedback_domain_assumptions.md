---
name: Don't smuggle code-domain assumptions into "universal" or "domain-agnostic" claims
description: When designing for a domain-agnostic format, every "every domain has X" claim must be checked against video/audio/molecules/social-graph/event-stream — not just verified against more code domains
type: feedback
originSessionId: 878f0a31-992e-4638-aeb2-f6c84dd3555c
---
**Rule:** When making "universal" or "domain-agnostic" design claims, verify against domains that *aren't* code-shaped. If the claim relies on hierarchy, names, or text-shaped content, it's probably a code-domain assumption.

**Why:** User pushback 2026-04-17: *"is that really a good enough breakdown of every possible primite to come like video and god knows what else do you get what i mean?"*

Context: I had argued that pragmatic Node shape `{id, repo, confidence, name, kind, parent, cells}` was domain-agnostic because "every domain has a name, a kind, and (usually) a hierarchy. Chemistry: Atom/Bond/Molecule. Climate: Station/Reading/Region. Policy: Section/Clause/Reference."

That examples list was code-shaped thinking. **Counter-examples the user surfaced (or that should have been considered):**
- **Video frames** have indices, not names. Frame 38472 isn't called anything.
- **Audio samples** have timestamps, not names.
- **Molecules at atom level** have elements (C, H, O), not "names" in the semantic sense.
- **Sensor / time series data** has timestamps + values, no hierarchy.
- **Event streams / logs** are flat, not hierarchical.
- **Social graphs** have persons (with names, sure) but relationships are flat.

The fix was to move to strict Node `{id, repo, confidence, cells}` and push navigation into **domain-owned indices** stored in the container.

**How to apply:**

1. When proposing "this works for every domain", **list at least three non-code domains explicitly** and check the design against each. Code, chemistry, video, audio, time series, policy, social graph.
2. **Hierarchy is not universal.** Don't put `parent: Option<NodeId>` in any "universal" struct.
3. **Names are not universal.** Don't put `name: String` in any "universal" struct.
4. **Text-shaped content is not universal.** Cells need `Bytes` payload variant, not just `Text`/`Json`.
5. When the user says "axis of decomposition" or pushes on universality, that's the signal to genericise harder, not defend the current shape.
6. **Indices are the escape valve.** Anything that varies per domain (navigation, lookup, traversal patterns) lives in domain-owned data structures, not in core types.

**The user's instinct here was sharper than mine — trust pushes on domain-agnostic claims.** They will keep pushing until the abstraction actually holds for video/policy/chemistry, not just for "more kinds of code".
