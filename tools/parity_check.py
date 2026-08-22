import os
import argparse
import pandas as pd
import numpy as np

IGNORE_FIELDS = {
    "Run_ID", "Generated_At_UTC", "Code_Version", "Runtime_Total_sec"
}

FLOAT_TOLERANCE = 1e-12

def check_parity(golden_dir, modular_dir):
    records = []
    
    # 1. Load Metadata & Check Preconditions
    meta_golden_path = os.path.join(golden_dir, "run_metadata_v0941b_T21fix_candidate.csv")
    if not os.path.exists(meta_golden_path):
        meta_golden_path = os.path.join(golden_dir, "run_metadata_v0941b.csv")
        
    meta_mod_path = os.path.join(modular_dir, "run_metadata_v0942.csv")

    if not os.path.exists(meta_golden_path) or not os.path.exists(meta_mod_path):
        print("❌ Metadata files missing for comparison.")
        return False

    meta_g = pd.read_csv(meta_golden_path).iloc[0]
    meta_m = pd.read_csv(meta_mod_path).iloc[0]

    u_hash_match = (str(meta_g.get('Universe_Hash', '')) == str(meta_m.get('Universe_Hash', '')))
    c_hash_match = (str(meta_g.get('Config_Hash', '')) == str(meta_m.get('Config_Hash', '')))
    d_hash_match = (str(meta_g.get('Data_Snapshot_ID', '')) == str(meta_m.get('Data_Snapshot_ID', '')))

    records.append({
        "Section": "Preconditions", "Check": "Universe_Hash",
        "Golden_Value": meta_g.get('Universe_Hash', ''), "Modular_Value": meta_m.get('Universe_Hash', ''),
        "Difference": "0" if u_hash_match else "Mismatch", "Status": "PASS" if u_hash_match else "FAIL"
    })
    records.append({
        "Section": "Preconditions", "Check": "Config_Hash",
        "Golden_Value": meta_g.get('Config_Hash', ''), "Modular_Value": meta_m.get('Config_Hash', ''),
        "Difference": "0" if c_hash_match else "Mismatch", "Status": "PASS" if c_hash_match else "FAIL"
    })
    records.append({
        "Section": "Preconditions", "Check": "Data_Snapshot_ID",
        "Golden_Value": meta_g.get('Data_Snapshot_ID', ''), "Modular_Value": meta_m.get('Data_Snapshot_ID', ''),
        "Difference": "0" if d_hash_match else "Mismatch", "Status": "PASS" if d_hash_match else "FAIL"
    })

    if not (u_hash_match and c_hash_match and d_hash_match):
        df_rep = pd.DataFrame(records)
        df_rep.loc[len(df_rep)] = {
            "Section": "Summary", "Check": "Final_Parity_Status",
            "Golden_Value": "N/A", "Modular_Value": "N/A",
            "Difference": "DATA_NOT_COMPARABLE", "Status": "DATA_NOT_COMPARABLE"
        }
        df_rep.to_csv("parity_report.csv", index=False)
        print("⚠️ Preconditions failed: Data environments are not identical (DATA_NOT_COMPARABLE).")
        return False

    # 2. File Mappings for CSV Comparison
    file_pairs = [
        ("strategy_event_history_v0941b_T21fix_candidate.csv", "strategy_event_history_v0942.csv", "Strategy Events"),
        ("stock_event_history_v0941b_T21fix_candidate.csv", "stock_event_history_v0942.csv", "Stock Events"),
        ("daily_stock_ranking_v0941b_T21fix_candidate.csv", "daily_stock_ranking_v0942.csv", "Daily Ranking"),
        ("test_report_v0941b_T21fix_candidate.csv", "test_report_v0942.csv", "Test Report")
    ]

    all_passed = True

    for g_fname, m_fname, label in file_pairs:
        g_path = os.path.join(golden_dir, g_fname)
        if not os.path.exists(g_path):
            g_path = os.path.join(golden_dir, g_fname.replace("_T21fix_candidate", ""))
        m_path = os.path.join(modular_dir, m_fname)

        if not os.path.exists(g_path) or not os.path.exists(m_path):
            records.append({
                "Section": label, "Check": "File_Existence",
                "Golden_Value": os.path.exists(g_path), "Modular_Value": os.path.exists(m_path),
                "Difference": "Missing File", "Status": "FAIL"
            })
            all_passed = False
            continue

        df_g = pd.read_csv(g_path)
        df_m = pd.read_csv(m_path)

        # Row Count Parity
        row_match = (len(df_g) == len(df_m))
        records.append({
            "Section": label, "Check": "Row_Count",
            "Golden_Value": len(df_g), "Modular_Value": len(df_m),
            "Difference": len(df_m) - len(df_g), "Status": "PASS" if row_match else "FAIL"
        })
        if not row_match: all_passed = False

        # Column Compare
        cols_to_check = [c for c in df_g.columns if c in df_m.columns and c not in IGNORE_FIELDS]
        for col in cols_to_check:
            s_g = df_g[col]
            s_m = df_m[col]

            if pd.api.types.is_numeric_dtype(s_g) and pd.api.types.is_numeric_dtype(s_m):
                diff = (s_g - s_m).abs()
                max_diff = diff.max(skipna=True) if not diff.dropna().empty else 0.0
                if max_diff <= FLOAT_TOLERANCE:
                    status = "PASS" if max_diff == 0 else "FLOAT_TOLERANCE_PASS"
                else:
                    status = "FAIL"
                    all_passed = False
                records.append({
                    "Section": label, "Check": f"Column_{col}",
                    "Golden_Value": f"MaxDiff: {max_diff}", "Modular_Value": "Within Tolerance",
                    "Difference": str(max_diff), "Status": status
                })
            else:
                mismatches = (s_g.astype(str) != s_m.astype(str)).sum()
                status = "PASS" if mismatches == 0 else "FAIL"
                if mismatches > 0: all_passed = False
                records.append({
                    "Section": label, "Check": f"Column_{col}",
                    "Golden_Value": f"Mismatches: {mismatches}", "Modular_Value": f"Total: {len(s_g)}",
                    "Difference": str(mismatches), "Status": status
                })

    final_status = "PASS" if all_passed else "FAIL"
    records.append({
        "Section": "Summary", "Check": "Final_Parity_Status",
        "Golden_Value": "PASS", "Modular_Value": final_status,
        "Difference": "0" if all_passed else "Mismatch Detected", "Status": final_status
    })

    df_rep = pd.DataFrame(records)
    df_rep.to_csv("parity_report.csv", index=False)
    print(f"📊 Parity Check Finished. Final Status: {final_status}")
    return all_passed

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V09.4.2 Modular Refactor Parity Checker")
    parser.add_argument("--golden_dir", type=str, default=".", help="Directory containing Golden Reference CSVs")
    parser.add_argument("--modular_dir", type=str, default=".", help="Directory containing V09.4.2 Modular Output CSVs")
    args = parser.parse_args()
    check_parity(args.golden_dir, args.modular_dir)
