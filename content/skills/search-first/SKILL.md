---
name: search-first
description: Find reusable repository code and verify uncertain or version-dependent APIs before adding implementation or dependencies.
---

# Search First

Search the repository first. Inspect nearby code, manifests, tests and dependency versions;
prefer an existing helper or established pattern. Consult official documentation for a
version-dependent API, new dependency or uncertain fact.

Use available hosting/package searches when selecting a reusable dependency would materially
help. External registry searches are not mandatory for ordinary local logic. Mention unavailable
channels only when relevant. Compare reuse, adaptation and local code against maintenance cost,
platform constraints and the actual requirement, not an arbitrary percentage threshold.
For external candidates, include license compatibility and transitive dependencies in that cost;
avoid a large package or a wrapper that erases the benefit of reuse for a small requirement.

Do not read credentials to enable search. Independent bounded research is optional when it
provides useful parallel progress.
