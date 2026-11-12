# Cost forecast v1 (2026-11-13)

Measured on run `proto20_2021_base_dev`: 12 rebalances x 20 companies, models claude-haiku-5-5; it cost **$0.2717** (Rs 23.91). Prices: `configs/pricing.yaml`. Exchange rate: Rs 88 per USD. Ranges are +-20%.

## Measured token profile (per API call)

| node | model | calls per rebalance | fresh input | cache write | cache read | output |
|---|---|---:|---:|---:|---:|---:|
| bob | claude-haiku-5-5 | 1.00  | 1,894 | 0 | 22,311 | 2,233 |
| dave | claude-haiku-5-5 | 1.00  | 3,553 | 0 | 22,311 | 2,174 |
| emily | claude-haiku-5-5 | 1.00  | 365 | 22,311 | 0 | 2,134 |
| memo | claude-haiku-5-5 | 0.99 per company | 1,789 | 21 | 1,237 | 820 |
| otto_draft | claude-haiku-5-5 | 1.00  | 5,134 | 0 | 22,311 | 1,946 |
| otto_final | claude-haiku-5-5 | 1.00  | 7,202 | 0 | 22,311 | 1,957 |

Committee prompt-cache read share: **69%** of committee input tokens (memos: 41%).

## Per rebalance (20 companies)

- dev tier (Haiku committee): $0.0226 (memos $0.0119, committee $0.0107)
- paper tier (Sonnet committee): $0.2263 (memos $0.0119, committee $0.2144); the brief's planning figure was about $0.25

## P6 runs against the MVP budget

| run | USD | range | INR |
|---|---:|---:|---:|
| Sonnet measurement pilot, thinking off (3 rebalances x 5 companies) | $0.65 | $0.52-$0.78 | Rs 57 |
| Sonnet measurement pilot, thinking on (rough: committee x2.5) | $1.62 | $1.29-$1.94 | Rs 142 |
| proto20 baseline, 2021-2023, paper tier (36 x 20) | $8.15 | $6.52-$9.78 | Rs 717 |
| proto20 enhanced, 2021-2023, paper tier (36 x 20) | $8.15 | $6.52-$9.78 | Rs 717 |
| proto20 names-hidden enhanced (optional, D44) | $8.15 | $6.52-$9.78 | Rs 717 |
| **Total P6** | **$26.71** | $21.37-$32.05 | Rs 2,350 |

MVP budget (stage `proto20`): $40.00; spent so far $0.3156; remaining $39.68; automatic stop at $32.00. **The P6 plan may not fit below the automatic stop: ask the user before P6.**

## Full runs (main plan, after proto20; separate approval)

| run | USD | range |
|---|---:|---:|
| Full baseline 2015-2023, paper tier (108 x ~100) | $30.73 | $24.59-$36.88 |
| Full enhanced 2015-2023, paper tier | $30.73 | $24.59-$36.88 |
| Full names-hidden enhanced, paper tier | $30.73 | $24.59-$36.88 |
| **Total** | **$92.20** | $73.76-$110.64 |

## Assumptions

- Sonnet answers are assumed to be as long as Haiku's (the +-20% range covers moderate differences; the Sonnet pilot in P6 measures it).
- The enhanced variant (P5) asks for a rating and confidence instead of a multiplier: about the same size.
- Thinking on: committee cost x2.5 (brief section 8); thinking stays off unless the user approves (D46).
- Full runs: ~100 memos per rebalance; the committee briefing adds ~40 tokens per extra company.
- Reruns from the response cache cost $0.
- The Sonnet pilot lines keep the 20-company committee size, so they are upper estimates (5 companies mean shorter briefings and answers).
- Committee answers were about 2,000 output tokens per call on Haiku; output is about half of the Sonnet committee cost, so shorter answers are the main lever if the budget gets tight.

## Summary to forward

We measured the full agent committee on 12 monthly decisions for 20 companies: it cost $0.27 on the cheap development model. On the paper's model mix, one monthly decision for 20 companies costs about $0.23, so the three 36-month prototype runs plus the model pilot come to about $27 ($21-$32), against $40 left of the $40 prototype budget. Nothing runs without approval first.
