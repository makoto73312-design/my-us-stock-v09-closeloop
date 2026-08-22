import hashlib
import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st

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
def fetch_us_macro_dataframe_fail_closed_v0941b():
    try:
        df_raw = yf.download(["^VIX", "SPY"], period="3y", progress=False, threads=False)
        if df_raw is not None and not df_raw.empty:
            if isinstance(df_raw.columns, pd.MultiIndex):
                df_close = df_raw['Close'].copy() if 'Close' in df_raw.columns.get_level_values(0) else df_raw.copy()
                df_open = df_raw['Open'].copy() if 'Open' in df_raw.columns.get_level_values(0) else df_raw.copy()
            else:
                df_close = df_raw.copy()
                df_open = df_raw.copy()

            spy_close_col = [c for c in df_close.columns if 'SPY' in str(c).upper()]
            vix_close_col = [c for c in df_close.columns if 'VIX' in str(c).upper()]
            spy_open_col = [c for c in df_open.columns if 'SPY' in str(c).upper()]

            if spy_close_col and vix_close_col and spy_open_col:
                df_macro_full = pd.DataFrame({
                    'SPY_Close': df_close[spy_close_col[0]],
                    'SPY_Open': df_open[spy_open_col[0]],
                    'VIX': df_close[vix_close_col[0]]
                }).dropna(how='all')
                df_macro_full.index = pd.to_datetime(pd.to_datetime(df_macro_full.index).date)
                df_macro_full = df_macro_full.ffill().dropna()

                macro_warmup_start = df_macro_full.index[0].strftime('%Y-%m-%d')
                
                df_macro_full['SPY_MA200'] = df_macro_full['SPY_Close'].rolling(200, min_periods=200).mean()
                df_macro_full['Market_Bull'] = np.where(
                    df_macro_full['SPY_MA200'].notna(),
                    df_macro_full['SPY_Close'] >= df_macro_full['SPY_MA200'],
                    np.nan
                )
                
                valid_ma200_df = df_macro_full[df_macro_full['SPY_MA200'].notna()]
                first_valid_ma200_date = valid_ma200_df.index[0].strftime('%Y-%m-%d') if not valid_ma200_df.empty else "N/A"

                end_date = df_macro_full.index[-1]
                start_research_date = end_date - pd.DateOffset(years=2)
                df_macro_res = df_macro_full[df_macro_full.index >= start_research_date].copy()
                research_start = df_macro_res.index[0].strftime('%Y-%m-%d')

                latest_vix = float(df_macro_res['VIX'].iloc[-1])
                latest_bull = bool(df_macro_res['Market_Bull'].iloc[-1]) if pd.notna(df_macro_res['Market_Bull'].iloc[-1]) else False
                latest_date_str = df_macro_res.index[-1].strftime('%Y-%m-%d')
                posture_auto = "🥶 極度謹慎" if (latest_vix >= 25 or not latest_bull) else ("🚀 大膽進攻" if (latest_vix <= 15 and latest_bull) else "🛡️ 標準平衡")
                
                audit_dict = {
                    "Macro_Warmup_Start_Date": macro_warmup_start,
                    "Research_Start_Date": research_start,
                    "First_Valid_SPY_MA200_Date": first_valid_ma200_date,
                    "SPY_MA200_Min_Periods": 200
                }
                
                return df_macro_res, latest_vix, latest_bull, posture_auto, "VALID_LIVE", "Yahoo Finance Live Bulk API (3y WarmUp)", latest_date_str, audit_dict
    except Exception:
        pass

    return pd.DataFrame(), np.nan, False, "🛑 數據熔斷", "INVALID", "None", "N/A", {}

def compute_data_snapshot_content_hash(stock_data_dict, df_macro_input):
    hasher = hashlib.sha256()
    
    if not df_macro_input.empty:
        macro_sub = df_macro_input[['SPY_Open', 'SPY_Close', 'VIX']].sort_index()
        macro_bytes = pd.util.hash_pandas_object(macro_sub, index=True).values.tobytes()
        hasher.update(macro_bytes)
        
    for tk in sorted(stock_data_dict.keys()):
        df_tk = stock_data_dict[tk]
        if not df_tk.empty and all(c in df_tk.columns for c in ['Open', 'High', 'Low', 'Close', 'Volume']):
            tk_sub = df_tk[['Open', 'High', 'Low', 'Close', 'Volume']].sort_index()
            tk_bytes = pd.util.hash_pandas_object(tk_sub, index=True).values.tobytes()
            hasher.update(tk.encode('utf-8'))
            hasher.update(tk_bytes)
            
    return "SNAP_" + hasher.hexdigest()[:12]
