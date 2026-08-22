import numpy as np
import pandas as pd
from core.config import MIN_OOS_VALID_WINDOWS, generate_run_id

def create_stock_event_history_v094(df_strat_in, run_id=None):
    if run_id is None:
        run_id = generate_run_id()
        
    stock_rows = []
    grouped = df_strat_in.groupby(['Market_Event_ID', 'Ticker', 'Signal_Date'], sort=False)
    
    for (mkt_event_id, ticker, sig_date), group in grouped:
        triggered_strats = group['Strategy'].tolist()
        strat_count = len(triggered_strats)
        
        best_row = group.sort_values(
            by=['Hist_T5_UpProb_WilsonLow', 'Net_Expectancy_T5', 'Hist_Excess_vs_Market_Median_T5'],
            ascending=[False, False, False],
            na_position='last'
        ).iloc[0]
        
        sim_n = best_row['Similarity_N_T5'] if pd.notna(best_row['Similarity_N_T5']) else 0
        wilson_low = best_row['Hist_T5_UpProb_WilsonLow']
        exp_t5 = best_row['Net_Expectancy_T5']
        excess_mkt = best_row['Hist_Excess_vs_Market_Median_T5']
        downside_risk = best_row['Downside_Risk_5D']
        
        fail_reasons = []
        if sim_n < 30: fail_reasons.append(f"N<30 ({sim_n})")
        if pd.isna(wilson_low) or wilson_low <= 0.50:
            val_str = f"{wilson_low:.3f}" if pd.notna(wilson_low) else 'NaN'
            fail_reasons.append(f"WilsonLow<=0.50 ({val_str})")
        if pd.isna(exp_t5) or exp_t5 <= 0:
            val_str = f"{exp_t5:.4f}" if pd.notna(exp_t5) else 'NaN'
            fail_reasons.append(f"Expectancy<=0 ({val_str})")
        if pd.isna(excess_mkt) or excess_mkt <= 0:
            val_str = f"{excess_mkt:.4f}" if pd.notna(excess_mkt) else 'NaN'
            fail_reasons.append(f"ExcessMedian<=0 ({val_str})")
            
        gate_pass = (len(fail_reasons) == 0)
        fail_reason_str = "; ".join(fail_reasons) if not gate_pass else "PASS"
        
        stock_rows.append({
            "Run_ID": run_id,
            "Market_Event_ID": mkt_event_id,
            "Signal_Date": sig_date,
            "Ticker": ticker,
            "Asset_Type": best_row['Asset_Type'],
            "Sector": best_row['Sector_Cluster'],
            "Triggered_Strategies": ", ".join(triggered_strats),
            "Strategy_Count": strat_count,
            "Best_Strategy": best_row['Strategy'],
            "Stock_Gate_Pass": gate_pass,
            "Stock_Gate_Fail_Reason": fail_reason_str,
            "Similarity_N_T5": sim_n,
            "WilsonLow": wilson_low,
            "Historical_UpProb": best_row['Hist_T5_UpProb'],
            "Net_Expectancy": exp_t5,
            "Historical_Excess": excess_mkt,
            "Downside_Risk": downside_risk,
            "T1_Return": best_row['T1_Return'],
            "T3_Return": best_row['T3_Return'],
            "T5_Return": best_row['T5_Return'],
            "T10_Return": best_row['T10_Return'],
            "T20_Return": best_row['T20_Return'],
            "MAE_5D": best_row['MAE_5D'],
            "Event_SPY_Return_T5": best_row['Event_SPY_Gross_Return_T5'],
            "Event_Excess_vs_SPY_T5": best_row['Event_Excess_vs_SPY_GrossBenchmark'],
            "Outcome_Available_Date_T5": best_row['Outcome_Available_Date_T5'],
            "Candidate_Status_Is_PostHoc": True
        })
        
    return pd.DataFrame(stock_rows)

def run_stock_level_gate_oos_expanding_v094(df_stock_events_in, run_id=None):
    if run_id is None:
        run_id = generate_run_id()

    df = df_stock_events_in.sort_values('Signal_Date').reset_index(drop=True)
    unique_dates = df['Signal_Date'].unique()
    
    oos_window_size = 60
    step_size = 30
    
    if len(unique_dates) < oos_window_size:
        return pd.DataFrame(), "INCONCLUSIVE", 0.0, 0.0, 0.0, 0.0, 0, 0

    window_records = []
    win_id = 1
    start_idx = 180 if len(unique_dates) >= 240 else 0

    while start_idx + oos_window_size <= len(unique_dates):
        oos_dates = unique_dates[start_idx : start_idx + oos_window_size]
        oos_events = df[df['Signal_Date'].isin(oos_dates)].copy()
        
        eligible_events = oos_events[oos_events['Stock_Gate_Pass'] == True].dropna(subset=['T5_Return'])
        non_eligible_events = oos_events[oos_events['Stock_Gate_Pass'] == False].dropna(subset=['T5_Return'])
        
        el_n, nel_n = len(eligible_events), len(non_eligible_events)
        
        el_uprate = float(np.mean(eligible_events['T5_Return'] > 0)) if el_n > 0 else np.nan
        nel_uprate = float(np.mean(non_eligible_events['T5_Return'] > 0)) if nel_n > 0 else np.nan
        el_mean = float(np.mean(eligible_events['T5_Return'])) if el_n > 0 else np.nan
        nel_mean = float(np.mean(non_eligible_events['T5_Return'])) if nel_n > 0 else np.nan
        el_med = float(np.median(eligible_events['T5_Return'])) if el_n > 0 else np.nan
        nel_med = float(np.median(non_eligible_events['T5_Return'])) if nel_n > 0 else np.nan
        el_excess_med = float(np.median(eligible_events['Event_Excess_vs_SPY_T5'].dropna())) if el_n > 0 else np.nan
        nel_excess_med = float(np.median(non_eligible_events['Event_Excess_vs_SPY_T5'].dropna())) if nel_n > 0 else np.nan
        el_mae_med = float(np.median(eligible_events['MAE_5D'].dropna())) if el_n > 0 else np.nan
        nel_mae_med = float(np.median(non_eligible_events['MAE_5D'].dropna())) if nel_n > 0 else np.nan
        
        uprate_lift = (el_uprate - nel_uprate) if not np.isnan(el_uprate) and not np.isnan(nel_uprate) else np.nan
        mean_return_lift = (el_mean - nel_mean) if not np.isnan(el_mean) and not np.isnan(nel_mean) else np.nan
        median_return_lift = (el_med - nel_med) if not np.isnan(el_med) and not np.isnan(nel_med) else np.nan
        excess_lift = (el_excess_med - nel_excess_med) if not np.isnan(el_excess_med) and not np.isnan(nel_excess_med) else np.nan
        mae_lift = (abs(el_mae_med) - abs(nel_mae_med)) if not np.isnan(el_mae_med) and not np.isnan(nel_mae_med) else np.nan
        
        is_valid_win = (el_n >= 5) and (nel_n >= 30)

        window_records.append({
            "Run_ID": run_id, "Window_ID": f"Win_{win_id:02d}",
            "OOS_Start_Date": oos_dates[0], "OOS_End_Date": oos_dates[-1],
            "Eligible_Stock_N": el_n, "NonEligible_Stock_N": nel_n,
            "Is_Valid_Window": is_valid_win,
            "Eligible_T5_UpRate": el_uprate, "NonEligible_T5_UpRate": nel_uprate,
            "Eligible_T5_Mean": el_mean, "NonEligible_T5_Mean": nel_mean,
            "Eligible_T5_Median": el_med, "NonEligible_T5_Median": nel_med,
            "Eligible_Excess_Median": el_excess_med, "NonEligible_Excess_Median": nel_excess_med,
            "Eligible_MAE_Median": el_mae_med, "NonEligible_MAE_Median": nel_mae_med,
            "UpRate_Lift": uprate_lift, "Mean_Return_Lift": mean_return_lift,
            "Median_Return_Lift": median_return_lift, "Excess_Lift": excess_lift, "MAE_Lift": mae_lift
        })
        win_id += 1
        start_idx += step_size

    df_windows = pd.DataFrame(window_records)
    if df_windows.empty: return df_windows, "INCONCLUSIVE", 0.0, 0.0, 0.0, 0.0, 0, 0

    valid_wins = df_windows[df_windows['Is_Valid_Window'] == True]
    valid_window_count = len(valid_wins)
    total_window_count = len(df_windows)

    if valid_window_count < MIN_OOS_VALID_WINDOWS:
        gate_oos_status = "INCONCLUSIVE"
        pos_uprate_ratio = float(np.mean(valid_wins['UpRate_Lift'] > 0)) if valid_window_count > 0 else 0.0
        pos_mean_ratio = float(np.mean(valid_wins['Mean_Return_Lift'] > 0)) if valid_window_count > 0 else 0.0
        pos_median_ratio = float(np.mean(valid_wins['Median_Return_Lift'] > 0)) if valid_window_count > 0 else 0.0
        pos_excess_ratio = float(np.mean(valid_wins['Excess_Lift'] > 0)) if valid_window_count > 0 else 0.0
    else:
        pos_uprate_ratio = float(np.mean(valid_wins['UpRate_Lift'] > 0))
        pos_mean_ratio = float(np.mean(valid_wins['Mean_Return_Lift'] > 0))
        pos_median_ratio = float(np.mean(valid_wins['Median_Return_Lift'] > 0))
        pos_excess_ratio = float(np.mean(valid_wins['Excess_Lift'] > 0))

        if (pos_median_ratio >= 0.60) and (pos_excess_ratio >= 0.60):
            gate_oos_status = "SUPPORTED"
        else:
            gate_oos_status = "NOT_SUPPORTED"

    return df_windows, gate_oos_status, pos_uprate_ratio, pos_mean_ratio, pos_median_ratio, pos_excess_ratio, total_window_count, valid_window_count

def assign_candidate_status_v0941(row, gate_oos_stat):
    pass_flag = row['Stock_Gate_Pass']
    sim_n = row['Similarity_N_T5']
    wilson_low = row['WilsonLow']
    
    if pass_flag:
        if gate_oos_stat == "SUPPORTED":
            return "HIGH_CONFIDENCE"
        elif gate_oos_stat == "INCONCLUSIVE":
            return "GATE_PASS_OOS_INCONCLUSIVE"
        else:
            return "GATE_PASS_OOS_UNSUPPORTED"
    elif sim_n >= 10 and pd.notna(wilson_low) and wilson_low > 0.45:
        return "WATCHLIST"
    elif sim_n < 10:
        return "INSUFFICIENT_EVIDENCE"
    else:
        return "REJECTED"

def generate_daily_stock_ranking_v094(df_stock_events_in, gate_oos_stat):
    latest_date = df_stock_events_in['Signal_Date'].max()
    scan_df = df_stock_events_in[df_stock_events_in['Signal_Date'] == latest_date].copy()
    
    scan_df['Rank_UpProb'] = scan_df['WilsonLow'].fillna(-1.0)
    scan_df['Rank_Exp'] = scan_df['Net_Expectancy'].fillna(-1.0)
    scan_df['Rank_Excess'] = scan_df['Historical_Excess'].fillna(-1.0)
    scan_df['Rank_Downside'] = scan_df['Downside_Risk'].fillna(999.0)

    scan_df = scan_df.sort_values(
        by=['Rank_UpProb', 'Rank_Exp', 'Rank_Excess', 'Rank_Downside'],
        ascending=[False, False, False, True]
    ).reset_index(drop=True)

    scan_df['Daily_Rank'] = scan_df.index + 1
    scan_df['Candidate_Status'] = [assign_candidate_status_v0941(r, gate_oos_stat) for _, r in scan_df.iterrows()]
    
    cols = [
        "Run_ID", "Signal_Date", "Daily_Rank", "Ticker", "Asset_Type", "Sector",
        "Stock_Gate_Pass", "Stock_Gate_Fail_Reason", "Candidate_Status", "Candidate_Status_Is_PostHoc",
        "Triggered_Strategies", "Strategy_Count", "Best_Strategy",
        "Similarity_N_T5", "WilsonLow", "Historical_UpProb", "Net_Expectancy", "Historical_Excess", "Downside_Risk"
    ]
    return scan_df[cols]

def run_ranking_validation_v094(df_stock_events_in, run_id=None):
    if run_id is None:
        run_id = generate_run_id()

    daily_ranks = []
    for sig_date, group in df_stock_events_in.groupby('Signal_Date'):
        g = group.copy()
        g['Rank_UpProb'] = g['WilsonLow'].fillna(-1.0)
        g['Rank_Exp'] = g['Net_Expectancy'].fillna(-1.0)
        g['Rank_Excess'] = g['Historical_Excess'].fillna(-1.0)
        g['Rank_Downside'] = g['Downside_Risk'].fillna(999.0)

        g = g.sort_values(
            by=['Rank_UpProb', 'Rank_Exp', 'Rank_Excess', 'Rank_Downside'],
            ascending=[False, False, False, True]
        ).reset_index(drop=True)
        g['Daily_Rank'] = g.index + 1
        daily_ranks.append(g)
        
    df_all_ranks = pd.concat(daily_ranks, ignore_index=True)
    
    def assign_tier(r):
        if r <= 10: return "1-10"
        elif r <= 30: return "11-30"
        elif r <= 50: return "31-50"
        else: return "51+"
        
    df_all_ranks['Rank_Tier'] = df_all_ranks['Daily_Rank'].apply(assign_tier)
    
    tier_records = []
    for tier_name in ["1-10", "11-30", "31-50", "51+"]:
        sub = df_all_ranks[df_all_ranks['Rank_Tier'] == tier_name]
        n_samples = len(sub)
        rec = {"Run_ID": run_id, "Rank_Tier": tier_name, "Sample_N": n_samples}
        for h in [1, 3, 5, 10, 20]:
            col_ret = f"T{h}_Return"
            valid_ret = sub[col_ret].dropna()
            rec[f"T{h}_UpRate"] = float(np.mean(valid_ret > 0)) if len(valid_ret)>0 else np.nan
            rec[f"T{h}_Mean"] = float(np.mean(valid_ret)) if len(valid_ret)>0 else np.nan
            rec[f"T{h}_Median"] = float(np.median(valid_ret)) if len(valid_ret)>0 else np.nan
            
        rec["T5_Excess_Median"] = float(np.median(sub['Event_Excess_vs_SPY_T5'].dropna())) if len(sub['Event_Excess_vs_SPY_T5'].dropna())>0 else np.nan
        rec["MAE_Median"] = float(np.median(sub['MAE_5D'].dropna())) if len(sub['MAE_5D'].dropna())>0 else np.nan
        tier_records.append(rec)
        
    df_tier_summary = pd.DataFrame(tier_records)
    
    daily_diffs = []
    for sig_date, group in df_all_ranks.groupby('Signal_Date'):
        top10 = group[group['Daily_Rank'] <= 10].dropna(subset=['T5_Return'])
        bot10 = group[group['Daily_Rank'] > 10].sort_values('Daily_Rank', ascending=False).head(10).dropna(subset=['T5_Return'])
        
        if len(top10) > 0 and len(bot10) > 0:
            top_med, bot_med = np.median(top10['T5_Return']), np.median(bot10['T5_Return'])
            top_mean, bot_mean = np.mean(top10['T5_Return']), np.mean(bot10['T5_Return'])
            daily_diffs.append({
                "Signal_Date": sig_date,
                "Daily_T5_Median_Diff": top_med - bot_med,
                "Daily_T5_Mean_Diff": top_mean - bot_mean
            })
            
    df_daily_diffs = pd.DataFrame(daily_diffs)
    
    np.random.seed(42)
    paired_diffs = df_daily_diffs['Daily_T5_Median_Diff'].values if not df_daily_diffs.empty else np.array([0.0])
    boot_diffs = []
    for _ in range(1000):
        s_paired = np.random.choice(paired_diffs, size=len(paired_diffs), replace=True)
        boot_diffs.append(np.mean(s_paired))
        
    ci_low, ci_high = float(np.percentile(boot_diffs, 2.5)), float(np.percentile(boot_diffs, 97.5))
    top_t5_med = df_tier_summary[df_tier_summary['Rank_Tier']=="1-10"]['T5_Median'].values[0] if not df_tier_summary.empty else 0.0
    bot_t5_med = df_tier_summary[df_tier_summary['Rank_Tier']=="51+"]['T5_Median'].values[0] if not df_tier_summary.empty else 0.0
    
    ranking_status = "SUPPORTED" if (top_t5_med > bot_t5_med and ci_low > 0) else "NOT_SUPPORTED"
    return df_tier_summary, ranking_status, ci_low, ci_high
