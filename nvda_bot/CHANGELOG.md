# Changelog

## [1.1.0] - 2026-03-17

### Added
- Real-time trade monitoring for NVDL (2x Long ETF)
- Real-time trade monitoring for NVD (2x Short ETF)
- Live price tracking with `handle_nvdl_trade()` and `handle_nvd_trade()` handlers
- Periodic logging every 30 seconds showing current prices and P&L
- Highest/lowest price tracking since entry
- Instant profit target detection using live prices (no polling delay)

### Changed
- Profit target checking now uses live trade prices instead of position polling
- Updated subscription model to include three streams:
  1. NVDA bars (entry signals)
  2. NVDL trades (long position monitoring)
  3. NVD trades (short position monitoring)

### Improved
- Architecture now consistent with MSOS bot (both use live trades)
- Faster profit target detection (real-time vs 1-2 second polling)
- Better visibility with periodic P&L updates
- More accurate stop loss awareness

### Technical Details
- Added `nvdl_current_price` and `nvd_current_price` state variables
- Added `should_log_periodic_update()` method for 30-second logging
- Modified `check_profit_target()` to accept current price parameter
- Removed position polling from `handle_nvda_bar()` loop
- Golden Gap exit now also handled in trade handlers

## [1.0.0] - 2026-03-17

### Initial Release
- 15-minute Opening Range Breakout strategy
- NVDA monitoring for entry signals
- NVDL (2x Long) and NVD (2x Short) trading
- Position sizing for $300 max loss with 2x leverage
- Dual-stage exit system:
  - Stage 1: 1.5% hard stop loss
  - Stage 2: 3% profit → 1% trailing stop upgrade
  - Stage 3: Golden Gap exit at 2:00 PM CST
- Max 1 trade per day
- Comprehensive logging and error handling
- Paper trading enabled by default
