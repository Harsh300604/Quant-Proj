# QuantAgents prototype: the student guide

This guide explains the 20-stock prototype in plain words: what it is, how it works, how we checked it, and how it performs. It is updated at the end of every build phase. Read it alongside your mentoring sessions. By the end you should be able to explain every part in your own words.

_Last updated: 12 Nov 2026 (phase P3: portfolio rules and the trading simulator)._

---

## 1. The idea in one paragraph

We built a team of AI "analysts" that manage a pretend stock portfolio. Every month, the team reads each company's prices, financial reports and news, and then decides which stocks to hold a little more of and which a little less of, compared with simply holding the market. We replay history month by month, from January 2021 to December 2023, and the computer is only ever allowed to see information that existed on that date. At the end, we compare our portfolio with the simple "just hold the market" choice to see whether the AI team added anything.

No real money is used. This is a research test on past data, called a **backtest**.

## 2. Words you need

| Word | Meaning |
|---|---|
| Stock / share | A small piece of ownership in a company |
| Market cap | The total value of a company on the stock market: share price × number of shares |
| Index | A list of companies with a weight for each, used to measure "the market". The NASDAQ-100 is the 100 largest non-financial companies on the Nasdaq exchange |
| Cap-weighted | Bigger companies get a bigger weight. If Apple is worth twice as much as Microsoft, it gets twice the weight |
| Portfolio | The set of stocks we hold and how much of each |
| Benchmark | What we compare ourselves against. Ours: holding the same 20 companies at their market weights |
| Rebalance | Changing the portfolio's weights. We do it once a month |
| Backtest | Replaying the past to see how a strategy would have done |
| Look-ahead bias | Accidentally using information from the future. It makes results look better than they could really have been |
| Survivorship bias | Testing only companies that still exist today. It ignores the ones that failed or were bought |
| LLM | Large language model, an AI that reads and writes text (we use Anthropic's Claude) |
| Stock split | A company divides each share into several cheaper ones (for example 10-for-1). The company is worth the same; the price per share drops |
| ADR / ADS | A certificate traded in the US that stands for shares of a foreign company. One ADS can stand for 2, 4, 25 or even 1/10 of a real share |

## 3. Why only 20 companies, and why 2021–2023?

- The full project uses all of the NASDAQ-100 from 2015 to 2023. Building and testing that takes longer and needs extra data that must be bought (prices for companies that no longer exist).
- So we first built a **prototype**: the same system, on fewer stocks and a shorter period, to get real results sooner.
- **Which 20?** The 20 largest NASDAQ-100 companies by market cap at the close of trading on **4 January 2021**, the first trading day of the test. We did not pick them by hand. A fixed rule picks them, using only that day's information, so we can't be accused of choosing companies we already knew would do well.
- **Why 2021–2023?** It's the same test period as the research paper our method comes from (*QuantAgents*), so our results can sit next to theirs.
- **The fair comparison:** our benchmark is the same 20 companies held at their market weights. Both sides of the comparison have the same companies, so the test is fair.

## 4. How the system works

Each month, the same steps run in order:

1. **Data gateway (Python).** One piece of code is the only door to the data. It refuses to hand out anything published after the decision date. This is how we stop look-ahead bias.
2. **Research memos (AI, small and cheap model).** One short report per company: recent price trends, financial results, news.
3. **The committee (AI, stronger model).** Four AI analysts meet in order:
   - **Emily** reads the news and the financial results;
   - **Bob** reads the results of simple trading rules that Python tested on the last 12 months;
   - **Dave** reads risk numbers that Python calculated;
   - **Otto**, the manager, makes the final call for each stock: hold more, the same, or less.
4. **Optimizer (Python).** Turns Otto's calls into exact weights that follow the rules:
   - each stock stays between 0× and 2× its market weight;
   - each sector stays within 2 percentage points of its market weight;
   - no borrowing, and the weights add up to 100%.
5. **Trading simulator (Python).** Buys and sells at the next day's opening price and charges a 0.1% trading cost. It then tracks the portfolio's value every day until the next month.

**A key rule:** the AI never does maths. Python calculates every number (weights, returns, risk), and the AI only reads those numbers and gives its judgement. AI models make arithmetic mistakes, and Python doesn't.

We test two versions:
- **Baseline:** the paper's method. Otto picks a multiplier per stock.
- **Enhanced:** Otto gives each stock a rating (strong sell … strong buy) and a confidence. A standard finance formula called **Black-Litterman** turns those ratings into weights. With no opinion, it simply holds the market weight.

## 5. What we built, phase by phase

### P0: checking the data (12 Nov 2026)

**What we did:** built the database (about 350,000 daily prices, 380,000 financial figures and 330,000 news articles) and looked at the list of the largest companies on 4 January 2021.

**What we found:** the list was clearly wrong. Apple, Microsoft and Amazon were missing, and Sirius XM appeared to be worth $262 billion when it was really worth about $27 billion. We traced it to five problems:

1. **Old files were never refreshed.** The first small test download (2014–2015 only) was treated as "done", so the full download skipped Apple, Microsoft, Nvidia and Amazon.
2. **Missing stock splits.** Yahoo Finance adjusts old prices for every split up to today. But our price files stop in April 2024, so splits after that (Nvidia, Broadcom, Netflix and others) were invisible. Their market caps came out 10 times too small, or, for Sirius XM, which did a reverse split, 10 times too big.
3. **Missing share counts.** Companies with several share classes (Alphabet, Meta, Comcast and Zoom) and many foreign companies report their share count in a way the government's free data file leaves out.
4. **ADR ratios.** A foreign company's US certificate can stand for a different number of real shares (NetEase: 1 certificate = 5 shares). Without that ratio, its value can be wrong by up to 25 times.
5. **Marvell** changed its legal home in 2021 and got a new government ID, so its older records weren't linked. It's too small to matter for the top 20, so we left it for the full run.

**How we fixed them:**
- the downloader now checks that a saved file covers the right dates;
- it saves every company's full split history;
- the database uses a backup source for the share count;
- the ADR ratio can change on a date.

We wrote an automated test for each fix, so the mistake can't come back unnoticed.

**Why this matters:** if we had not checked, the "top 20" would have contained the wrong companies, and every result after that would have been meaningless. Checking data against common sense ("Apple must be near the top") is one of the most important steps in any data project.

### P1: choosing the 20 and building the benchmark (12 Nov 2026)

**Choosing the 20.** We wrote the rule as code instead of typing a list:
1. Take the NASDAQ-100 members on 4 January 2021 that have price data.
2. Sort them by their weight in the index at that day's close (a bigger market cap means a bigger weight).
3. Keep the top 20. If two have exactly the same weight, the one whose code comes first alphabetically wins.

The result is saved in `reference/proto20_universe.csv`, and a check command confirms that the rule still gives the same list.

| Rank | Company | Weight among the 20 |
|---|---|---|
| 1–3 | Apple, Microsoft, Amazon | 19.9%, 14.9%, 14.5% |
| 4–7 | Alphabet, Facebook, Tesla, Nvidia | 10.6%, 7.0%, 6.3%, 2.9% |
| 8–20 | PayPal, Adobe, Comcast, Netflix, ASML, Intel, PepsiCo, Pinduoduo, Cisco, Broadcom, Costco, Qualcomm, T-Mobile | 1.5–2.5% each |

These 20 companies made up about **75% of the whole NASDAQ-100** on that day. The index is very top-heavy.

**A test that the rule can't cheat:** we rebuilt the whole database as if it were 4 January 2021 (deleting everything after that day) and ran the rule again. It picked exactly the same 20. So nothing from the future influenced the choice.

**The benchmark.** "Holding the same 20 at their market weights":
- each day, every company's weight is its market cap divided by the total market cap of the 20;
- the benchmark's return on a day uses the weights from the **previous** day's close times each stock's return that day, because you can only invest using weights you already know.

| Year | Our 20-stock benchmark | QQQ (whole NASDAQ-100, for reference) |
|---|---|---|
| 2021 | +33.2% | +27.4% |
| 2022 | −37.6% | −32.6% |
| 2023 | +68.9% | +54.9% |

_(Corrected in P3, after the stock-split bug fix described below.)_

The biggest companies rose more than the index in good years and fell more in 2022. Our AI portfolio has to beat the left-hand column, not QQQ.

**Other changes:**
- two new indicators for the analysts:
  - **ADX**: how strong a price trend is, from 0 to 100;
  - **relative volume**: today's trading volume compared with the last 20 days;
- Pinduoduo moved from "Industrials" to "Consumer Discretionary", because it's an online shop like Amazon;
- the spending limit for the whole prototype is set in the code: $40, with an automatic stop at $32.

### P2: talking to the AI safely and cheaply (12 Nov 2026)

**One door to the AI.** Every request to Claude goes through one piece of code (`quantagents/llm/client.py`). It makes sure that:
- **the answer comes back in a fixed form.** We describe the exact fields we want (for a memo: business summary, price trend, fundamentals, news, positives, risks, a 3-month outlook and a conviction level), and the program checks the answer against that list. If the answer is broken, it asks once more. If it's still broken, the stock gets "no opinion" (neutral), never a made-up one;
- **the same question is never paid for twice.** Every answer is saved in a small database on the laptop, and asking the exact same question again reads the saved answer for free. That also makes results repeatable;
- **money can't run away.** A cost ledger records every call with its cost in dollars and rupees. Before each call, it works out the most that call could cost and refuses it if that could push spending past the limit. For the whole prototype the limit is $40, and it stops automatically at $32.
- **the API key stays secret.** It's read from a private file, never written into logs, the database or error messages, and an automated test checks this.

**The first memos.** A research memo is the AI's one-page note on one company. Python first gathers the facts from the database: returns over 1, 3, 6 and 12 months, indicators, the latest financial results, and up to 15 recent headlines, all as of the decision date. The AI (Claude Haiku, the small, cheap model) then writes the memo from those facts only.

We tested it on 8 memos:
- 5 on 2 March 2015: Apple, Microsoft, Nvidia, Amazon and American Airlines;
- 3 on 4 January 2021: Apple, Pinduoduo and T-Mobile.

| What | Cost |
|---|---|
| 8 memos (first time) | $0.0049, less than half a rupee |
| The same 8 again | $0.0000 (all answered from the saved copies) |
| One memo, on average | about $0.0006 |

**Two bugs found before any money was spent:** a free "dry run" prints exactly what the AI would see, and it showed that:
- Pinduoduo's results were in Chinese yuan but were shown with a dollar sign;
- Apple's headquarters showed as "unknown".

Both were fixed first. Lesson: always look at what you're about to send to the AI.

**What we noticed:** all 8 memos said "neutral, low conviction". Our instructions told the junior analyst to be careful, and it was. The real decisions are made by the committee in P4, and we'll watch whether this caution carries through.

### P3: the rules of the portfolio and the trading simulator (12 Nov 2026)

**The rules (constraints).** Whatever the AI suggests, the final portfolio must:
- keep each stock between 0× and 2× its benchmark weight. If Apple is 20% of the benchmark, we may hold 0–40%;
- keep each sector within ±2 percentage points of the benchmark. If tech is 50%, we must hold 48–52%;
- invest all the money, with no borrowing and no short selling.

**The optimizer.** The AI suggests a multiplier for each stock (for example "1.3× Apple, 0.6× Intel"). Python then finds the portfolio that obeys every rule and is as close as possible to that suggestion. There is an exact method for this, which we tested against thousands of random cases. Every multiplier at 1 gives back exactly the benchmark.

**The trading simulator (backtest engine).** It replays history month by month:
1. On the first trading day of each month, at the 4 pm close, the strategy decides. It can only see data up to that moment.
2. It trades at the next morning's opening price and pays 0.1% of whatever it buys or sells.
3. Every day after that, the portfolio's value moves with the stocks' prices and dividends.
4. If a company stops trading (for example it was bought by another), its value is kept as cash until the next month.
5. After every month it saves its progress, so a stopped run carries on where it left off and gives exactly the same answer.

**Two tests with no AI (free):**

| Strategy | Total 2021–2023 | Benchmark | Trading costs |
|---|---|---|---|
| Hold the benchmark | +43.2% | +42.8% | 0.14% |
| Random tilts (random multipliers each month) | +35.0% (+39.3% with the P4 optimizer change, D50) | +42.8% | 2.47% |

Holding the benchmark almost exactly reproduces the benchmark, which shows the simulator's accounting is right. Random tilts trade a lot (about 63% of the portfolio a month) and lose about 8 points (about 3.5 after the P4 change). That's the bar the AI has to clear: doing better than random, after costs.

**Another bug found by checking:** at first, "hold the benchmark" trailed the benchmark by 2 points. Tracing it day by day showed the cause. When Alphabet and Amazon split their shares 20-for-1 in 2022, the price per share dropped 20×, but the share count stayed at its old figure until the next quarterly report. For a few weeks, those companies looked 20 times smaller than they were. We fixed it and added a test, and the gap shrank to 0.3 points. Lesson: when a number is a little off, find out why. Don't accept "close enough" until you understand it.

### P4: the AI investment committee (12–13 Nov 2026)

**What happens every month (one "meeting day"):**
1. **20 junior analysts** (cheap AI calls, run four at a time) each write a one-page memo on one company.
2. **Python prepares a briefing** for the committee. Everything in it is calculated by Python, never by the AI:
   - a table of each stock's returns, volatility (how much it jumps around) and beta (how strongly it moves with the market);
   - **simulated trading** for Bob: Python tests five simple rules over the past year, for example "buy last year's winners" or "buy the calmest stocks". It reports which rules would have beaten the benchmark;
   - **risk numbers** for Dave, including a single risk score R. The benchmark itself scores 0.75, and higher means riskier;
   - the committee's **track record**: how its own views from 3 months ago turned out. It only counts results that are fully known, so it starts empty and fills from April.
3. **Market analysis meeting:** Emily (news and company results), then Bob (numbers and simulated trading), then Dave (risk). Each one reads what the earlier ones said.
4. **Strategy meeting:** Otto, the manager, drafts a multiplier for each stock, from 0× to 2× in steps of 0.25.
5. **Python checks the draft.** It reports what the rules would change, how much would be traded, what that costs, and how risky the draft is.
6. **Decision meeting:** Otto confirms or adjusts the draft. Python turns the final multipliers into weights that obey every rule.
7. Everything is written to a **transcript** you can read, one per month.

**Cheap by design.** All five committee members read the same long briefing, about 10,000 tokens (roughly 7,500 words). The AI service can keep a copy of a repeated text block and charge a tenth of the price to re-read it ("prompt caching"). We found that the answer format counts as part of that block, and each member had a different format. So the briefing was being paid for in full four times a month. Giving everyone the same answer format fixed it and cut the committee's cost by about 40%.

**A design decision made from evidence (D50).** In the 5-stock trial, Otto asked to keep NVIDIA at normal weight and to sell all of American Airlines. The sector rules then forced a correction. The optimizer spread that correction as the same number of percentage points per stock, and that was huge for the tiny NVIDIA position: the result doubled NVIDIA and *raised* American Airlines. We changed "closest portfolio" to be measured in multipliers, so every stock's multiplier moves by the same small amount. Now the outcome was NVIDIA ×1.10 and American Airlines ×0.24, close to what Otto asked for. The random-tilt yardstick became +39.3% (turnover 55% a month).

**Safety checks after every run ("red flags").** The run is flagged if:
- the results look too good (a Sharpe ratio above 2, or no losing year over two or more years);
- the portfolio has a 15% day the benchmark didn't have;
- any rule was broken or any month traded more than 100%;
- any data was read from after the decision time.

**First real test: 2021, all 20 companies, cheap AI model (13 Nov 2026).**

| | Committee (AI) | Benchmark (same 20) | QQQ (reference) |
|---|---|---|---|
| Total return 2021 | +36.8% | +35.5% | +29.3% |
| Volatility | 20.0% | 20.3% | 18.2% |
| Worst fall (max drawdown) | −10.6% | −11.4% | −10.9% |

- All 12 meetings produced a valid decision on all 20 companies. Nothing failed, and the safety checks raised no flags.
- The committee was cautious:
  - most of the time it left a stock at normal weight (134 of 240 choices);
  - it underweighted more often than it overweighted;
  - it traded about 12% of the portfolio a month (random tilts: 55%).
- **Honest reading:** being 1.4 points ahead after one year is well within luck. One example: the committee held Tesla at half weight all year while Tesla rose faster than the benchmark. Its track record says 60% of its views were "right", but that's flattered by 2021's pattern. The biggest companies led the market, so most smaller stocks lagged the benchmark whatever the committee thought of them.
- **Cost:** $0.27 (about Rs 24) for the whole year of meetings, using the cheap model. With the stronger model planned for the real runs, a year costs about $2.70, and the full 3 years about $8 per version.

_(Later phases are added here as they are built.)_

## 6. How we know the test is fair

- **No peeking at the future:**
  - every piece of data carries the moment it became public;
  - the gateway refuses anything later;
  - automated "leak tests" try to catch it cheating, and fail the build if it does.
- **Same 20 on both sides:** survivorship bias affects both our portfolio and the benchmark equally.
- **Names-hidden run (optional):** the AI may have "memorised" how these famous companies did. In one run, company names are replaced with codes like "Company 017, semiconductors, large cap", and we check whether the results change. With 20 famous companies this is a weak check, and we say so.
- **Red flags:** the system raises a warning automatically if the results look too good to be true (for example a Sharpe ratio above 2).

## 7. Results

_(Filled in after the paper-tier runs in phase P6.)_

## 8. Limitations to state honestly

- Only 20 companies and 36 months: a short test, so differences may be luck. We don't claim statistical significance unless the numbers support it.
- The results are about these 20 companies, not about "beating the NASDAQ-100".
- Our index weights are calculated from public filings. They're close to the official weights but not identical.

## 9. Questions a mentor or professor may ask

| Question | Short answer |
|---|---|
| How did you choose the 20 stocks? | A fixed rule: the 20 largest by market cap on 4 Jan 2021, using only that day's data |
| How do you know the AI didn't see the future? | All data goes through one gateway that checks publication times, and automated tests try to break it |
| Why not let the AI calculate the weights? | AI models make arithmetic mistakes; Python is exact and checkable |
| How do you know the simulator's accounting is right? | Holding the benchmark reproduces the benchmark within 0.3 points over 3 years, and a hand-calculated 3-stock example matches to the cent |
| What stops the AI from building a crazy portfolio? | Python enforces the rules (0-2x each stock, sectors within 2 points); the AI only suggests |
| How do you control the AI cost? | A ledger records every call and refuses one that could pass the limit; repeated questions are answered from saved copies for free |
| What happens if the AI gives a broken answer? | It is checked against a fixed form, asked again once, and otherwise the stock gets "no opinion" (kept at market weight) |
| What is your benchmark, and why not QQQ? | The same 20 companies held at market weight. Comparing 20 stocks with 100 would mix up "AI skill" with "big companies did better" |
| How do you know the 20 weren't picked with hindsight? | We rebuilt the database as of 4 Jan 2021 and the rule picked the same 20 |
| Why five AI meetings a month instead of one? | It follows the paper's structure (analysts, then strategy, then decision), and it lets Otto react to Python's check of his draft (rules, trading costs, risk) before deciding |
| Does the AI see how its earlier calls turned out? | Yes, a "track record" of its own views, but only views whose 3-month result is fully known at the decision date |
| What did you find when you checked the data? | The first top-20 list was wrong because of missing splits, missing share counts and stale files. We fixed each one and added a test |

## 10. Who did what

_(To be filled in honestly by the mentor and student: for example "the mentor and an AI coding assistant built the reference system; the student studied it in 16 sessions and rebuilt parts X and Y".)_
