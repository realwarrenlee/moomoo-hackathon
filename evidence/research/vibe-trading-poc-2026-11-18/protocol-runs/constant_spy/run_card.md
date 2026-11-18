# Backtest Run Card

Generated: 2026-11-18T01:47:45.297520Z
Run directory: `C:\Users\Warren\Downloads\qoder trading challenge\evidence\research\vibe-trading-poc-2026-11-18\protocol-runs\constant_spy`

## Backtest Summary
- codes: ['AAPL', 'AMD', 'AMZN', 'AVGO', 'COST', 'GOOGL', 'HD', 'JNJ', 'JPM', 'MA', 'META', 'MSFT', 'NFLX', 'NVDA', 'PG', 'TSLA', 'UNH', 'V', 'WMT', 'XOM', 'SPY']
- start_date: 2015-01-02
- end_date: 2024-12-31
- interval: 1D
- engine: global_equity
- initial_cash: 100000.0
- source: moomoo_protocol_2015_2024

## Reproducibility
- config_hash: `2ba12c16be3ef3da561119e54920637d9c404b896d9a28107f72087d9155dbfd`

## Model provenance
- config.json: Unknown
- Training cutoff: Unknown

## Data Sources
- moomoo_protocol_2015_2024

## Metrics
- final_value: 147891.0701139543
- total_return: 0.47891070113954304
- annual_return: 0.044517691533658255
- max_drawdown: -0.11245714164458383
- sharpe: 0.8460703267070576
- calmar: 0.3959
- sortino: 1.1778
- win_rate: 0.9766355140186916
- profit_loss_ratio: 24.7126
- profit_factor: 1032.9854
- max_consecutive_loss: 5
- avg_holding_days: 576.2
- trade_count: 214
- benchmark_return: 9.120467
- excess_return: -8.641556
- information_ratio: -1.4921
- tracking_error: 0.156933
- benchmark_beta: 0.2439
- avg_turnover: 0.000484
- total_turnover: 1.09679
- benchmark_kind: equal_weight
- benchmark_label: equal-weight basket of 21 symbols
- unfilled_plan_rejections: 0
- rebalance_bars_executed: 470
- target_change_count: 939
- rebalance_executed_bars: 337
- rebalance_executed_fills: 337
- rebalance_realized_turnover: 0.7981212202068442
- rebalance_turnover_mean: 0.14999999999999997
- rebalance_turnover_max: 0.15
- position_adjustment: rebalance
- rebalance_tolerance: 0.0
- dropped_target_adjustment_count: 0
- risk_xray_hhi: 1.0
- risk_xray_effective_n: 1.0
- risk_xray_annualized_vol: 0.17838290129955042
- risk_xray_max_drawdown: -0.337173884337483
- risk_xray_avg_invested: 0.2989326542042771

## Structured metrics

Non-scalar metrics, which the `metrics` block cannot hold - carried so they can be inspected by key instead of only as a flattened count.

- unfilled_plan_rejections_by_symbol: {}
- execution_costs: {"commission_rate": 0.0, "market": "us_equity", "slippage_buy_rate": 0.00019999999999997797, "slippage_config_key": "slippage_us", "slippage_sell_rate": 0.00019999999999997797}
- by_symbol: {"SPY": {"avg_pnl": 223.79, "count": 214, "total_pnl": 47891.07, "win_rate": 0.9766}}
- by_exit_reason: {"end_of_backtest": {"count": 1, "total_pnl": 16872.18}, "target_rebalance": {"count": 213, "total_pnl": 31018.89}}
- dropped_target_adjustments: []
- _omitted: ["rebalance_mask"]

## Validation
- Not present.

## Warnings
- benchmark 'none' could not be resolved over the evaluation window; benchmark-relative metrics use the equal-weight basket of 21 symbols
- No strategy model provenance was recorded for config.json; writer identity is unknown.
- Training cutoff for unknown model is unknown; assume results may reflect what the model remembers.

## Execution records
- backtest (ok): 2026-11-18T01:47:36.778207Z → 2026-11-18T01:47:45.295471Z; args sha256 `d39ef372ded3b1b31e39d9d3569ce7bb902bebf0339d3221910491491f322f00`, result sha256 `2c554a4241ebc38b20515439d48229c74c253e3240e2399a5f1d0809c4b8bd4d`

## Metric evidence
- final_value: `artifacts/metrics.csv`, column `final_value`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- total_return: `artifacts/metrics.csv`, column `total_return`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- annual_return: `artifacts/metrics.csv`, column `annual_return`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- max_drawdown: `artifacts/metrics.csv`, column `max_drawdown`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- sharpe: `artifacts/metrics.csv`, column `sharpe`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- calmar: `artifacts/metrics.csv`, column `calmar`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- sortino: `artifacts/metrics.csv`, column `sortino`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- win_rate: `artifacts/metrics.csv`, column `win_rate`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- profit_loss_ratio: `artifacts/metrics.csv`, column `profit_loss_ratio`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- profit_factor: `artifacts/metrics.csv`, column `profit_factor`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- max_consecutive_loss: `artifacts/metrics.csv`, column `max_consecutive_loss`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- avg_holding_days: `artifacts/metrics.csv`, column `avg_holding_days`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- trade_count: `artifacts/metrics.csv`, column `trade_count`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- benchmark_return: `artifacts/metrics.csv`, column `benchmark_return`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- excess_return: `artifacts/metrics.csv`, column `excess_return`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- information_ratio: `artifacts/metrics.csv`, column `information_ratio`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- tracking_error: `artifacts/metrics.csv`, column `tracking_error`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- benchmark_beta: `artifacts/metrics.csv`, column `benchmark_beta`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- avg_turnover: `artifacts/metrics.csv`, column `avg_turnover`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- total_turnover: `artifacts/metrics.csv`, column `total_turnover`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- benchmark_kind: `artifacts/metrics.csv`, column `benchmark_kind`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- benchmark_label: `artifacts/metrics.csv`, column `benchmark_label`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- unfilled_plan_rejections: `artifacts/metrics.csv`, column `unfilled_plan_rejections`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- rebalance_bars_executed: `artifacts/metrics.csv`, column `rebalance_bars_executed`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- target_change_count: `artifacts/metrics.csv`, column `target_change_count`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- rebalance_executed_bars: `artifacts/metrics.csv`, column `rebalance_executed_bars`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- rebalance_executed_fills: `artifacts/metrics.csv`, column `rebalance_executed_fills`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- rebalance_realized_turnover: `artifacts/metrics.csv`, column `rebalance_realized_turnover`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- rebalance_turnover_mean: `artifacts/metrics.csv`, column `rebalance_turnover_mean`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- rebalance_turnover_max: `artifacts/metrics.csv`, column `rebalance_turnover_max`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- position_adjustment: `artifacts/metrics.csv`, column `position_adjustment`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- rebalance_tolerance: `artifacts/metrics.csv`, column `rebalance_tolerance`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- dropped_target_adjustment_count: `artifacts/metrics.csv`, column `dropped_target_adjustment_count`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- risk_xray_hhi: `artifacts/metrics.csv`, column `risk_xray_hhi`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- risk_xray_effective_n: `artifacts/metrics.csv`, column `risk_xray_effective_n`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- risk_xray_annualized_vol: `artifacts/metrics.csv`, column `risk_xray_annualized_vol`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- risk_xray_max_drawdown: `artifacts/metrics.csv`, column `risk_xray_max_drawdown`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`
- risk_xray_avg_invested: `artifacts/metrics.csv`, column `risk_xray_avg_invested`, data row 1, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`

## Artifacts
- `artifacts/equity.csv` (287940 bytes, sha256 `427bf554b7c216c9dc8a39b279cdc053af67454bcce04b2afc4776f12c5f5ed8`)
- `artifacts/fills.jsonl` (99428 bytes, sha256 `a59ad13fd6dc0a56d01211f4b715b527f5c8aad3868840751cc52f5713037324`)
- `artifacts/metrics.csv` (7718 bytes, sha256 `49e859298419ff99c2ef2c94c82d796086b734e1d27b64bf22a39b4f9230abba`)
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
- `artifacts/positions.csv` (286197 bytes, sha256 `12bbc217ade12db8cc794510974d8c4bcf60623a749a4d1a36d0b2ff4828d025`)
- `artifacts/rebalance_notes.json` (321029 bytes, sha256 `5c0075b2c5764574eddafbbbf5284a2864a5253bf7a39691d3434ef701433d60`)
- `artifacts/rebalance_notes.md` (80051 bytes, sha256 `df31c80e2d6bd58de9943966d0f45912ce2379b6981904bd3dc33e8989f0405a`)
- `artifacts/risk_xray.json` (1491 bytes, sha256 `2ea0375142a08615ddfb34fdebabd8f11bb294874e3c45cd85c0db4809e6b7f0`)
- `artifacts/risk_xray.md` (368 bytes, sha256 `f2c81a097ecbc710f81df1a39cf08928bda919a8bfc590d8480d8c2f32c33983`)
- `artifacts/target_positions.csv` (251405 bytes, sha256 `a1c8b71024caf9b60b4b4408b5f0c4ce856d6cd98dd441c11855dbeb577757cc`)
- `artifacts/trades.csv` (37326 bytes, sha256 `0da61f5a788069fbe9343cc8acece40a3c7a574407e82cff1d8c5f64fae586c3`)
- `config.json` (9700 bytes, sha256 `2ba12c16be3ef3da561119e54920637d9c404b896d9a28107f72087d9155dbfd`)
