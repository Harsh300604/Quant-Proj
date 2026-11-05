# Review of materials sent by the client (6 Nov 2026)

Files reviewed: the QuantAgents paper (arXiv 2510.04643), its website summary (quantagents.github.io),
the TradingAgents paper (arXiv 2412.20138), a README ("shared by professor") and the notebook
`QuantAgents_v17_fixeddata.ipynb`. All seven suggestions below were adopted by the user on 6 Nov 2026 (D32-D37).

## What the QuantAgents paper actually does

| Aspect | Paper | Our brief / build |
|---|---|---|
| Agents | Otto = manager; **Bob = simulated trading analyst**; Dave = risk control analyst; **Emily = market news analyst** | Emily = fundamental analyst, Bob = quantitative analyst, Dave = risk, Otto = manager (brief §6) |
| Meetings | Market analysis (weekly), **strategy development with simulated trading** (weekly), **risk alert** (triggered when a risk score > 0.75) | Market analysis → strategy → decision, monthly; risk veto loop out of scope |
| Simulated trading | Bob backtests a pool of candidate strategies on data before t and picks the best; Otto weighs simulated vs real performance (sigmoid of recent relative returns) | Not in the brief |
| Risk score | R = w1·portfolio beta + w2·(1/liquidity ratio) + w3·max sector exposure + w4·volatility | Dave reads "portfolio risk stats" (unspecified) |
| Memory | 3 memories (market info, strategy, reports); top-10 similar past cases retrieved by embeddings; reflection updates | Stateless graph with `prior_report` |
| Data | NASDAQ-100, Yahoo Finance prices, **Alpaca news**, financial reports; train 2010-2020, test 2021-2023 | Same sources; 2015-2023 point-in-time |
| Model | GPT-4o, temperature 0.7, one run | Claude Haiku/Sonnet 5.5, no temperature (API rejects it), response cache |
| Metrics | TR, ARR, Sharpe, Calmar, Sortino, MDD, volatility, **Entropy (ENT)**, **Effective Number of Bets (ENB)** | Brief's list (no ENT/ENB) |
| Results | ~300% total return 2021-2023, Sharpe 3.11, MDD 16.9%; NDX 32.5% | — |
| Cost | ~$180 over 3 years (weekly, GPT-4o) | Planned ~$60-90 for three 9-year monthly runs |
| Own limitation | "backtesting may be affected by potential LLM information leakage" | Our names-hidden run and point-in-time gateway target exactly this |

## Suggestions (all adopted 6 Nov 2026: decisions D32-D37)

1. **Add ENT and ENB, plus a 2021-2023 sub-period**, so our table can sit next to the paper's Table 2. No API cost.
2. **Python "simulated trading" for Bob**: each rebalance, Python backtests a small fixed pool of rule-based strategies (e.g. momentum, reversal, low volatility, quality) on data before t via the gateway; Bob gets the computed results. Closer to the paper's method; respects "LLMs never do maths". Small token cost.
3. **The paper's risk score inputs for Dave**, computed in Python (beta, liquidity, max sector exposure, volatility). The risk-alert meeting itself stays out of scope.
4. **A point-in-time track record** as the paper's "strategy memory": the committee sees how its own views from 3+ months ago turned out (only outcomes fully known at t). Must be identical for baseline and enhanced.
5. **Persona wording from the paper's profiles** (also in the notebook) as the starting point of our prompts, keeping the brief's roles; optionally rename Emily "market news & fundamentals analyst" to match the paper.
6. Two more scale-free indicators from the notebook: ADX(14) and relative volume (20-day).
7. **Poster framing:** the paper's own limitation (possible LLM leakage) and its very high Sharpe (3.11, above our red-flag line of 2) motivate our point-in-time design and names-hidden control.

## Not to adopt (from the notebook)

- **Hard-coded API keys** (Perplexity and Alpaca) in the notebook: the owner should revoke and replace them; the notebook should not be shared further or committed anywhere.
- **Web-grounded LLM research** (Perplexity "sonar-pro" with "assume today's date is ..."): web search returns today's information, a look-ahead leak in a backtest.
- **Asking the LLM for the NASDAQ-100 list**: returns today's members (survivorship and look-ahead).
- **LLM-produced dollar allocations, price targets, stop-losses and VaR numbers**: LLMs doing maths.
- Setting `temperature` (rejected by the API since Oct 2026); weekly meetings (our cadence is monthly, decided).

## TradingAgents

Confirms choices already in the plan: structured reports instead of chat history, a fast/strong model split, bull/bear debate with a facilitator (our stretch item S1). Nothing new to add.
