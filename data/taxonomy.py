import os
import time
import hashlib
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf

from core.config import (
    TICKER_MASTER_FILE,
    CANONICAL_SECTOR_MAP,
    KNOWN_ETF_MAP,
    STATIC_SECTOR_MAP
)

def load_ticker_master_df():
    if os.path.exists(TICKER_MASTER_FILE):
        try:
            return pd.read_csv(TICKER_MASTER_FILE)
        except Exception:
            pass
    return pd.DataFrame(columns=["Ticker", "Sector", "Asset_Type", "Taxonomy_Source", "Last_Updated_UTC"])

def save_ticker_master_df(master_df):
    try:
        master_df.to_csv(TICKER_MASTER_FILE, index=False)
    except Exception:
        pass

def compute_ticker_master_hash(master_df):
    if master_df.empty:
        return "EMPTY_MASTER"
    sorted_df = master_df[['Ticker', 'Sector', 'Asset_Type']].sort_values('Ticker').astype(str)
    canonical_str = "\n".join([f"{r.Ticker},{r.Sector},{r.Asset_Type}" for r in sorted_df.itertuples()])
    return hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()

def fetch_yahoo_taxonomy_with_retry(ticker, max_retries=3):
    tk_u = str(ticker).upper().strip()
    for attempt in range(max_retries):
        try:
            info = yf.Ticker(tk_u).info
            quote_type = info.get('quoteType', 'EQUITY').upper()
            sec = info.get('sector', None)
            asset_type = "ETF" if quote_type == 'ETF' else "Stock"
            if asset_type == "ETF":
                return ("ETF / Multi-Sector", asset_type, "Yahoo_API")
            if sec and isinstance(sec, str) and len(sec.strip()) > 0:
                sec_clean = CANONICAL_SECTOR_MAP.get(sec.strip(), sec.strip())
                return (sec_clean, asset_type, "Yahoo_API")
        except Exception:
            time.sleep(0.3 * (2 ** attempt))
    return ("Unknown", "Stock", "Unknown")

def resolve_taxonomy_for_ticker(ticker, master_df):
    tk_u = str(ticker).upper().strip()
    
    # Priority 1: KNOWN_ETF_MAP
    if tk_u in KNOWN_ETF_MAP:
        return ("ETF / Multi-Sector", KNOWN_ETF_MAP[tk_u], "KNOWN_ETF_MAP")
        
    # Priority 2: STATIC_SECTOR_MAP
    if tk_u in STATIC_SECTOR_MAP:
        sec, atype = STATIC_SECTOR_MAP[tk_u]
        return (CANONICAL_SECTOR_MAP.get(sec, sec), atype, "STATIC_SECTOR_MAP")
        
    # Priority 3: ticker_master.csv (if valid sector)
    if master_df is not None and not master_df.empty and tk_u in master_df['Ticker'].values:
        m_row = master_df[master_df['Ticker'] == tk_u].iloc[0]
        sec_m = str(m_row['Sector']).strip()
        if sec_m not in ["Unknown", "nan", ""]:
            return (CANONICAL_SECTOR_MAP.get(sec_m, sec_m), m_row['Asset_Type'], "ticker_master.csv")
            
    # Priority 4: Yahoo Finance API with Backoff
    sec, atype, source = fetch_yahoo_taxonomy_with_retry(tk_u)
    if sec != "Unknown":
        return sec, atype, source
        
    # Priority 5: Honest Unknown
    return ("Unknown", "Stock", "Unknown")

def update_and_audit_taxonomy_master(ticker_list):
    master_df = load_ticker_master_df()
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    
    master_dict = {}
    if not master_df.empty:
        for _, row in master_df.iterrows():
            master_dict[str(row['Ticker']).upper().strip()] = {
                "Ticker": str(row['Ticker']).upper().strip(),
                "Sector": str(row['Sector']),
                "Asset_Type": str(row['Asset_Type']),
                "Taxonomy_Source": str(row['Taxonomy_Source']),
                "Last_Updated_UTC": str(row['Last_Updated_UTC'])
            }
            
    # UPSERT current universe tickers
    for tk in sorted(list(set(ticker_list))):
        existing_item = master_dict.get(tk, None)
        existing_sec = existing_item["Sector"] if existing_item else "Unknown"
        
        # Resolve using priority chain
        new_sec, new_atype, new_source = resolve_taxonomy_for_ticker(tk, master_df)
        
        if existing_sec not in ["Unknown", "nan", ""] and new_sec == "Unknown":
            # Rule 4: Unknown MUST NOT overwrite Known
            continue
        
        if new_sec != "Unknown" or existing_item is None:
            master_dict[tk] = {
                "Ticker": tk,
                "Sector": new_sec,
                "Asset_Type": new_atype,
                "Taxonomy_Source": new_source,
                "Last_Updated_UTC": now_str
            }
            # Immediate persistent save for each updated item
            save_ticker_master_df(pd.DataFrame(list(master_dict.values())).sort_values("Ticker").reset_index(drop=True))

    full_master_df = pd.DataFrame(list(master_dict.values())).sort_values("Ticker").reset_index(drop=True)
    save_ticker_master_df(full_master_df)

    # Coverage Audit for Current Universe
    curr_universe_set = set(ticker_list)
    known_count = 0
    unknown_count = 0
    for tk in curr_universe_set:
        item = master_dict.get(tk, None)
        if item and item["Sector"] not in ["Unknown", "nan", ""]:
            known_count += 1
        else:
            unknown_count += 1

    total = len(curr_universe_set)
    cov_rate = (known_count / total) if total > 0 else 0.0
    status = "PASS" if cov_rate >= 0.95 else ("WARN" if cov_rate >= 0.80 else "FAIL")

    return full_master_df, known_count, unknown_count, cov_rate, status
