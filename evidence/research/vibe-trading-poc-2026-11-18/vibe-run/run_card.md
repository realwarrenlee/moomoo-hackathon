# Backtest Run Card

Generated: 2026-11-18T02:00:03.053089Z
Run directory: `C:\Users\Warren\Downloads\qoder trading challenge\evidence\research\vibe-trading-poc-2026-11-18\vibe-run`

## Backtest Summary
- codes: ['SPY', 'QQQ', 'IWM']
- start_date: 2025-05-29
- end_date: 2026-11-16
- interval: 1D
- engine: global_equity
- initial_cash: 100000.0
- source: moomoo_fixture

## Reproducibility
- config_hash: `33c59d594679a456b847aa26e8db29d582d5efabac46b7292bdbe8a02e782858`
- strategy_hash: `94f72e33fef767a813f66a3b8184e65b0367d52211c003869c0266b57fa0766a`

## Model provenance
- config.json: Unknown
- code/signal_engine.py: Unknown
- Training cutoff: Unknown

## Data Sources
- moomoo_fixture

## Metrics
- final_value: 100089.45874243704
- total_return: 0.0008945874243704299
- annual_return: 0.0006458682393446491
- max_drawdown: -0.012155503827850125
- sharpe: 0.05730273467929389
- calmar: 0.0531
- sortino: 0.0761
- win_rate: 0.2608695652173913
- profit_loss_ratio: 2.9432
- profit_factor: 1.0388
- max_consecutive_loss: 5
- avg_holding_days: 10.0
- trade_count: 23
- benchmark_return: 0.223148
- excess_return: -0.222253
- information_ratio: -1.0345
- tracking_error: 0.152453
- benchmark_beta: 0.0549
- avg_turnover: 0.006435
- total_turnover: 2.245658
- benchmark_kind: equal_weight
- benchmark_label: equal-weight basket of 3 symbols
- unfilled_plan_rejections: 0
- target_change_count: 45
- rebalance_executed_bars: 0
- rebalance_executed_fills: 0
- rebalance_realized_turnover: 0.0
- rebalance_turnover_mean: 0.04999999999999998
- rebalance_turnover_max: 0.05
- position_adjustment: hold
- rebalance_tolerance: 0.0
- dropped_target_adjustment_count: 0
- risk_xray_hhi: 0.33720215914358476
- risk_xray_effective_n: 2.9655800619419757
- risk_xray_annualized_vol: 0.1605781582013694
- risk_xray_max_drawdown: -0.09939279366741856
- risk_xray_avg_invested: 0.06639306274941431

## Structured metrics

Non-scalar metrics, which the `metrics` block cannot hold - carried so they can be inspected by key instead of only as a flattened count.

- unfilled_plan_rejections_by_symbol: {}
- execution_costs: {"commission_rate": 0.0, "market": "us_equity", "slippage_buy_rate": 0.00019999999999997797, "slippage_config_key": "slippage_us", "slippage_sell_rate": 0.00019999999999997797}
- by_symbol: {"IWM": {"avg_pnl": -10.19, "count": 7, "total_pnl": -71.36, "win_rate": 0.4286}, "QQQ": {"avg_pnl": -90.44, "count": 8, "total_pnl": -723.56, "win_rate": 0.125}, "SPY": {"avg_pnl": 110.55, "count": 8, "total_pnl": 884.38, "win_rate": 0.25}}
- by_exit_reason: {"signal": {"count": 23, "total_pnl": 89.46}}
- dropped_target_adjustments: []

## Validation
- Not present.

## Warnings
- benchmark 'none' could not be resolved over the evaluation window; benchmark-relative metrics use the equal-weight basket of 3 symbols
- No strategy model provenance was recorded for config.json; writer identity is unknown.
- No strategy model provenance was recorded for code/signal_engine.py; writer identity is unknown.
- Training cutoff for unknown model is unknown; assume results may reflect what the model remembers.

## Execution records
- backtest (ok): 2026-11-18T02:00:02.885231Z → 2026-11-18T02:00:03.050899Z; args sha256 `9f7d4ea823e01f535fcd7504496567e6c1c7e571ad45fc3b09ba116013959a74`, result sha256 `af00db0d795d23075a4ad624ebb90f41cdef35f26f45839b6d8c4fe72aaec721`

## Metric evidence
- final_value: `artifacts/metrics.csv`, column `final_value`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- total_return: `artifacts/metrics.csv`, column `total_return`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- annual_return: `artifacts/metrics.csv`, column `annual_return`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- max_drawdown: `artifacts/metrics.csv`, column `max_drawdown`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- sharpe: `artifacts/metrics.csv`, column `sharpe`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- calmar: `artifacts/metrics.csv`, column `calmar`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- sortino: `artifacts/metrics.csv`, column `sortino`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- win_rate: `artifacts/metrics.csv`, column `win_rate`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- profit_loss_ratio: `artifacts/metrics.csv`, column `profit_loss_ratio`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- profit_factor: `artifacts/metrics.csv`, column `profit_factor`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- max_consecutive_loss: `artifacts/metrics.csv`, column `max_consecutive_loss`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- avg_holding_days: `artifacts/metrics.csv`, column `avg_holding_days`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- trade_count: `artifacts/metrics.csv`, column `trade_count`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- benchmark_return: `artifacts/metrics.csv`, column `benchmark_return`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- excess_return: `artifacts/metrics.csv`, column `excess_return`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- information_ratio: `artifacts/metrics.csv`, column `information_ratio`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- tracking_error: `artifacts/metrics.csv`, column `tracking_error`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- benchmark_beta: `artifacts/metrics.csv`, column `benchmark_beta`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- avg_turnover: `artifacts/metrics.csv`, column `avg_turnover`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- total_turnover: `artifacts/metrics.csv`, column `total_turnover`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- benchmark_kind: `artifacts/metrics.csv`, column `benchmark_kind`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- benchmark_label: `artifacts/metrics.csv`, column `benchmark_label`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- unfilled_plan_rejections: `artifacts/metrics.csv`, column `unfilled_plan_rejections`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- target_change_count: `artifacts/metrics.csv`, column `target_change_count`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- rebalance_executed_bars: `artifacts/metrics.csv`, column `rebalance_executed_bars`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- rebalance_executed_fills: `artifacts/metrics.csv`, column `rebalance_executed_fills`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- rebalance_realized_turnover: `artifacts/metrics.csv`, column `rebalance_realized_turnover`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- rebalance_turnover_mean: `artifacts/metrics.csv`, column `rebalance_turnover_mean`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- rebalance_turnover_max: `artifacts/metrics.csv`, column `rebalance_turnover_max`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- position_adjustment: `artifacts/metrics.csv`, column `position_adjustment`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- rebalance_tolerance: `artifacts/metrics.csv`, column `rebalance_tolerance`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- dropped_target_adjustment_count: `artifacts/metrics.csv`, column `dropped_target_adjustment_count`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- risk_xray_hhi: `artifacts/metrics.csv`, column `risk_xray_hhi`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- risk_xray_effective_n: `artifacts/metrics.csv`, column `risk_xray_effective_n`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- risk_xray_annualized_vol: `artifacts/metrics.csv`, column `risk_xray_annualized_vol`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- risk_xray_max_drawdown: `artifacts/metrics.csv`, column `risk_xray_max_drawdown`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`
- risk_xray_avg_invested: `artifacts/metrics.csv`, column `risk_xray_avg_invested`, data row 1, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`

## Artifacts
- `artifacts/equity.csv` (43381 bytes, sha256 `9ce9a070f756e84a6d47aac5b90cf3ca2dd6b39e0a68e24d4958deb0dbd8cda8`)
- `artifacts/fills.jsonl` (11970 bytes, sha256 `df709e75fa25b4b7d928ff92780d007d96edbb4e8ca045b670b704d699ccf8a2`)
- `artifacts/metrics.csv` (1100 bytes, sha256 `a36c0a5b6fdb9ff2135149a166c124c72a7d48d310d7f310e17556d489640545`)
- `artifacts/ohlcv_IWM.csv` (24144 bytes, sha256 `b3324d15aba46a651ba9a2e0ddf42dacef37bfb2a961c5dbb70ce64520ec028d`)
- `artifacts/ohlcv_QQQ.csv` (23921 bytes, sha256 `08fef4639d35039f9ca41527a15409c7130f791bccdfdb12306ff0895b79aedf`)
- `artifacts/ohlcv_SPY.csv` (23762 bytes, sha256 `7e228a996029fa6d22d5cfb7a013ff9bc61fa4002b2db717a32fb6297d8489aa`)
- `artifacts/positions.csv` (17278 bytes, sha256 `e90391bbd2885d7495029680968c8052ff9bf3a588ebdb411e1c3c3485f200a5`)
- `artifacts/rebalance_notes.json` (15706 bytes, sha256 `d167aca3590a30dac7163c7b271843aa3add5d5f2935a99be7414d5d60a9f370`)
- `artifacts/rebalance_notes.md` (4054 bytes, sha256 `7793df0d4895554b0ff8bb132a3db6329685de25348e146e5609cc69cba03dd8`)
- `artifacts/risk_xray.json` (1699 bytes, sha256 `296fc3667233c2250d7ed6cd21304420d08950ec0205419ec0dc707f884d91e1`)
- `artifacts/risk_xray.md` (375 bytes, sha256 `c2bccbfe9b9c285e718a8af1e0b9521d3aec8d3aa035c9fa4e7bba41e4de77bb`)
- `artifacts/target_positions.csv` (13634 bytes, sha256 `1909637b6c6f078beb4f6b1823001bf5c5e62a178461e85486a93b32c99f7364`)
- `artifacts/trades.csv` (3282 bytes, sha256 `a25f353b42237d9304de28853814dd24d75fef3da18e8d7c2df9c24102a57872`)
- `code/signal_engine.py` (1295 bytes, sha256 `94f72e33fef767a813f66a3b8184e65b0367d52211c003869c0266b57fa0766a`)
- `config.json` (422 bytes, sha256 `33c59d594679a456b847aa26e8db29d582d5efabac46b7292bdbe8a02e782858`)
