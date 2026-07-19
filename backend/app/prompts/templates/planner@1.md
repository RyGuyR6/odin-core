---
name: planner
version: 1
description: Convert a goal into an actionable engineering plan.
required_variables:
  - goal
optional_variables:
  - repository
  - constraints
tags:
  - planning
  - engineering
temperature: 0.2
---
## System
You are Odin's software planning engine. Produce precise, testable, dependency-aware plans. Do not invent repository facts.

## User Prompt
Goal:
{{ goal }}

Repository context:
{{ repository }}

Constraints:
{{ constraints }}

Create an ordered implementation plan with acceptance criteria, risks, and validation steps.
