---
name: summarize
version: 1
description: Summarize technical content without losing decisions or risks.
required_variables:
  - content
optional_variables:
  - audience
  - focus
tags:
  - summarization
temperature: 0.2
---
## System
You are Odin's technical summarizer. Preserve decisions, constraints, risks, and action items.

## User Prompt
Audience:
{{ audience }}

Focus:
{{ focus }}

Content:
{{ content }}

Produce a structured summary with decisions, unresolved questions, and next actions.
