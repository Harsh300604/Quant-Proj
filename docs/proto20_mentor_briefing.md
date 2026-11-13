# Mentor briefing: how to explain proto20 to the student

_For the mentor (no finance background needed). 13 November 2026. It answers five questions: what the numbers mean, which files to use, what to share and show, how the AI was used and what it cost, and what we improved over the student's own version._

## 1. The numbers in plain words

**The one-sentence story:** we asked AI "analysts" to run a portfolio of 20 big tech-heavy companies for three years, under fair rules, and they did exactly as well as simply holding those 20 companies, no better and no worse.

**The words you need**, with our numbers as examples:

| term | what it means | our example | what to say |
|---|---|---|---|
| Portfolio | how much money goes into each company | Apple 21%, Microsoft 18%, … | "the AI decides these percentages every month" |
| Benchmark | the simple thing you compare against | the same 20 companies, each held in proportion to its size | "if the AI can't beat this, it added nothing" |
| Total return | how much $1 grew over the 3 years | AI +42.6% to +42.9%; benchmark +42.8% | "$1 became about $1.43 either way" |
| CAGR (return per year) | the same growth spread evenly over the years | about +12.7% a year | |
| Volatility | how much the value jumps around | about 26% a year | "a bumpy ride, normal for tech stocks" |
| Max drawdown (worst fall) | the biggest drop from a peak | about −40% (during 2022) | "at the worst point, $1 had fallen to $0.60" |
| Sharpe ratio | return earned per unit of bumpiness; higher is better | 0.49 to 0.50 for both AI and benchmark | "same reward for the same risk"; above 2 is suspicious |
| Active return | AI's return minus the benchmark's | between −0.07% and +0.02% | "practically zero" |
| Tracking error | how far the AI strayed from the benchmark | 0.4% to 0.6% a year | "it stayed very close to the benchmark" |
| Information ratio | active return per unit of straying; the main "skill" score | −0.05 to −0.24 | "zero means no skill; ours is about zero" |
| 90% interval | the range the true value probably lies in, given only 3 years of data | information ratio between about −1.0 and +0.8 | "it includes zero, so we can't claim any skill or harm" |
| Alpha (Carhart) | return left over after the usual market effects are explained | AI's active alpha −0.05% to −0.15%, t about −0.2 to −0.6 | "a t-value needs to be about 2 to count; ours is far from that" |
| Rank IC | did the stocks the AI liked do better afterwards? from −1 to +1 | +0.05 to +0.09 | "a very weak signal" |
| Hit rate | how often an over- or underweight call was right | about 50 to 60% | "close to a coin toss" |
| Turnover | how much of the portfolio is traded each month | 6 to 8% a month | "it traded calmly; trading costs were tiny (0.3% in 3 years)" |
| ENT / ENB | how spread out the bets are | similar to the benchmark | "it didn't concentrate risk" |
| Look-ahead bias | accidentally using information from the future | we made it impossible | "the most common way backtests fool people" |
| Survivorship bias | testing only companies that we now know survived | the 20 were chosen with 2021 data only | |
| Black-Litterman | a standard method that turns opinions plus confidence into portfolio weights | used in the "enhanced" version | "a careful translator from opinions to percentages" |

**The three numbers the student should remember:**
1. **+42.8%:** what simply holding the 20 companies made. All three AI versions are within 0.4 points of it.
2. **Information ratio about zero, with an interval that includes zero:** no measurable skill, positive or negative.
3. **About 300%:** what the paper reports for the same years. Under our leak-proof conditions, that kind of gain did not appear.

**What the result means:** this is a fair, useful "negative" result. The AI behaved responsibly, but found no edge, and the paper's big claim did not reappear when future information was locked away. It does not prove the paper wrong, because the setups differ (20 companies, strict rules, monthly decisions).

## 2. Which files to use, in which order

Everything is in two places: the project folder `D:\CreatED-Quant\quantagents\docs\`, and the pack folder `D:\CreatED-Quant\qa_store\reports\proto20\`, which holds the Word versions and the pictures.

| order | file | what it's for | time |
|---|---|---|---|
| 1 | `proto20_professor_recap.docx` | the whole project in about 3 pages: question, method, results, conclusion | 10 min |
| 2 | `proto20_student_guide.docx` | the full story in simple language, phase by phase, with a glossary and "questions a professor may ask" | 1 hour |
| 3 | `architecture.svg` | a picture of one month's process | 5 min |
| 4 | `proto20_summary.docx` | all the numbers, the comparison with the paper, the limitations | 30 min |
| 5 | `sample_transcript_proto20_paper_enhanced_2022-06-01.md` | one real AI committee meeting: what each AI "analyst" was asked and answered | 20 min |
| 6 | `proto20_problems_log.docx` | 24 problems we found and how we solved them; the best material for "how do you know it's right?" | 30 min |
| 7 | this briefing | AI usage, costs, and what changed from the student's version | 20 min |
| reference | `results.md` / `results.csv` | every number, for when someone asks for a detail | as needed |

**A suggested way to teach it** (about 4 sessions):
1. The question and the idea (recap, architecture picture).
2. How one month works (student guide sections 4 and 5, the sample meeting).
3. The results and what they mean (section 1 of this briefing, the summary, the charts).
4. How we know it's right (problems log, fairness checks), and rehearsing answers to the professor's questions (student guide section 9).

## 3. What to share with the student, and how to show the AI help honestly

**Share these with the student:**
- the whole `reports/proto20/` folder (Word files, pictures, sample meeting, results);
- the `docs/` folder;
- this briefing.

**Showing the work was done with AI help.** The professor wants to see that the student did real work with AI assistance. Our records already show how the project was built, step by step:

| evidence | where | what it shows |
|---|---|---|
| Decision records | `decisions.md`, `decisions_20.md` | every design choice, who made it and why (D1 to D55) |
| Build plan with ticks | `implementation_plan_20.md` | the phases P0 to P7, planned and then completed |
| Problems log | `docs/proto20_problems_log.md` | the real problems met along the way, and their fixes |
| Code history | the git branch (`git log`) | every change, dated, in order |
| AI committee records | the run folders (`runs/<run>/transcripts/`, `memos/`, `llm_inputs/`) | every question the AI agents were asked, and every answer |
| Cost ledger | `scripts/ledger_report.py` | every paid AI call, with its tokens and cost |

The student guide's last section, "Who did what", is deliberately left blank. **Please fill it in honestly with the student.** It should say what the mentor and the AI coding assistant built, and what the student studied, checked or rebuilt.

The strongest proof of understanding is for the student to redo one piece themselves. For example:
- recalculate the benchmark return by hand for one month in a spreadsheet;
- re-read one committee meeting and explain Otto's decision;
- reproduce one row of the problems log, such as the stock-split check.

**Visuals ready to use** (SVG pictures; in Word or PowerPoint use Insert > Pictures):

| picture | what it shows |
|---|---|
| `architecture.svg` | the 12 steps of one month, coloured by who does them: data, AI or Python |
| `growth_of_1.svg` | how $1 grew from 2021 to 2023 for the AI versions, the benchmark, QQQ and the NASDAQ-100. The AI lines sit on top of the benchmark line, and that overlap *is* the finding |
| `active_return.svg` | each AI version's lead or lag against the benchmark over time; it never moves more than about ±1% |
| `growth_of_1.html` | the same growth chart as a web page |

Tables from the summary (results, view accuracy, comparison with the paper) can be copied straight from the Word files into slides.

## 4. How the AI agents were used

**Two kinds of AI call:**

| role | model | settings | per month | what it produces |
|---|---|---|---|---|
| Junior analyst (research memo) | Claude Haiku 5.5, small and cheap | effort low; up to 1,500 output tokens; 4 run at the same time | 20 calls, one per company | a one-page memo: outlook, key points, risks |
| Committee (Emily, Bob, Dave, Otto draft, Otto final) | Claude Sonnet 5.5, stronger | effort medium; thinking off; up to 6,000 output tokens | 5 calls, one after another | a view on each of the 20 companies (and, in the enhanced version, a rating and confidence) |

**Rules for every call:**
- No "temperature" or other randomness settings are sent. The API doesn't accept them, and leaving them out keeps runs comparable.
- Every answer must fit a fixed format, which is checked by code. A bad answer is asked again once; after that the company gets "no opinion" and keeps its benchmark weight. In the final runs, no answer failed.
- **The AI never calculates.** Python computes every number the AI reads, every weight and every result.
- A ledger records every call and stops automatically before the budget limit.

**Every run that cost money:**

| run | purpose | paid calls | free (cached) answers | cost | time |
|---|---|---:|---:|---:|---:|
| `memo_check` | first test of memos on 3–5 companies | 8 | 13 | $0.005 | 7 min |
| `pilot_base_dev` | first full committee test (5 companies × 3 months) | 51 | 74 | $0.049 | 59 min (incl. a fix and rerun) |
| `proto20_2021_base_dev` | baseline on 2021 only, cheap models | 297 | 303 | $0.272 | 21 min |
| `pilot_enh_dev` | enhanced version test | 26 | 34 | $0.024 | 14 min |
| `pilot_enh_hidden_dev` | names-hidden test (leak scan) | 30 | 0 | $0.021 | 1.5 min |
| `proto20_2021_enh_dev` | enhanced on 2021, cheap models | 60 | 240 | $0.133 | 10 min |
| `thinking_off_pilot` / `thinking_on_pilot` | does "thinking longer" help the committee? | 15 + 15 | 15 + 15 | $0.245 + $0.245 | 2 + 2 min |
| **`proto20_paper_baseline`** | **final baseline, 36 months** | 660 | 240 | **$7.96** | 52 min |
| **`proto20_paper_enhanced`** | **final enhanced, 36 months** | 180 | 720 | **$8.14** | 43 min |
| **`proto20_paper_enh_hidden`** | **final names-hidden, 36 months** | 900 | 0 | **$8.47** | 58 min |
| **Total** | | **2,242** | **1,654** | **$25.57** (Rs 2,250) | about 4.5 hours |

**Why a final run takes about an hour:** each of the 36 months needs 20 memos (4 at a time) and then 5 committee calls in order, because each member reads the one before. That is about 1.5 minutes a month.

**Tokens used**, where a token is about ¾ of a word:

| kind of token | total | what it is |
|---|---:|---|
| new input | 8.2 million | text sent fresh |
| cache write | 3.7 million | text sent once and stored for re-use (costs a little extra) |
| cache read | 17.5 million | stored text re-used (costs about a tenth of the normal price) |
| output | 4.2 million | text the AI wrote |

63% of all input was read from the cache at the reduced price: 69% for the committee and 53% for the memos.

**How we kept the cost down without changing the results:**
1. **Prompt caching.** The committee's briefing (about 22,000 tokens, roughly 16,000 words) is sent once a month and re-read by the other four members at about a tenth of the price. This needed a fix: all five members had to share one answer format (problems log #12). It saved about 40% of the committee cost, about $8 across the final runs. The AI reads exactly the same text, so the answers are unaffected.
2. **Saved answers (response cache).** An identical question gets the stored answer for free:
   - the enhanced run reused all 720 of the baseline's memos (same memos, so a fairer comparison) and paid only for its 180 committee calls;
   - the baseline reused the 240 memos from the 2021 test.

   The names-hidden run had to pay for everything, because its memos read differently (codes instead of names).
3. **The right model for each job.** The cheap model writes the 720 memos per run; the stronger model makes only the 180 decisions. We did not test whether better memos would change the results; that is a possible future check.
4. **Thinking off.** A pilot ran the committee with and without extra "thinking": same cost to the cent and the same answers. So it stayed off, with no loss.
5. **Short, structured answers.** Reasons are capped at about 25 words, and the answers are tables rather than essays.
6. **Monthly, not weekly, decisions**, with cheap pilots before every paid run and a budget stop at $32 of $40.

For comparison, the paper reports about $180 for its own 3-year run (weekly, GPT-4o). Our three final runs cost about $8 each.

## 5. What we improved over the student's version

We reviewed the student's notebook (`QuantAgents_v17_fixeddata.ipynb`) and the professor's README on 6 Nov 2026. We kept its good ideas, including the persona descriptions and two of its indicators (ADX and relative volume). We changed the parts that would make a backtest unreliable or unsafe:

| in the student's version | the problem | what we did |
|---|---|---|
| API keys (Perplexity, Alpaca) written into the notebook | anyone with the file can spend on those accounts | keys live only in a private `.env` file that is never shared or committed. **The old keys should be revoked** |
| Research by AI web search, with "assume today's date is …" | web search returns *today's* news, so the backtest "knows the future" (look-ahead bias) | one point-in-time data gateway: every news item, filing and price carries its publication time, and anything later is refused. Tests try to break it |
| Asking the AI for the list of NASDAQ-100 companies | it returns *today's* members (look-ahead and survivorship bias) | the 20 companies are chosen by a fixed rule from stored 2021 data, and the choice was re-checked with a database cut at that date |
| The AI produced dollar amounts, price targets, stop-losses, risk (VaR) numbers | language models make arithmetic mistakes | Python computes all numbers; the AI only gives opinions in a fixed format |
| `temperature` setting | rejected by the current API; runs not repeatable | removed; saved answers make every run exactly repeatable |
| No fair benchmark | beating "the market" with 20 winners proves nothing | the benchmark is the same 20 companies at market weight; QQQ and the NASDAQ-100 are shown for reference only |
| Weekly runs on a large model | costly (the paper: about $180) | monthly runs, a model per job, prompt caching: about $8 a run, with a ledger and an automatic budget stop |

**Added on top:**
- Data cleaning with checks: stock splits, foreign share ratios, a risk-free rate series. Each one was found by comparing against known facts (problems log #1–#9).
- Portfolio rules enforced by Python (0× to 2× per stock, sectors within ±2 points) and a realistic trading simulator (next-day prices, 0.1% cost).
- The paper's ideas rebuilt safely:
  - Bob's "simulated trading" (Python tests simple strategies on past data only);
  - Dave's risk score;
  - the committee's own track record (only results already known at the time).
- Two ways of turning opinions into weights (simple multipliers, and Black-Litterman with a risk budget), and a names-hidden control.
- Honest statistics: uncertainty intervals, factor-adjusted alpha, automatic "too good to be true" red flags.
- 456 automated tests, and a full written trail (decisions, plan, problems log, student guide).

**What to tell the student:** "Your version showed the idea could be built. Ours makes the test trustworthy: no future information, no AI arithmetic, a fair benchmark and honest statistics. That is why our result is believable, even though it is modest."
