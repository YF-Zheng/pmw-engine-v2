# Model Matrix Candidates

Status: planning candidates only. Inclusion, current availability, exact request
IDs, costs, limits, and metadata exposure must be verified immediately before
the preregistration freeze. No entry authorizes collection.

## Selection rule

Each matrix targets at least two frontier/high-capability systems, at least one
medium-capability system, and at least one smaller or open-weight system, with
different training organizations/families where feasible. These are intended
strata, not verified claims about present capability. The nested matrices keep
design comparisons legible while the owner chooses a cost tier.

| Key | Candidate | Intended stratum | Proposed exact request ID | Proposed provider/path |
|---|---|---|---|---|
| LUNA | GPT-5.6 Luna | smaller/efficient system | `gpt-5.6-luna` | OpenAI Responses API |
| CLAUDE | Claude Opus 4.8 | frontier/high | `claude-opus-4-8` | Anthropic Messages API |
| GEMINI | Gemini 2.5 Flash | medium | `gemini-2.5-flash` | Google Gemini API |
| QWEN | Qwen3 32B | smaller/open-weight | `Qwen/Qwen3-32B` | Open-weight serving provider |
| TERRA | GPT-5.6 Terra | frontier/high | `gpt-5.6-terra` | OpenAI Responses API |
| MISTRAL | Mistral Small 3.1 24B Instruct | smaller/open-weight | `mistralai/Mistral-Small-3.1-24B-Instruct-2503` | Open-weight serving provider |

The OpenAI, Anthropic, and Google public lifecycle/model listings were checked
on 2026-10-07. This verifies only that the proposed public ID is documented and
not known retired on that date. Account entitlement, accepted request controls,
rate limits, prices, and returned identity still require an account-level
transport-only preflight before freeze. Qwen and Mistral serving paths remain
entirely `UNVERIFIED`; their weight identifiers are not provider request IDs.

## Candidate matrices

| Gate choice | Members | Design intent |
|---|---|---|
| 4-model budget | TERRA, CLAUDE, GEMINI, QWEN | Two intended high-capability systems, one medium system, one open-weight system; four organizations/families. |
| 5-model balanced | Budget + LUNA | Adds the second pilot-tested OpenAI system and an efficient capability point while retaining cross-family coverage. |
| 6-model extended | Balanced + MISTRAL | Adds another open-weight family and size/capability point. |

The prior DEV pilot establishes historical transport for LUNA and TERRA only;
it does not verify formal-date availability, pricing, aliases, rate limits, or
relative capability, and it must not determine a directional hypothesis.

## Metadata policy

For every candidate, the following remain `UNVERIFIED` until documented by a
provider preflight or authoritative account metadata before freeze:

- availability and access entitlement;
- exact accepted model ID and whether it is version-pinned;
- reasoning mode and the mapping needed by either inference-budget policy;
- temperature, top-p, maximum-output, and other sampling controls;
- provider-enforced seed support;
- API/CLI path and transport semantics;
- input, cached-input, and output token prices;
- request/token rate limits and concurrency;
- returned model identity availability;
- provider request-ID and session-ID availability.

Unexposed metadata must be recorded as `unavailable` with a reason, never
invented. A dynamic alias is a documented limitation. Prefer a version-pinned
ID when the provider exposes one.

## Inference-budget policy owner gate

### Option A: system-level configuration

Use each deployed system's verified standard high-quality configuration.
This estimates the capability of the deployed AI system. It improves ecological
validity, but reasoning effort, token allocation, latency, and price may differ
and are therefore part of the treatment rather than controlled confounders.

### Option B: approximate matched inference budget

Predefine comparable maximum output/reasoning-token and effort targets, then
map each provider's verified controls to them. This better targets capability
under a comparable inference allowance, but provider controls are not necessarily
commensurate, hidden compute remains unmatched, and some systems may lack the
needed controls. Any approximation and deviation must be frozen and reported.

No mixture is allowed: one policy applies to the entire final matrix. If exact
matching is impossible under Option B, the owner must approve and freeze the
documented approximation before collection.

```text
OWNER_DECISION_REQUIRED:
model_matrix = null              # budget | balanced | extended
inference_budget_policy = null   # system_level | matched_budget
```
