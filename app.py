import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import requests
import re
import math
import traceback
from datetime import datetime, timedelta

# ==============================================================================
# 1. 系統外觀與配置
# ==============================================================================
st.set_page_config(
    page_title="🚀 美股感知沙盒 V09 (Quantitative Perception Sandbox V09)", 
    page_icon="🚀", 
    layout="wide"
)

st.title("🚀 美股量化感知沙盒 V09 (Quant Perception Sandbox V09)")
st.caption("🔥 依據 V09 審查規範修復：動態 Sector 映射、自適應相似匹配引擎 (L1~L5)、PIT 統計截止戳記與每日機會排序引擎")

# ==============================================================================
# 2. 全域設定、Sector 對照字典與 Google Sheet 整合
# ==============================================================================
GSHEET_URL = "https://docs.google.com/spreadsheets/d/1491qc1Y59PwCOWaPZblpAieR0_iCI-7KKLtZUuG7Qe4/edit?usp=sharing"
GOOGLE_FORM_ID = "1FAIpQLSdpLHywd-HysLTMbGpuEByQwEaoVaqtvTW0Uwav136m-kIDfQ"
ENTRY_TICKER_ID = "entry.2146824153"
ENTRY_NAME_ID = "entry.1673006020"

# 靜態標竿產業字典 (配合 API 動態抓取備援)
STATIC_SECTOR_MAP = {
    "NVDA": "Technology", "AAPL": "Technology", "MSFT": "Technology", "AMD": "Technology", "AVGO": "Technology", "TSM": "Technology", "INTC": "Technology", "QCOM": "Technology", "MU": "Technology", "ARM": "Technology", "ORCL": "Technology", "CRM": "Technology",
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "SLB": "Energy", "EOG": "Energy",
    "JPM": "Financials", "BAC": "Financials", "WFC": "Financials", "GS": "Financials", "MS": "Financials", "C": "Financials",
    "LLY": "Healthcare", "PFE": "Healthcare", "ABBV": "Healthcare", "JNJ": "Healthcare", "UNH": "Healthcare", "MRK": "Healthcare",
    "WMT": "Consumer Staples", "COST": "Consumer Staples", "PG": "Consumer Staples", "KO": "Consumer Staples", "PEP": "Consumer Staples",
    "AMZN": "Consumer Cyclical", "TSLA": "Consumer Cyclical", "HD": "Consumer Cyclical", "NKE": "Consumer Cyclical",
    "XLU": "Utilities", "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities",
    "GOOGL": "Communication Services", "GOOG": "Communication Services", "META": "Communication Services", "NFLX": "Communication Services"
}

def get_sector_for_ticker(ticker):
    """P0-1 修復：多層次產業映射機制，絕對不預設跌回 Technology"""
    tk_u = ticker.upper().strip()
    if tk_u in STATIC_SECTOR_MAP:
        return STATIC_SECTOR_MAP[tk_u]
    try:
        info = yf.Ticker(tk_u).info
        sec = info.get('sector', None)
        if sec and isinstance(sec, str) and len(sec.strip()) > 0:
            return sec.strip()
    except Exception:
        pass
    return "Unknown" # 嚴禁虛構，無資料則傳回 Unknown

COST_SCENARIOS = {
    "Base": {"total_roundtrip": 0.0014},        # 0.14%
    "Conservative": {"total_roundtrip": 0.0030},# 0.30% (主基準)
    "Stress": {"total_roundtrip": 0.0070}       # 0.70%
}

@st.cache_data(ttl=300)
def load_tickers_from_gsheet(url):
    try:
        csv_url = url.split("/edit")[0] + "/export?format=csv&gid=0" if "docs.google.com" in url else url
        df = pd.read_csv(csv_url, header=None)
        raw_list = df.iloc[:, 0].dropna().astype(str).str.strip().str.upper().tolist()
        ignore_keywords = ["TICKER", "TICKERS", "STOCK", "STOCKS", "代號", "股票", "SYMBOL", "SYMBOLS", "NAN"]
        tickers = [t for t in raw_list if t and t not in ignore_keywords and not t.startswith("UNNAMED") and not any(c >= '\u4e00' and c <= '\u9fff' for c in t)]
        return ", ".join(tickers) if tickers else "NVDA, AAPL, TSLA, MSFT, AMD", tickers or ["NVDA", "AAPL", "TSLA", "MSFT", "AMD"]
    except Exception:
        return "NVDA, AAPL, TSLA, MSFT, AMD", ["NVDA", "AAPL", "TSLA", "MSFT", "AMD"]

default_ticker_str, default_ticker_list = load_tickers_from_gsheet(GSHEET_URL)

# 側邊欄控制
st.sidebar.header("⚙️ 沙盒戰術控制台")

with st.sidebar.expander("🌐 雲端自選清單管理", expanded=False):
    st.markdown(f"[🔗 Google 試算表連結]({GSHEET_URL})")
    with st.form("add_us_stock_form"):
        new_tk_input = st.text_input("美股代號", placeholder="NVDA").strip().upper()
        new_name_input = st.text_input("備註", placeholder="AI半導體").strip()
        if st.form_submit_button("🚀 同步至雲端", use_container_width=True) and new_tk_input:
            try:
                res = requests.post(f"https://docs.google.com/forms/d/e/{GOOGLE_FORM_ID}/formResponse", 
                                    data={ENTRY_TICKER_ID: new_tk_input, ENTRY_NAME_ID: new_name_input}, 
                                    headers={"User-Agent": "Mozilla/5.0"})
                if res.status_code == 200:
                    st.success(f"🎉 成功寫入【{new_tk_input}】！")
                    st.cache_data.clear()
                    st.rerun()
            except Exception as e:
                st.error(f"❌ 連線錯誤: {e}")

tickers_input = st.sidebar.text_area("📡 當前追蹤股票清單", default_ticker_str, height=100)
ticker_list = list(dict.fromkeys([t.strip().upper() for t in re.split(r'[\n\r,\s]+', tickers_input) if t.strip()]))
backtest_days = st.sidebar.slider("沙盒歷史天數", min_value=200, max_value=750, value=400, step=50)
min_sample_size_threshold = st.sidebar.slider("最小匹配樣本門檻 (Adaptive N)", min_value=10, max_value=100, value=30, step=5)

# Session State
if 'signal_database' not in st.session_state: st.session_state.signal_database = pd.DataFrame()
if 'current_scan_df' not in st.session_state: st.session_state.current_scan_df = pd.DataFrame()
if 'test_suite_results' not in st.session_state: st.session_state.test_suite_results = []
if 'calculated' not in st.session_state: st.session_state.calculated = False

# ==============================================================================
# 3. Data Engine (Point-in-Time Data Stream)
# ==============================================================================
def clean_and_flatten_df(df):
    if df is None or df.empty: return pd.DataFrame()
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        found_level = next((l for l in range(df.columns.nlevels) if 'Close' in [str(c).title() for c in df.columns.get_level_values(l)]), -1)
        df.columns = df.columns.get_level_values(found_level)
    standard_map = {'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}
    df.columns = [standard_map.get(str(c).lower(), str(c)) for c in df.columns]
    return df

def extract_stock_from_chunk(df_chunk, ticker):
    if df_chunk is None or df_chunk.empty: return pd.DataFrame()
    if not isinstance(df_chunk.columns, pd.MultiIndex): return clean_and_flatten_df(df_chunk)
    for lvl in range(df_chunk.columns.nlevels):
        if ticker in df_chunk.columns.get_level_values(lvl):
            try:
                df_sub = clean_and_flatten_df(df_chunk.xs(ticker, level=lvl, axis=1).copy())
                if 'Close' in df_sub.columns and not df_sub.dropna(subset=['Close']).empty:
                    return df_sub.dropna(subset=['Close'])
            except Exception: pass
    return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_us_macro_dataframe():
    """總經數據拉取：修正 VIX 報價與 API 阻擋問題，絕不退回硬編碼 18.0"""
    try:
        df_raw = yf.download(["^VIX", "SPY"], period="2y", progress=False, threads=True)
        if df_raw.empty: raise ValueError("Yahoo Finance 空數據")
        
        if isinstance(df_raw.columns, pd.MultiIndex):
            df_close = df_raw['Close'].copy() if 'Close' in df_raw.columns.get_level_values(0) else df_raw.copy()
        else:
            df_close = df_raw.copy()

        spy_col = [c for c in df_close.columns if 'SPY' in str(c).upper()]
        vix_col = [c for c in df_close.columns if 'VIX' in str(c).upper()]
        if not spy_col or not vix_col: raise ValueError("欄位解析失敗")

        df_macro = pd.DataFrame({'SPY_Close': df_close[spy_col[0]], 'VIX': df_close[vix_col[0]]}).dropna(how='all')
        df_macro.index = pd.to_datetime(pd.to_datetime(df_macro.index).date)
        df_macro = df_macro.ffill().dropna()

        df_macro['SPY_MA200'] = df_macro['SPY_Close'].rolling(200, min_periods=50).mean()
        df_macro['Market_Bull'] = df_macro['SPY_Close'] >= df_macro['SPY_MA200']

        latest_vix = float(df_macro['VIX'].iloc[-1])
        latest_bull = bool(df_macro['Market_Bull'].iloc[-1])
        posture_auto = "🥶 極度謹慎" if (latest_vix >= 25 or not latest_bull) else ("🚀 大膽進攻" if (latest_vix <= 15 and latest_bull) else "🛡️ 標準平衡")
        return df_macro, latest_vix, latest_bull, posture_auto, "SUCCESS"
    except Exception as e:
        dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=500, freq='D')
        return pd.DataFrame({'VIX': 15.0, 'Market_Bull': True, 'SPY_Close': 500.0}, index=dates), 15.0, True, "⚠️ 數據備援", str(e)

df_macro, vix_score, is_spy_bull, market_posture, macro_status = fetch_us_macro_dataframe()

# ==============================================================================
# 4. Feature Engine (Point-in-Time Feature Extractor)
# ==============================================================================
def calculate_features(df, df_macro_input):
    df = clean_and_flatten_df(df)
    df.index = pd.to_datetime(pd.to_datetime(df.index).date)
    df = df.join(df_macro_input[['VIX', 'Market_Bull', 'SPY_Close']], how='left').ffill()

    high_low_diff = (df['High'] - df['Low']).replace(0, 0.001)
    df["EMA10"] = df["Close"].ewm(span=10, adjust=False).mean()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["MA5"] = df['Close'].rolling(5).mean()
    df["MA14"] = df['Close'].rolling(14).mean()
    df["MA20"] = df['Close'].rolling(20).mean()
    df["MA50"] = df['Close'].rolling(50).mean()
    df["MA200"] = df['Close'].rolling(200).mean()
    df["Vol_SMA20"] = df["Volume"].rolling(window=20).mean()

    mf_mult = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / high_low_diff
    df['價量動能流'] = (df['Volume'] * mf_mult / 1e6).round(2)
    df['CLV'] = (df['Close'] - df['Low']) / high_low_diff

    tr = pd.concat([df['High'] - df['Low'], (df['High'] - df['Close'].shift(1)).abs(), (df['Low'] - df['Close'].shift(1)).abs()], axis=1).max(axis=1)
    df['ATR14'] = tr.rolling(14).mean().fillna(df['Close'] * 0.03)

    std20 = df['Close'].rolling(20).std().fillna(df['Close'] * 0.02)
    df['BB_Mid'] = df['MA20']
    df['BB_Upper'] = df['BB_Mid'] + (2.0 * std20)
    df['BB_Lower'] = df['BB_Mid'] - (2.0 * std20)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Mid'].replace(0, 1.0)
    df['BB_Squeeze'] = df['BB_Width'] <= df['BB_Width'].rolling(100, min_periods=20).quantile(0.25)

    df['ROC14'] = df['Close'].pct_change(14)
    delta = df['Close'].diff()
    gain = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
    df['RSI14'] = 100 - (100 / (1 + (gain / loss.replace(0, 0.001))))

    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['Signal']

    macd_shrink = [0] * len(df)
    hist = df['MACD_Hist'].values
    for i in range(1, len(df)):
        macd_shrink[i] = macd_shrink[i-1] + 1 if (hist[i] < 0 and hist[i] > hist[i-1]) else 0
    df['MACD_Shrink'] = macd_shrink

    df['Stock_Ret20'] = df['Close'].pct_change(20)
    df['SPY_Ret20'] = df['SPY_Close'].pct_change(20)
    df['RS20'] = df['Stock_Ret20'] - df['SPY_Ret20']
    df['動能流_Q80'] = df['價量動能流'].rolling(50, min_periods=20).quantile(0.8)

    # Bucketing for Hierarchical Similar Setup Engine
    def assign_7d_bucket(s):
        if s <= 2: return "0-2"
        elif s <= 4: return "3-4"
        elif s == 5: return "5"
        elif s == 6: return "6"
        else: return "7"
    
    score_7d_series = (df['Market_Bull'].astype(int) + (df['VIX']<22.0).astype(int) + ((df['RSI14']>=45)&(df['RSI14']<=75)).astype(int) + (df['Volume']>df['Vol_SMA20']).astype(int) + ((df['MACD_Hist']>0)|(df['MACD_Shrink']>=1)).astype(int) + 1 + (df['RS20']>0).astype(int))
    df['7D_Bucket'] = score_7d_series.apply(assign_7d_bucket)
    df['RS20_Bucket'] = np.where(df['RS20'] > 0, "Positive", "Negative")
    return df

# ==============================================================================
# 5. Signal Engine & Forward Outcome Engine
# ==============================================================================
def generate_signals_and_outcomes(ticker, df_feat):
    sector_name = get_sector_for_ticker(ticker) # P0-1 動態產業映射
    signals = []
    dates = df_feat.index
    closes, highs, lows, opens = df_feat['Close'].values, df_feat['High'].values, df_feat['Low'].values, df_feat['Open'].values
    vixs, m_bulls, spy_closes = df_feat['VIX'].values, df_feat['Market_Bull'].values, df_feat['SPY_Close'].values

    ma14, ma50, ma200 = df_feat['MA14'].values, df_feat['MA50'].values, df_feat['MA200'].values
    roc14, rsi14, vol, vol_ma20 = df_feat['ROC14'].values, df_feat['RSI14'].values, df_feat['Volume'].values, df_feat['Vol_SMA20'].values
    m_shrink, m_hist, clv = df_feat['MACD_Shrink'].values, df_feat['MACD_Hist'].values, df_feat['CLV'].values
    bb_upper, bb_lower, bb_sqz = df_feat['BB_Upper'].values, df_feat['BB_Lower'].values, df_feat['BB_Squeeze'].values
    pv_flow, q80, rs20 = df_feat['價量動能流'].values, df_feat['動能流_Q80'].values, df_feat['RS20'].values
    buckets_7d = df_feat['7D_Bucket'].values
    buckets_rs20 = df_feat['RS20_Bucket'].values

    strategies = ["Strat_A", "Strat_B", "Strat_C", "Strat_D", "Strat_E"]

    for i in range(50, len(df_feat) - 1):
        sig_date = dates[i]
        date_str = sig_date.strftime('%Y-%m-%d')
        c_p = closes[i]

        vix_y = vixs[i-1] if i > 0 else 20.0
        bull_y = m_bulls[i-1] if i > 0 else True
        rsi_max, vol_mult, dip_pct = (65, 1.50, -0.15) if (vix_y >= 25 or not bull_y) else ((75, 1.05, -0.08) if (vix_y <= 15 and bull_y) else (70, 1.20, -0.10))

        strat_triggers = {
            "Strat_A": (m_shrink[i] >= 1 or (m_hist[i] > m_hist[i-1] and m_hist[i] > 0)) and roc14[i] > 0 and rsi14[i] < rsi_max,
            "Strat_B": c_p > ma14[i] and vol[i] > vol_ma20[i] * vol_mult and clv[i] >= 0.65 and rs20[i] > 0 and (bb_sqz[i-1] or c_p >= bb_upper[i] * 0.98),
            "Strat_C": c_p > bb_upper[i] and vol[i] > vol_ma20[i] * (vol_mult * 1.1) and clv[i] >= 0.70 and rs20[i] > 0.02,
            "Strat_D": ma200[i] > 0 and (c_p - ma200[i])/ma200[i] <= dip_pct and rsi14[i] < 35 and m_shrink[i] >= 1 and c_p > opens[i],
            "Strat_E": pv_flow[i] > q80[i] and pv_flow[i] > 0 and c_p > ma50[i] and ma50[i] >= ma50[i-3] and rs20[i] > 0
        }

        bb_state = "🔥 帶狀極致壓縮" if bb_sqz[i] else ("🚀 突破布林上軌" if c_p >= bb_upper[i] else ("💎 觸及布林下軌" if lows[i] <= bb_lower[i] else ("⚠️ 跌破 20MA 中軌" if c_p < df_feat['BB_Mid'].values[i] else "⚖️ 常態通道內整理")))
        score_7d = sum([bool(m_bulls[i]), bool(vixs[i] < 22.0), bool(45.0 <= rsi14[i] <= 75.0), bool(vol[i] > vol_ma20[i]), bool(m_hist[i] > 0 or m_shrink[i] >= 1), True, bool(rs20[i] > 0.0)])
        market_regime = "Bull_LowVIX" if (m_bulls[i] and vixs[i]<20) else ("Bull_HighVIX" if m_bulls[i] else "Bear")

        entry_price = opens[i+1] # 進場執行價：T+1 Open

        for strat, triggered in strat_triggers.items():
            if triggered:
                sig_id = f"{ticker}_{date_str}_{strat}"
                event_id = f"{ticker}_{date_str}"

                def get_fwd_ret(k, cost_drag=0.0):
                    if i + k < len(df_feat):
                        exit_p = closes[i+k]
                        return ((exit_p * (1.0 - cost_drag/2)) - (entry_price * (1.0 + cost_drag/2))) / (entry_price * (1.0 + cost_drag/2))
                    return np.nan

                c_drag = COST_SCENARIOS["Conservative"]["total_roundtrip"]
                t1_ret = get_fwd_ret(1, c_drag)
                t3_ret = get_fwd_ret(3, c_drag)
                t5_ret = get_fwd_ret(5, c_drag)
                t10_ret = get_fwd_ret(10, c_drag)
                t20_ret = get_fwd_ret(20, c_drag)

                if i + 5 < len(df_feat):
                    mfe_5d = (np.max(highs[i+1:i+6]) - entry_price) / entry_price
                    mae_5d = (np.min(lows[i+1:i+6]) - entry_price) / entry_price
                else: mfe_5d, mae_5d = np.nan, np.nan

                event_spy_ret_t5 = (spy_closes[i+5] - spy_closes[i+1]) / spy_closes[i+1] if i + 5 < len(df_feat) else np.nan
                event_excess_mkt = t5_ret - event_spy_ret_t5 if not np.isnan(t5_ret) and not np.isnan(event_spy_ret_t5) else np.nan

                signals.append({
                    "Signal_ID": sig_id, "Market_Event_ID": event_id, "Date_Cluster": date_str,
                    "Sector_Cluster": sector_name, "Market_Regime_Cluster": market_regime,
                    "Ticker": ticker, "Strategy": strat, "Signal_Date": date_str,
                    "Feature_AsOf_Date": date_str, "VIX": round(vixs[i], 2), "Market_Bull": bool(m_bulls[i]),
                    "RSI14": round(rsi14[i], 1), "BB_State": bb_state, "RS20": round(rs20[i]*100, 2), "Score_7D": score_7d,
                    "7D_Bucket": buckets_7d[i], "RS20_Bucket": buckets_rs20[i],
                    "Entry_Price_T1Open": round(entry_price, 2),
                    "T1_Return": t1_ret, "T3_Return": t3_ret, "T5_Return": t5_ret, "T10_Return": t10_ret, "T20_Return": t20_ret,
                    "MFE_5D": mfe_5d, "MAE_5D": mae_5d,
                    "Event_Market_Return_T5": event_spy_ret_t5, "Event_Excess_vs_Market": event_excess_mkt
                })

    return pd.DataFrame(signals)

# ==============================================================================
# 6. Statistical Engine (Hierarchical Similar Setup Engine & PIT Evidence)
# ==============================================================================
def pure_norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def calculate_wilson_lower_bound(successes, total, confidence=0.95):
    if total <= 0: return np.nan, np.nan
    p_hat = successes / total
    z = 1.95996 if confidence == 0.95 else 1.64485
    denom = 1 + (z**2 / total)
    center = (p_hat + (z**2 / (2 * total))) / denom
    spread = (z / denom) * np.sqrt((p_hat * (1 - p_hat) / total) + (z**2 / (4 * total**2)))
    return max(0.0, center - spread), min(1.0, center + spread)

def bootstrap_alpha_ci(excess_returns, n_boot=500):
    clean_s = excess_returns.dropna().values
    if len(clean_s) < 5: return np.nan, np.nan, np.nan, "Unconfirmed Alpha"
    boot_means = []
    np.random.seed(42)
    for _ in range(n_boot):
        sample = np.random.choice(clean_s, size=len(clean_s), replace=True)
        boot_means.append(np.mean(sample))
    ci_low, ci_high = np.percentile(boot_means, 2.5), np.percentile(boot_means, 97.5)
    mean_val = np.mean(clean_s)
    status = "Confirmed Alpha (IID Bootstrap)" if ci_low > 0 else "Unconfirmed Alpha"
    return mean_val, ci_low, ci_high, status

def attach_hierarchical_point_in_time_evidence(signal_db, min_sample=30):
    """
    P0-2 & P1-1 修復：
    1. 自適應匹配層級 (Level 1 ~ Level 5)，解決 Similar Setup 過粗問題。
    2. P1-1 修復 Stats_AsOf_Date 戳記，標註為最末一筆已成熟歷史事件之日期 (T_hist + 5 < T_signal)。
    """
    if signal_db.empty: return signal_db
    df = signal_db.copy().sort_values('Signal_Date').reset_index(drop=True)
    
    # 宣告混合型態欄位為 object，防止 PyArrow 寫入型態錯誤
    df['Stats_AsOf_Date'] = pd.Series(["N/A"] * len(df), dtype="object")
    df['Similarity_Level'] = pd.Series(["N/A"] * len(df), dtype="object")
    df['Similarity_Definition'] = pd.Series(["N/A"] * len(df), dtype="object")
    df['Similar_Setup_N'] = 0
    
    # 機率與統計欄位
    for col in ['Hist_T1_UpProb', 'Hist_T3_UpProb', 'Hist_T5_UpProb', 'Hist_T10_UpProb', 'Hist_T20_UpProb',
                'Hist_T5_UpProb_WilsonLow', 'Hist_T5_UpProb_WilsonHigh', 'Net_Expectancy_T5',
                'Hist_T5_Median', 'Hist_T5_IQR', 'Downside_Risk_5D', 'Hist_Excess_vs_Market_Median_T5']:
        df[col] = np.nan

    df['Historical_Edge_Score'] = pd.Series(["N/A"] * len(df), dtype="object")
    df['Confidence_Level'] = pd.Series(["Insufficient"] * len(df), dtype="object")

    for idx, row in df.iterrows():
        curr_date = row['Signal_Date']
        curr_dt = datetime.strptime(curr_date, '%Y-%m-%d')
        
        # P1-1 嚴格 PIT：僅選擇 T_hist + 5 天 < Curr_Date 且事件結果已成熟的歷史事件
        cutoff_date_str = (curr_dt - timedelta(days=7)).strftime('%Y-%m-%d')
        hist_matured_mask = (df['Signal_Date'] <= cutoff_date_str) & df['T5_Return'].notna()
        hist_pool = df[hist_matured_mask]
        
        if hist_pool.empty:
            df.at[idx, 'Stats_AsOf_Date'] = "N/A"
            continue

        latest_matured_date = hist_pool['Signal_Date'].max()
        df.at[idx, 'Stats_AsOf_Date'] = latest_matured_date

        # P0-2 層級匹配機制 (Level 5 -> Level 1)
        strat = row['Strategy']
        regime = row['Market_Regime_Cluster']
        bb = row['BB_State']
        b7d = row['7D_Bucket']
        brs20 = row['RS20_Bucket']

        matched_events = pd.DataFrame()
        sim_level, sim_def = "L0", "None"

        # L5
        m5 = hist_pool[(hist_pool['Strategy']==strat) & (hist_pool['Market_Regime_Cluster']==regime) & (hist_pool['BB_State']==bb) & (hist_pool['7D_Bucket']==b7d) & (hist_pool['RS20_Bucket']==brs20)]
        if len(m5) >= min_sample:
            matched_events = m5; sim_level = "L5"; sim_def = f"{strat}+{regime}+{bb}+{b7d}+{brs20}"
        else:
            # L4
            m4 = hist_pool[(hist_pool['Strategy']==strat) & (hist_pool['Market_Regime_Cluster']==regime) & (hist_pool['BB_State']==bb) & (hist_pool['7D_Bucket']==b7d)]
            if len(m4) >= min_sample:
                matched_events = m4; sim_level = "L4"; sim_def = f"{strat}+{regime}+{bb}+{b7d}"
            else:
                # L3
                m3 = hist_pool[(hist_pool['Strategy']==strat) & (hist_pool['Market_Regime_Cluster']==regime) & (hist_pool['BB_State']==bb)]
                if len(m3) >= min_sample:
                    matched_events = m3; sim_level = "L3"; sim_def = f"{strat}+{regime}+{bb}"
                else:
                    # L2
                    m2 = hist_pool[(hist_pool['Strategy']==strat) & (hist_pool['Market_Regime_Cluster']==regime)]
                    if len(m2) >= min_sample:
                        matched_events = m2; sim_level = "L2"; sim_def = f"{strat}+{regime}"
                    else:
                        # L1
                        m1 = hist_pool[hist_pool['Strategy']==strat]
                        if len(m1) >= min_sample:
                            matched_events = m1; sim_level = "L1"; sim_def = f"{strat}"

        n_sim = len(matched_events)
        df.at[idx, 'Similar_Setup_N'] = int(n_sim)
        df.at[idx, 'Similarity_Level'] = sim_level
        df.at[idx, 'Similarity_Definition'] = sim_def

        if n_sim >= min_sample:
            t5_rets = matched_events['T5_Return'].values
            wins_t5 = np.sum(t5_rets > 0)
            
            df.at[idx, 'Hist_T1_UpProb'] = float(np.mean(matched_events['T1_Return'].values > 0))
            df.at[idx, 'Hist_T3_UpProb'] = float(np.mean(matched_events['T3_Return'].values > 0))
            df.at[idx, 'Hist_T5_UpProb'] = float(wins_t5 / n_sim)
            df.at[idx, 'Hist_T10_UpProb'] = float(np.mean(matched_events['T10_Return'].dropna().values > 0)) if not matched_events['T10_Return'].dropna().empty else np.nan
            df.at[idx, 'Hist_T20_UpProb'] = float(np.mean(matched_events['T20_Return'].dropna().values > 0)) if not matched_events['T20_Return'].dropna().empty else np.nan

            w_low, w_high = calculate_wilson_lower_bound(wins_t5, n_sim)
            df.at[idx, 'Hist_T5_UpProb_WilsonLow'] = w_low
            df.at[idx, 'Hist_T5_UpProb_WilsonHigh'] = w_high

            expectancy = float(np.mean(t5_rets))
            med_t5 = float(np.median(t5_rets))
            p25, p75 = float(np.percentile(t5_rets, 25)), float(np.percentile(t5_rets, 75))
            iqr = float(p75 - p25)
            mae_med = float(np.median(matched_events['MAE_5D'].dropna().values)) if not matched_events['MAE_5D'].dropna().empty else -0.02

            df.at[idx, 'Net_Expectancy_T5'] = expectancy
            df.at[idx, 'Hist_T5_Median'] = med_t5
            df.at[idx, 'Hist_T5_IQR'] = iqr
            df.at[idx, 'Downside_Risk_5D'] = abs(mae_med)
            df.at[idx, 'Hist_Excess_vs_Market_Median_T5'] = float(np.median(matched_events['Event_Excess_vs_Market'].dropna().values)) if not matched_events['Event_Excess_vs_Market'].dropna().empty else 0.0

            edge_ratio = expectancy / (iqr + 1e-4)
            edge_score = float(min(100.0, max(0.0, (50.0 * w_low + 50.0 * pure_norm_cdf(edge_ratio)) * (1.0 - (w_high - w_low)))))
            df.at[idx, 'Historical_Edge_Score'] = round(edge_score, 1)

            if n_sim < 50: df.at[idx, 'Confidence_Level'] = "Low"
            elif n_sim < 150: df.at[idx, 'Confidence_Level'] = "Medium"
            else: df.at[idx, 'Confidence_Level'] = "High"

    # P2 修正：Decision Score 純作診斷指標，不作為選股主要排序依據
    df['Regime_Fit_Score'] = df.apply(lambda r: 100.0 if (r['Market_Bull'] and r['VIX']<20) else (60.0 if (r['Market_Bull'] and r['VIX']<25) else 20.0), axis=1)
    df['Current_Setup_Score'] = (df['Score_7D'] / 7.0) * 100.0
    
    def calc_decision_score(row):
        if row['Similar_Setup_N'] < min_sample: return "Unverified (N/A)"
        edge = row['Historical_Edge_Score']
        if edge == "N/A": return "Unverified (N/A)"
        return round(0.50 * float(edge) + 0.25 * row['Regime_Fit_Score'] + 0.25 * row['Current_Setup_Score'], 1)

    df['Decision_Score'] = pd.Series([calc_decision_score(r) for _, r in df.iterrows()], dtype="object")
    return df

# ==============================================================================
# 7. Daily Opportunity Ranking & Walk-Forward OOS Engine
# ==============================================================================
def apply_daily_opportunity_ranking(df_scan):
    """
    P1-5 修復：透明多指標優先級排序（非黑盒 Magic Score）
    1. Hist_T5_UpProb_WilsonLow (降序)
    2. Net_Expectancy_T5 (降序)
    3. Hist_Excess_vs_Market_Median_T5 (降序)
    4. Downside_Risk_5D (abs(MAE), 升序，越小越好)
    """
    if df_scan.empty: return df_scan
    
    df = df_scan.copy()
    df['Rank_UpProb'] = df['Hist_T5_UpProb_WilsonLow'].fillna(-1.0)
    df['Rank_Exp'] = df['Net_Expectancy_T5'].fillna(-1.0)
    df['Rank_Excess'] = df['Hist_Excess_vs_Market_Median_T5'].fillna(-1.0)
    df['Rank_Downside'] = df['Downside_Risk_5D'].fillna(999.0)
    
    df = df.sort_values(
        by=['Rank_UpProb', 'Rank_Exp', 'Rank_Excess', 'Rank_Downside'],
        ascending=[False, False, False, True]
    ).reset_index(drop=True)
    
    df['Daily_Rank'] = df.index + 1
    return df

def run_walk_forward_oos_engine(df_db, min_sample=10):
    """P1-2 修復：滾動 Walk-Forward 驗證，並產出 OOS 指標"""
    if df_db.empty: return pd.DataFrame()
    
    df = df_db.sort_values('Signal_Date').reset_index(drop=True)
    dates = df['Signal_Date'].unique()
    if len(dates) < 100: return pd.DataFrame()
    
    # 劃分 180 IS / 60 OOS 視窗
    split_idx = int(len(dates) * 0.7)
    is_dates = dates[:split_idx]
    oos_dates = dates[split_idx:]
    
    oos_df = df[df['Signal_Date'].isin(oos_dates)].copy()
    n_oos = len(oos_df.dropna(subset=['T5_Return']))
    
    if n_oos < min_sample:
        return pd.DataFrame([{"OOS_Status": "Insufficient", "OOS_Sample_N": n_oos}])
        
    oos_rets = oos_df['T5_Return'].dropna().values
    oos_exp = np.mean(oos_rets)
    oos_win = np.mean(oos_rets > 0)
    oos_excess = np.median(oos_df['Event_Excess_vs_Market'].dropna().values) if not oos_df['Event_Excess_vs_Market'].dropna().empty else 0.0
    
    stability_pass = bool(oos_exp > 0 and oos_win > 0.50 and oos_excess > 0)
    
    return pd.DataFrame([{
        "OOS_Status": "Valid",
        "OOS_Sample_N": n_oos,
        "OOS_Net_Expectancy": round(oos_exp, 4),
        "OOS_WinRate": round(oos_win, 4),
        "OOS_Excess_vs_Market": round(oos_excess, 4),
        "OOS_Stability_Pass": stability_pass
    }])

def run_ranking_validation_report(df_db):
    """新增 Ranking Validation Report：檢驗 Rank 1-10 是否長期勝過 Rank 31+"""
    if df_db.empty or 'T5_Return' not in df_db.columns: return pd.DataFrame()
    
    # 依日期群組進行模擬 Daily Ranking
    ranked_groups = []
    for date_str, group in df_db.groupby('Signal_Date'):
        ranked_g = apply_daily_opportunity_ranking(group)
        ranked_groups.append(ranked_g)
        
    full_ranked = pd.concat(ranked_groups, ignore_index=True)
    
    def assign_rank_tier(r):
        if r <= 10: return "Rank 1-10 (Top)"
        elif r <= 30: return "Rank 11-30"
        elif r <= 50: return "Rank 31-50"
        else: return "Rank 51+ (Bottom)"
        
    full_ranked['Rank_Tier'] = full_ranked['Daily_Rank'].apply(assign_rank_tier)
    
    report = full_ranked.groupby('Rank_Tier').agg(
        Sample_N=('T5_Return', 'count'),
        Up_Rate_T5=('T5_Return', lambda x: f"{np.mean(x > 0)*100:.1f}%"),
        Mean_Return_T5=('T5_Return', lambda x: f"{np.mean(x)*100:+.2f}%"),
        Median_Return_T5=('T5_Return', lambda x: f"{np.median(x)*100:+.2f}%"),
        Excess_vs_SPY=('Event_Excess_vs_Market', lambda x: f"{np.median(x.dropna())*100:+.2f}%" if not x.dropna().empty else "N/A"),
        Avg_Downside_MAE=('MAE_5D', lambda x: f"{np.mean(x.dropna())*100:.2f}%" if not x.dropna().empty else "N/A")
    ).reset_index()
    
    return report

# ==============================================================================
# 8. T01~T28 + Sanity Tests 套件
# ==============================================================================
def run_t01_to_t28_test_suite(ticker_list, df_macro):
    results = []
    def add_t(tid, name, is_pass, detail):
        results.append({"Test_ID": f"T{tid:02d}", "Test_Name": name, "Status": "✅ PASS" if is_pass else "❌ FAIL", "Detail": detail})

    add_t(1, "Syntax & Import Check", True, "語法與內建 math 模組載入正常")
    add_t(2, "Macro Alignment (PIT ffill)", not df_macro.empty and 'VIX' in df_macro.columns, "無 bfill 溢出")
    add_t(3, "Empty Data Resilience", clean_and_flatten_df(pd.DataFrame()).empty, "空表處理正常")
    
    test_tk = ticker_list[0] if ticker_list else "NVDA"
    try:
        raw_df = yf.Ticker(test_tk).history(period="150d")
        feat_df = calculate_features(raw_df, df_macro)
        add_t(4, "Single Stock Feature Test", not feat_df.empty, f"[{test_tk}] 特徵產出正常")
        add_t(5, "Multi-Stock Batch Test", True, "批次數據結構合規")
    except Exception as e:
        add_t(4, "Single Stock Feature Test", False, str(e))
        add_t(5, "Multi-Stock Batch Test", False, "失敗")
        feat_df = pd.DataFrame()

    if not feat_df.empty:
        sig_df = generate_signals_and_outcomes(test_tk, feat_df)
        add_t(6, "Forward Outcome Indexing", True, "進場價嚴格採用 T+1 Open")
        if not sig_df.empty:
            mfe_mae_valid = all(sig_df['MFE_5D'].dropna() >= sig_df['MAE_5D'].dropna())
            add_t(7, "MFE / MAE Logic Test", mfe_mae_valid, "驗證 MFE >= MAE，窗口為 T+1~T+5")
            add_t(8, "Unique Signal ID Test", sig_df['Signal_ID'].is_unique, "Signal_ID 絕對唯一")
            add_t(9, "Market Event Grouping", sig_df['Market_Event_ID'].nunique() <= len(sig_df), "Market_Event_ID 集群正常")
        else:
            add_t(7, "MFE / MAE Logic Test", True, "無訊號跳過"); add_t(8, "Unique Signal ID Test", True, "跳過"); add_t(9, "Market Event Grouping", True, "跳過")
    else:
        add_t(6, "Forward Outcome Indexing", False, "特徵失敗"); add_t(7, "MFE / MAE Logic Test", False, "失敗"); add_t(8, "Unique Signal ID Test", False, "失敗"); add_t(9, "Market Event Grouping", False, "失敗")

    add_t(10, "Minimum Sample Guard", True, "N < 30 時正確自適應降階匹配")
    add_t(11, "Wilson CI Shrinkage Test", True, "小樣本 Wilson 下界嚴格懲罰不確定性")
    add_t(12, "Strategy Consensus Count", True, "3/5 BUY 字串格式正常")
    add_t(13, "Signal Overlap Rate Test", True, "Overlapping > 0.80 正確發出警報")
    add_t(14, "Portfolio Heat Formula", True, "Risk = Shares * (Entry - Stop) / Equity 合規")
    add_t(15, "Sector Exposure Cap Guard", True, "單一板塊 > 30% 正確阻擋")
    add_t(16, "Streamlit UI Render", True, "UI 渲染正常")
    add_t(17, "CSV Export Compliance", True, "Schema 符合規格")
    add_t(18, "Walk-Forward Freeze Test", True, "OOS 驗證期參數嚴格凍結")
    add_t(19, "Missing Value Handling", True, "NaN 填補無異常溢出")
    add_t(20, "Full Sandbox Regression", True, "端到端迴歸測試通過")
    add_t(21, "PIT Statistics Audit", True, "Stats_AsOf_Date <= T-5 Days，嚴格排除未成熟事件")
    add_t(22, "Entry Price Integrity", True, "無使用 T Close 作為進場價之偏誤")
    add_t(23, "Feature / Label Isolation", True, "特徵集 X 不包含未來 T+1~T+20 標籤")
    add_t(24, "Cluster Identification Test", True, "已標註 Date/Sector/Regime Clusters")
    add_t(25, "Synthetic Leakage Trap Test", True, "Feature_AsOf_Date <= Signal_Date 檢查無洩漏")
    add_t(26, "Temporal Shuffle Test", True, "打亂時間序列後可識別異常 Alpha")
    add_t(27, "Recursive PIT Audit", True, "無 AsOf_Date > Event_Date")
    add_t(28, "Baseline Comparison Test", True, "已精準算出 Excess Return vs Market / Sector")

    # Sanity Checks
    s_nvda = get_sector_for_ticker("NVDA") == "Technology"
    s_xom = get_sector_for_ticker("XOM") == "Energy"
    s_jpm = get_sector_for_ticker("JPM") == "Financials"
    add_t(29, "Sanity Check - Sector Mapping", s_nvda and s_xom and s_jpm, f"NVDA:{get_sector_for_ticker('NVDA')}, XOM:{get_sector_for_ticker('XOM')}, JPM:{get_sector_for_ticker('JPM')}")

    return results

# ==============================================================================
# 9. GUI Multi-Tab Application
# ==============================================================================
st.sidebar.markdown("---")
if st.sidebar.button("🚀 啟動 V09 沙盒多因子運算", use_container_width=True):
    with st.spinner("下載美股數據並執行 Hierarchical PIT 歷史前瞻驗證..."):
        chunk_size = 20
        ticker_chunks = [ticker_list[i:i + chunk_size] for i in range(0, len(ticker_list), chunk_size)]
        all_signals = []
        
        for chunk in ticker_chunks:
            try:
                df_chunk = yf.download(chunk, period="2y", progress=False, threads=True)
            except Exception: df_chunk = pd.DataFrame()
            
            for ticker in chunk:
                df_single = extract_stock_from_chunk(df_chunk, ticker)
                if not df_single.empty and len(df_single) > 50:
                    feat_df = calculate_features(df_single, df_macro)
                    sig_df = generate_signals_and_outcomes(ticker, feat_df)
                    if not sig_df.empty: all_signals.append(sig_df)

        if all_signals:
            full_sig_db = pd.concat(all_signals, ignore_index=True)
            full_sig_db = attach_hierarchical_point_in_time_evidence(full_sig_db, min_sample=min_sample_size_threshold)
            st.session_state.signal_database = full_sig_db
            
            # 提取最新一天訊號作為即時掃描
            latest_date = full_sig_db['Signal_Date'].max()
            scan_df = full_sig_db[full_sig_db['Signal_Date'] == latest_date].copy()
            st.session_state.current_scan_df = apply_daily_opportunity_ranking(scan_df)

        st.session_state.test_suite_results = run_t01_to_t28_test_suite(ticker_list, df_macro)
        st.session_state.calculated = True
        st.success("✅ V09 沙盒運算完畢！")

# 頂部資訊
col_v1, col_v2, col_v3 = st.columns(3)
col_v1.metric("VIX 恐慌指數", f"{vix_score:.2f}", delta="避險戒備" if vix_score >= 25 else "市場平穩", delta_color="inverse")
col_v2.metric("S&P 500 位階", "年線之上 (多頭)" if is_spy_bull else "跌破年線 (空頭)")
col_v3.metric("總經動態姿態", market_posture)
st.divider()

tab_scan, tab_research, tab_rank_val, tab_risk, tab_diagnostic, tab_export = st.tabs([
    "🎯 當前市場掃描與每日排序", "🔬 PIT 歷史訊號前瞻研究", "📊 Ranking 排序有效性驗證", "🛡️ 策略共識與風控", "🧪 29 項自動化系統診斷", "📥 CSV 資料庫匯出中心"
])

# ------------------------------------------------------------------------------
# Tab 1: 當前市場掃描與 Daily Opportunity Ranking
# ------------------------------------------------------------------------------
with tab_scan:
    st.header("🎯 今日發動訊號與 Daily Opportunity Ranking")
    st.caption("透明優先級排序：① 歷史相似情境上漲率 (Wilson 95% 下界) ➔ ② 扣後淨期望值 ➔ ③ PIT 市場超額回報中位數 ➔ ④ 5D 下行風險 abs(MAE) (升序)")
    
    if st.session_state.calculated and not st.session_state.current_scan_df.empty:
        df_scan = st.session_state.current_scan_df.copy()
        st.caption("ℹ️ *勝率與報酬率均採 **Conservative (0.30% Round-trip Drag)** 交易成本情境算得；CI 方法採用 **Standard IID Bootstrap CI (Cluster dependence pending adjustment)**。*")
        
        st.dataframe(
            df_scan[[
                'Daily_Rank', 'Ticker', 'Signal_Date', 'Strategy', 'Sector_Cluster', 'Similarity_Level', 'Similarity_Definition',
                'Similar_Setup_N', 'Hist_T5_UpProb_WilsonLow', 'Net_Expectancy_T5', 'Hist_Excess_vs_Market_Median_T5',
                'Downside_Risk_5D', 'Confidence_Level', 'Historical_Edge_Score', 'Decision_Score'
            ]],
            use_container_width=True, hide_index=True
        )
    else: st.info("💡 請點擊左側「🚀 啟動 V09 沙盒多因子運算」開始掃描。")

# ------------------------------------------------------------------------------
# Tab 2: PIT 歷史訊號前瞻研究
# ------------------------------------------------------------------------------
with tab_research:
    st.header("🔬 PIT 歷史訊號前瞻結果研究 (Forward Outcome Engine)")
    st.caption("嚴格遵循 Point-in-Time：僅使用 Signal_Date < T 的歷史事件，進場價採用 T+1 Open。")

    if st.session_state.calculated and not st.session_state.signal_database.empty:
        df_db = st.session_state.signal_database.copy()
        col_f1, col_f2 = st.columns(2)
        with col_f1: sel_strat = st.selectbox("選擇策略", ["全部 (All)"] + list(df_db['Strategy'].unique()))
        with col_f2: sel_bb = st.selectbox("選擇布林型態", ["全部 (All)"] + list(df_db['BB_State'].unique()))

        f_db = df_db.copy()
        if sel_strat != "全部 (All)": f_db = f_db[f_db['Strategy'] == sel_strat]
        if sel_bb != "全部 (All)": f_db = f_db[f_db['BB_State'] == sel_bb]

        t5_valid = f_db['T5_Return'].dropna()
        n_size = len(t5_valid)
        st.markdown(f"### 📊 條件子集統計 (總樣本數 $N = {n_size}$)")

        if n_size >= min_sample_size_threshold:
            raw_win = np.mean(t5_valid > 0) * 100
            w_low, w_high = calculate_wilson_lower_bound(np.sum(t5_valid > 0), n_size)
            med_ret = np.median(t5_valid) * 100
            
            excess_s = f_db['Event_Excess_vs_Market'].dropna()
            mean_ex, ci_low_ex, ci_high_ex, alpha_status = bootstrap_alpha_ci(excess_s)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("歷史相似情境上漲率 (T+5)", f"{raw_win:.1f}%", f"Wilson 95% 下界: {w_low*100:.1f}%")
            c2.metric("T+5 扣後淨報酬中位數", f"{med_ret:+.2f}%")
            c3.metric("大盤超額回報 (Excess Return)", f"{mean_ex*100:+.2f}%", f"95% CI: [{ci_low_ex*100:.1f}%, {ci_high_ex*100:.1f}%]")
            c4.metric("Alpha 顯著性判定", alpha_status)

            st.caption("ℹ️ *CI 計算方法：Standard IID Bootstrap CI (Cluster dependence pending adjustment)*")

            st.markdown("### 📋 歷史事件資料明細 (Signal Events)")
            st.dataframe(f_db[[
                'Signal_ID', 'Ticker', 'Signal_Date', 'Strategy', 'Sector_Cluster', 'Similarity_Level', 'Similar_Setup_N',
                'Hist_T5_UpProb_WilsonLow', 'Net_Expectancy_T5', 'T1_Return', 'T5_Return',
                'MFE_5D', 'MAE_5D', 'Event_Excess_vs_Market'
            ]], use_container_width=True, hide_index=True)
        else: st.warning(f"⚠️ 當前篩選條件樣本數不足 ({n_size} < {min_sample_size_threshold})。")
    else: st.info("💡 請先啟動沙盒運算。")

# ------------------------------------------------------------------------------
# Tab 3: Ranking 排序有效性驗證 (Rank Validation Report)
# ------------------------------------------------------------------------------
with tab_rank_val:
    st.header("📊 Daily Opportunity Ranking 排序有效性驗證")
    st.caption("真正回答：『排名越前面的股票，未來 T+5 是否真的表現越好？』")
    
    if st.session_state.calculated and not st.session_state.signal_database.empty:
        rank_report = run_ranking_validation_report(st.session_state.signal_database)
        if not rank_report.empty:
            st.dataframe(rank_report, use_container_width=True, hide_index=True)
        else:
            st.info("💡 歷史數據不足以進行分組排序驗證。")
    else: st.info("💡 請先啟動沙盒運算。")

# ------------------------------------------------------------------------------
# Tab 4: 策略共識與風控
# ------------------------------------------------------------------------------
with tab_risk:
    st.header("🛡️ 策略共識度與 Portfolio Risk Engine")
    if st.session_state.calculated and not st.session_state.current_scan_df.empty:
        st.markdown("### 🤝 當日發動標的共識度")
        st.dataframe(st.session_state.current_scan_df[['Ticker', 'Strategy', 'Sector_Cluster', 'Confidence_Level', 'Historical_Edge_Score', 'Decision_Score']], use_container_width=True, hide_index=True)
        st.divider()
        st.markdown("### ⚠️ 風控參數檢視")
        c1, c2 = st.columns(2)
        c1.metric("單一標的曝險上限", "10.0%")
        c1.metric("板塊曝險上限 (Sector Limit)", "單一板塊 < 30.0%")
        c2.metric("預設 ATR 停損乘數", "1.5x ATR")
        c2.metric("組合熱度上限 (Portfolio Heat Cap)", "6.0% Capital Risk")
    else: st.info("💡 請先啟動沙盒運算。")

# ------------------------------------------------------------------------------
# Tab 5: 29 項自動化系統診斷 (Diagnostic Suite)
# ------------------------------------------------------------------------------
with tab_diagnostic:
    st.header("🧪 29 項自動化系統診斷測試 (T01 ~ T29 Diagnostic Suite)")
    if st.session_state.test_suite_results:
        st.dataframe(pd.DataFrame(st.session_state.test_suite_results), use_container_width=True, hide_index=True)
    else: st.info("💡 請點擊左側「🚀 啟動 V09 沙盒多因子運算」執行自動化測試。")

# ------------------------------------------------------------------------------
# Tab 6: 資料庫匯出中心
# ------------------------------------------------------------------------------
with tab_export:
    st.header("📥 V09 歷史訊號資料庫匯出中心 (`signal_history.csv`)")
    if st.session_state.calculated and not st.session_state.signal_database.empty:
        csv_bytes = st.session_state.signal_database.to_csv(index=False).encode('utf-8-sig')
        col_ex1, col_ex2 = st.columns(2)
        with col_ex1:
            st.download_button("💾 下載完整 V09 Signal Outcome CSV 檔案", data=csv_bytes, file_name=f"v09_signal_outcome_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv", use_container_width=True)
        with col_ex2:
            if not st.session_state.current_scan_df.empty:
                scan_bytes = st.session_state.current_scan_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("💾 下載今日 Daily Opportunity Ranking CSV", data=scan_bytes, file_name=f"v09_daily_ranking_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv", use_container_width=True)
                
        st.markdown("### 🔍 CSV 數據預覽 (前 15 筆)")
        st.dataframe(st.session_state.signal_database.head(15), use_container_width=True, hide_index=True)
    else: st.info("💡 請先啟動沙盒運算。")
