# Backtest Run Card

Generated: 2026-11-18T01:47:36.501553Z
Run directory: `C:\Users\Warren\Downloads\qoder trading challenge\evidence\research\vibe-trading-poc-2026-11-18\protocol-runs\exposure_matched_spy`

## Backtest Summary
- codes: ['AAPL', 'AMD', 'AMZN', 'AVGO', 'COST', 'GOOGL', 'HD', 'JNJ', 'JPM', 'MA', 'META', 'MSFT', 'NFLX', 'NVDA', 'PG', 'TSLA', 'UNH', 'V', 'WMT', 'XOM', 'SPY']
- start_date: 2015-01-02
- end_date: 2024-12-31
- interval: 1D
- engine: global_equity
- initial_cash: 100000.0
- source: moomoo_protocol_2015_2024

## Reproducibility
- config_hash: `edcb940e6bb8a2a4caefd07fa89726be1f7e849627fef8a2ad44187f80f81bfa`

## Model provenance
- config.json: Unknown
- Training cutoff: Unknown

## Data Sources
- moomoo_protocol_2015_2024

## Metrics
- final_value: 120471.32603242314
- total_return: 0.20471326032423143
- annual_return: 0.02094643026992027
- max_drawdown: -0.030863456934334982
- sharpe: 0.8668400278060064
- calmar: 0.6787
- sortino: 1.1903
- win_rate: 0.7528089887640449
- profit_loss_ratio: 0.7432
- profit_factor: 2.2633
- max_consecutive_loss: 3
- avg_holding_days: 14.0
- trade_count: 178
- benchmark_return: 9.120467
- excess_return: -8.915753
- information_ratio: -1.3268
- tracking_error: 0.194529
- benchmark_beta: 0.0625
- avg_turnover: 0.009905
- total_turnover: 22.425192
- benchmark_kind: equal_weight
- benchmark_label: equal-weight basket of 21 symbols
- unfilled_plan_rejections: 0
- rebalance_bars_executed: 470
- target_change_count: 610
- rebalance_executed_bars: 194
- rebalance_executed_fills: 194
- rebalance_realized_turnover: 9.48961008672309
- rebalance_turnover_mean: 0.11016393442622954
- rebalance_turnover_max: 0.15000000000000002
- position_adjustment: rebalance
- rebalance_tolerance: 0.0
- dropped_target_adjustment_count: 0
- risk_xray_hhi: 1.0
- risk_xray_effective_n: 1.0
- risk_xray_annualized_vol: 0.17838290129955042
- risk_xray_max_drawdown: -0.337173884337483
- risk_xray_avg_invested: 0.14243793437067243

## Structured metrics

Non-scalar metrics, which the `metrics` block cannot hold - carried so they can be inspected by key instead of only as a flattened count.

- unfilled_plan_rejections_by_symbol: {}
- execution_costs: {"commission_rate": 0.0, "market": "us_equity", "slippage_buy_rate": 0.00019999999999997797, "slippage_config_key": "slippage_us", "slippage_sell_rate": 0.00019999999999997797}
- by_symbol: {"SPY": {"avg_pnl": 115.01, "count": 178, "total_pnl": 20471.33, "win_rate": 0.7528}}
- by_exit_reason: {"end_of_backtest": {"count": 1, "total_pnl": -819.92}, "signal": {"count": 63, "total_pnl": 9980.87}, "target_rebalance": {"count": 114, "total_pnl": 11310.38}}
- dropped_target_adjustments: []
- _omitted: ["rebalance_mask"]

## Validation
- Not present.

## Warnings
- benchmark 'none' could not be resolved over the evaluation window; benchmark-relative metrics use the equal-weight basket of 21 symbols
- No strategy model provenance was recorded for config.json; writer identity is unknown.
- Training cutoff for unknown model is unknown; assume results may reflect what the model remembers.

## Execution records
- backtest (ok): 2026-11-18T01:47:28.889309Z → 2026-11-18T01:47:36.499252Z; args sha256 `868da5ff8ed4619a85c42e9114c3354d0a9e69adcd55c63cefd97a67425de605`, result sha256 `c987ef6ca7cfd04d5ddc06facc347a90336e6a17b765f2d06be39173f48a6c7b`

## Metric evidence
- final_value: `artifacts/metrics.csv`, column `final_value`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- total_return: `artifacts/metrics.csv`, column `total_return`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- annual_return: `artifacts/metrics.csv`, column `annual_return`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- max_drawdown: `artifacts/metrics.csv`, column `max_drawdown`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- sharpe: `artifacts/metrics.csv`, column `sharpe`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- calmar: `artifacts/metrics.csv`, column `calmar`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- sortino: `artifacts/metrics.csv`, column `sortino`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- win_rate: `artifacts/metrics.csv`, column `win_rate`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- profit_loss_ratio: `artifacts/metrics.csv`, column `profit_loss_ratio`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- profit_factor: `artifacts/metrics.csv`, column `profit_factor`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- max_consecutive_loss: `artifacts/metrics.csv`, column `max_consecutive_loss`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- avg_holding_days: `artifacts/metrics.csv`, column `avg_holding_days`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- trade_count: `artifacts/metrics.csv`, column `trade_count`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- benchmark_return: `artifacts/metrics.csv`, column `benchmark_return`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- excess_return: `artifacts/metrics.csv`, column `excess_return`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- information_ratio: `artifacts/metrics.csv`, column `information_ratio`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- tracking_error: `artifacts/metrics.csv`, column `tracking_error`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- benchmark_beta: `artifacts/metrics.csv`, column `benchmark_beta`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- avg_turnover: `artifacts/metrics.csv`, column `avg_turnover`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- total_turnover: `artifacts/metrics.csv`, column `total_turnover`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- benchmark_kind: `artifacts/metrics.csv`, column `benchmark_kind`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- benchmark_label: `artifacts/metrics.csv`, column `benchmark_label`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- unfilled_plan_rejections: `artifacts/metrics.csv`, column `unfilled_plan_rejections`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- rebalance_bars_executed: `artifacts/metrics.csv`, column `rebalance_bars_executed`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- target_change_count: `artifacts/metrics.csv`, column `target_change_count`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- rebalance_executed_bars: `artifacts/metrics.csv`, column `rebalance_executed_bars`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- rebalance_executed_fills: `artifacts/metrics.csv`, column `rebalance_executed_fills`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- rebalance_realized_turnover: `artifacts/metrics.csv`, column `rebalance_realized_turnover`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- rebalance_turnover_mean: `artifacts/metrics.csv`, column `rebalance_turnover_mean`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- rebalance_turnover_max: `artifacts/metrics.csv`, column `rebalance_turnover_max`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- position_adjustment: `artifacts/metrics.csv`, column `position_adjustment`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- rebalance_tolerance: `artifacts/metrics.csv`, column `rebalance_tolerance`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- dropped_target_adjustment_count: `artifacts/metrics.csv`, column `dropped_target_adjustment_count`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- risk_xray_hhi: `artifacts/metrics.csv`, column `risk_xray_hhi`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- risk_xray_effective_n: `artifacts/metrics.csv`, column `risk_xray_effective_n`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- risk_xray_annualized_vol: `artifacts/metrics.csv`, column `risk_xray_annualized_vol`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- risk_xray_max_drawdown: `artifacts/metrics.csv`, column `risk_xray_max_drawdown`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`
- risk_xray_avg_invested: `artifacts/metrics.csv`, column `risk_xray_avg_invested`, data row 1, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`

## Artifacts
- `artifacts/equity.csv` (276278 bytes, sha256 `6497eaf456cb71b2ba0ef2460cf173821dded69ffb3554b09f5e746ce275c3ee`)
- `artifacts/fills.jsonl` (92114 bytes, sha256 `9fcb96d97153f5f49bad493996d7e5a890949daf087ef506ecd3d41ab79ad923`)
- `artifacts/metrics.csv` (7730 bytes, sha256 `d9fc8c90c32279216311053b9f162c1d33c7c546d00eb3e9c0a65a13c3a10a35`)
- `artifacts/ohlcv_AAPL.csv` (225771 bytes, sha256 `f9b8f97c66304855b3e0dbf42651dd857310600a1a2bc85dfbd868e620b883ad`)
- `artifacts/ohlcv_AMD.csv` (151115 bytes, sha256 `8af66eff91b1bdccef324645d51bfd0be8ffda0e4bf9297e2f6c903178fdf495`)
- `artifacts/ohlcv_AMZN.csv` (166892 bytes, sha256 `c7d2ddbabf81111fb9660df3dad605c0689147f360c8b1296977e129312ec4a9`)
- `artifacts/ohlcv_AVGO.csv` (220392 bytes, sha256 `51849bc4a6e8897c2db17fb0b9b557a5ad9270e31e54c372fc01c5849a0f2a3e`)
- `artifacts/ohlcv_COST.csv` (227737 bytes, sha256 `33c1be3832a073e91b591487c495bd674e88dcd59ac650ac084fb4298d02df1d`)
- `artifacts/ohlcv_GOOGL.csv` (223566 bytes, sha256 `aec7ccda2b1046ad22e6ce237576ac0e5fb2d55eb26ea7610e0283691a9b4d56`)
- `artifacts/ohlcv_HD.csv` (226486 bytes, sha256 `d821e9faeadb93c3d85f27b59fa14c28061a8e73aec7d8b24c6c6831397db834`)
- `artifacts/ohlcv_JNJ.csv` (225389 bytes, sha256 `a5f42b96dd3c0fe3118f103d9bccdb257ca004f909f8353325710163fa4f598c`)
- `artifacts/ohlcv_JPM.csv` (224010 bytes, sha256 `268d1e423087e4adcdd8e1f9950e9d3dd6b8c7c2885e2096ed64add4f810a3c4`)
- `artifacts/ohlcv_MA.csv` (225590 bytes, sha256 `fe8947f3150a2bcdbd2260cf0bc0054b0aee92c82a0e4fbf4324a799938ea0de`)
- `artifacts/ohlcv_META.csv` (229301 bytes, sha256 `78c107f510f6cef9c037a8a6599b53ac1084451bddd5bd55f1a9a75ece598686`)
- `artifacts/ohlcv_MSFT.csv` (226468 bytes, sha256 `b35ce5405c0a723cdd9116a5f643c7b500ab995c99a3e629a53d994ce1490c9b`)
- `artifacts/ohlcv_NFLX.csv` (165199 bytes, sha256 `97f91c31ad7a0bdd883005d779d2d6f31198ff85ddbb188e3d513441112ca838`)
- `artifacts/ohlcv_NVDA.csv` (217908 bytes, sha256 `2c5c2ced92450ab2b42a1794b48b88a636da946bf980dc3e14acfc1988d8ad2d`)
- `artifacts/ohlcv_PG.csv` (223318 bytes, sha256 `5fd8747432a77097b1407dcee9661e987bc8d08faa275d00e8ceb62c050e6bad`)
- `artifacts/ohlcv_SPY.csv` (230981 bytes, sha256 `74750b948b8519279993b2553c71fe3befddaf8c2e0792c83f2912360a487ff2`)
- `artifacts/ohlcv_TSLA.csv` (197847 bytes, sha256 `d999a452d2d1ed974140a1eda06a431d87a0e7267317ee69f15ebda056017ff1`)
- `artifacts/ohlcv_UNH.csv` (226845 bytes, sha256 `0f27f2ef45076d20a5a201dcaaa14f1cd78968c4ec6e8be3c34c3a6aec701004`)
- `artifacts/ohlcv_V.csv` (225500 bytes, sha256 `8dd827c43513d7d7934a0e2bec546c73025281e82d831e56b4fe647d77cb89db`)
- `artifacts/ohlcv_WMT.csv` (220246 bytes, sha256 `f3cb5f9eb4cfd3e43ec3fff3b2fb050bf4c08281fce81f593bdf0f36123061b1`)
- `artifacts/ohlcv_XOM.csv` (220555 bytes, sha256 `ad07c7b483a4d44827c69c949608c526ca5b58071ddf4b4e4e992e5f5c77af79`)
- `artifacts/positions.csv` (274364 bytes, sha256 `2c60d0474d30af5f7872c8a3797f896aa622dd60813d8d4a91359d574df6b344`)
- `artifacts/rebalance_notes.json` (227322 bytes, sha256 `e50b607552aa90809713bc686a0a80d5b589b070cff6963cef22b39d7f183d98`)
- `artifacts/rebalance_notes.md` (52086 bytes, sha256 `258b87a590486b7dd9a5a248044366dfde620c9250d29e61128b37891cd40c0c`)
- `artifacts/risk_xray.json` (1491 bytes, sha256 `7424f212f1fc35978b763214ba3352f7c678c1b6d65348d90942dcbe6543040c`)
- `artifacts/risk_xray.md` (368 bytes, sha256 `f2c81a097ecbc710f81df1a39cf08928bda919a8bfc590d8480d8c2f32c33983`)
- `artifacts/target_positions.csv` (253789 bytes, sha256 `86a43f390e6691dbdb6378c5c59713e91026833700b5f4571b1fabe6a207568a`)
- `artifacts/trades.csv` (28849 bytes, sha256 `a6132b20ed799938f764fbb1e7ed48052e4dc4fd7f6f56c3a26dcdbbf5158bb6`)
- `config.json` (9708 bytes, sha256 `edcb940e6bb8a2a4caefd07fa89726be1f7e849627fef8a2ad44187f80f81bfa`)
