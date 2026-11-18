# Backtest Run Card

Generated: 2026-11-18T01:47:28.685827Z
Run directory: `C:\Users\Warren\Downloads\qoder trading challenge\evidence\research\vibe-trading-poc-2026-11-18\protocol-runs\strategy`

## Backtest Summary
- codes: ['AAPL', 'AMD', 'AMZN', 'AVGO', 'COST', 'GOOGL', 'HD', 'JNJ', 'JPM', 'MA', 'META', 'MSFT', 'NFLX', 'NVDA', 'PG', 'TSLA', 'UNH', 'V', 'WMT', 'XOM', 'SPY']
- start_date: 2015-01-02
- end_date: 2024-12-31
- interval: 1D
- engine: global_equity
- initial_cash: 100000.0
- source: moomoo_protocol_2015_2024

## Reproducibility
- config_hash: `c06b91ef7bf86fce63e30e9da25e49205a47b51df4b07fbd110aadecbec41a94`

## Model provenance
- config.json: Unknown
- Training cutoff: Unknown

## Data Sources
- moomoo_protocol_2015_2024

## Metrics
- final_value: 136815.38279145904
- total_return: 0.3681538279145904
- annual_return: 0.03550649648859361
- max_drawdown: -0.05293750793534659
- sharpe: 0.7351292617359642
- calmar: 0.6707
- sortino: 1.1
- win_rate: 0.5934426229508196
- profit_loss_ratio: 0.9963
- profit_factor: 1.4543
- max_consecutive_loss: 5
- avg_holding_days: 6.2
- trade_count: 610
- benchmark_return: 9.120467
- excess_return: -8.752313
- information_ratio: -1.2616
- tracking_error: 0.192639
- benchmark_beta: 0.0925
- avg_turnover: 0.022706
- total_turnover: 51.405585
- benchmark_kind: equal_weight
- benchmark_label: equal-weight basket of 21 symbols
- unfilled_plan_rejections: 0
- rebalance_bars_executed: 470
- target_change_count: 610
- rebalance_executed_bars: 120
- rebalance_executed_fills: 140
- rebalance_realized_turnover: 0.33682529568834696
- rebalance_turnover_mean: 0.11016393442622954
- rebalance_turnover_max: 0.15000000000000002
- position_adjustment: rebalance
- rebalance_tolerance: 0.0
- dropped_target_adjustment_count: 0
- risk_xray_hhi: 0.056213417931386164
- risk_xray_effective_n: 17.78934704202821
- risk_xray_annualized_vol: 0.23739384044236836
- risk_xray_max_drawdown: -0.3455076044804155
- risk_xray_avg_invested: 0.14282977326555185

## Structured metrics

Non-scalar metrics, which the `metrics` block cannot hold - carried so they can be inspected by key instead of only as a flattened count.

- unfilled_plan_rejections_by_symbol: {}
- execution_costs: {"commission_rate": 0.0, "market": "us_equity", "slippage_buy_rate": 0.00019999999999997797, "slippage_config_key": "slippage_us", "slippage_sell_rate": 0.00019999999999997797}
- by_symbol: {"AAPL": {"avg_pnl": 152.04, "count": 37, "total_pnl": 5625.4, "win_rate": 0.8378}, "AMD": {"avg_pnl": 64.65, "count": 56, "total_pnl": 3620.37, "win_rate": 0.5714}, "AMZN": {"avg_pnl": -9.93, "count": 35, "total_pnl": -347.7, "win_rate": 0.6286}, "AVGO": {"avg_pnl": 60.65, "count": 41, "total_pnl": 2486.84, "win_rate": 0.6341}, "COST": {"avg_pnl": 58.78, "count": 23, "total_pnl": 1351.97, "win_rate": 0.6522}, "GOOGL": {"avg_pnl": 75.2, "count": 30, "total_pnl": 2256.06, "win_rate": 0.5667}, "HD": {"avg_pnl": 45.82, "count": 20, "total_pnl": 916.36, "win_rate": 0.55}, "JNJ": {"avg_pnl": 30.8, "count": 16, "total_pnl": 492.84, "win_rate": 0.5625}, "JPM": {"avg_pnl": 103.7, "count": 27, "total_pnl": 2799.8, "win_rate": 0.7037}, "MA": {"avg_pnl": -7.35, "count": 22, "total_pnl": -161.65, "win_rate": 0.5909}, "META": {"avg_pnl": -199.6, "count": 26, "total_pnl": -5189.61, "win_rate": 0.2308}, "MSFT": {"avg_pnl": -1.31, "count": 22, "total_pnl": -28.73, "win_rate": 0.5}, "NFLX": {"avg_pnl": -11.97, "count": 39, "total_pnl": -467.02, "win_rate": 0.4872}, "NVDA": {"avg_pnl": 364.72, "count": 48, "total_pnl": 17506.76, "win_rate": 0.7917}, "PG": {"avg_pnl": 13.79, "count": 23, "total_pnl": 317.23, "win_rate": 0.5652}, "TSLA": {"avg_pnl": 117.59, "count": 40, "total_pnl": 4703.69, "win_rate": 0.675}, "UNH": {"avg_pnl": -76.02, "count": 27, "total_pnl": -2052.63, "win_rate": 0.3704}, "V": {"avg_pnl": 36.35, "count": 27, "total_pnl": 981.52, "win_rate": 0.5556}, "WMT": {"avg_pnl": 1.32, "count": 27, "total_pnl": 35.6, "win_rate": 0.5556}, "XOM": {"avg_pnl": 82.01, "count": 24, "total_pnl": 1968.27, "win_rate": 0.5417}}
- by_exit_reason: {"end_of_backtest": {"count": 3, "total_pnl": -144.0}, "signal": {"count": 511, "total_pnl": 31112.13}, "target_rebalance": {"count": 96, "total_pnl": 5847.25}}
- dropped_target_adjustments: []
- _omitted: ["rebalance_mask"]

## Validation
- Not present.

## Warnings
- benchmark 'none' could not be resolved over the evaluation window; benchmark-relative metrics use the equal-weight basket of 21 symbols
- No strategy model provenance was recorded for config.json; writer identity is unknown.
- Training cutoff for unknown model is unknown; assume results may reflect what the model remembers.

## Execution records
- backtest (ok): 2026-11-18T01:47:21.540435Z → 2026-11-18T01:47:28.683192Z; args sha256 `4cd9fa42d4f2c68721e055a40d13273a89f1408579128fe473f046c7b433400b`, result sha256 `8e190b93362c6d705a464293a7de62783bffaa7a4e0c173ac0f0b2531f32d37a`

## Metric evidence
- final_value: `artifacts/metrics.csv`, column `final_value`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- total_return: `artifacts/metrics.csv`, column `total_return`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- annual_return: `artifacts/metrics.csv`, column `annual_return`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- max_drawdown: `artifacts/metrics.csv`, column `max_drawdown`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- sharpe: `artifacts/metrics.csv`, column `sharpe`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- calmar: `artifacts/metrics.csv`, column `calmar`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- sortino: `artifacts/metrics.csv`, column `sortino`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- win_rate: `artifacts/metrics.csv`, column `win_rate`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- profit_loss_ratio: `artifacts/metrics.csv`, column `profit_loss_ratio`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- profit_factor: `artifacts/metrics.csv`, column `profit_factor`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- max_consecutive_loss: `artifacts/metrics.csv`, column `max_consecutive_loss`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- avg_holding_days: `artifacts/metrics.csv`, column `avg_holding_days`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- trade_count: `artifacts/metrics.csv`, column `trade_count`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- benchmark_return: `artifacts/metrics.csv`, column `benchmark_return`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- excess_return: `artifacts/metrics.csv`, column `excess_return`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- information_ratio: `artifacts/metrics.csv`, column `information_ratio`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- tracking_error: `artifacts/metrics.csv`, column `tracking_error`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- benchmark_beta: `artifacts/metrics.csv`, column `benchmark_beta`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- avg_turnover: `artifacts/metrics.csv`, column `avg_turnover`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- total_turnover: `artifacts/metrics.csv`, column `total_turnover`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- benchmark_kind: `artifacts/metrics.csv`, column `benchmark_kind`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- benchmark_label: `artifacts/metrics.csv`, column `benchmark_label`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- unfilled_plan_rejections: `artifacts/metrics.csv`, column `unfilled_plan_rejections`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- rebalance_bars_executed: `artifacts/metrics.csv`, column `rebalance_bars_executed`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- target_change_count: `artifacts/metrics.csv`, column `target_change_count`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- rebalance_executed_bars: `artifacts/metrics.csv`, column `rebalance_executed_bars`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- rebalance_executed_fills: `artifacts/metrics.csv`, column `rebalance_executed_fills`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- rebalance_realized_turnover: `artifacts/metrics.csv`, column `rebalance_realized_turnover`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- rebalance_turnover_mean: `artifacts/metrics.csv`, column `rebalance_turnover_mean`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- rebalance_turnover_max: `artifacts/metrics.csv`, column `rebalance_turnover_max`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- position_adjustment: `artifacts/metrics.csv`, column `position_adjustment`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- rebalance_tolerance: `artifacts/metrics.csv`, column `rebalance_tolerance`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- dropped_target_adjustment_count: `artifacts/metrics.csv`, column `dropped_target_adjustment_count`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- risk_xray_hhi: `artifacts/metrics.csv`, column `risk_xray_hhi`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- risk_xray_effective_n: `artifacts/metrics.csv`, column `risk_xray_effective_n`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- risk_xray_annualized_vol: `artifacts/metrics.csv`, column `risk_xray_annualized_vol`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- risk_xray_max_drawdown: `artifacts/metrics.csv`, column `risk_xray_max_drawdown`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`
- risk_xray_avg_invested: `artifacts/metrics.csv`, column `risk_xray_avg_invested`, data row 1, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`

## Artifacts
- `artifacts/equity.csv` (276984 bytes, sha256 `e1bc618d2a39c2b97e75b510e2d7d37e4c18ca0748c2ab504d1f07fcf06465ee`)
- `artifacts/fills.jsonl` (319973 bytes, sha256 `c508250270b3d2f980b0e4713f3c42c8d37b58abfd875b2b615db37456db3b41`)
- `artifacts/metrics.csv` (7759 bytes, sha256 `9138fe9a62da014340c4961779cf00a14e65666d537f2df821f8aa00823f3fc4`)
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
- `artifacts/positions.csv` (302813 bytes, sha256 `d04ea4b44b5b78af13ed3c35de2e5fbcb0f825184c654f9103c024759979a9e3`)
- `artifacts/rebalance_notes.json` (356158 bytes, sha256 `550a2fa3970083e7ee537408e9badd9d68f354f4cb023e906ff2a6e3a80922a3`)
- `artifacts/rebalance_notes.md` (82554 bytes, sha256 `9d321325f5c684712e2d23df55937901a77bb0e7a33c5ec898a5b2d8b2931127`)
- `artifacts/risk_xray.json` (2437 bytes, sha256 `e37152ab3d300c0208d6e798b3d5aae09f841a1c8cb3a25c56fee4c2e249f1c6`)
- `artifacts/risk_xray.md` (467 bytes, sha256 `33bb484a36fba13733a50cc115934d35796ac0309ddb0b18d194b4e3bffef7fe`)
- `artifacts/target_positions.csv` (251405 bytes, sha256 `748fb403aec24fd8bb4c48986a9f1982d46dd56faa78aba9921ed86de32ceb0e`)
- `artifacts/trades.csv` (90475 bytes, sha256 `3db86dafafdbfaa831e38aec7ae7676f50a85a92a6b96f7e789f593c673b1306`)
- `config.json` (9696 bytes, sha256 `c06b91ef7bf86fce63e30e9da25e49205a47b51df4b07fbd110aadecbec41a94`)
