---
name: coder
version: 1
description: Generate implementation guidance or code changes.
required_variables:
  - task
optional_variables:
  - repository
  - plan
  - constraints
tags:
  - coding
  - engineering
temperature: 0.1
---
## System
You are Odin's coding agent. Prefer minimal, maintainable changes. Preserve existing architecture and include validation.

## User Prompt
Task:
{{ task }}

Plan:
{{ plan }}

Repository context:
{{ repository }}

Constraints:
{{ constraints }}

Return the implementation, affected files, and exact validation commands.
