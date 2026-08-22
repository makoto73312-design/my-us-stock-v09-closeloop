import time
import hashlib
import json
import pandas as pd
import numpy as np
import streamlit as st

from core import (
    VERSION,
    VERSION_NAME,
    generate_run_id,
    get_gen_time,
    GSHEET_URL,
    GOOGLE_FORM_ID,
    ENTRY_TICKER_ID,
    ENTRY_NAME_ID
)

from data import (
    load_tickers_from_gsheet,
    extract_stock_from_chunk,
    fetch_us_macro_dataframe_fail_closed_v0941b,
    compute_data_snapshot_content_hash,
    update_and_audit_taxonomy_master,
    compute_ticker_master_hash
)

from research import (
    calculate_features,
    generate_signals_and_outcomes,
    attach_hierarchical_point_in_time_evidence_v094
)

from validation import (
    create_stock_event_history_v094,
    run_stock_level_gate_oos_expanding_v094,
    assign_candidate_status_v0941,
    generate_daily_stock_ranking_v094,
    run_ranking_validation_v094,
    run_executable_test_suite_v0941b
)

# Page Config
RUN_ID = generate_run_id()
GEN_TIME = get_gen_time()

st.set_page_config(
    page_title=f"🚀 美股感知沙盒 {VERSION} (Modular Refactor)", 
    page_icon="🚀", 
    layout="wide"
)

st.title(f"🚀 美股量化感知沙盒 {VERSION} (Modular Refactor)")
st.caption(f"🔥 機械化模組拆分版 | Run_ID: {RUN_ID} | Clean Architecture Orchestrator Layer")

# UI Controls & Setup
default_ticker_str, default_ticker_list = load_tickers_from_gsheet(GSHEET_URL)
st.sidebar.header(f"⚙️ {VERSION} 沙盒控制台")

run_mode = st.sidebar.radio(
    "運算模式 (Performance Mode)", 
    ["🔬 完整研究重建 (FULL_RESEARCH_REBUILD)", "⚡ 每日快速更新（尚未實作）"], 
    index=0
)

if "尚未實作" in run_mode:
    st.sidebar.error("❌ DAILY_INCREMENTAL 尚未實作，請使用 FULL_RESEARCH_REBUILD。")

tickers_input = st.sidebar.text_area("📡 當前追蹤股票清單", default_ticker_str, height=100)
import re
ticker_list = list(dict.fromkeys([t.strip().upper() for t in re.split(r'[\n\r,\s]+', tickers_input) if t.strip()]))
min_sample_size_threshold = st.sidebar.slider("最小匹配樣本門檻 (Adaptive N)", min_value=10, max_value=100, value=30, step=5)

# Session State Initialization
if 'signal_database' not in st.session_state: st.session_state.signal_database = pd.DataFrame()
if 'stock_database' not in st.session_state: st.session_state.stock_database = pd.DataFrame()
if 'daily_stock_ranking' not in st.session_state: st.session_state.daily_stock_ranking = pd.DataFrame()
if 'test_suite_results' not in st.session_state: st.session_state.test_suite_results = []
if 'gate_oos_report' not in st.session_state: st.session_state.gate_oos_report = pd.DataFrame()
if 'gate_oos_status' not in st.session_state: st.session_state.gate_oos_status = "INCONCLUSIVE"
if 'rank_val_report' not in st.session_state: st.session_state.rank_val_report = pd.DataFrame()
if 'rank_pred_status' not in st.session_state: st.session_state.rank_pred_status = "INCONCLUSIVE"
if 'performance_report' not in st.session_state: st.session_state.performance_report = pd.DataFrame()
if 'horizon_audit' not in st.session_state: st.session_state.horizon_audit = pd.DataFrame()
if 'run_metadata' not in st.session_state: st.session_state.run_metadata = pd.DataFrame()
if 'ticker_master_export' not in st.session_state: st.session_state.ticker_master_export = pd.DataFrame()
if 'calculated' not in st.session_state: st.session_state.calculated = False

df_macro, vix_score, is_spy_bull, market_posture, macro_status, macro_source, macro_asof, macro_audit_info = fetch_us_macro_dataframe_fail_closed_v0941b()

# Orchestration Pipeline Execution
st.sidebar.markdown("---")
if st.sidebar.button(f"🚀 啟動 {VERSION} 感知沙盒運算", use_container_width=True):
    if "尚未實作" in run_mode:
        st.warning("DAILY_INCREMENTAL 尚未實作，請使用 FULL_RESEARCH_REBUILD。")
        st.stop()
        
    if macro_status == "INVALID":
        st.error("🛑 DATA ERROR: Macro data unavailable. Calculation aborted.")
    else:
        with st.spinner(f"執行 {VERSION} Modular Orchestrator Pipeline..."):
            import yfinance as yf
            t_start_total = time.perf_counter()
            
            # Step 1: Taxonomy Module
            master_df, known_cnt, unknown_cnt, tax_cov_rate, tax_status_str = update_and_audit_taxonomy_master(ticker_list)
            st.session_state.ticker_master_export = master_df
            
            # Step 2: Download & Feature & Signal
            t0 = time.perf_counter()
            chunk_size = 50
            ticker_chunks = [ticker_list[i:i + chunk_size] for i in range(0, len(ticker_list), chunk_size)]
            all_signals = []
            stock_data_dict = {}
            
            for chunk in ticker_chunks:
                try:
                    df_chunk = yf.download(chunk, period="2y", progress=False, threads=False)
                except Exception: df_chunk = pd.DataFrame()
                
                for ticker in chunk:
                    df_single = extract_stock_from_chunk(df_chunk, ticker)
                    if not df_single.empty and len(df_single) > 50:
                        stock_data_dict[ticker] = df_single
                        feat_df = calculate_features(df_single, df_macro)
                        sig_df = generate_signals_and_outcomes(ticker, feat_df, master_df, run_id=RUN_ID)
                        if not sig_df.empty: all_signals.append(sig_df)
            t1 = time.perf_counter()
            s2_time = t1 - t0
            
            # Step 3: Evidence Engine
            t0 = time.perf_counter()
            if all_signals:
                full_sig_db = pd.concat(all_signals, ignore_index=True)
                full_sig_db = attach_hierarchical_point_in_time_evidence_v094(full_sig_db, min_sample=min_sample_size_threshold)
                st.session_state.signal_database = full_sig_db
            else:
                full_sig_db = pd.DataFrame()
            t1 = time.perf_counter()
            s3_time = t1 - t0
            
            # Step 4: Stock Aggregation
            t0 = time.perf_counter()
            if not full_sig_db.empty:
                df_stock_events = create_stock_event_history_v094(full_sig_db, run_id=RUN_ID)
                st.session_state.stock_database = df_stock_events
            else: df_stock_events = pd.DataFrame()
            t1 = time.perf_counter()
            s5_time = t1 - t0
            
            # Step 5: Gate OOS
            t0 = time.perf_counter()
            if not df_stock_events.empty:
                gate_oos_df, gate_status, pos_uprate_r, pos_mean_r, pos_median_r, pos_excess_r, tot_wins, valid_wins = run_stock_level_gate_oos_expanding_v094(df_stock_events, run_id=RUN_ID)
                st.session_state.gate_oos_report = gate_oos_df
                st.session_state.gate_oos_status = gate_status
            else: gate_oos_df, gate_status = pd.DataFrame(), "INCONCLUSIVE"
            t1 = time.perf_counter()
            s6_time = t1 - t0
            
            # Step 6: Daily Ranking & Validation
            t0 = time.perf_counter()
            if not df_stock_events.empty:
                df_stock_events['Candidate_Status'] = [assign_candidate_status_v0941(r, gate_status) for _, r in df_stock_events.iterrows()]
                st.session_state.daily_stock_ranking = generate_daily_stock_ranking_v094(df_stock_events, gate_status)
                rank_rep, rank_status, rank_ci_low, rank_ci_high = run_ranking_validation_v094(df_stock_events, run_id=RUN_ID)
                st.session_state.rank_val_report = rank_rep
                st.session_state.rank_pred_status = rank_status
            else: rank_rep, rank_status, rank_ci_low, rank_ci_high = pd.DataFrame(), "INCONCLUSIVE", 0.0, 0.0
            t1 = time.perf_counter()
            s7_time = t1 - t0
            
            # Step 7: Test Suite
            t0 = time.perf_counter()
            if not full_sig_db.empty:
                st.session_state.test_suite_results = run_executable_test_suite_v0941b(
                    ticker_list, full_sig_db, df_stock_events, gate_oos_df, st.session_state.daily_stock_ranking,
                    gate_status, rank_status, rank_ci_low, rank_ci_high, macro_status, tax_status_str, tax_cov_rate, df_macro, run_id=RUN_ID
                )
            t1 = time.perf_counter()
            s8_time = t1 - t0
            
            t_total = time.perf_counter() - t_start_total
            
            # Performance Profile & Horizon Audit Data
            st.session_state.performance_report = pd.DataFrame([
                {"Stage": "Stage_1_Macro_Fetch", "V0942_Runtime": "0.0 sec (Preloaded)"},
                {"Stage": "Stage_2_Download_Feature_Signal", "V0942_Runtime": f"{round(s2_time, 2)} sec"},
                {"Stage": "Stage_3_PIT_Evidence_Engine", "V0942_Runtime": f"{round(s3_time, 2)} sec"},
                {"Stage": "Stage_5_Stock_Aggregation", "V0942_Runtime": f"{round(s5_time, 2)} sec"},
                {"Stage": "Stage_6_Gate_OOS", "V0942_Runtime": f"{round(s6_time, 2)} sec"},
                {"Stage": "Stage_7_Ranking_Validation", "V0942_Runtime": f"{round(s7_time, 2)} sec"},
                {"Stage": "Stage_8_Test_Suite", "V0942_Runtime": f"{round(s8_time, 2)} sec"},
                {"Stage": "Total_Runtime", "V0942_Runtime": f"{round(t_total, 2)} sec"}
            ])
            
            if not full_sig_db.empty:
                audit_rows = []
                for k in [1, 3, 5, 10, 20]:
                    col_asof = f"Stats_AsOf_T{k}"
                    col_n = f"Hist_T{k}_N"
                    col_up = f"Hist_T{k}_UpProb"
                    s_asof = full_sig_db[col_asof].replace("N/A", np.nan).dropna()
                    latest_asof = pd.to_datetime(s_asof).max().strftime('%Y-%m-%d') if not s_asof.empty else "N/A"
                    audit_rows.append({
                        "Horizon": f"T+{k}",
                        "Avg_Historical_Sample_N": round(full_sig_db[col_n].mean(), 1),
                        "Avg_UpProb": round(full_sig_db[col_up].mean(), 4),
                        "Latest_Stats_AsOf": latest_asof
                    })
                st.session_state.horizon_audit = pd.DataFrame(audit_rows)
            
            universe_hash = hashlib.sha256(",".join(sorted(ticker_list)).encode('utf-8')).hexdigest()[:12]
            config_dict = {
                "universe_hash": universe_hash,
                "min_sample": min_sample_size_threshold,
                "backtest_days": "2y_fixed",
                "cost_model": "Conservative_0.0030",
                "mode": "FULL_RESEARCH_REBUILD"
            }
            config_hash = hashlib.sha256(json.dumps(config_dict, sort_keys=True).encode('utf-8')).hexdigest()[:12]
            snap_hash = compute_data_snapshot_content_hash(stock_data_dict, df_macro)
            master_hash = compute_ticker_master_hash(master_df)

            st.session_state.run_metadata = pd.DataFrame([{
                "Run_ID": RUN_ID,
                "Generated_At_UTC": GEN_TIME,
                "Code_Version": VERSION_NAME,
                "Run_Mode": "FULL_RESEARCH_REBUILD",
                "Runtime_Total_sec": round(t_total, 2),
                "Worker_Count": 1,
                "Parallel_Execution_Used": False,
                "Macro_Data_Source": macro_source,
                "Macro_Warmup_Start_Date": macro_audit_info.get("Macro_Warmup_Start_Date", "N/A"),
                "Research_Start_Date": full_sig_db['Signal_Date'].min() if not full_sig_db.empty else "N/A",
                "Research_End_Date": full_sig_db['Signal_Date'].max() if not full_sig_db.empty else "N/A",
                "First_Valid_SPY_MA200_Date": macro_audit_info.get("First_Valid_SPY_MA200_Date", "N/A"),
                "SPY_MA200_Min_Periods": 200,
                "Universe_Count": len(ticker_list),
                "Known_Taxonomy_Count": known_cnt,
                "Unknown_Taxonomy_Count": unknown_cnt,
                "Taxonomy_Coverage_Rate": f"{tax_cov_rate*100:.1f}%",
                "Ticker_Master_Row_Count": len(master_df),
                "Ticker_Master_Hash": master_hash,
                "Universe_Hash": universe_hash,
                "Config_Hash": config_hash,
                "Data_Snapshot_ID": snap_hash
            }])

            st.session_state.calculated = True

# Top Status Metrics
col_v1, col_v2, col_v3 = st.columns(3)
col_v1.metric("VIX 恐慌指數", f"{vix_score:.2f}" if not np.isnan(vix_score) else "N/A")
col_v2.metric("S&P 500 位階 (真 200DMA)", "年線之上 (多頭)" if is_spy_bull else "跌破年線 (空頭)")
col_v3.metric("總經姿態 / Run_ID", f"{market_posture} ({RUN_ID[:12]})")
st.divider()

# UI Tabs & Views
tab_scan, tab_stock_db, tab_research, tab_rank_val, tab_gate_oos, tab_perf, tab_diagnostic, tab_export = st.tabs([
    "🎯 今日 Daily Ranking", "📦 Stock-Level 歷史庫", "🔬 PIT 前瞻研究", "📊 Paired Ranking 驗證", "🔄 Gate Rolling OOS", "⚡ 效能與 Horizon 稽核", "🧪 32 項系統測試", "📥 官方 Artifacts 匯出"
])

with tab_scan:
    st.header("🎯 今日發動股票 Ranking (Stock-Level Unique)")
    if st.session_state.calculated and not st.session_state.daily_stock_ranking.empty:
        st.dataframe(st.session_state.daily_stock_ranking, use_container_width=True, hide_index=True)
    else: st.info("💡 請點擊左側「🚀 啟動 V09.4.2 感知沙盒運算」。")

with tab_stock_db:
    st.header("📦 Stock-Level Historical Event Dataset (stock_event_history_v0942)")
    if st.session_state.calculated and not st.session_state.stock_database.empty:
        st.dataframe(st.session_state.stock_database, use_container_width=True, hide_index=True)
    else: st.info("💡 請先啟動沙盒運算。")

with tab_research:
    st.header("🔬 PIT 歷史訊號前瞻研究 (strategy_event_history_v0942)")
    if st.session_state.calculated and not st.session_state.signal_database.empty:
        st.dataframe(st.session_state.signal_database.head(50), use_container_width=True, hide_index=True)
    else: st.info("💡 請先啟動沙盒運算。")

with tab_rank_val:
    st.header("📊 Same-Day Paired Difference Bootstrap Ranking 驗證")
    st.caption(f"判定結果: **{st.session_state.rank_pred_status}**")
    if st.session_state.calculated and not st.session_state.rank_val_report.empty:
        st.dataframe(st.session_state.rank_val_report, use_container_width=True, hide_index=True)
    else: st.info("💡 請先啟動沙盒運算。")

with tab_gate_oos:
    st.header(f"🔄 Rolling OOS Monitoring | Status: **{st.session_state.gate_oos_status}**")
    if st.session_state.calculated and not st.session_state.gate_oos_report.empty:
        st.dataframe(st.session_state.gate_oos_report, use_container_width=True, hide_index=True)
    else: st.info("💡 請先啟動沙盒運算。")

with tab_perf:
    st.header("⚡ 效能 Profiler 與 Horizon 成熟度稽核報告")
    if st.session_state.calculated:
        c_p1, c_p2 = st.columns(2)
        with c_p1:
            st.subheader("⏱ Stage Runtime Profile")
            st.dataframe(st.session_state.performance_report, use_container_width=True, hide_index=True)
        with c_p2:
            st.subheader("🔍 Horizon Maturity Audit")
            st.dataframe(st.session_state.horizon_audit, use_container_width=True, hide_index=True)
    else: st.info("💡 請先啟動沙盒運算。")

with tab_diagnostic:
    st.header("🧪 32 項系統測試與診斷")
    if st.session_state.test_suite_results is not None and not pd.DataFrame(st.session_state.test_suite_results).empty:
        st.dataframe(pd.DataFrame(st.session_state.test_suite_results), use_container_width=True, hide_index=True)
    else: st.info("💡 請先啟動沙盒運算。")

with tab_export:
    st.header("📥 V09.4.2 Modular Artifacts 匯出中心")
    if st.session_state.calculated and not st.session_state.signal_database.empty:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.download_button("💾 strategy_event_history_v0942.csv", st.session_state.signal_database.to_csv(index=False).encode('utf-8-sig'), "strategy_event_history_v0942.csv", "text/csv")
        c2.download_button("💾 stock_event_history_v0942.csv", st.session_state.stock_database.to_csv(index=False).encode('utf-8-sig'), "stock_event_history_v0942.csv", "text/csv")
        c3.download_button("💾 daily_stock_ranking_v0942.csv", st.session_state.daily_stock_ranking.to_csv(index=False).encode('utf-8-sig'), "daily_stock_ranking_v0942.csv", "text/csv")
        c4.download_button("💾 gate_oos_validation_v0942.csv", st.session_state.gate_oos_report.to_csv(index=False).encode('utf-8-sig'), "gate_oos_validation_v0942.csv", "text/csv")
        c5.download_button("💾 ranking_validation_v0942.csv", st.session_state.rank_val_report.to_csv(index=False).encode('utf-8-sig'), "ranking_validation_v0942.csv", "text/csv")
        
        st.markdown("---")
        c6, c7, c8, c9, c10 = st.columns(5)
        c6.download_button("💾 test_report_v0942.csv", pd.DataFrame(st.session_state.test_suite_results).to_csv(index=False).encode('utf-8-sig'), "test_report_v0942.csv", "text/csv")
        c7.download_button("💾 run_metadata_v0942.csv", st.session_state.run_metadata.to_csv(index=False).encode('utf-8-sig'), "run_metadata_v0942.csv", "text/csv")
        c8.download_button("💾 performance_report_v0942.csv", st.session_state.performance_report.to_csv(index=False).encode('utf-8-sig'), "performance_report_v0942.csv", "text/csv")
        c9.download_button("💾 horizon_maturity_audit_v0942.csv", st.session_state.horizon_audit.to_csv(index=False).encode('utf-8-sig'), "horizon_maturity_audit_v0942.csv", "text/csv")
        c10.download_button("💾 ticker_master.csv", st.session_state.ticker_master_export.to_csv(index=False).encode('utf-8-sig'), "ticker_master.csv", "text/csv")
    else: st.info("💡 請先啟動沙盒運算。")
