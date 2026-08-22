import hashlib
import json
from datetime import datetime, timezone

# ==============================================================================
# Version & System Configuration
# ==============================================================================
VERSION = "V09.4.2"
VERSION_NAME = "V09.4.2 Modular Refactor"
TICKER_MASTER_FILE = "ticker_master.csv"

def generate_run_id():
    return f"V0942_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_f8c2b0"

def get_gen_time():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

# ==============================================================================
# External Integration & Forms
# ==============================================================================
GSHEET_URL = "https://docs.google.com/spreadsheets/d/1491qc1Y59PwCOWaPZblpAieR0_iCI-7KKLtZUuG7Qe4/edit?usp=sharing"
GOOGLE_FORM_ID = "1FAIpQLSdpLHywd-HysLTMbGpuEByQwEaoVaqtvTW0Uwav136m-kIDfQ"
ENTRY_TICKER_ID = "entry.2146824153"
ENTRY_NAME_ID = "entry.1673006020"

# ==============================================================================
# Sector & Taxonomy Mappings
# ==============================================================================
CANONICAL_SECTOR_MAP = {
    "Financial Services": "Financials",
    "Financial": "Financials",
    "Consumer Defensive": "Consumer Staples",
    "Consumer Cyclical": "Consumer Cyclical",
    "Consumer Discretionary": "Consumer Cyclical",
    "Information Technology": "Technology",
    "Tech": "Technology",
    "Health Care": "Healthcare",
    "Healthcare": "Healthcare",
    "Basic Materials": "Basic Materials",
    "Energy": "Energy",
    "Communication Services": "Communication Services"
}

KNOWN_ETF_MAP = {
    "SPY": "ETF", "VOO": "ETF", "QQQ": "ETF", "IWM": "ETF", "XLV": "ETF", "SMH": "ETF", "XBI": "ETF", "XLU": "ETF",
    "LABU": "Leveraged ETF", "TQQQ": "Leveraged ETF", "SOXL": "Leveraged ETF", "SQQQ": "Leveraged ETF", "SOXS": "Leveraged ETF"
}

STATIC_SECTOR_MAP = {
    "NVDA": ("Technology", "Stock"), "AAPL": ("Technology", "Stock"), "MSFT": ("Technology", "Stock"), 
    "AMD": ("Technology", "Stock"), "AVGO": ("Technology", "Stock"), "TSM": ("Technology", "Stock"), 
    "INTC": ("Technology", "Stock"), "QCOM": ("Technology", "Stock"), "MU": ("Technology", "Stock"), 
    "ARM": ("Technology", "Stock"), "ORCL": ("Technology", "Stock"), "CRM": ("Technology", "Stock"),
    "MRVL": ("Technology", "Stock"), "ADBE": ("Technology", "Stock"), "PYPL": ("Financials", "Stock"),
    "HOOD": ("Financials", "Stock"), "BABA": ("Consumer Cyclical", "Stock"), "PDD": ("Consumer Cyclical", "Stock"),
    "AMZN": ("Consumer Cyclical", "Stock"), "TSLA": ("Consumer Cyclical", "Stock"), "HD": ("Consumer Cyclical", "Stock"),
    "FCX": ("Basic Materials", "Stock"), "HAL": ("Energy", "Stock"), "XOM": ("Energy", "Stock"),
    "CVX": ("Energy", "Stock"), "COP": ("Energy", "Stock"), "SLB": ("Energy", "Stock"),
    "SPOT": ("Communication Services", "Stock"), "NFLX": ("Communication Services", "Stock"), "DIS": ("Communication Services", "Stock"),
    "COIN": ("Financials", "Stock"), "RIOT": ("Financials", "Stock"), "RIVN": ("Consumer Cyclical", "Stock"),
    "KO": ("Consumer Staples", "Stock"), "WMT": ("Consumer Staples", "Stock"), "COST": ("Consumer Staples", "Stock"),
    "PG": ("Consumer Staples", "Stock"), "TMO": ("Healthcare", "Stock"), "LLY": ("Healthcare", "Stock"),
    "PFE": ("Healthcare", "Stock"), "ABBV": ("Healthcare", "Stock"), "JNJ": ("Healthcare", "Stock"),
    "UNH": ("Healthcare", "Stock"), "MRK": ("Healthcare", "Stock"), "JPM": ("Financials", "Stock"),
    "BAC": ("Financials", "Stock"), "WFC": ("Financials", "Stock"), "GS": ("Financials", "Stock"),
    "MS": ("Financials", "Stock"), "C": ("Financials", "Stock")
}

# ==============================================================================
# Feature & Model Column Sets
# ==============================================================================
MODEL_FEATURE_COLUMNS = {
    "VIX", "Market_Bull", "RSI14", "BB_State", "RS20", "Score_7D", "7D_Bucket", "RS20_Bucket",
    "EMA10", "EMA20", "MA5", "MA14", "MA20", "MA50", "MA200", "Vol_SMA20", "CLV", "ATR14",
    "BB_Mid", "BB_Upper", "BB_Lower", "BB_Width", "BB_Squeeze", "ROC14", "MACD", "Signal", "MACD_Hist", "MACD_Shrink"
}

RANKING_FEATURE_COLUMNS = {
    "WilsonLow", "Net_Expectancy", "Historical_Excess", "Downside_Risk", "Similarity_N_T5", "Historical_Edge_Score"
}

FORBIDDEN_FEATURE_COLUMNS = {
    "Candidate_Status", "Candidate_Status_Is_PostHoc", "Gate_OOS_Status", "Ranking_Validation_Status",
    "T1_Return", "T3_Return", "T5_Return", "T10_Return", "T20_Return",
    "MFE_5D", "MAE_5D", "Event_SPY_Gross_Return_T5", "Event_Excess_vs_SPY_GrossBenchmark",
    "Stock_Gate_Pass", "Stock_Gate_Fail_Reason"
}

# ==============================================================================
# Research Constants & Cost Scenarios
# ==============================================================================
COST_SCENARIOS = {
    "Base": {"total_roundtrip": 0.0014},
    "Conservative": {"total_roundtrip": 0.0030},
    "Stress": {"total_roundtrip": 0.0070}
}

MIN_OOS_VALID_WINDOWS = 4
OOS_WINDOW_SIZE = 60
OOS_STEP_SIZE = 30
