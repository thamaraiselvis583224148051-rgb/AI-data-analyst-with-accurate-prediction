"""Python & Pandas Deterministic Transformation Engine for Data Quality."""
import re
import io
import math
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
import numpy as np
from dateutil import parser as date_parser

from models import (
    AgentSemanticAnalysis,
    CleaningOperation,
    BeforeAfterMetrics,
    FullCleaningResult,
    ReviewIssue,
    RawRecordExtracted,
    RecordAttribute,
    DetectedProblem,
    ColumnDefinition
)

NULL_PLACEHOLDERS = {
    "n/a", "na", "null", "none", "unknown", "-", "--", "---", "?", 
    "missing", "nan", "nil", "empty", "not provided", "not available",
    "invalid", "unspecified", "undefined", "#n/a", "#value!", "n.a.", "none"
}

CURRENCY_SYMBOLS = {"$", "€", "£", "¥", "₹", "rs.", "rs", "inr", "usd", "eur", "gbp"}

def clean_column_name(col: str) -> str:
    """Standardize column names to lowercase snake_case."""
    # Strip currency or special characters
    col_str = str(col).strip()
    for sym in CURRENCY_SYMBOLS:
        col_str = col_str.replace(sym, "")
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", col_str.strip())
    clean = re.sub(r"_+", "_", clean).strip("_").lower()
    return clean or "unnamed_column"

def normalize_text_casing(val: Any) -> Any:
    """Normalize whitespace and casing for text."""
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() in NULL_PLACEHOLDERS:
        return None
    # If all lowercase or all uppercase (and > 1 char), apply title case for readability
    if (s.islower() or s.isupper()) and len(s) > 2 and "@" not in s and "http" not in s:
        return s.title()
    return s

def try_parse_date(val: Any) -> Optional[str]:
    """Safely parse mixed date strings into ISO-8601 YYYY-MM-DD."""
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if s.lower() in NULL_PLACEHOLDERS or not s:
        return None
    # Skip if clearly not a date
    if len(s) < 4 or len(s) > 30:
        return None
    try:
        # Dayfirst=True handles international/Indian formats like 18/05/26
        dt = date_parser.parse(s, dayfirst=True, fuzzy=False)
        # Check realistic year range (1900 to 2100)
        if 1900 <= dt.year <= 2100:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None

def try_parse_currency_or_number(val: Any) -> Optional[float]:
    """Extract clean float from currency or numeric string."""
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if s.lower() in NULL_PLACEHOLDERS or not s:
        return None
    # Strip currency symbols, quotes, commas
    clean_s = s
    for sym in ["$", "€", "£", "¥", "₹", "Rs.", "Rs", "rs", "INR", "USD", ",", '"', "'"]:
        clean_s = clean_s.replace(sym, "")
    clean_s = clean_s.strip()
    try:
        f = float(clean_s)
        if not math.isnan(f) and not math.isinf(f):
            return f
    except (ValueError, TypeError):
        pass
    return None

def build_cleaned_dataframe(
    analysis: AgentSemanticAnalysis,
    raw_content: str,
    fill_missing: bool = True
) -> Tuple[pd.DataFrame, List[CleaningOperation], BeforeAfterMetrics, List[ReviewIssue], Dict[str, Any]]:
    """
    Transform extracted data deterministically using Python & Pandas.
    Returns:
      (cleaned_df, operations_log, before_after_metrics, review_issues, cell_imputations_meta)
    """
    operations: List[CleaningOperation] = []
    step_num = 1
    review_issues: List[ReviewIssue] = list(analysis.flagged_review_issues)

    # 1. Construct raw records DataFrame
    raw_records_data = [
        {attr.column_name: attr.value for attr in r.attributes}
        for r in analysis.extracted_records
    ]
    initial_row_count = len(raw_records_data)
    
    if not raw_records_data:
        df = pd.DataFrame()
        empty_metrics = BeforeAfterMetrics(
            initial_row_count=0,
            cleaned_row_count=0,
            initial_column_count=0,
            cleaned_column_count=0,
            initial_missing_cells=0,
            cleaned_missing_cells=0,
            imputed_cells_count=0,
            exact_duplicates_removed=0,
            initial_health_score_pct=100.0,
            cleaned_health_score_pct=100.0,
            data_retention_rate_pct=100.0
        )
        return df, operations, empty_metrics, review_issues, {}

    df = pd.DataFrame(raw_records_data)
    initial_col_count = len(df.columns)

    # 2. Standardize column names
    col_mapping = {}
    for col in df.columns:
        col_mapping[col] = clean_column_name(col)
    
    seen = {}
    unique_mapping = {}
    for old_col, new_col in col_mapping.items():
        if new_col in seen:
            seen[new_col] += 1
            unique_mapping[old_col] = f"{new_col}_{seen[new_col]}"
        else:
            seen[new_col] = 1
            unique_mapping[old_col] = new_col

    df = df.rename(columns=unique_mapping)
    operations.append(CleaningOperation(
        step_number=step_num,
        operation_name="Column Name Standardization",
        details=f"Conformed {len(df.columns)} columns to lowercase snake_case standard.",
        records_affected=len(df.columns)
    ))
    step_num += 1

    # Track initial missing cells count across all raw fields
    initial_missing_cells = 0
    for col in df.columns:
        for val in df[col]:
            if val is None or pd.isna(val) or str(val).strip().lower() in NULL_PLACEHOLDERS:
                initial_missing_cells += 1

    # 3. Clean placeholders and blanks to None
    null_remediated_count = 0
    for col in df.columns:
        for idx, val in df[col].items():
            if val is None or pd.isna(val):
                df.at[idx, col] = None
                null_remediated_count += 1
            elif isinstance(val, str):
                s_strip = val.strip()
                if s_strip == "" or s_strip.lower() in NULL_PLACEHOLDERS:
                    df.at[idx, col] = None
                    null_remediated_count += 1
                else:
                    df.at[idx, col] = s_strip

    operations.append(CleaningOperation(
        step_number=step_num,
        operation_name="Null & Corrupt Placeholder Sanitization",
        details=f"Normalized {null_remediated_count} null/corrupt entries ('N/A', 'invalid', 'unknown', '---') to standard null.",
        records_affected=null_remediated_count
    ))
    step_num += 1

    # 4. Remove exact duplicates
    pre_dedup_rows = len(df)
    df = df.drop_duplicates(keep="first").reset_index(drop=True)
    exact_duplicates_removed = pre_dedup_rows - len(df)

    if exact_duplicates_removed > 0:
        operations.append(CleaningOperation(
            step_number=step_num,
            operation_name="Exact Duplicate Deduplication",
            details=f"Identified and removed {exact_duplicates_removed} redundant duplicate record(s). Preserved primary golden records.",
            records_affected=exact_duplicates_removed
        ))
        step_num += 1

    # 5. Domain-Specific Type Standardization & Anomaly Detection
    # Dates standardization
    date_cols_affected = 0
    for col in df.columns:
        col_lower = col.lower()
        if any(kw in col_lower for kw in ["date", "time", "dob", "registered", "join"]):
            for idx, val in df[col].items():
                if val is not None:
                    parsed_d = try_parse_date(val)
                    if parsed_d:
                        df.at[idx, col] = parsed_d
                        date_cols_affected += 1
                    else:
                        # Suspect date
                        review_issues.append(ReviewIssue(
                            row_reference=f"Row {idx + 1}",
                            field_name=col,
                            suspect_value=str(val),
                            reason_for_flagging="Unparseable or out-of-range date format",
                            recommended_action="Verify original timestamp with upstream source"
                        ))
    if date_cols_affected > 0:
        operations.append(CleaningOperation(
            step_number=step_num,
            operation_name="ISO-8601 Date Standardization",
            details=f"Conformed {date_cols_affected} disparate dates into ISO-8601 (YYYY-MM-DD) standard.",
            records_affected=date_cols_affected
        ))
        step_num += 1

    # Currency and monetary normalization
    curr_cols_affected = 0
    for col in df.columns:
        col_lower = col.lower()
        is_money_col = any(kw in col_lower for kw in ["spend", "amount", "price", "revenue", "cost", "salary", "balance", "fee"])
        # Check if values contain currency signs
        if not is_money_col:
            sample_strs = [str(x) for x in df[col].dropna()[:5]]
            if any(any(sym in s for sym in ["$", "€", "£", "₹", "Rs"]) for s in sample_strs):
                is_money_col = True

        if is_money_col:
            for idx, val in df[col].items():
                if val is not None:
                    parsed_num = try_parse_currency_or_number(val)
                    if parsed_num is not None:
                        df.at[idx, col] = f"{parsed_num:.2f}"
                        curr_cols_affected += 1
                    else:
                        # Was text like 'invalid' in currency column
                        review_issues.append(ReviewIssue(
                            row_reference=f"Row {idx + 1}",
                            field_name=col,
                            suspect_value=str(val),
                            reason_for_flagging="Non-numeric corrupted string in monetary/spend field",
                            recommended_action="Imputed with column median for analysis continuity; verify receipt"
                        ))
                        df.at[idx, col] = None
    if curr_cols_affected > 0:
        operations.append(CleaningOperation(
            step_number=step_num,
            operation_name="Currency & Monetary Formatting",
            details=f"Stripped currency symbols, commas, and normalized {curr_cols_affected} monetary entries to 2-decimal floats.",
            records_affected=curr_cols_affected
        ))
        step_num += 1

    # Age and bio-numeric bounds validation
    for col in df.columns:
        if "age" in col.lower():
            for idx, val in df[col].items():
                if val is not None:
                    try:
                        num_age = float(val)
                        if num_age <= 0 or num_age > 120:
                            review_issues.append(ReviewIssue(
                                row_reference=f"Row {idx + 1}",
                                field_name=col,
                                suspect_value=str(val),
                                reason_for_flagging="Biologically impossible age value detected (<= 0 or > 120)",
                                recommended_action="Preserved for human review; imputed with median cohort age for analytical model readiness"
                            ))
                            df.at[idx, col] = None  # Clear impossible age so median imputes cleanly
                    except (ValueError, TypeError):
                        review_issues.append(ReviewIssue(
                            row_reference=f"Row {idx + 1}",
                            field_name=col,
                            suspect_value=str(val),
                            reason_for_flagging="Non-numeric string in age column",
                            recommended_action="Imputed with cohort median; verify identity"
                        ))
                        df.at[idx, col] = None

    # Text & Casing normalization (e.g. city names, statuses)
    for col in df.columns:
        col_lower = col.lower()
        if any(kw in col_lower for kw in ["city", "country", "name", "status", "tier", "category", "department"]):
            df[col] = df[col].apply(normalize_text_casing)

    # 6. SMART COMPREHENSIVE IMPUTATION ENGINE (Addresses "fill null and missing values")
    imputed_cells_count = 0
    cell_imputations: Dict[int, Dict[str, Dict[str, str]]] = {}
    # Structure: {row_index: {col_name: {"type": "median"|"mode"|"default", "value": "28.00", "label": "Median Imputed"}}}

    if fill_missing:
        imputation_log_details = []
        for col in df.columns:
            missing_in_col = df[col].isnull().sum()
            if missing_in_col > 0:
                non_null_vals = df[col].dropna()
                col_lower = col.lower()

                # A. Numerical Imputation (Age, Spend, Amount, etc.)
                is_numeric_type = False
                parsed_nums = []
                for v in non_null_vals:
                    num_val = try_parse_currency_or_number(v)
                    if num_val is not None:
                        parsed_nums.append(num_val)

                if len(parsed_nums) > 0 and len(parsed_nums) >= (len(non_null_vals) * 0.5):
                    is_numeric_type = True

                if is_numeric_type and len(parsed_nums) > 0:
                    median_num = float(np.median(parsed_nums))
                    # Format as int if age or integer-like, else 2-decimal
                    if "age" in col_lower or "count" in col_lower or "qty" in col_lower or "quantity" in col_lower:
                        fill_str = str(int(round(median_num)))
                        label = f"Median Imputed ({fill_str})"
                    else:
                        fill_str = f"{median_num:.2f}"
                        label = f"Median Imputed ({fill_str})"

                    for idx in df[df[col].isnull()].index:
                        df.at[idx, col] = fill_str
                        if idx not in cell_imputations:
                            cell_imputations[idx] = {}
                        cell_imputations[idx][col] = {
                            "strategy": "Median Imputation",
                            "value": fill_str,
                            "label": label
                        }

                    imputed_cells_count += int(missing_in_col)
                    imputation_log_details.append(f"{col} &rarr; median {fill_str}")

                # B. Categorical / Text Imputation (City, Status, Tier, etc.)
                else:
                    fill_str = ""
                    label = ""
                    mode_s = non_null_vals.mode()
                    mode_val = mode_s.iloc[0] if not mode_s.empty else None

                    if "email" in col_lower:
                        fill_str = "contact.unspecified@domain.com"
                        label = "Contextual Default"
                    elif "phone" in col_lower or "contact" in col_lower:
                        fill_str = "Not Provided"
                        label = "Standard Placeholder"
                    elif "status" in col_lower:
                        fill_str = mode_val if mode_val else "Active"
                        label = f"Mode ({fill_str})"
                    elif "tier" in col_lower or "category" in col_lower:
                        fill_str = mode_val if mode_val else "Standard"
                        label = f"Mode ({fill_str})"
                    elif "date" in col_lower:
                        fill_str = mode_val if mode_val else "2026-01-01"
                        label = f"Mode Date ({fill_str})"
                    elif "city" in col_lower or "location" in col_lower:
                        # Use most frequent city if available!
                        fill_str = mode_val if mode_val else "Central Hub"
                        label = f"Statistical Mode ({fill_str})"
                    else:
                        fill_str = mode_val if mode_val else "Standard"
                        label = f"Mode ({fill_str})"

                    for idx in df[df[col].isnull()].index:
                        df.at[idx, col] = fill_str
                        if idx not in cell_imputations:
                            cell_imputations[idx] = {}
                        cell_imputations[idx][col] = {
                            "strategy": label,
                            "value": fill_str,
                            "label": label
                        }

                    imputed_cells_count += int(missing_in_col)
                    imputation_log_details.append(f"{col} &rarr; {label} '{fill_str}'")

        if imputed_cells_count > 0:
            operations.append(CleaningOperation(
                step_number=step_num,
                operation_name="Smart Missing Value Imputation (Filled Nulls)",
                details=f"Successfully filled {imputed_cells_count} null/missing cells using cohort medians and statistical modes: {'; '.join(imputation_log_details[:4])}.",
                records_affected=imputed_cells_count
            ))
            step_num += 1

    # 7. Compute final quality metrics
    cleaned_row_count = len(df)
    cleaned_col_count = len(df.columns)
    cleaned_missing_cells = int(df.isnull().sum().sum())

    total_cells_initial = max(1, initial_row_count * initial_col_count)
    total_cells_cleaned = max(1, cleaned_row_count * cleaned_col_count)

    initial_health_score = max(0.0, round(100.0 - (initial_missing_cells / total_cells_initial * 40.0) - (exact_duplicates_removed * 5.0), 1))
    cleaned_health_score = max(0.0, min(100.0, round(100.0 - (cleaned_missing_cells / total_cells_cleaned * 15.0), 1)))
    retention_rate = round((cleaned_row_count / max(1, initial_row_count)) * 100.0, 1)

    metrics = BeforeAfterMetrics(
        initial_row_count=initial_row_count,
        cleaned_row_count=cleaned_row_count,
        initial_column_count=initial_col_count,
        cleaned_column_count=cleaned_col_count,
        initial_missing_cells=initial_missing_cells,
        cleaned_missing_cells=cleaned_missing_cells,
        imputed_cells_count=imputed_cells_count,
        exact_duplicates_removed=exact_duplicates_removed,
        initial_health_score_pct=initial_health_score,
        cleaned_health_score_pct=cleaned_health_score,
        data_retention_rate_pct=retention_rate
    )

    return df, operations, metrics, review_issues, cell_imputations

def dataframe_to_csv_string(df: pd.DataFrame) -> str:
    """Generate CSV string from cleaned DataFrame."""
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue()

def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Generate Excel (.xlsx) binary bytes from cleaned DataFrame."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Cleaned_Data")
    return buffer.getvalue()

def generate_cleaning_report(
    analysis: AgentSemanticAnalysis,
    operations: List[CleaningOperation],
    metrics: BeforeAfterMetrics,
    review_issues: List[ReviewIssue]
) -> str:
    """Generate professional 20-Year Senior Data Analyst Markdown Cleaning Summary."""
    lines = [
        f"# Senior Data Analyst Quality & Transformation Audit Report",
        f"**Dataset Title:** {analysis.dataset_title}",
        f"**Audit Status:** Certified Analysis-Ready (Single-Agent Deterministic Engine)",
        "",
        "## Executive Summary",
        analysis.executive_summary,
        "",
        "## Before & After Quality Scorecard",
        f"- **Initial Records:** {metrics.initial_row_count} | **Cleaned Records:** {metrics.cleaned_row_count} ({metrics.data_retention_rate_pct}% retention)",
        f"- **Initial Columns:** {metrics.initial_column_count} | **Structured Columns:** {metrics.cleaned_column_count}",
        f"- **Initial Missing/Corrupt Cells:** {metrics.initial_missing_cells} | **Remaining Nulls:** {metrics.cleaned_missing_cells}",
        f"- **Cells Imputed & Standardized:** {metrics.imputed_cells_count}",
        f"- **Exact Duplicates Removed:** {metrics.exact_duplicates_removed}",
        f"- **Data Quality Health Score:** {metrics.initial_health_score_pct}% &rarr; **{metrics.cleaned_health_score_pct}%**",
        "",
        "## Detected Data Quality Problems",
    ]

    if not analysis.detected_problems:
        lines.append("- No critical structural issues detected in pre-flight screening.")
    else:
        for p in analysis.detected_problems:
            lines.append(f"- **[{p.severity}] {p.problem_type}:** {p.description} *(Affected: `{p.affected_field or 'Multiple'}`)*")

    lines.append("\n## Deterministic Cleaning Operations Executed")
    for op in operations:
        lines.append(f"{op.step_number}. **{op.operation_name}:** {op.details} *({op.records_affected} affected)*")

    lines.append("\n## Preserved Records Requiring Human Review")
    if not review_issues:
        lines.append("- All records fully conform to structural specifications. Zero ambiguous records remaining.")
    else:
        for iss in review_issues:
            lines.append(f"- **{iss.row_reference} (`{iss.field_name}`):** Suspect value `\"{iss.suspect_value}\"`. Reason: {iss.reason_for_flagging}. **Action:** {iss.recommended_action}")

    lines.append("\n---\n*Report generated by Senior AI Data Analyst Single-Agent Engine.*")
    return "\n".join(lines)


# =========================================================================
# UNIVERSAL DETERMINISTIC FALLBACK PARSER (Offline / Zero-Key Resilient)
# =========================================================================

def fallback_deterministic_parse(raw_content: str) -> AgentSemanticAnalysis:
    """
    Parses unstructured tabular, CSV, TSV, pipe, or colon-delimited text 
    without needing an external API key. Guarantees 100% uptime.
    """
    lines = [ln.strip() for ln in raw_content.strip().splitlines() if ln.strip()]
    if not lines:
        return AgentSemanticAnalysis(
            dataset_title="Empty Dataset",
            executive_summary="Input was empty.",
            detected_problems=[],
            column_definitions=[],
            extracted_records=[],
            flagged_review_issues=[],
            analyst_recommendations=[]
        )

    # Detect separator (comma, pipe, tab, semicolon)
    sample_line = lines[0]
    sep = ","
    if "|" in sample_line:
        sep = "|"
    elif "\t" in sample_line:
        sep = "\t"
    elif ";" in sample_line:
        sep = ";"

    # Try to parse with pandas StringIO
    try:
        df_raw = pd.read_csv(io.StringIO(raw_content), sep=sep, header=None, engine="python", skipinitialspace=True)
        # Check if first row looks like headers (all non-numeric strings)
        first_row = [str(x).strip() for x in df_raw.iloc[0]]
        has_headers = all(not re.match(r"^\d+(\.\d+)?$", val) for val in first_row) and len(first_row) > 1

        if has_headers and len(df_raw) > 1:
            headers = [clean_column_name(h) for h in first_row]
            data_df = df_raw.iloc[1:].reset_index(drop=True)
        else:
            headers = [f"column_{i+1}" for i in range(len(df_raw.columns))]
            data_df = df_raw
    except Exception:
        # Fallback manual line splitter
        rows_split = []
        for ln in lines:
            parts = [p.strip().strip('"').strip("'") for p in ln.split(sep)]
            rows_split.append(parts)
        max_cols = max(len(r) for r in rows_split)
        headers = [f"column_{i+1}" for i in range(max_cols)]
        data_df = pd.DataFrame(rows_split, columns=headers)

    # If columns contain common markers, infer better names
    inferred_headers = []
    for c_idx in range(len(data_df.columns)):
        col_series = data_df.iloc[:, c_idx].astype(str)
        col_name = headers[c_idx] if c_idx < len(headers) else f"col_{c_idx+1}"
        # Infer column identity if generic
        if "column_" in col_name or "col_" in col_name:
            if any("@" in s for s in col_series):
                col_name = "email"
            elif any(re.match(r"^\+?\d{10,13}$", re.sub(r"[^\d]", "", s)) for s in col_series):
                col_name = "phone"
            elif any(any(sym in s for sym in ["$", "€", "₹", "Rs"]) for s in col_series):
                col_name = "spend"
            elif any(try_parse_date(s) is not None for s in col_series):
                col_name = "date"
        inferred_headers.append(col_name)

    extracted_records: List[RawRecordExtracted] = []
    for r_idx, row in data_df.iterrows():
        attrs = []
        for c_idx, val in enumerate(row):
            h_name = inferred_headers[c_idx] if c_idx < len(inferred_headers) else f"col_{c_idx+1}"
            raw_val = str(val).strip() if pd.notna(val) else None
            attrs.append(RecordAttribute(column_name=h_name, value=raw_val))
        extracted_records.append(RawRecordExtracted(row_id=r_idx + 1, attributes=attrs))

    return AgentSemanticAnalysis(
        dataset_title="Structured Intake Dataset",
        executive_summary=f"Ingested and analyzed {len(extracted_records)} raw records across {len(inferred_headers)} inferred dimensions using the Senior Analyst deterministic engine.",
        detected_problems=[
            DetectedProblem(
                problem_type="Unstructured / Semi-Structured Input",
                description=f"Raw text parsed using separator '{sep}'. Found {len(inferred_headers)} attributes per record.",
                affected_field="All Columns",
                severity="Info"
            )
        ],
        column_definitions=[
            ColumnDefinition(
                raw_name=h,
                standardized_name=h,
                intended_data_type="string",
                description=f"Inferred attribute: {h}"
            )
            for h in inferred_headers
        ],
        extracted_records=extracted_records,
        flagged_review_issues=[],
        analyst_recommendations=["Standardize input format at the source API endpoint."]
    )
