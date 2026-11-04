# Getting prices for delisted companies from WRDS (CRSP)

**Who:** the student, with a UT Dallas WRDS account (ask the UTD library for access to WRDS and the CRSP database).
**Why:** 43 companies that were NASDAQ-100 members in 2014–2023 have no price history on Yahoo Finance (they were acquired, merged or taken private). Without them the backtest has survivorship bias. See decision D26 in `decisions.md`.
**Cost:** free with university access. Download size is small (a few MB).

## What to download

CRSP **daily stock file**, 1 January 2014 to 30 April 2024, for the companies below.

WRDS currently offers CRSP in two layouts. Use whichever your account shows; the names differ slightly:

| What we need | Classic layout ("CRSP Daily Stock File", `dsf`) | New layout ("CRSP Stock – Version 2 / CIZ", `dsf_v2`) |
|---|---|---|
| Permanent id | `PERMNO` | `PERMNO` |
| Date | `DATE` | `DlyCalDt` |
| Ticker, company name | `TICKER`, `COMNAM` (from the names file) | `Ticker`, `IssuerNm` |
| Open, high, low, close | `OPENPRC`, `ASKHI`, `BIDLO`, `PRC` | `DlyOpen`, `DlyHigh`, `DlyLow`, `DlyPrc` |
| Volume | `VOL` | `DlyVol` |
| Total return, return without dividends | `RET`, `RETX` | `DlyRet`, `DlyRetx` |
| Shares outstanding | `SHROUT` | `ShrOut` |
| Price / share adjustment factors | `CFACPR`, `CFACSHR` | `DlyFacPrc` |
| **Delisting**: date, code, return | `DLSTDT`, `DLSTCD`, `DLRET` (delisting file) | `DelistingDt`, `DelReasonType`, `DlyDelFlg` / delisting return |

Steps (classic layout; the new layout is similar):
1. WRDS → **CRSP** → **Stock / Security Files** → **Daily Stock File**.
2. Date range: `2014-01-01` to `2024-04-30`.
3. Company codes: choose **TICKER** and paste the ticker list below (or upload it as a text file, one per line). Tickers are reused over the years, so if a ticker matches two companies, keep the one whose name matches the table below.
4. Tick the variables in the table above. If offered, also tick the **delisting information**.
5. Output: **comma-delimited (.csv)**, dates as `YYYY-MM-DD`.
6. Save the file to `D:\CreatED-Quant\qa_store\manual_prices\crsp_daily.csv` and tell the dev chat. The importer that splits it into the project's format is written once the file exists, so it matches exactly what WRDS gives.

## The 43 companies

| Ticker | Company (for orientation) | Ticker | Company (for orientation) |
|---|---|---|---|
| ALTR | Altera | LLTC | Linear Technology |
| ALXN | Alexion Pharmaceuticals | LMCK | Liberty Media (Series C) |
| ANSS | Ansys | MXIM | Maxim Integrated |
| ATVI | Activision Blizzard | MYL | Mylan |
| BBBY | Bed Bath & Beyond | QRTEA | Qurate Retail (Series A) |
| BRCM | Broadcom Corporation (the pre-2016 company) | QVCA | Liberty Interactive QVC Group (Series A) |
| CA | CA Technologies | SGEN | Seagen |
| CELG | Celgene | SHPG | Shire (ADR) |
| CERN | Cerner | SIAL | Sigma-Aldrich |
| CTRX | Catamaran | SNDK | SanDisk |
| CTXS | Citrix Systems | SPLK | Splunk |
| DISCA | Discovery Communications (Series A) | SPLS | Staples |
| DISH | DISH Network | SRCL | Stericycle |
| DTV | DirecTV | TFCF | Twenty-First Century Fox (Class B) |
| EA | Electronic Arts | TFCFA | Twenty-First Century Fox (Class A) |
| ENDP | Endo International | VIA | Viacom (Class A) |
| ESRX | Express Scripts | VIAB | Viacom (Class B) |
| GMCR | Keurig Green Mountain | WBA | Walgreens Boots Alliance |
| HOLX | Hologic | WBD | Warner Bros. Discovery |
| KRFT | Kraft Foods Group | WFM | Whole Foods Market |
| | | WLTW | Willis Towers Watson |
| | | XLNX | Xilinx |
| | | YHOO | Yahoo |

The company names are for orientation only; the authoritative list is `D:\CreatED-Quant\qa_store\raw\prices\missing.csv` on the laptop (it may shrink after the WLTW→WTW and QVC Group alias fixes).
