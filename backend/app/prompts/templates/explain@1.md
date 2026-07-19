---
name: explain
version: 1
description: Explain a technical subject for a target audience.
required_variables:
  - topic
optional_variables:
  - audience
  - context
tags:
  - education
temperature: 0.3
---
## System
You are Odin's technical educator. Be accurate, concrete, and adapt depth to the audience.

## User Prompt
Topic:
{{ topic }}

Audience:
{{ audience }}

Context:
{{ context }}

Explain the topic with a practical example and common failure modes.
