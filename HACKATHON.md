# TrueFoundry - Resilient Agents - Online Hackathon
## About Event
​Infrastructure fails. Rate limits hit. Timeouts happen. Most agents just crash.

​Resilient Agents is a one-week online hackathon hosted by TrueFoundry with support from AWS Bedrock. The challenge: build an agent that keeps working when providers slow down, rate limits hit, tools fail, or model calls break.

## The Challenge

​Use TrueFoundry AI Gateway to connect to AWS Bedrock models, route LLM calls, and configure fallbacks. If your agent uses tools, add MCP Gateway and Guardrails so tool access is controlled and risky actions can be checked before they run.

​Then stress-test it against failures like:
- ​rate limits
- ​model or provider outages
- slow responses
- ​tool failures
- ​bad intermediate outputs
- ​cascading errors across multiple steps

## What You'll Build With
- **​AWS Bedrock**: access foundation models from providers like Amazon, Anthropic, Meta, Mistral AI, Cohere, and others through a managed AWS service.
- **​TrueFoundry AI Gateway**: route requests, configure fallbacks, monitor usage, and keep LLM calls governed from one place.
- **​TrueFoundry MCP Gateway**: give your agent safe, centralized access to tools and data sources. Use it to expose only the tools your agent needs, manage auth centrally, and keep an audit trail of tool usage.
- **​Guardrails**: add safety checks around LLM calls and MCP tool calls. Use them to block unsafe inputs, redact sensitive data, validate tool arguments before execution, and inspect tool results before the model sees them.

​What Judges Care About

- ​AI Gateway setup: routing, fallback, observability, and control
- ​MCP Gateway usage: safe tool access, scoped permissions, auth, and auditability
- ​Guardrails: checks that block, redact, or validate risky LLM and tool behavior
- ​Resilience: retries, fallback behavior, state preservation, and graceful degradation
- ​Usefulness: a real problem for a clear user
- ​Demo clarity: show what failed, how the agent recovered, and why it worked