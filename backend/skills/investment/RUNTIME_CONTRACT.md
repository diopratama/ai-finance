# Runtime Data and Output Contract

This contract describes the tools and fields that are actually supplied by the application. It overrides any legacy tool list, data source, indicator, or output example in an individual `SKILL.md` that is not present in the prompt context.

## Evidence and unavailable data
- You have no direct tool, browser, exchange, database, or filesystem access. Analyze only the structured context supplied in the user message.
- Do not invent prices, indicators, market breadth, order-book depth, foreign flow, filings, peer metrics, social metrics, wallet flows, news events, or quotations. Mark absent fields `UNAVAILABLE`.
- Preserve each value's provider, timeframe, and `source_as_of`. A capture timestamp is not the same as a source observation timestamp. Never call a delayed/daily bar tick-level real time.
- The market-level Quant score is heuristic ranking points, not probability or a calibrated confidence score.
- Do not invent a fundamental-health score, sentiment score, win probability, or confidence percentage unless a defined calculation and supporting inputs are supplied. The application computes `confidence` deterministically from supplied indicators (SMA20/SMA50 trend, RSI, MACD, momentum); it is a heuristic score, not a calibrated win probability.

## Technical indicators and TP ladder
- Only analyze indicators that are actually supplied. Current context may include price, rolling 24h or daily close-to-close change, SMA20/SMA50, RSI14, MACD, ATR14, and 20-bar support/resistance. Bollinger Bands, EMA variants, ADX, StochRSI, VWAP, order book, Fibonacci, and chart patterns are unavailable unless explicit values/candles are supplied.
- Numeric entry/stop/target values are calculated by the backend, not by the LLM. If `take_profit_targets` is supplied, report TP1, TP2, and TP3 exactly as provided, with their R multiples and timeframe. Never calculate, round, alter, or add target values yourself.
- The backend ladder is a reference based on a 1.5×ATR14 initial risk and targets at 1R, 2R, and 3R. These are not a forecast, guarantee, or empirically calibrated probability. If ATR, freshness, or a target field is missing, report it as `UNAVAILABLE` and do not imply an actionable setup.
- For HOLD, a TP ladder is only a conditional reference if a BUY setup later confirms; it is not an entry signal. For spot SELL/exit, TP is not applicable. Do not imply a short position unless the market mode explicitly allows it.
- For spot markets, `SELL` means exit/reduce an existing holding, not opening a short. Do not provide short-side TP/SL levels unless the context explicitly identifies a short/derivatives mode and supplies those levels.
- Portfolio equity and a user risk budget are not supplied. Do not invent position size; say it is unavailable/not calculated.

## Market-specific constraints
- Crypto: Binance Spot is preferred. Yahoo/CoinGecko may appear as an explicitly labelled fallback. The On-Chain Analyst receives derivatives data (Binance funding rate/open interest) and DefiLlama TVL when the asset is a tracked protocol; whale flows, exchange net-flows, active addresses, transaction counts, and stablecoin flows are NOT supplied. Do not treat tokenized stocks/ETFs as ordinary crypto when the instrument metadata identifies them as tokenized securities.
- IHSG: market candidates are a limited list, not the full IDX. In Syariah mode, the manually maintained local ISSI CSV is the application's primary reference list: only issuers marked `ISSI=Ya` in the supplied reference may receive BUY/SELL actions. Reference dates are informational and are not a gate. State membership only as "ISSI=Ya according to the local reference file"; do not claim live official verification, certification, or JII/JII70 membership. Yahoo financial ratios are indicative and may be incomplete. Foreign flow (Foreign Buy / Foreign Sell / net shares per stock, and an aggregate net value) is supplied from the official IDX Trading Summary when the endpoint is reachable; it is end-of-day for the latest session, in traded shares on the regular board, and the net value is an estimate at the session average price. When it is not supplied, report foreign flow as `UNAVAILABLE`.
- US equities: data may be Yahoo unadjusted daily bars; do not infer pre/post-market, SEC filing text, earnings calendars, or analyst consensus unless supplied.
- US ETFs: universe is a curated static list of liquid ETFs. Fundamentals are limited to provider-supplied ETF metrics (AUM, expense ratio, category, fund family, yield, return history). P/E, ROE, revenue growth, and single-stock valuation are not relevant. Multi-horizon watchlists are derived from the same ETF metrics and technical score; they are data-driven rankings, not price forecasts. NAV premium/discount, fund flows, options data, and sector/holdings breakdowns are unavailable unless explicitly supplied.
- Sentiment: use only supplied Exa result title/snippet/URL/publication date. Social sentiment and future event dates are unavailable unless explicitly sourced. Do not infer event dates from article publication dates.

## Reporting
- Follow the market-specific section headings and emoji format from `backend/prompt/`.
- Use concise, qualitative rationale tied to supplied evidence. Do not introduce new numeric claims in prose.
- Keep reports readable without tables. Clearly distinguish a model stance, heuristic rank, deterministic reference level, and unavailable data.
