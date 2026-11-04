// Builds docs/QuantAgents_Client_Requirements.docx.  Usage: node scripts/build_client_requirements.js docs/QuantAgents_Client_Requirements.docx  (needs the npm "docx" package)
const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType,
  ShadingType, AlignmentType, LevelFormat, HeadingLevel, BorderStyle, Footer, PageNumber,
} = require('docx');

const FONT = 'Arial';
const W = 9638; // A4 text width with 2 cm margins (11906 - 2*1134)
const ACCENT = '1F4E79';
const border = { style: BorderStyle.SINGLE, size: 4, color: 'BFBFBF' };
const borders = { top: border, bottom: border, left: border, right: border };

const p = (text, opts = {}) => new Paragraph({
  spacing: { after: 120 },
  ...opts,
  children: (Array.isArray(text) ? text : [text]).map(t =>
    typeof t === 'string' ? new TextRun({ text: t }) : new TextRun(t)),
});
const h1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const h2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const bullet = (text) => new Paragraph({
  numbering: { reference: 'bullets', level: 0 }, spacing: { after: 60 },
  children: (Array.isArray(text) ? text : [text]).map(t =>
    typeof t === 'string' ? new TextRun({ text: t }) : new TextRun(t)),
});
const check = (text) => new Paragraph({
  numbering: { reference: 'checks', level: 0 }, spacing: { after: 80 },
  children: [new TextRun(text)],
});

function table(widths, rows, headerFill = ACCENT) {
  return new Table({
    width: { size: W, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((r, i) => new TableRow({
      tableHeader: i === 0,
      children: r.map((c, j) => {
        const isHead = i === 0;
        const cell = typeof c === 'object' && !Array.isArray(c) ? c : { text: c };
        return new TableCell({
          borders,
          width: { size: widths[j], type: WidthType.DXA },
          shading: isHead ? { fill: headerFill, type: ShadingType.CLEAR, color: 'auto' }
            : cell.fill ? { fill: cell.fill, type: ShadingType.CLEAR, color: 'auto' } : undefined,
          margins: { top: 60, bottom: 60, left: 100, right: 100 },
          children: String(cell.text).split('\n').map(line => new Paragraph({
            spacing: { after: 0 },
            children: [new TextRun({ text: line, bold: isHead || cell.bold, color: isHead ? 'FFFFFF' : undefined, size: 19 })],
          })),
        });
      }),
    })),
  });
}

const PAID = 'FCE4D6', FREE = 'E2EFDA', OPT = 'FFF2CC';

// One block per requirement
function reqBlock(num, title, rows) {
  return [
    h2(`${num}. ${title}`),
    table([2300, W - 2300], [
      ['Item', 'Details'],
      ...rows.map(([k, v]) => [{ text: k, bold: true }, v]),
    ]),
    p(''),
  ];
}

const children = [
  new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun('QuantAgents: What We Need From You')] }),
  p([{ text: 'Requirements for the client (student and professor)', italics: true, color: '595959' }]),
  p([{ text: 'Updated 5 November 2026 (staged funding)  ·  Review package due 15 January 2027  ·  Poster: UT Dallas Biz AI Conference, March 2027', size: 19, color: '595959' }]),

  h1('1. Why this document'),
  p('QuantAgents is a research project: a team of AI agents manages a simulated NASDAQ-100 portfolio, replayed month by month from 2015 to 2023 using only information available at each date. No real money is invested and nothing is traded.'),
  p('To build and run it, the developer needs a few accounts, keys and decisions from you. This document lists each one, why the project needs it, when it is needed, and whether it costs money.'),
  p([{ text: 'Short answer on cost: ', bold: true }, 'the only required item that costs money is the Anthropic API credit: up to $150 in total, released in stages, and each stage only after the previous one shows working results. The first request is about $20, in week 3. Everything else is free. A paid market-data subscription is optional.']),

  h1('2. Summary'),
  table([2900, 2700, 1600, 2438], [
    ['What we need', 'Used for', 'Needed by', 'Cost'],
    ['Anthropic API key with prepaid credit, in stages', 'All AI agent calls: pilot, then the full backtests', 'Stage 1 ~week 3 (~$20); Stage 2 after an approved forecast (~$80–90)', { text: 'PAID: up to $150 in total (≈ ₹13,200), in stages', fill: PAID }],
    ['Alpaca account (API key + secret)', 'Historical news for each stock, 2015–2023', 'Week 1', { text: 'Free', fill: FREE }],
    ['Name + contact email for SEC access', 'Company financials from SEC EDGAR', 'Week 1', { text: 'Free', fill: FREE }],
    ['Answer: WRDS / CRSP access at UT Dallas?', 'Accurate prices of companies that left the index', 'Week 1', { text: 'Free via university, if available', fill: FREE }],
    ['Decision: paid historical dataset? (optional)', 'More accurate index membership and delisted prices', 'Week 1', { text: 'OPTIONAL: vendor price', fill: OPT }],
    ['Professor confirms the success measure', 'Deciding what counts as "the AI did better"', 'Week 4 (before full results)', { text: 'Free', fill: FREE }],
    ['Confirm default settings', 'Portfolio rules and view scoring', 'Week 3', { text: 'Free', fill: FREE }],
    ['Poster rules from the conference', 'Final poster layout', 'Week 8', { text: 'Free', fill: FREE }],
    ['Spend approvals', 'Go-ahead before each paid run', 'As each run comes up', { text: 'Free', fill: FREE }],
  ]),
  p(''),
  p([{ text: 'Colour key: ', bold: true }, { text: 'orange', bold: true, color: 'C55A11' }, ' = costs money, ', { text: 'yellow', bold: true, color: 'BF8F00' }, ' = optional cost, ', { text: 'green', bold: true, color: '548235' }, ' = free.']),

  h1('3. Items that cost money'),
  ...reqBlock('3.1', 'Anthropic API key with prepaid credit (required)', [
    ['What', 'An API key from the Anthropic Console (console.anthropic.com), on an account with prepaid credit. This is separate from any Claude Pro or Max subscription: a subscription does not cover API usage.'],
    ['Why the project needs it', 'Every "agent" in the system is a call to Claude through the API, billed per word-piece (token). Each month of the backtest, a fast model (Haiku 5.5) writes a one-page research memo on every index member (~100 stocks), then a stronger model (Sonnet 5.5) runs the committee meetings: fundamental analyst, quant analyst, risk manager and portfolio manager.'],
    ['Exactly why this amount', 'The project runs three full backtests of 108 months each (2015–2023): the baseline, the enhanced version, and a "names-hidden" version that checks the AI is not just remembering history. Planning estimates:\n• Baseline run: ~$16–20\n• Enhanced run: ~$22–26\n• Names-hidden run: ~$22–26\n• Development, pilots and checks: ~$20–30\nTotal expected ~$100–110. The $150 cap leaves a safety margin.'],
    ['How spend is controlled', '• Every call is logged with its cost; the system stops itself when a run budget is reached.\n• A response cache means rerunning anything already done costs $0.\n• You approve each paid run in advance, with a cost estimate.\n• Before the first full run we measure real costs on small tests and send you an exact forecast.'],
    ['Funded in stages', 'We never ask for money ahead of evidence. Each stage is requested only after the previous one shows working output, with a short report: what was built, proof it works, what was spent, and the forecast for the next stage.\n• Stage 0 (now): developer\'s own key, ₹300. Builds and proves the whole system on small tests. No cost to you.\n• Stage 1 (~week 3): ~$20. A small pilot with the stronger model, and a first test run.\n• Stage 2 (after you approve a cost forecast, accurate to ±20%): ~$80–90. The three full 2015–2023 backtests.\n• Contingency (only if the forecast shows a need, and only with your approval): the rest, up to $150 in total.'],
    ['What the money buys', 'Test runs, not outcomes. We promise a fair, reproducible comparison. We do not promise that the AI beats the index. Whatever the result, you receive the working system, the baseline vs. NASDAQ-100 results, the AI decision transcripts, the poster materials and the handoff documents. If the enhancement does not outperform, that is reported honestly with an analysis of why.'],
    ['Cost', 'Up to $150 in total (about ₹13,200 at ₹88 per $1; plus any bank or tax charges), released stage by stage. Anthropic credits are prepaid, so spend cannot go above what is loaded.'],
    ['Needed by', 'Stage 1 (~$20) around week 3; Stage 2 (~$80–90) after the cost forecast is shared and approved. Until then the developer builds and tests on a personal key limited to ₹300.'],
    ['Suggested setup', '1. Create a dedicated Workspace in the Console, e.g. "QuantAgents".\n2. Load only the approved stage\'s credit (e.g. $20 for Stage 1) and set the workspace spend limit to the total approved so far, never above $150.\n3. Create one API key named "quantagents".\n4. Top up when the next stage is approved. You can revoke the key when the project ends.'],
  ]),
  ...reqBlock('3.2', 'Paid historical stock dataset (optional)', [
    ['What', 'A dataset with (a) the exact list of NASDAQ-100 members on every date and (b) daily prices for companies that were later acquired or delisted. Examples: Norgate Data, EODHD, Tiingo, Sharadar. Prices vary; ask the vendor for a quote.'],
    ['Why it matters', 'If we test only today\'s survivors, results look better than they really were ("survivorship bias"). The free price source (Yahoo Finance) often has no data for companies that left the index.'],
    ['Default if you say no', 'We rebuild the membership list for free from public records (Wikipedia change history cross-checked with Nasdaq\'s yearly announcements), and use Yahoo Finance for prices. Any company with no price data is left out on that date and logged, and we report how much of the index this affects. This is a stated limitation on the poster.'],
    ['Free alternative to check first', 'If UT Dallas gives the student WRDS access (CRSP database), it covers delisted prices to research standard at no cost. Please check with the university library.'],
    ['Cost', 'Optional. Vendor price, if chosen. $0 if we use the free default or WRDS.'],
    ['Needed by', 'Week 1. This decision affects the first data download.'],
  ]),

  h1('4. Free items (accounts and information)'),
  ...reqBlock('4.1', 'Alpaca account: API key ID and secret key', [
    ['What', 'A free account at alpaca.markets, then an API key ID and secret from its dashboard. A paper-trading (simulated) account is enough. No deposit and no trading needed. Please confirm when signing up that the free plan includes historical news.'],
    ['Why the project needs it', 'The agents read news about each company. Alpaca provides historical news headlines and summaries from 2015 with exact publish times.'],
    ['Exactly why it must be timestamped', 'A core rule is "no peeking at the future": news published after the 4 pm New York market close may only be used from the next trading day. Without precise publish times, the backtest could use news before it existed and overstate results.'],
    ['Cost', 'Free.'],
    ['Needed by', 'Week 1. News takes the longest to download.'],
  ]),
  ...reqBlock('4.2', 'Name and contact email for SEC EDGAR access', [
    ['What', 'A name and contact email, e.g. "QuantAgents research, student@utdallas.edu". This is not an account or a password.'],
    ['Why the project needs it', 'Company financials (revenue, margins, earnings, debt, shares outstanding) come from SEC EDGAR, the US government filing system. The SEC requires every automated download to identify who is making it.'],
    ['Exactly why SEC and not another source', 'EDGAR records the exact time each filing was accepted, so each figure is used only from the day it became public, not the end of the quarter it describes. Shares outstanding from filings are also used to compute each stock\'s index weight.'],
    ['Cost', 'Free.'],
    ['Needed by', 'Week 1.'],
  ]),
  h2('4.3 Free data that needs nothing from you'),
  p('Listed for transparency; the developer downloads these directly:'),
  bullet([{ text: 'Yahoo Finance: ', bold: true }, 'daily prices, plus the QQQ fund and the NASDAQ-100 index (^NDX) as benchmarks.']),
  bullet([{ text: 'FRED (US Federal Reserve): ', bold: true }, '3-month Treasury bill rate, used as the "risk-free" return in risk-adjusted measures.']),
  bullet([{ text: 'Kenneth French Data Library: ', bold: true }, 'standard academic factors (market, size, value, momentum), used to check whether any outperformance is genuine skill.']),

  h1('5. Decisions and confirmations (free)'),
  ...reqBlock('5.1', 'Success measure: professor to confirm', [
    ['What we propose', 'The main measures are (1) information ratio against the NASDAQ-100: extra return per unit of deviation from the index; and (2) factor-adjusted alpha (Carhart 4-factor): return not explained by market, size, value or momentum. Sharpe ratio, Sortino ratio and maximum drawdown are reported alongside.'],
    ['Why it must be agreed first', 'Agreeing the measure before seeing results prevents choosing whichever number looks best afterwards. That matters for an honest research poster.'],
    ['Needed by', 'Week 4, before any full-run results are produced. All measures are computed either way.'],
  ]),
  ...reqBlock('5.2', 'Confirm default settings (or tell us your values)', [
    ['Sector band', 'Each sector\'s weight stays within ±2 percentage points of its weight in the index. This keeps the portfolio comparable to the NASDAQ-100, so results are not just a sector bet.'],
    ['Rating scale', 'For the enhanced version, analyst ratings map to expected 3-month returns relative to the index: strong sell −6%, sell −3%, hold 0%, buy +3%, strong buy +6%.'],
    ['Index weights', 'Computed from company size (shares × price), without Nasdaq\'s exact capping rules. We check this against the QQQ fund and report the difference.'],
    ['Needed by', 'Week 3. All are adjustable later in a settings file.'],
  ]),
  ...reqBlock('5.3', 'Poster rules from the conference', [
    ['What', 'Poster size, template, file format and submission deadlines from the UT Dallas Biz AI Conference.'],
    ['Why', 'So the charts and tables are produced at the right size and layout.'],
    ['Needed by', 'Week 8.'],
  ]),
  ...reqBlock('5.4', 'Spend approvals', [
    ['What', 'A quick "go ahead" message before each paid run. Each request includes the estimated cost.'],
    ['Why', 'Keeps the API spend within the agreed budget, with no surprises.'],
    ['Needed by', 'Whenever a paid run is ready (mostly weeks 4–7).'],
  ]),

  h1('6. Already covered by the developer (no action needed)'),
  bullet('Laptop, storage and software setup.'),
  bullet('A personal Anthropic key (limited to ₹300) for development and small tests, until your key arrives. Swapping in your key needs no code changes, and work already done carries over at no extra cost.'),
  bullet('All programming, testing, documentation, poster figures and the final handoff documents.'),

  h1('7. How to share keys safely'),
  bullet('Please do not paste keys into email, WhatsApp, Slack or documents. Anyone who sees a key can spend the credit on it.'),
  bullet('Best: share through a password manager\'s secure-share feature (e.g., Bitwarden Send or 1Password), set to expire after one view, or enter the key directly into the project settings file on the developer\'s laptop.'),
  bullet('Keys are stored only in a private settings file (".env") that is never uploaded to GitHub or written to logs.'),
  bullet('You can revoke or rotate any key at any time from the provider\'s dashboard.'),

  h1('8. Checklist'),
  p('Tick each item when sent or decided:'),
  check('Week 1: Alpaca API key ID and secret (shared securely)'),
  check('Week 1: Name and contact email for SEC access'),
  check('Week 1: Does the student have WRDS / CRSP access at UT Dallas? (yes / no)'),
  check('Week 1: Paid historical dataset? (no, use free default / yes, which vendor)'),
  check('Week 3: Default settings confirmed (sector band ±2 pp, rating scale, index weights)'),
  check('~Week 3: Stage 1 approved: Anthropic API key with ~$20 credit and a matching spend limit (shared securely)'),
  check('After the cost forecast: Stage 2 approved (~$80–90 top-up)'),
  check('Week 4: Professor confirms the success measure'),
  check('Week 8: Conference poster rules'),
  p(''),
  p([{ text: 'Total required spend: ', bold: true }, 'up to $150 of Anthropic API credit (≈ ₹13,200) in total, released in stages after evidence: ~$20 first, then ~$80–90 after an approved forecast, and a contingency only if needed. Everything else is free unless you choose a paid dataset.']),
];

const doc = new Document({
  creator: 'QuantAgents',
  title: 'QuantAgents: What We Need From You',
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: 'Title', name: 'Title', basedOn: 'Normal', next: 'Normal', run: { font: FONT, size: 40, bold: true, color: ACCENT }, paragraph: { spacing: { before: 0, after: 120 }, keepNext: true } },
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: FONT, size: 30, bold: true, color: ACCENT }, paragraph: { spacing: { before: 300, after: 120 }, keepNext: true, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: FONT, size: 24, bold: true, color: '2E2E2E' }, paragraph: { spacing: { before: 200, after: 100 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  numbering: {
    config: [
      { reference: 'bullets', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
      { reference: 'checks', levels: [{ level: 0, format: LevelFormat.BULLET, text: '☐', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] },
    ],
  },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: 'QuantAgents client requirements  ·  page ', size: 16, color: '808080' }), new TextRun({ children: [PageNumber.CURRENT], size: 16, color: '808080' })] })] }) },
    children,
  }],
});

Packer.toBuffer(doc).then(b => { fs.writeFileSync(process.argv[2], b); console.log('written'); });
