# Backtest Run Card

Generated: 2026-11-18T01:48:02.553536Z
Run directory: `C:\Users\Warren\Downloads\qoder trading challenge\evidence\research\vibe-trading-poc-2026-11-18\protocol-runs\equal_weight`

## Backtest Summary
- codes: ['AAPL', 'AMD', 'AMZN', 'AVGO', 'COST', 'GOOGL', 'HD', 'JNJ', 'JPM', 'MA', 'META', 'MSFT', 'NFLX', 'NVDA', 'PG', 'TSLA', 'UNH', 'V', 'WMT', 'XOM', 'SPY']
- start_date: 2015-01-02
- end_date: 2024-12-31
- interval: 1D
- engine: global_equity
- initial_cash: 100000.0
- source: moomoo_protocol_2015_2024

## Reproducibility
- config_hash: `07affd7ed6302d1f7634dea23e056c02b21b94bd7f2dacc980f3209745dd424a`

## Model provenance
- config.json: Unknown
- Training cutoff: Unknown

## Data Sources
- moomoo_protocol_2015_2024

## Metrics
- final_value: 207484.216974179
- total_return: 1.0748421697417898
- annual_return: 0.08463294086473816
- max_drawdown: -0.09688487076659474
- sharpe: 1.3667771086919038
- calmar: 0.8735
- sortino: 1.9405
- win_rate: 0.9071832122679581
- profit_loss_ratio: 2.8515
- profit_factor: 27.8703
- max_consecutive_loss: 8
- avg_holding_days: 304.0
- trade_count: 2478
- benchmark_return: 9.120467
- excess_return: -8.045624
- information_ratio: -1.3466
- tracking_error: 0.145569
- benchmark_beta: 0.2945
- avg_turnover: 0.000988
- total_turnover: 2.23671
- benchmark_kind: equal_weight
- benchmark_label: equal-weight basket of 21 symbols
- unfilled_plan_rejections: 0
- rebalance_bars_executed: 470
- target_change_count: 939
- rebalance_executed_bars: 469
- rebalance_executed_fills: 4486
- rebalance_realized_turnover: 1.9467099755744248
- rebalance_turnover_mean: 0.14999999999999997
- rebalance_turnover_max: 0.15000000000000002
- position_adjustment: rebalance
- rebalance_tolerance: 0.0
- dropped_target_adjustment_count: 0
- risk_xray_hhi: 0.05002261132391084
- risk_xray_effective_n: 19.99095955876257
- risk_xray_annualized_vol: 0.20895841856777533
- risk_xray_max_drawdown: -0.2987196418415943
- risk_xray_avg_invested: 0.2916963474631019

## Structured metrics

Non-scalar metrics, which the `metrics` block cannot hold - carried so they can be inspected by key instead of only as a flattened count.

- unfilled_plan_rejections_by_symbol: {}
- execution_costs: {"commission_rate": 0.0, "market": "us_equity", "slippage_buy_rate": 0.00019999999999997797, "slippage_config_key": "slippage_us", "slippage_sell_rate": 0.00019999999999997797}
- by_symbol: {"AAPL": {"avg_pnl": 41.05, "count": 141, "total_pnl": 5787.52, "win_rate": 0.9433}, "AMD": {"avg_pnl": 47.0, "count": 210, "total_pnl": 9870.56, "win_rate": 0.9}, "AMZN": {"avg_pnl": 35.77, "count": 135, "total_pnl": 4829.57, "win_rate": 0.8519}, "AVGO": {"avg_pnl": 39.62, "count": 215, "total_pnl": 8518.76, "win_rate": 0.9814}, "COST": {"avg_pnl": 124.44, "count": 36, "total_pnl": 4479.9, "win_rate": 0.9167}, "GOOGL": {"avg_pnl": 31.68, "count": 135, "total_pnl": 4276.2, "win_rate": 0.9111}, "HD": {"avg_pnl": 61.08, "count": 52, "total_pnl": 3176.42, "win_rate": 0.9808}, "JNJ": {"avg_pnl": 20.06, "count": 63, "total_pnl": 1264.08, "win_rate": 0.9841}, "JPM": {"avg_pnl": 33.67, "count": 122, "total_pnl": 4108.03, "win_rate": 0.8852}, "MA": {"avg_pnl": 77.89, "count": 51, "total_pnl": 3972.53, "win_rate": 0.9412}, "META": {"avg_pnl": 64.1, "count": 79, "total_pnl": 5063.94, "win_rate": 0.8101}, "MSFT": {"avg_pnl": 66.18, "count": 74, "total_pnl": 4897.12, "win_rate": 0.9189}, "NFLX": {"avg_pnl": 28.83, "count": 216, "total_pnl": 6227.15, "win_rate": 0.838}, "NVDA": {"avg_pnl": 53.55, "count": 253, "total_pnl": 13547.74, "win_rate": 0.9091}, "PG": {"avg_pnl": 29.16, "count": 81, "total_pnl": 2361.62, "win_rate": 0.9877}, "TSLA": {"avg_pnl": 57.81, "count": 194, "total_pnl": 11215.09, "win_rate": 0.7887}, "UNH": {"avg_pnl": 75.37, "count": 48, "total_pnl": 3617.76, "win_rate": 0.9792}, "V": {"avg_pnl": 51.0, "count": 68, "total_pnl": 3467.81, "win_rate": 0.9853}, "WMT": {"avg_pnl": 23.95, "count": 174, "total_pnl": 4166.77, "win_rate": 1.0}, "XOM": {"avg_pnl": 20.12, "count": 131, "total_pnl": 2635.62, "win_rate": 0.8473}}
- by_exit_reason: {"end_of_backtest": {"count": 20, "total_pnl": 16864.1}, "target_rebalance": {"count": 2458, "total_pnl": 90620.11}}
- dropped_target_adjustments: []
- _omitted: ["rebalance_mask"]

## Validation
- Not present.

## Warnings
- benchmark 'none' could not be resolved over the evaluation window; benchmark-relative metrics use the equal-weight basket of 21 symbols
- No strategy model provenance was recorded for config.json; writer identity is unknown.
- Training cutoff for unknown model is unknown; assume results may reflect what the model remembers.

## Execution records
- backtest (ok): 2026-11-18T01:47:45.479418Z → 2026-11-18T01:48:02.551027Z; args sha256 `2642c34a823d7caaba262b76e77d9bad3a8cb1b9c40687eccfe162eb2f106ad5`, result sha256 `82bd400b7f5cf79c85c68c20bedfee65f8db7d89cf5cad4f6853d59a2a59af19`

## Metric evidence
- final_value: `artifacts/metrics.csv`, column `final_value`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- total_return: `artifacts/metrics.csv`, column `total_return`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- annual_return: `artifacts/metrics.csv`, column `annual_return`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- max_drawdown: `artifacts/metrics.csv`, column `max_drawdown`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- sharpe: `artifacts/metrics.csv`, column `sharpe`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- calmar: `artifacts/metrics.csv`, column `calmar`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- sortino: `artifacts/metrics.csv`, column `sortino`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- win_rate: `artifacts/metrics.csv`, column `win_rate`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- profit_loss_ratio: `artifacts/metrics.csv`, column `profit_loss_ratio`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- profit_factor: `artifacts/metrics.csv`, column `profit_factor`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- max_consecutive_loss: `artifacts/metrics.csv`, column `max_consecutive_loss`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- avg_holding_days: `artifacts/metrics.csv`, column `avg_holding_days`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- trade_count: `artifacts/metrics.csv`, column `trade_count`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- benchmark_return: `artifacts/metrics.csv`, column `benchmark_return`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- excess_return: `artifacts/metrics.csv`, column `excess_return`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- information_ratio: `artifacts/metrics.csv`, column `information_ratio`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- tracking_error: `artifacts/metrics.csv`, column `tracking_error`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- benchmark_beta: `artifacts/metrics.csv`, column `benchmark_beta`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- avg_turnover: `artifacts/metrics.csv`, column `avg_turnover`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- total_turnover: `artifacts/metrics.csv`, column `total_turnover`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- benchmark_kind: `artifacts/metrics.csv`, column `benchmark_kind`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- benchmark_label: `artifacts/metrics.csv`, column `benchmark_label`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- unfilled_plan_rejections: `artifacts/metrics.csv`, column `unfilled_plan_rejections`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- rebalance_bars_executed: `artifacts/metrics.csv`, column `rebalance_bars_executed`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- target_change_count: `artifacts/metrics.csv`, column `target_change_count`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- rebalance_executed_bars: `artifacts/metrics.csv`, column `rebalance_executed_bars`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- rebalance_executed_fills: `artifacts/metrics.csv`, column `rebalance_executed_fills`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- rebalance_realized_turnover: `artifacts/metrics.csv`, column `rebalance_realized_turnover`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- rebalance_turnover_mean: `artifacts/metrics.csv`, column `rebalance_turnover_mean`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- rebalance_turnover_max: `artifacts/metrics.csv`, column `rebalance_turnover_max`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- position_adjustment: `artifacts/metrics.csv`, column `position_adjustment`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- rebalance_tolerance: `artifacts/metrics.csv`, column `rebalance_tolerance`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- dropped_target_adjustment_count: `artifacts/metrics.csv`, column `dropped_target_adjustment_count`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- risk_xray_hhi: `artifacts/metrics.csv`, column `risk_xray_hhi`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- risk_xray_effective_n: `artifacts/metrics.csv`, column `risk_xray_effective_n`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- risk_xray_annualized_vol: `artifacts/metrics.csv`, column `risk_xray_annualized_vol`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- risk_xray_max_drawdown: `artifacts/metrics.csv`, column `risk_xray_max_drawdown`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`
- risk_xray_avg_invested: `artifacts/metrics.csv`, column `risk_xray_avg_invested`, data row 1, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`

## Artifacts
- `artifacts/equity.csv` (285730 bytes, sha256 `e4757725c90738cbd6ff63a51a6f85ef54d06f5502bdb85754f84ba5b178a356`)
- `artifacts/fills.jsonl` (1303674 bytes, sha256 `62c2710e6888910afa75599d9a5d6671fd800eae8c9e74326f97c0ae141b883b`)
- `artifacts/metrics.csv` (7760 bytes, sha256 `f6ff7311365ace371e39c187a294d82ff811e3b2dc90826a5e9d2340c66ab39e`)
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
- `artifacts/positions.csv` (1011728 bytes, sha256 `b2a33c42bcfba5878d857106b8af0fb8e99f9093b655ab5abc58cecfb1773f28`)
- `artifacts/rebalance_notes.json` (2169950 bytes, sha256 `90351a70604c8b9d93344cae5ea47fcdd9c6f199e996ddcb35fd1b91060f1e43`)
- `artifacts/rebalance_notes.md` (310107 bytes, sha256 `ee0e1fd681077485557a7cbca435568e1d13d8768d7cdb3079870a3243ee6637`)
- `artifacts/risk_xray.json` (2431 bytes, sha256 `fecee8d0ae7d7e04609228acb9f05491175abfde350bae145588f02d7a133ef6`)
- `artifacts/risk_xray.md` (467 bytes, sha256 `cada5103758e6672feb2404567f494b8cbaec3de2f385fa6dd1c2ef5dc6f2f28`)
- `artifacts/target_positions.csv` (270205 bytes, sha256 `bd523ddc7b5f4d28834ac766a647708aa8ca113af4fe59dba6fa884ad9184fa2`)
- `artifacts/trades.csv` (420712 bytes, sha256 `c83cbffbd39a05b00be7531e2e08133e579f98ad1514b58a01bfba6aa0e6c194`)
- `config.json` (9700 bytes, sha256 `07affd7ed6302d1f7634dea23e056c02b21b94bd7f2dacc980f3209745dd424a`)
