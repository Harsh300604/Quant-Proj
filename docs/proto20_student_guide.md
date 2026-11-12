# QuantAgents prototype: the student guide

This guide explains the 20-stock prototype in plain words: what it is, how it works, how we checked it, and how it performs. It is updated at the end of every build phase. Read it alongside your mentoring sessions. By the end you should be able to explain every part in your own words.

_Last updated: 12 Nov 2026 (phase P1: the 20 companies and the benchmark)._

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
| 2021 | +32.7% | +27.4% |
| 2022 | −37.0% | −32.6% |
| 2023 | +68.9% | +54.9% |

The biggest companies rose more than the index in good years and fell more in 2022. Our AI portfolio has to beat the left-hand column, not QQQ.

**Other changes:**
- two new indicators for the analysts:
  - **ADX**: how strong a price trend is, from 0 to 100;
  - **relative volume**: today's trading volume compared with the last 20 days;
- Pinduoduo moved from "Industrials" to "Consumer Discretionary", because it's an online shop like Amazon;
- the spending limit for the whole prototype is set in the code: $40, with an automatic stop at $32.

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
| What is your benchmark, and why not QQQ? | The same 20 companies held at market weight. Comparing 20 stocks with 100 would mix up "AI skill" with "big companies did better" |
| How do you know the 20 weren't picked with hindsight? | We rebuilt the database as of 4 Jan 2021 and the rule picked the same 20 |
| What did you find when you checked the data? | The first top-20 list was wrong because of missing splits, missing share counts and stale files. We fixed each one and added a test |

## 10. Who did what

_(To be filled in honestly by the mentor and student: for example "the mentor and an AI coding assistant built the reference system; the student studied it in 16 sessions and rebuilt parts X and Y".)_
