# Forward Deployment Kit for CmdClaw

## Installation

Setup the MCP server

## How to use
use the /cmdclaw-coworker-orchestrator command to create a new coworker

example prompt:
/cmdclaw-coworker-orchestrator create a new coworker that get my latest email from gmail and give me a summary of the email.

## What it does

Start 3 subagents inside codex/claude code to implement the coworker.
1. cmdclaw-coworker-orchestrator
ask you questions to understand the coworker and create a PRD (Product Requirements Document)
2. cmdclaw-coworker-implementer
implement the PRD
3. cmdclaw-coworker-reviewer
review the implementation 

2. and 3. loop until 1. is happy with the output.
