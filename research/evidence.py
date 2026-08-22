import math
import numpy as np
import pandas as pd

def calc_wilson_lower_bound(successes, total, confidence=0.95):
    if total <= 0: return np.nan, np.nan
    p_hat = successes / total
    z = 1.95996 if confidence == 0.95 else 1.64485
    denom = 1 + (z**2 / total)
    center = (p_hat + (z**2 / (2 * total))) / denom
    spread = (z / denom) * np.sqrt((p_hat * (1 - p_hat) / total) + (z**2 / (4 * total**2)))
    return max(0.0, center - spread), min(1.0, center + spread)

def attach_hierarchical_point_in_time_evidence_v094(signal_db, min_sample=30):
    if signal_db.empty: return signal_db
    df = signal_db.copy().sort_values('Signal_Date').reset_index(drop=True)
    horizons = [1, 3, 5, 10, 20]
    n_rows = len(df)
    
    hist_n = {k: np.zeros(n_rows, dtype=int) for k in horizons}
    hist_uprate = {k: np.full(n_rows, np.nan) for k in horizons}
    stats_asof = {k: np.full(n_rows, "N/A", dtype=object) for k in horizons}
    
    sim_levels = np.full(n_rows, "N/A", dtype=object)
    sim_defs = np.full(n_rows, "N/A", dtype=object)
    sim_n_t5 = np.zeros(n_rows, dtype=int)
    wilson_low = np.full(n_rows, np.nan)
    wilson_high = np.full(n_rows, np.nan)
    net_exp_t5 = np.full(n_rows, np.nan)
    hist_t5_med = np.full(n_rows, np.nan)
    hist_t5_iqr = np.full(n_rows, np.nan)
    downside_risk = np.full(n_rows, np.nan)
    hist_excess_med = np.full(n_rows, np.nan)
    edge_scores = np.full(n_rows, "N/A", dtype=object)
    confidence_levels = np.full(n_rows, "Insufficient", dtype=object)
    
    unique_dates = df['Signal_Date'].unique()
    strat_arr, regime_arr = df['Strategy'].values, df['Market_Regime_Cluster'].values
    bb_arr, b7d_arr, brs20_arr = df['BB_State'].values, df['7D_Bucket'].values, df['RS20_Bucket'].values
    
    date_indices = df.groupby('Signal_Date').indices
    
    for curr_date in unique_dates:
        curr_idxs = date_indices[curr_date]
        if len(curr_idxs) == 0: continue
            
        sub_mature = {}
        for k in horizons:
            col_avail, col_ret = f'Outcome_Available_Date_T{k}', f'T{k}_Return'
            sub_mature[k] = df[(df[col_avail] < curr_date) & df[col_ret].notna()]
            
        pool5 = sub_mature[5]
        if pool5.empty: continue
            
        key_cache = {}
        for idx in curr_idxs:
            strat, regime, bb, b7d, brs20 = strat_arr[idx], regime_arr[idx], bb_arr[idx], b7d_arr[idx], brs20_arr[idx]
            combo_key = (strat, regime, bb, b7d, brs20)
            
            if combo_key not in key_cache:
                m5 = pool5[(pool5['Strategy']==strat) & (pool5['Market_Regime_Cluster']==regime) & (pool5['BB_State']==bb) & (pool5['7D_Bucket']==b7d) & (pool5['RS20_Bucket']==brs20)]
                if len(m5) >= min_sample:
                    s_lvl, s_def, lvl_num = "L5", f"{strat}+{regime}+{bb}+{b7d}+{brs20}", 5
                else:
                    m4 = pool5[(pool5['Strategy']==strat) & (pool5['Market_Regime_Cluster']==regime) & (pool5['BB_State']==bb) & (pool5['7D_Bucket']==b7d)]
                    if len(m4) >= min_sample:
                        s_lvl, s_def, lvl_num = "L4", f"{strat}+{regime}+{bb}+{b7d}", 4
                    else:
                        m3 = pool5[(pool5['Strategy']==strat) & (pool5['Market_Regime_Cluster']==regime) & (pool5['BB_State']==bb)]
                        if len(m3) >= min_sample:
                            s_lvl, s_def, lvl_num = "L3", f"{strat}+{regime}+{bb}", 3
                        else:
                            m2 = pool5[(pool5['Strategy']==strat) & (pool5['Market_Regime_Cluster']==regime)]
                            if len(m2) >= min_sample:
                                s_lvl, s_def, lvl_num = "L2", f"{strat}+{regime}", 2
                            else:
                                m1 = pool5[pool5['Strategy']==strat]
                                if len(m1) >= min_sample:
                                    s_lvl, s_def, lvl_num = "L1", f"{strat}", 1
                                else:
                                    s_lvl, s_def, lvl_num = "L0", "None", 0
                                    
                res_dict = {
                    'sim_level': s_lvl, 'sim_def': s_def, 'lvl_num': lvl_num,
                    'nk': {}, 'uprate_k': {}, 'asof_k': {},
                    'w_low': np.nan, 'w_high': np.nan, 'exp5': np.nan, 'med5': np.nan,
                    'iqr5': np.nan, 'downside': np.nan, 'excess5': np.nan,
                    'edge_score': "N/A", 'conf_level': "Insufficient"
                }
                
                if lvl_num > 0:
                    for k in horizons:
                        p_k = sub_mature[k]
                        if lvl_num == 5: sub_k = p_k[(p_k['Strategy']==strat) & (p_k['Market_Regime_Cluster']==regime) & (p_k['BB_State']==bb) & (p_k['7D_Bucket']==b7d) & (p_k['RS20_Bucket']==brs20)]
                        elif lvl_num == 4: sub_k = p_k[(p_k['Strategy']==strat) & (p_k['Market_Regime_Cluster']==regime) & (p_k['BB_State']==bb) & (p_k['7D_Bucket']==b7d)]
                        elif lvl_num == 3: sub_k = p_k[(p_k['Strategy']==strat) & (p_k['Market_Regime_Cluster']==regime) & (p_k['BB_State']==bb)]
                        elif lvl_num == 2: sub_k = p_k[(p_k['Strategy']==strat) & (p_k['Market_Regime_Cluster']==regime)]
                        elif lvl_num == 1: sub_k = p_k[p_k['Strategy']==strat]
                            
                        nk = len(sub_k)
                        res_dict['nk'][k] = int(nk)
                        if nk > 0:
                            ret_k = sub_k[f'T{k}_Return'].values
                            res_dict['uprate_k'][k] = float(np.mean(ret_k > 0))
                            res_dict['asof_k'][k] = sub_k[f'Outcome_Available_Date_T{k}'].max()
                        else:
                            res_dict['uprate_k'][k] = np.nan
                            res_dict['asof_k'][k] = "N/A"
                            
                    n5 = res_dict['nk'][5]
                    if n5 >= min_sample:
                        sub5 = sub_mature[5][(sub_mature[5]['Strategy']==strat) & (sub_mature[5]['Market_Regime_Cluster']==regime) & (sub_mature[5]['BB_State']==bb) & (sub_mature[5]['7D_Bucket']==b7d) & (sub_mature[5]['RS20_Bucket']==brs20)] if lvl_num == 5 else (
                            sub_mature[5][(sub_mature[5]['Strategy']==strat) & (sub_mature[5]['Market_Regime_Cluster']==regime) & (sub_mature[5]['BB_State']==bb) & (sub_mature[5]['7D_Bucket']==b7d)] if lvl_num == 4 else (
                            sub_mature[5][(sub_mature[5]['Strategy']==strat) & (sub_mature[5]['Market_Regime_Cluster']==regime) & (sub_mature[5]['BB_State']==bb)] if lvl_num == 3 else (
                            sub_mature[5][(sub_mature[5]['Strategy']==strat) & (sub_mature[5]['Market_Regime_Cluster']==regime)] if lvl_num == 2 else
                            sub_mature[5][sub_mature[5]['Strategy']==strat])))
                        
                        t5_rets = sub5['T5_Return'].values
                        wins_t5 = np.sum(t5_rets > 0)
                        w_low, w_high = calc_wilson_lower_bound(wins_t5, n5)
                        res_dict['w_low'], res_dict['w_high'] = w_low, w_high
                        
                        exp5, med5 = float(np.mean(t5_rets)), float(np.median(t5_rets))
                        p25, p75 = float(np.percentile(t5_rets, 25)), float(np.percentile(t5_rets, 75))
                        iqr5 = float(p75 - p25)
                        mae_med = float(np.median(sub5['MAE_5D'].dropna().values)) if not sub5['MAE_5D'].dropna().empty else -0.02
                        
                        res_dict['exp5'], res_dict['med5'], res_dict['iqr5'], res_dict['downside'] = exp5, med5, iqr5, abs(mae_med)
                        res_dict['excess5'] = float(np.median(sub5['Event_Excess_vs_SPY_GrossBenchmark'].dropna().values)) if not sub5['Event_Excess_vs_SPY_GrossBenchmark'].dropna().empty else 0.0
                        
                        edge_ratio = exp5 / (iqr5 + 1e-4)
                        edge_score = float(min(100.0, max(0.0, (50.0 * w_low + 50.0 * (0.5 * (1.0 + math.erf(edge_ratio / math.sqrt(2.0))))) * (1.0 - (w_high - w_low)))))
                        res_dict['edge_score'] = round(edge_score, 1)
                        
                        if n5 < 50: res_dict['conf_level'] = "Low"
                        elif n5 < 150: res_dict['conf_level'] = "Medium"
                        else: res_dict['conf_level'] = "High"
                        
                key_cache[combo_key] = res_dict
                
            res = key_cache[combo_key]
            sim_levels[idx], sim_defs[idx] = res['sim_level'], res['sim_def']
            for k in horizons:
                hist_n[k][idx] = res['nk'].get(k, 0)
                hist_uprate[k][idx] = res['uprate_k'].get(k, np.nan)
                stats_asof[k][idx] = res['asof_k'].get(k, "N/A")
                
            sim_n_t5[idx] = res['nk'].get(5, 0)
            wilson_low[idx], wilson_high[idx] = res['w_low'], res['w_high']
            net_exp_t5[idx], hist_t5_med[idx], hist_t5_iqr[idx] = res['exp5'], res['med5'], res['iqr5']
            downside_risk[idx], hist_excess_med[idx] = res['downside'], res['excess5']
            edge_scores[idx], confidence_levels[idx] = res['edge_score'], res['conf_level']
            
    df['Similarity_Level'], df['Similarity_Definition'] = sim_levels, sim_defs
    for k in horizons:
        df[f'Hist_T{k}_N'] = hist_n[k]
        df[f'Hist_T{k}_UpProb'] = hist_uprate[k]
        df[f'Stats_AsOf_T{k}'] = stats_asof[k]
        
    df['Similarity_N_T5'] = sim_n_t5
    df['Hist_T5_UpProb_WilsonLow'], df['Hist_T5_UpProb_WilsonHigh'] = wilson_low, wilson_high
    df['Net_Expectancy_T5'], df['Hist_T5_Median'], df['Hist_T5_IQR'] = net_exp_t5, hist_t5_med, hist_t5_iqr
    df['Downside_Risk_5D'], df['Hist_Excess_vs_Market_Median_T5'] = downside_risk, hist_excess_med
    df['Historical_Edge_Score'], df['Confidence_Level'] = edge_scores, confidence_levels
    
    df['Regime_Fit_Score'] = df.apply(lambda r: 100.0 if (r['Market_Bull'] and r['VIX']<20) else (60.0 if (r['Market_Bull'] and r['VIX']<25) else 20.0), axis=1)
    df['Current_Setup_Score'] = (df['Score_7D'] / 7.0) * 100.0
    
    def calc_decision_score(row):
        if row['Similarity_N_T5'] < min_sample: return "Unverified (N/A)"
        edge = row['Historical_Edge_Score']
        if edge == "N/A": return "Unverified (N/A)"
        return round(0.50 * float(edge) + 0.25 * row['Regime_Fit_Score'] + 0.25 * row['Current_Setup_Score'], 1)

    df['Decision_Score (Diagnostic Only)'] = pd.Series([calc_decision_score(r) for _, r in df.iterrows()], dtype="object")
    return df
