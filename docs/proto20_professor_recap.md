# QuantAgents prototype: project recap

_For the professor. 13 November 2026. Details are in the summary (`proto20_summary.docx`); every problem we met is in the problems log (`proto20_problems_log.docx`)._

## The question

The QuantAgents paper (arXiv 2510.04643) reports that a committee of AI agents made about 300% on NASDAQ-100 stocks from 2021 to 2023, while the index made 32.5%. The paper itself warns that its backtest "may be affected by potential LLM information leakage". **We rebuilt the idea under strict, leak-proof conditions, to see whether any edge remains.**

## What we built

A 20-stock prototype, called proto20, that runs the whole pipeline end to end:

- **Universe:** the 20 largest NASDAQ-100 companies on 4 Jan 2021, chosen with that day's data only.
- **Period:** January 2021 to December 2023, 36 monthly decisions (the paper's test period).
- **Benchmark:** the same 20 companies at market weight.
- **AI analysts:** 20 short research memos a month (Claude Haiku), then a five-step committee modelled on the paper (Claude Sonnet):
  - **Emily:** news and fundamentals;
  - **Bob:** quantitative signals;
  - **Dave:** risk;
  - **Otto:** draft, then final decision.
- **Python does all the maths:**
  - simulated trading of simple strategies for Bob, risk statistics for Dave, and the committee's own track record;
  - the weights, the trading simulation and every metric;
  - a check of every AI answer against a fixed format.

**Three versions were compared:**
1. **Baseline:** Otto scales each benchmark weight between 0× and 2×.
2. **Enhanced:** Otto gives ratings and confidences, which Black-Litterman turns into weights under a 2%-a-year risk budget.
3. **Enhanced with names hidden:** company names and tickers are replaced by codes.

## How we kept the test fair

- **Point-in-time data:** one gateway serves all data and refuses anything published after the decision time. Leak tests try to break it, and every data read is logged. No run ever read future data.
- **Fixed rules:** each stock stays at 0× to 2× its benchmark weight, and each sector within ±2 points. There is no borrowing and no short selling, and trading costs 0.1%.
- **Red-flag checks:** results that look too good are flagged automatically, for example a Sharpe above 2 or a year with no loss.
- **Checking every result:** we logged 24 issues in plain language. They include data bugs we fixed (missing stock splits, wrong foreign share ratios, a broken risk-free series) and findings we noted.

## Results, 2021 to 2023

| | total return | per year | worst fall | Sharpe | info. ratio (90% interval) | active alpha (t) |
|---|---:|---:|---:|---:|---|---:|
| Baseline | +42.61% | +12.64% | −40.31% | 0.49 | −0.16 (−1.00 to +0.69) | −0.15% (−0.46) |
| Enhanced | +42.94% | +12.73% | −40.46% | 0.50 | −0.05 (−1.17 to +0.82) | −0.05% (−0.22) |
| Enhanced, names hidden | +42.57% | +12.63% | −40.19% | 0.49 | −0.24 (−1.25 to +0.64) | −0.15% (−0.58) |
| **Same-20 benchmark** | **+42.84%** | +12.70% | −40.49% | 0.49 | – | – |
| NASDAQ-100 (^NDX) | +32.54% | +9.91% | −35.56% | 0.42 | – | – |
| _Paper's QuantAgents (reported)_ | _+299.55%_ | _+58.68%_ | _−16.86%_ | _3.11 (note)_ | – | – |

Note: the paper's Sharpe uses a definition we could not reproduce, so it is not directly comparable. Our ^NDX row matches the paper's NDX on return, worst fall and volatility.

## What we found

1. **No measurable edge.** All three AI versions ended within 0.4 points of simply holding the 20 companies at market weight. Every uncertainty interval includes zero, and the views barely predicted the next 3 months (rank correlation +0.05 to +0.09).
2. **Responsible behaviour.** Across 108 monthly decisions there were:
   - no rule breaks;
   - no use of future data;
   - no invalid answers;
   - no red flags.

   Trading costs were 0.24 to 0.30% over three years.
3. **Hiding names changed almost nothing.** There's no sign that the AI relied on remembering these famous companies, though for 20 giants this is a weak test.
4. **The gap over the NASDAQ-100 (about 10 points) comes from which companies were chosen, not from the AI.** Large technology stocks led in these years.
5. **The paper's large gains did not appear under point-in-time conditions.** This supports the paper's own caution about information leakage. It does not disprove the paper: the setups differ (20 fixed companies, tight benchmark rules, monthly decisions).

## Cost

$25.57 in AI fees (about Rs 2,250), within a $40 budget. That's about $0.23 per monthly decision for the committee, about 40% cheaper thanks to prompt caching. The professor pack was made from stored results at no cost.

## Limitations

- 36 months is a short sample, so statistical tests have little power.
- The test covers 20 mega-caps fixed on one day; it says nothing about "beating the NASDAQ-100".
- The tight rules limit how far any version can differ from the benchmark.
- Each version ran once, and a second run could differ slightly.

## Next step

The full study: about 100 NASDAQ-100 companies from 2015 to 2023. It will use licensed data for companies that left the index, so that the test is free of survivorship bias, and it will have its own budget. **We would like to agree the success measure with you before it runs.** Our proposal is the information ratio and the Carhart alpha against the benchmark.
