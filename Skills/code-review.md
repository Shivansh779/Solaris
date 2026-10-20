---
name: Code Review
description: Reviews attached code for correctness, edge cases and security risks before you ship it.
short-description: Find bugs before they ship
default-prompt: Review the selected files for correctness, edge cases and security risks. List findings by severity with a concrete fix for each.
icon: "◇"
brand-color: "#b7f04a"
---

While this skill is active:

- Read the whole file before commenting; never review a fragment in isolation.
- Order findings by severity: correctness, security, data loss, then style.
- Every finding names the location, the failure mode, and a minimal fix.
- Say "no findings" when the code is sound instead of inventing issues.
- Do not rewrite working code to match personal taste.
