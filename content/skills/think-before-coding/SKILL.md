---
name: think-before-coding
description: Resolve meaningful ambiguity and state assumptions before a nontrivial implementation.
---

# Think Before Coding

Read the request, project instructions and nearby implementation. State assumptions affecting
behavior; infer routine details from established conventions and continue. Ask only when the
missing choice materially changes scope, outcome, compatibility or authority.

Prefer the smallest sufficient approach. Compare alternatives when their tradeoff matters.
Existing implementation authorization covers normal edits and verification; do not ask again
per file or step. A diagnosis or review request alone does not authorize implementation.

For example, validation can follow a parser's documented contract. Rejecting previously accepted
input in a public protocol needs an explicit compatibility decision before the dependent edit.
