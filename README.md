# 美股量化感知沙盒 V09.4.2 Modular Refactor

## 1. Project Title & Overview
本專案為美股短線策略研發與量化驗證平台 (**V09.4.2 Modular Refactor**)，專注於市場事件偵測、歷史相似度匹配（PIT Evidence Engine）及 Gate OOS / Ranking 門檻驗證。

## 2. Golden Reference Baseline
本模組化重構版本的唯一 Golden Reference Baseline 為：
* **V09.4.1c Accepted Monolithic Baseline** (Golden Source 檔案內部標籤為 `V09.4.1b_T21fix_candidate`)。

## 3. Module Mapping Matrix

| 原始 Monolithic Function | V09.4.2 新模組位置 |
| :--- | :--- |
| `load_ticker_master_df`, `save_ticker_master_df`, `compute_ticker_master_hash`, `fetch_yahoo_taxonomy_with_retry`, `resolve_taxonomy_for_ticker`, `update_and_audit_taxonomy_master` | `data/taxonomy.py` |
| `load_tickers_from_gsheet`, `clean_and_flatten_df`, `extract_stock_from_chunk`, `fetch_us_macro_dataframe_fail_closed_v0941b`, `compute_data_snapshot_content_hash` | `data/market_data.py` |
| `calculate_features` | `research/features.py` |
| `generate_signals_and_outcomes` | `research/signals.py` |
| `calc_wilson_lower_bound`, `attach_hierarchical_point_in_time_evidence_v094` | `research/evidence.py` |
| `create_stock_event_history_v094`, `run_stock_level_gate_oos_expanding_v094`, `assign_candidate_status_v0941`, `generate_daily_stock_ranking_v094`, `run_ranking_validation_v094` | `validation/research_validation.py` |
| `run_executable_test_suite_v0941b` | `validation/test_suite.py` |
| UI Rendering, Controls, Cloud Form Sync, Pipeline Orchestration | `app.py` |

## 4. Strict Freeze Statement
本版本為 **MECHANICAL REFACTOR ONLY**，完全凍結所有 Quant / Research Core 邏輯：
- 未修改任何策略觸發條件（Strat_A ~ Strat_E）。
- 未修改特徵公式、訊號條件、 Entry/Exit 機制、Forward Returns。
- 未修改 Similarity Hierarchy (L0~L5) 或 Wilson Lower Bound 算式。
- 未使用 Parallel Processing、ProcessPoolExecutor 或 Cache Optimization。

## 5. Known Issues (Frozen Unchanged)
- **KNOWN ISSUE 1**: Taxonomy Coverage 尚未穩定達 95%（Golden run 約 83.5%）。
- **KNOWN ISSUE 2**: T29 目前 `tax_status` WARN 仍會在 Test Table 顯示 PASS（Reporting semantic 議題）。
- **KNOWN ISSUE 3**: Evidence Engine 尚未實作 Vectorization / Precomputation 效能優化（保留至 V09.4.3）。
- **KNOWN ISSUE 4**: `DAILY_INCREMENTAL` 尚未實作，點選時強制停止。

## 6. Streamlit Cloud Deployment Note
`app.py` 開頭保留專案根目錄之 `sys.path` 動態載入（`sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))`），因第一次 Modular 部署曾發生 `core` 模組引入 `ImportError`，此相容性修復嚴格保留，禁止移除。

## 7. Dependencies & Installation

```bash
pip install -r requirements.txt
