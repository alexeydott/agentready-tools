# Notice

The protocol selection and behavior were researched from public specifications,
Cloudflare's public Agent Readiness materials, and the public behavior of
`isitagentready.com`.

The MIT-licensed projects below were reviewed as independent references for
engineering patterns and observable validation behavior:

- https://github.com/itaides/agent-readiness
- https://github.com/kodustech/agent-readiness

AgentReady Tools is an independent Python implementation. It does not contain a
runtime dependency on either project. Kodus targets source-code repository
readiness; only general patterns such as configuration, CI gates, maturity
progress, and impact/effort recommendation ranking were adapted to the separate
website/protocol-readiness problem.

Names and trademarks of Cloudflare, MCP, A2A, Agent Skills, UCP, x402, MPP and
ACP belong to their respective owners. This project is not an official
Cloudflare product and does not claim exact score parity.
