import os
import sys
import argparse
import pandas as pd
import numpy as np

FLOAT_TOLERANCE = 1e-12

REQUIRED_STRATEGY_COLS = [
    "Signal_ID", "Market_Event_ID", "Ticker", "Strategy", "Signal_Date",
    "Asset_Type", "Sector_Cluster", "Market_Regime_Cluster", "VIX", "Market_Bull",
    "RSI14", "BB_State", "RS20", "Score_7D", "7D_Bucket", "RS20_Bucket",
    "Entry_Price_T1Open", "Outcome_Available_Date_T1", "Outcome_Available_Date_T3",
    "Outcome_Available_Date_T5", "Outcome_Available_Date_T10", "Outcome_Available_Date_T20",
    "T1_Return", "T3_Return", "T5_Return", "T10_Return", "T20_Return",
    "MFE_5D", "MAE_5D", "Event_SPY_Gross_Return_T5", "Event_Excess_vs_SPY_GrossBenchmark",
    "Similarity_Level", "Similarity_Definition", "Hist_T1_N", "Hist_T3_N", "Hist_T5_N",
    "Hist_T10_N", "Hist_T20_N", "Hist_T1_UpProb", "Hist_T3_UpProb", "Hist_T5_UpProb",
    "Hist_T10_UpProb", "Hist_T20_UpProb", "Stats_AsOf_T1", "Stats_AsOf_T3", "Stats_AsOf_T5",
    "Stats_AsOf_T10", "Stats_AsOf_T20", "Similarity_N_T5", "Hist_T5_UpProb_WilsonLow",
    "Hist_T5_UpProb_WilsonHigh", "Net_Expectancy_T5", "Hist_T5_Median", "Hist_T5_IQR",
    "Downside_Risk_5D", "Hist_Excess_vs_Market_Median_T5", "Historical_Edge_Score",
    "Confidence_Level", "Regime_Fit_Score", "Current_Setup_Score", "Decision_Score"
]

REQUIRED_STOCK_EVENT_COLS = [
    "Market_Event_ID", "Ticker", "Signal_Date", "Asset_Type", "Sector",
    "Triggered_Strategies", "Strategy_Count", "Best_Strategy", "Stock_Gate_Pass",
    "Stock_Gate_Fail_Reason", "Similarity_N_T5", "WilsonLow", "Historical_UpProb",
    "Net_Expectancy", "Historical_Excess", "Downside_Risk", "T1_Return", "T3_Return",
    "T5_Return", "T10_Return", "T20_Return", "MAE_5D", "Event_SPY_Return_T5",
    "Event_Excess_vs_SPY_T5", "Outcome_Available_Date_T5", "Candidate_Status_Is_PostHoc",
    "Candidate_Status"
]

REQUIRED_GATE_OOS_COLS = [
    "Window_ID", "OOS_Start_Date", "OOS_End_Date", "Eligible_Stock_N", "NonEligible_Stock_N",
    "Is_Valid_Window", "Eligible_T5_UpRate", "NonEligible_T5_UpRate", "Eligible_T5_Mean",
    "NonEligible_T5_Mean", "Eligible_T5_Median", "NonEligible_T5_Median", "Eligible_Excess_Median",
    "NonEligible_Excess_Median", "Eligible_MAE_Median", "NonEligible_MAE_Median", "UpRate_Lift",
    "Mean_Return_Lift", "Median_Return_Lift", "Excess_Lift", "MAE_Lift"
]

REQUIRED_RANKING_VAL_COLS = [
    "Rank_Tier", "Sample_N", "T1_UpRate", "T1_Mean", "T1_Median", "T3_UpRate", "T3_Mean",
    "T3_Median", "T5_UpRate", "T5_Mean", "T5_Median", "T10_UpRate", "T10_Mean", "T10_Median",
    "T20_UpRate", "T20_Mean", "T20_Median", "T5_Excess_Median", "MAE_Median"
]

def check_nan_mask_and_values(df_g, df_m, cols):
    for col in cols:
        g_series = df_g[col]
        m_series = df_m[col]
        
        g_isna = g_series.isna()
        m_isna = m_series.isna()
        if not g_isna.equals(m_isna):
            return False, f"NaN mask mismatch in column {col}"
        
        valid_mask = ~g_isna
        if not valid_mask.any():
            continue
            
        v_g = g_series[valid_mask]
        v_m = m_series[valid_mask]
        
        if pd.api.types.is_numeric_dtype(v_g) and pd.api.types.is_numeric_dtype(v_m):
            diff = (v_g.astype(float) - v_m.astype(float)).abs()
            if (diff > FLOAT_TOLERANCE).any():
                max_diff = diff.max()
                return False, f"Value mismatch in numeric column {col} (max diff: {max_diff})"
        else:
            if not (v_g.astype(str) == v_m.astype(str)).all():
                return False, f"Value mismatch in string/categorical column {col}"
    return True, "OK"

def verify_schema(df_g, df_m, required_cols):
    missing_g = [c for c in required_cols if c not in df_g.columns]
    missing_m = [c for c in required_cols if c not in df_m.columns]
    if missing_m:
        return False, f"MISSING_COLUMN:{missing_m[0]}"
    if missing_g:
        return False, f"GOLDEN_MISSING_COLUMN:{missing_g[0]}"
    return True, "OK"

def run_parity_check(golden_dir, modular_dir, output_file="parity_report.csv"):
    report = {
        "DATA_COMPARABLE": "FAIL",
        "Signal_ID_Parity": "FAIL",
        "Strategy_Schema_Parity": "FAIL",
        "Outcome_Parity": "FAIL",
        "Evidence_Parity": "FAIL",
        "Market_Event_ID_Parity": "FAIL",
        "Stock_Event_Parity": "FAIL",
        "Daily_Ranking_Parity": "FAIL",
        "Gate_OOS_Parity": "FAIL",
        "Ranking_Validation_Parity": "FAIL",
        "Test_Status_Parity": "FAIL",
        "T21_Parity": "FAIL",
        "Final_Parity_Status": "FAIL"
    }

    g_meta_path = os.path.join(golden_dir, "run_metadata_v0941b_T21fix_candidate.csv")
    m_meta_path = os.path.join(modular_dir, "run_metadata_v0942.csv")

    if not os.path.exists(g_meta_path) or not os.path.exists(m_meta_path):
        report["Final_Parity_Status"] = "DATA_NOT_COMPARABLE"
        save_report(report, output_file)
        return report

    df_g_meta = pd.read_csv(g_meta_path).set_index("Metric") if "Metric" in pd.read_csv(g_meta_path).columns else pd.read_csv(g_meta_path)
    df_m_meta = pd.read_csv(m_meta_path).set_index("Metric") if "Metric" in pd.read_csv(m_meta_path).columns else pd.read_csv(m_meta_path)

    hash_keys = ["Universe_Hash", "Config_Hash", "Data_Snapshot_ID"]
    comparable = True
    for hk in hash_keys:
        val_g = df_g_meta.loc[hk, "Value"] if hk in df_g_meta.index else None
        val_m = df_m_meta.loc[hk, "Value"] if hk in df_m_meta.index else None
        if val_g is None or val_m is None or str(val_g).strip() != str(val_m).strip():
            comparable = False
            break

    if not comparable:
        report["DATA_COMPARABLE"] = "FALSE"
        report["Final_Parity_Status"] = "DATA_NOT_COMPARABLE"
        save_report(report, output_file)
        return report

    report["DATA_COMPARABLE"] = "TRUE"

    # 1. Strategy Events
    g_strat = os.path.join(golden_dir, "strategy_event_history_v0941b_T21fix_candidate.csv")
    m_strat = os.path.join(modular_dir, "strategy_event_history_v0942.csv")
    if os.path.exists(g_strat) and os.path.exists(m_strat):
        df_gs = pd.read_csv(g_strat)
        df_ms = pd.read_csv(m_strat)

        schema_ok, detail = verify_schema(df_gs, df_ms, REQUIRED_STRATEGY_COLS)
        if schema_ok:
            report["Strategy_Schema_Parity"] = "PASS"
            if df_gs["Signal_ID"].is_unique and df_ms["Signal_ID"].is_unique and set(df_gs["Signal_ID"]) == set(df_ms["Signal_ID"]):
                report["Signal_ID_Parity"] = "PASS"
                df_gs = df_gs.sort_values("Signal_ID").reset_index(drop=True)
                df_ms = df_ms.sort_values("Signal_ID").reset_index(drop=True)

                out_cols = [c for c in REQUIRED_STRATEGY_COLS if "Return" in c or "MFE" in c or "MAE" in c or "Outcome" in c]
                ev_cols = [c for c in REQUIRED_STRATEGY_COLS if "Hist_" in c or "Similarity" in c or "Expectancy" in c or "Score" in c]
                
                ok_out, _ = check_nan_mask_and_values(df_gs, df_ms, out_cols)
                if ok_out:
                    report["Outcome_Parity"] = "PASS"

                ok_ev, _ = check_nan_mask_and_values(df_gs, df_ms, ev_cols)
                if ok_ev:
                    report["Evidence_Parity"] = "PASS"

    # 2. Stock Events
    g_stock = os.path.join(golden_dir, "stock_event_history_v0941b_T21fix_candidate.csv")
    m_stock = os.path.join(modular_dir, "stock_event_history_v0942.csv")
    if os.path.exists(g_stock) and os.path.exists(m_stock):
        df_gk = pd.read_csv(g_stock)
        df_mk = pd.read_csv(m_stock)

        schema_ok, _ = verify_schema(df_gk, df_mk, REQUIRED_STOCK_EVENT_COLS)
        if schema_ok:
            if df_gk["Market_Event_ID"].is_unique and df_mk["Market_Event_ID"].is_unique and set(df_gk["Market_Event_ID"]) == set(df_mk["Market_Event_ID"]):
                report["Market_Event_ID_Parity"] = "PASS"
                df_gk = df_gk.sort_values("Market_Event_ID").reset_index(drop=True)
                df_mk = df_mk.sort_values("Market_Event_ID").reset_index(drop=True)
                ok_st, _ = check_nan_mask_and_values(df_gk, df_mk, REQUIRED_STOCK_EVENT_COLS)
                if ok_st:
                    report["Stock_Event_Parity"] = "PASS"

    # 3. Daily Ranking
    g_rank = os.path.join(golden_dir, "daily_stock_ranking_v0941b_T21fix_candidate.csv")
    m_rank = os.path.join(modular_dir, "daily_stock_ranking_v0942.csv")
    if os.path.exists(g_rank) and os.path.exists(m_rank):
        df_gr = pd.read_csv(g_rank)
        df_mr = pd.read_csv(m_rank)
        df_gr["pk"] = df_gr["Signal_Date"].astype(str) + "_" + df_gr["Ticker"].astype(str)
        df_mr["pk"] = df_mr["Signal_Date"].astype(str) + "_" + df_mr["Ticker"].astype(str)
        if set(df_gr["pk"]) == set(df_mr["pk"]):
            df_gr = df_gr.sort_values("pk").reset_index(drop=True)
            df_mr = df_mr.sort_values("pk").reset_index(drop=True)
            ok_rk, _ = check_nan_mask_and_values(df_gr, df_mr, [c for c in df_gr.columns if c != "pk"])
            if ok_rk:
                report["Daily_Ranking_Parity"] = "PASS"

    # 4. Gate OOS Validation
    g_goos = os.path.join(golden_dir, "gate_oos_validation_v0941b_T21fix_candidate.csv")
    m_goos = os.path.join(modular_dir, "gate_oos_validation_v0942.csv")
    if os.path.exists(g_goos) and os.path.exists(m_goos):
        df_gg = pd.read_csv(g_goos)
        df_mg = pd.read_csv(m_goos)
        schema_ok, _ = verify_schema(df_gg, df_mg, REQUIRED_GATE_OOS_COLS)
        if schema_ok and set(df_gg["Window_ID"]) == set(df_mg["Window_ID"]):
            df_gg = df_gg.sort_values("Window_ID").reset_index(drop=True)
            df_mg = df_mg.sort_values("Window_ID").reset_index(drop=True)
            ok_go, _ = check_nan_mask_and_values(df_gg, df_mg, REQUIRED_GATE_OOS_COLS)
            if ok_go:
                report["Gate_OOS_Parity"] = "PASS"

    # 5. Ranking Validation
    g_rkval = os.path.join(golden_dir, "ranking_validation_v0941b_T21fix_candidate.csv")
    m_rkval = os.path.join(modular_dir, "ranking_validation_v0942.csv")
    if os.path.exists(g_rkval) and os.path.exists(m_rkval):
        df_grv = pd.read_csv(g_rkval)
        df_mrv = pd.read_csv(m_rkval)
        schema_ok, _ = verify_schema(df_grv, df_mrv, REQUIRED_RANKING_VAL_COLS)
        if schema_ok and set(df_grv["Rank_Tier"]) == set(df_mrv["Rank_Tier"]):
            df_grv = df_grv.sort_values("Rank_Tier").reset_index(drop=True)
            df_mrv = df_mrv.sort_values("Rank_Tier").reset_index(drop=True)
            ok_rv, _ = check_nan_mask_and_values(df_grv, df_mrv, REQUIRED_RANKING_VAL_COLS)
            if ok_rv:
                report["Ranking_Validation_Parity"] = "PASS"

    # 6. Test Report & T21
    g_tr = os.path.join(golden_dir, "test_report_v0941b_T21fix_candidate.csv")
    m_tr = os.path.join(modular_dir, "test_report_v0942.csv")
    if os.path.exists(g_tr) and os.path.exists(m_tr):
        df_gtr = pd.read_csv(g_tr)
        df_mtr = pd.read_csv(m_tr)
        if "Test_ID" in df_gtr.columns and "Test_ID" in df_mtr.columns:
            if set(df_gtr["Test_ID"]) == set(df_mtr["Test_ID"]):
                df_gtr = df_gtr.sort_values("Test_ID").reset_index(drop=True)
                df_mtr = df_mtr.sort_values("Test_ID").reset_index(drop=True)
                if (df_gtr["Status"].astype(str) == df_mtr["Status"].astype(str)).all():
                    report["Test_Status_Parity"] = "PASS"
                
                t21_row = df_mtr[df_mtr["Test_ID"] == "T21"]
                if not t21_row.empty:
                    detail_str = str(t21_row.iloc[0].get("Detail", ""))
                    if ("Samples_Checked: 30" in detail_str or "30" in detail_str) and \
                       ("Horizons_Checked: 5" in detail_str or "5" in detail_str) and \
                       ("Total_Comparisons: 150" in detail_str or "150" in detail_str):
                        report["T21_Parity"] = "PASS"

    all_pass = all(v == "PASS" for k, v in report.items() if k not in ["DATA_COMPARABLE", "Final_Parity_Status"])
    report["Final_Parity_Status"] = "PASS" if all_pass else "FAIL"

    save_report(report, output_file)
    return report

def save_report(report, filename):
    df = pd.DataFrame(list(report.items()), columns=["Parity_Item", "Status"])
    df.to_csv(filename, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V09.4.2 Parity Checker")
    parser.add_argument("--golden_dir", required=True, help="Path to golden files directory")
    parser.add_argument("--modular_dir", required=True, help="Path to modular outputs directory")
    parser.add_argument("--output", default="parity_report.csv", help="Path to output CSV report")
    args = parser.parse_args()

    run_parity_check(args.golden_dir, args.modular_dir, args.output)
