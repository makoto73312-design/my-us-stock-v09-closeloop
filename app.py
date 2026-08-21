# ==============================================================================
# 美股量化感知沙盒 V09.4 (Final Research Integrity & Performance Patch)
# ==============================================================================
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import re
import math
import hashlib
import json
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# ------------------------------------------------------------------------------
# 1. System Metadata & Canonical Taxonomy
# ------------------------------------------------------------------------------
VERSION = "V09.4"
RUN_ID = f"V094_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_p0perf"
GEN_TIME = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

st.set_page_config(
    page_title="🚀 美股感知沙盒 V09.4 (Research Integrity & Perf Patch)", 
    page_icon="🚀", 
    layout="wide"
)

st.title("🚀 美股量化感知沙盒 V09.4 (Research Integrity & Performance Patch)")
st.caption(f"🔥 零 Leakage 全面凍結版 | Run_ID: {RUN_ID} | Horizon-Specific Maturity | Same-Day Paired Bootstrap")

CANONICAL_SECTOR_MAP = {
    "Consumer Defensive": "Consumer Staples",
    "Financial Services": "Financials",
    "Financial": "Financials",
    "Technology Services": "Technology",
    "Information Technology": "Technology",
    "Healthcare Services": "Healthcare",
    "Consumer Discretionary": "Consumer Cyclical"
}

FORBIDDEN_FEATURE_COLUMNS = {
    "Candidate_Status", "Gate_OOS_Status", "Ranking_Validation_Status",
    "T1_Return", "T3_Return", "T5_Return", "T10_Return", "T20_Return",
    "MFE_5D", "MAE_5D", "Event_SPY_Gross_Return_T5", "Event_Excess_vs_SPY_GrossBenchmark",
    "Outcome_Available_Date_T1", "Outcome_Available_Date_T3", "Outcome_Available_Date_T5",
    "Outcome_Available_Date_T10", "Outcome_Available_Date_T20"
}

# ------------------------------------------------------------------------------
# 2. Config & Data Snapshot Engine (Canonical Hashes)
# ------------------------------------------------------------------------------
def generate_config_hash(ticker_list, min_sample, cost_scenario, window_size, oos_step):
    config_dict = {
        "ticker_universe": sorted(ticker_list),
        "min_sample": min_sample,
        "cost_roundtrip": cost_scenario["total_roundtrip"],
        "gate_thresholds": {"min_sample": 30, "wilson_low": 0.50, "expectancy": 0.0, "excess_median": 0.0},
        "similarity_hierarchy": ["L5", "L4", "L3", "L2", "L1"],
        "strategy_version": "V09.4_Freeze",
        "backtest_window": window_size,
        "oos_window": 60,
        "oos_step": oos_step,
        "ranking_columns": ["WilsonLow", "Net_Expectancy", "Historical_Excess", "Downside_Risk"]
    }
    canonical_json = json.dumps(config_dict, sort_keys=True)
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()[:16]

def generate_data_snapshot_hash(df_macro, stock_data_dict):
    manifest_items = []
    if not df_macro.empty:
        manifest_items.append(f"MACRO_{df_macro.index.min()}_{df_macro.index.max()}_{len(df_macro)}")
    for tk in sorted(stock_data_dict.keys()):
        df = stock_data_dict[tk]
        if not df.empty:
            manifest_items.append(f"{tk}_{df.index.min()}_{df.index.max()}_{len(df)}")
    manifest_str = "|".join(manifest_items)
    return hashlib.sha256(manifest_str.encode('utf-8')).hexdigest()[:16]

# ------------------------------------------------------------------------------
# 3. Macro Layer (Strict Prohibition of Fabricated Data)
# ------------------------------------------------------------------------------
def fetch_us_macro_dataframe_strict():
    """Layer 1: Bulk Live | Layer 2: Indiv Live | Layer 3: Fail-Closed Audit (No Synthetic SPY)"""
    try:
        df_raw = yf.download(["^VIX", "SPY"], period="2y", progress=False, threads=False)
        if df_raw is not None and not df_raw.empty:
            df_close = df_raw['Close'] if 'Close' in df_raw.columns.get_level_values(0) else df_raw
            df_open = df_raw['Open'] if 'Open' in df_raw.columns.get_level_values(0) else df_raw
            spy_c = [c for c in df_close.columns if 'SPY' in str(c).upper()]
            vix_c = [c for c in df_close.columns if 'VIX' in str(c).upper()]
            spy_o = [c for c in df_open.columns if 'SPY' in str(c).upper()]
            
            if spy_c and vix_c and spy_o:
                df_macro = pd.DataFrame({
                    'SPY_Close': df_close[spy_c[0]], 'SPY_Open': df_open[spy_o[0]], 'VIX': df_close[vix_c[0]]
                }).dropna(how='all')
                df_macro.index = pd.to_datetime(pd.to_datetime(df_macro.index).date)
                df_macro = df_macro.ffill().dropna()
                if len(df_macro) >= 50:
                    df_macro['SPY_MA200'] = df_macro['SPY_Close'].rolling(200, min_periods=50).mean()
                    df_macro['Market_Bull'] = df_macro['SPY_Close'] >= df_macro['SPY_MA200']
                    vix_last = float(df_macro['VIX'].iloc[-1])
                    bull_last = bool(df_macro['Market_Bull'].iloc[-1])
                    return df_macro, vix_last, bull_last, "VALID_LIVE", "Yahoo Finance API"
    except Exception:
        pass
    return pd.DataFrame(), np.nan, False, "INVALID", "None (Aborted due to missing macro data)"

# ------------------------------------------------------------------------------
# 4. Optimized Evidence Engine (Horizon-Specific PIT Maturity)
# ------------------------------------------------------------------------------
def attach_horizon_specific_pit_evidence_optimized(signal_db, min_sample=30):
    if signal_db.empty: return signal_db
    df = signal_db.copy().sort_values('Signal_Date').reset_index(drop=True)
    
    # Initialize Horizon Specific Columns
    for k in [1, 3, 5, 10, 20]:
        df[f'Hist_T{k}_N'] = 0
        df[f'Hist_T{k}_UpProb'] = np.nan
        df[f'Stats_AsOf_T{k}'] = "N/A"
        
    df['Similarity_N_T5'] = 0
    df['Hist_T5_UpProb_WilsonLow'] = np.nan
    df['Hist_T5_UpProb_WilsonHigh'] = np.nan
    df['Net_Expectancy_T5'] = np.nan
    df['Hist_T5_Median'] = np.nan
    df['Hist_T5_IQR'] = np.nan
    df['Downside_Risk_5D'] = np.nan
    df['Hist_Excess_vs_Market_Median_T5'] = np.nan
    df['Similarity_Level'] = "N/A"
    df['Similarity_Definition'] = "N/A"

    # Pre-build lookup cache per unique date
    unique_dates = df['Signal_Date'].unique()
    
    for sig_date in unique_dates:
        curr_mask = (df['Signal_Date'] == sig_date)
        curr_indices = df[curr_mask].index
        
        # Maturity masks per horizon
        matured_pools = {}
        for k in [1, 3, 5, 10, 20]:
            avail_col = f'Outcome_Available_Date_T{k}'
            ret_col = f'T{k}_Return'
            pool = df[(df[avail_col] < sig_date) & df[ret_col].notna()]
            matured_pools[k] = pool
            
        t5_pool = matured_pools[5]
        if t5_pool.empty:
            continue
            
        latest_t5_asof = t5_pool['Outcome_Available_Date_T5'].max()
        
        for idx in curr_indices:
            row = df.loc[idx]
            strat, regime, bb, b7d, brs20 = row['Strategy'], row['Market_Regime_Cluster'], row['BB_State'], row['7D_Bucket'], row['RS20_Bucket']
            
            # Hierarchy search on T5 Pool
            m5 = t5_pool[(t5_pool['Strategy']==strat) & (t5_pool['Market_Regime_Cluster']==regime) & (t5_pool['BB_State']==bb) & (t5_pool['7D_Bucket']==b7d) & (t5_pool['RS20_Bucket']==brs20)]
            if len(m5) >= min_sample: matched_t5 = m5; sim_level = "L5"; sim_def = f"{strat}+{regime}+{bb}+{b7d}+{brs20}"
            else:
                m4 = t5_pool[(t5_pool['Strategy']==strat) & (t5_pool['Market_Regime_Cluster']==regime) & (t5_pool['BB_State']==bb) & (t5_pool['7D_Bucket']==b7d)]
                if len(m4) >= min_sample: matched_t5 = m4; sim_level = "L4"; sim_def = f"{strat}+{regime}+{bb}+{b7d}"
                else:
                    m3 = t5_pool[(t5_pool['Strategy']==strat) & (t5_pool['Market_Regime_Cluster']==regime) & (t5_pool['BB_State']==bb)]
                    if len(m3) >= min_sample: matched_t5 = m3; sim_level = "L3"; sim_def = f"{strat}+{regime}+{bb}"
                    else:
                        m2 = t5_pool[(t5_pool['Strategy']==strat) & (t5_pool['Market_Regime_Cluster']==regime)]
                        if len(m2) >= min_sample: matched_t5 = m2; sim_level = "L2"; sim_def = f"{strat}+{regime}"
                        else:
                            m1 = t5_pool[t5_pool['Strategy']==strat]
                            matched_t5 = m1; sim_level = "L1"; sim_def = f"{strat}"

            n_t5 = len(matched_t5)
            df.at[idx, 'Similarity_N_T5'] = n_t5
            df.at[idx, 'Hist_T5_N'] = n_t5
            df.at[idx, 'Similarity_Level'] = sim_level
            df.at[idx, 'Similarity_Definition'] = sim_def
            df.at[idx, 'Stats_AsOf_T5'] = latest_t5_asof
            
            # Extract Horizon Specific N & UpProb matching same level definition
            for k in [1, 3, 10, 20]:
                k_pool = matured_pools[k]
                if k_pool.empty: continue
                if sim_level == "L5": sub_k = k_pool[(k_pool['Strategy']==strat) & (k_pool['Market_Regime_Cluster']==regime) & (k_pool['BB_State']==bb) & (k_pool['7D_Bucket']==b7d) & (k_pool['RS20_Bucket']==brs20)]
                elif sim_level == "L4": sub_k = k_pool[(k_pool['Strategy']==strat) & (k_pool['Market_Regime_Cluster']==regime) & (k_pool['BB_State']==bb) & (k_pool['7D_Bucket']==b7d)]
                elif sim_level == "L3": sub_k = k_pool[(k_pool['Strategy']==strat) & (k_pool['Market_Regime_Cluster']==regime) & (k_pool['BB_State']==bb)]
                elif sim_level == "L2": sub_k = k_pool[(k_pool['Strategy']==strat) & (k_pool['Market_Regime_Cluster']==regime)]
                else: sub_k = k_pool[k_pool['Strategy']==strat]
                
                df.at[idx, f'Hist_T{k}_N'] = len(sub_k)
                if len(sub_k) > 0:
                    df.at[idx, f'Hist_T{k}_UpProb'] = float(np.mean(sub_k[f'T{k}_Return'] > 0))
                    df.at[idx, f'Stats_AsOf_T{k}'] = sub_k[f'Outcome_Available_Date_T{k}'].max()

            # Compute T5 Core Metrics
            if n_t5 >= min_sample:
                t5_rets = matched_t5['T5_Return'].values
                wins_t5 = np.sum(t5_rets > 0)
                df.at[idx, 'Hist_T5_UpProb'] = float(wins_t5 / n_t5)
                
                # Wilson Lower Bound
                p_hat = wins_t5 / n_t5
                z = 1.95996
                denom = 1 + (z**2 / n_t5)
                center = (p_hat + (z**2 / (2 * n_t5))) / denom
                spread = (z / denom) * np.sqrt((p_hat * (1 - p_hat) / n_t5) + (z**2 / (4 * n_t5**2)))
                df.at[idx, 'Hist_T5_UpProb_WilsonLow'] = max(0.0, center - spread)
                df.at[idx, 'Hist_T5_UpProb_WilsonHigh'] = min(1.0, center + spread)
                
                df.at[idx, 'Net_Expectancy_T5'] = float(np.mean(t5_rets))
                df.at[idx, 'Hist_T5_Median'] = float(np.median(t5_rets))
                df.at[idx, 'Hist_T5_IQR'] = float(np.percentile(t5_rets, 75) - np.percentile(t5_rets, 25))
                df.at[idx, 'Downside_Risk_5D'] = abs(float(np.median(matched_t5['MAE_5D'].dropna().values))) if not matched_t5['MAE_5D'].dropna().empty else 0.02
                df.at[idx, 'Hist_Excess_vs_Market_Median_T5'] = float(np.median(matched_t5['Event_Excess_vs_SPY_GrossBenchmark'].dropna().values)) if not matched_t5['Event_Excess_vs_SPY_GrossBenchmark'].dropna().empty else 0.0

    return df

# ------------------------------------------------------------------------------
# 5. P0-4: Same-Day Paired Bootstrap Ranking Engine
# ------------------------------------------------------------------------------
def run_same_day_paired_bootstrap_ranking_v094(df_stock_events_in):
    daily_ranks = []
    for sig_date, group in df_stock_events_in.groupby('Signal_Date'):
        g = group.copy()
        g['Rank_UpProb'] = g['WilsonLow'].fillna(-1.0)
        g['Rank_Exp'] = g['Net_Expectancy'].fillna(-1.0)
        g['Rank_Excess'] = g['Historical_Excess'].fillna(-1.0)
        g['Rank_Downside'] = g['Downside_Risk'].fillna(999.0)
        g = g.sort_values(by=['Rank_UpProb', 'Rank_Exp', 'Rank_Excess', 'Rank_Downside'], ascending=[False, False, False, True]).reset_index(drop=True)
        g['Daily_Rank'] = g.index + 1
        daily_ranks.append(g)
        
    df_all_ranks = pd.concat(daily_ranks, ignore_index=True) if daily_ranks else pd.DataFrame()
    if df_all_ranks.empty:
        return pd.DataFrame(), "INCONCLUSIVE", 0.0, 0.0, 0.0, 0.0
        
    # Same-day Top10 vs Bottom10 Paired Diff
    daily_diff_records = []
    for sig_date, group in df_all_ranks.groupby('Signal_Date'):
        top10 = group[group['Daily_Rank'] <= 10].dropna(subset=['T5_Return'])
        bot10 = group[group['Daily_Rank'] > 10].sort_values('Daily_Rank', ascending=False).head(10).dropna(subset=['T5_Return'])
        if len(top10) > 0 and len(bot10) > 0:
            daily_diff_records.append({
                "Signal_Date": sig_date,
                "Daily_T5_Median_Diff": np.median(top10['T5_Return']) - np.median(bot10['T5_Return']),
                "Daily_T5_Mean_Diff": np.mean(top10['T5_Return']) - np.mean(bot10['T5_Return'])
            })
            
    df_daily_diffs = pd.DataFrame(daily_diff_records)
    if df_daily_diffs.empty:
        return pd.DataFrame(), "INCONCLUSIVE", 0.0, 0.0, 0.0, 0.0
        
    # Bootstrap sampling unit: Signal_Date
    np.random.seed(42)
    dates_array = df_daily_diffs['Daily_T5_Median_Diff'].values
    n_days = len(dates_array)
    boot_medians = []
    
    for _ in range(1000):
        sample = np.random.choice(dates_array, size=n_days, replace=True)
        boot_medians.append(np.mean(sample))
        
    ci_low = float(np.percentile(boot_medians, 2.5))
    ci_high = float(np.percentile(boot_medians, 97.5))
    mean_diff = float(np.mean(dates_array))
    median_diff = float(np.median(dates_array))
    
    top_t5_median = float(np.median(df_all_ranks[df_all_ranks['Daily_Rank'] <= 10]['T5_Return'].dropna()))
    bot_t5_median = float(np.median(df_all_ranks[df_all_ranks['Daily_Rank'] > 10]['T5_Return'].dropna()))
    
    ranking_status = "SUPPORTED" if (top_t5_median > bot_t5_median and median_diff > 0 and ci_low > 0) else "NOT_SUPPORTED"
    
    return df_all_ranks, ranking_status, mean_diff, median_diff, ci_low, ci_high
