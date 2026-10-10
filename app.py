"""Flask Web Application for Senior AI Data Analyst Single-Agent Studio."""
import os
import uuid
import logging
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, Response
import io
import pandas as pd

from config import get_api_key, DEFAULT_MODEL, PROJECT_ROOT, MAX_FILE_SIZE_BYTES
from agent import SingleAgentDataAnalyst
from pipeline import (
    build_cleaned_dataframe,
    dataframe_to_csv_string,
    dataframe_to_excel_bytes,
    generate_cleaning_report,
    fallback_deterministic_parse
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_BYTES

# In-memory storage for export downloads (keyed by session_id)
EXPORT_CACHE = {}

# Pre-seed demo sample with zero nulls (Alice's email cleanly imputed) so download buttons and scorecard are instantly active
demo_df = pd.DataFrame([
    {"customer_name": "Johnathan Doe", "email": "jdoe@enterprise.org", "phone": "555-019-2834", "join_date": "2023-01-12", "account_tier": "Platinum", "total_spend": "1250.00", "status": "Active"},
    {"customer_name": "Alice Walker", "email": "alice.w@standard-enterprise.org", "phone": "555-981-4422", "join_date": "2024-03-15", "account_tier": "Standard", "total_spend": "340.50", "status": "Pending"},
    {"customer_name": "Robert Smith", "email": "bob.smith@techcorp.io", "phone": "555-443-9911", "join_date": "2023-08-15", "account_tier": "Gold", "total_spend": "4500.00", "status": "Active"},
    {"customer_name": "Claire Redfield", "email": "claire.r@umbrella-labs.com", "phone": "555-776-2319", "join_date": "2024-05-20", "account_tier": "Gold", "total_spend": "2100.75", "status": "Active"}
])
EXPORT_CACHE["demo_sample"] = {
    "df": demo_df,
    "csv": dataframe_to_csv_string(demo_df),
    "excel": dataframe_to_excel_bytes(demo_df),
    "report": "# Sample Cleaning Audit Report\n\nAll quality checks, currency standardizations, and null imputations completed successfully.",
    "title": "customer_intake"
}

INDIAN_CUSTOMERS_SAMPLE = """Lakshmi V, 31, Coimbatore, lakshmi.v@example.com, 18/05/26, "1,100", 9876543217
Mohammed A, -5, Trichy, mohammed.a@example.com, 2026-06-01, "500", 9876543218
Nila P, 24, Coimbatore, nila.p@example.com, 2026-06-12, "₹1,999", 9876543219
Vijay R, 29, Chennai, vijay.r@example.com, 2026-07-03, "3,000", 9876543220
Anu S, 26, madurai, anu.s@example.com, 07/14/2026, "1,250", 9876543221
Bala N, , Unknown, bala.n@example.com, 2026-08-02, invalid, 9876543222
Sara J, 33, Coimbatore, sara.j@example.com, 2026-08-10, 950, 9876543223"""

@app.route("/")
def index():
    """Render main web dashboard."""
    has_env_key = bool(
        os.getenv("GEMINI_API_KEY", "").strip() 
        and os.getenv("GEMINI_API_KEY") != "your_gemini_api_key_here"
    )
    return render_template("index.html", has_env_key=has_env_key, default_model=DEFAULT_MODEL)

@app.route("/api/sample/<name>", methods=["GET"])
def get_sample(name):
    """Retrieve sample dataset text."""
    if name == "indian_customers":
        return jsonify({"success": True, "content": INDIAN_CUSTOMERS_SAMPLE})

    samples = {
        "customers": PROJECT_ROOT / "sample_data" / "messy_customers.txt",
        "transactions": PROJECT_ROOT / "sample_data" / "messy_transactions.log",
    }
    sample_path = samples.get(name)
    if sample_path and sample_path.exists():
        content = sample_path.read_text(encoding="utf-8")
        return jsonify({"success": True, "content": content})
    return jsonify({"success": False, "error": f"Sample '{name}' not found."}), 404

@app.route("/api/clean", methods=["POST"])
def clean_data():
    """Process unstructured data through the Senior Data Analyst Single-Agent System."""
    try:
        data = request.get_json(force=True)
        raw_text = data.get("raw_text", "").strip()
        custom_key = data.get("api_key", "").strip()
        model_name = data.get("model", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        target_schema = data.get("target_schema", [])
        custom_rules = data.get("custom_rules", "").strip() or None
        fill_missing = bool(data.get("fill_missing", True))

        if not raw_text:
            return jsonify({"success": False, "error": "No input data provided."}), 400

        # Enforce untrusted data limits if too large
        if len(raw_text) > 500000:
            return jsonify({
                "success": False,
                "error": "The input dataset is too large (exceeds 500KB limit for web processing). Please submit in smaller batches."
            }), 400

        # Resolve API Key
        api_key = custom_key
        if not api_key:
            try:
                api_key = get_api_key()
            except ValueError:
                api_key = None

        analysis = None
        # 1. AI Agent: Ingest, infer structure, detect semantic problems, extract records
        if api_key:
            try:
                agent = SingleAgentDataAnalyst(api_key=api_key, model_name=model_name)
                analysis = agent.analyze_and_extract(
                    raw_content=raw_text,
                    target_schema_hint=target_schema if target_schema else None,
                    custom_instructions=custom_rules
                )
            except Exception as api_err:
                logging.warning(f"AI Agent call failed, using deterministic fallback: {api_err}")
                analysis = None

        # Resilient fallback: If no API key or if API failed, use deterministic parser
        if analysis is None:
            analysis = fallback_deterministic_parse(raw_text)
            if target_schema:
                analysis.executive_summary += f" Target schema aligned with: {', '.join(target_schema)}."

        # 2. Python & Pandas: Deterministic data transformations & metrics computation
        df, operations, metrics, review_issues, cell_imputations = build_cleaned_dataframe(
            analysis, 
            raw_text, 
            fill_missing=fill_missing
        )

        # 3. Generate report and exports
        report_text = generate_cleaning_report(analysis, operations, metrics, review_issues)
        csv_str = dataframe_to_csv_string(df)
        excel_bytes = dataframe_to_excel_bytes(df)

        # Cache exports for direct browser download
        cache_id = str(uuid.uuid4())
        EXPORT_CACHE[cache_id] = {
            "df": df,
            "csv": csv_str,
            "excel": excel_bytes,
            "report": report_text,
            "title": analysis.dataset_title
        }

        # Keep cache trimmed to last 25 sessions
        if len(EXPORT_CACHE) > 25:
            oldest_key = next(iter(EXPORT_CACHE))
            del EXPORT_CACHE[oldest_key]

        # Convert records for JSON response and attach imputation tags
        records = []
        for idx, row in df.iterrows():
            row_dict = {}
            for col in df.columns:
                val = row[col]
                row_dict[col] = None if (val is None or pd.isna(val)) else str(val)
            # Imputation metadata for this row
            row_imp = cell_imputations.get(idx, {})
            row_dict["_imputations"] = row_imp
            row_dict["_imputed_fields"] = list(row_imp.keys())
            records.append(row_dict)

        return jsonify({
            "success": True,
            "cache_id": cache_id,
            "dataset_title": analysis.dataset_title,
            "executive_summary": analysis.executive_summary,
            "original_preview": raw_text[:2000] + ("..." if len(raw_text) > 2000 else ""),
            "detected_problems": [p.model_dump() for p in analysis.detected_problems],
            "headers": list(df.columns),
            "column_definitions": [c.model_dump() for c in analysis.column_definitions],
            "records": records,
            "cleaning_operations": [op.model_dump() for op in operations],
            "before_after_metrics": metrics.model_dump(),
            "review_issues": [iss.model_dump() for iss in review_issues],
            "cell_imputations": cell_imputations,
            "csv_content": csv_str,
            "cleaning_report": report_text
        })

    except Exception as e:
        logging.error(f"Error in clean_data: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

def get_export_item(cache_id):
    """Retrieve cached export data with dynamic demo_sample fallback."""
    if cache_id in EXPORT_CACHE:
        return EXPORT_CACHE[cache_id]
    if cache_id == "demo_sample":
        return {
            "df": demo_df,
            "csv": dataframe_to_csv_string(demo_df),
            "excel": dataframe_to_excel_bytes(demo_df),
            "report": "# Sample Cleaning Audit Report\n\nAll quality checks, currency standardizations, and null imputations completed successfully.",
            "title": "customer_intake"
        }
    return None

@app.route("/api/download/<cache_id>/csv", methods=["GET"])
def download_csv(cache_id):
    """Download cleaned dataset as CSV."""
    item = get_export_item(cache_id)
    if not item:
        return jsonify({"success": False, "error": "Export session expired or not found."}), 404

    csv_data = item["csv"]
    title = item.get("title", "cleaned_dataset").lower().replace(" ", "_")
    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={title}_cleaned.csv"}
    )

@app.route("/api/download/<cache_id>/excel", methods=["GET"])
def download_excel(cache_id):
    """Download cleaned dataset as Microsoft Excel (.xlsx)."""
    item = get_export_item(cache_id)
    if not item:
        return jsonify({"success": False, "error": "Export session expired or not found."}), 404

    excel_bytes = item["excel"]
    title = item.get("title", "cleaned_dataset").lower().replace(" ", "_")
    return send_file(
        io.BytesIO(excel_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"{title}_cleaned.xlsx"
    )

@app.route("/api/download/<cache_id>/report", methods=["GET"])
def download_report(cache_id):
    """Download Markdown Cleaning Audit Report."""
    item = get_export_item(cache_id)
    if not item:
        return jsonify({"success": False, "error": "Export session expired or not found."}), 404

    report_text = item["report"]
    title = item.get("title", "cleaning_audit").lower().replace(" ", "_")
    return Response(
        report_text,
        mimetype="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={title}_report.md"}
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("\n" + "=" * 57)
    print("[RUNNING] Senior AI Data Analyst Single-Agent Studio")
    print(f"[URL] Open in your browser: http://127.0.0.1:{port}")
    print("=" * 57 + "\n")
    app.run(host="127.0.0.1", port=port, debug=False)
