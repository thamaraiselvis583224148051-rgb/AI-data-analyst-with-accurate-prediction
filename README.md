# 🧹 Enterprise Data Cleaning & Structuring Agent (CLI)

An autonomous single-agent CLI tool powered by the **Google Gemini API** (`gemini-2.5-flash`), built with the rigor of a **Senior Principal Data Analyst with 20 years of enterprise data quality experience**.

It takes messy, unstructured, inconsistent, or corrupted text, logs, and tables, and converts them into **clean, deduplicated, standardized relational datasets** (CSV, JSON, TSV) alongside a comprehensive **Data Governance Audit Report**.

---

## 🏛️ The 20-Year Data Quality Protocol

This agent enforces the **6 Core Dimensions of Enterprise Data Quality**:

1. **Completeness**: Drops corrupted records lacking primary identifiers; properly tags missing fields.
2. **Uniqueness**: Prunes both **exact duplicates** and **fuzzy/semantic duplicates** (different date formats or spellings for the same entity) to preserve a single golden record.
3. **Consistency**: Enforces uniform schemas across disparate input fragments.
4. **Validity & Normalization**:
   - **Dates**: Strict ISO 8601 (`YYYY-MM-DD`).
   - **Monetary/Numeric**: Strips currency symbols (`$`, `€`, `£`, commas) and normalizes to clean floats.
   - **Emails**: Normalized to lowercase, stripped of whitespace.
   - **Missing Values**: Converts strings like `"N/A"`, `"none"`, `"-"`, `"null"`, `"unknown"` to true nulls (`None`).
5. **Integrity**: Aligns all entities into uniform tabular structures.
6. **Auditability**: Produces a full audit trail detailing every merged duplicate, remediated null, and calculated health score.

---

## 📁 Project Architecture

```
data-cleaning-agent/
├── .env.example              # Environment template for Gemini API key
├── requirements.txt          # Python dependencies (google-genai, pandas, pydantic, rich)
├── config.py                 # Configuration loader and key validation
├── models.py                 # Pydantic models for structured output & audit metrics
├── agent.py                  # Core DataQualityAgent with Gemini API integration
├── pipeline.py               # DataFrame conversion, hygiene metrics, and exporters
├── main.py                   # Terminal CLI with rich tables, spinners, and audit panels
├── sample_data/
│   ├── messy_customers.txt   # Test dataset with duplicate customers, bad dates, nulls
│   └── messy_transactions.log# Test log with duplicate transaction IDs & failed rows
└── README.md                 # Full documentation
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.10+
- A Google Gemini API Key ([Get one from Google AI Studio](https://aistudio.google.com/))

### 2. Setup Virtual Environment & Dependencies
```powershell
# Navigate into the project folder
cd C:\Users\Admin\.gemini\antigravity\scratch\data-cleaning-agent

# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

### 3. Configure Your API Key
Copy `.env.example` to `.env`:
```powershell
copy .env.example .env
```
Open `.env` and set your key:
```env
GEMINI_API_KEY=AIzaSyYourActualGeminiApiKeyHere
```
*(Alternatively, you can pass `--api-key YOUR_KEY` directly to the CLI command).*

## 🌐 Running the Web Application (Studio Dashboard)

You can run the interactive web interface in your browser:

```powershell
# In the project directory with .venv active:
.\.venv\Scripts\python.exe app.py
```
Open **[http://localhost:5000](http://localhost:5000)** in your browser!

### ✨ Web Studio Features:
- **Instant Sample Testing**: Click **"Sample Customers"** or **"Transactions"** to test immediately.
- **Drag & Drop**: Upload raw `.txt`, `.csv`, `.log` files directly.
- **Interactive Data Table**: Inspect cleaned rows, missing values (`<null>` badges), and normalized columns.
- **Data Quality Scorecard**: Live KPI cards for Duplicates Pruned, Records Retained, and Health Score.
- **Lead Analyst Audit Trail**: Detailed narrative and transformation logs.
- **1-Click Export**: Download cleaned dataset as `.csv` or `.json`, or copy to clipboard.

---

## 💻 CLI Usage (Terminal Utility)

### A. Process a Messy Input File (Recommended)
Clean the bundled sample customer file and save to CSV:
```powershell
python main.py --input sample_data/messy_customers.txt --output cleaned_customers.csv --format csv
```

### B. Clean Direct Text from the Terminal
```powershell
python main.py --text "John Doe, jdoe@test.com, 01/12/2023, $150 | John Doe, jdoe@test.com, Jan 12 2023, 150.00" --output test.csv
```

### C. Export to JSON with Target Schema Guidance
```powershell
python main.py --input sample_data/messy_customers.txt --output output.json --format json --schema "customer_name,email,phone_number,join_date,tier,spend_usd"
```

### D. Enforce Custom Business Rules
```powershell
python main.py -i sample_data/messy_customers.txt -o out.csv --rules "Only retain customers with spend greater than 500. Drop records with missing emails."
```

---

## 📊 Sample Output & Audit Report

When you run the tool, you get a clean terminal preview and scorecard:

```
┌───────────────────────────────────────┐
│ ENTERPRISE DATA CLEANING AGENT (CLI)  │
└───────────────────────────────────────┘

✓ Loaded raw input from sample_data/messy_customers.txt (1,048 characters)

                        Cleaned Structured Data (Preview)                         
┏━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┓
┃ # ┃ name             ┃ email                  ┃ phone          ┃ join_date  ┃ tier     ┃ spend    ┃ status ┃
┡━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━┩
│ 1 │ John Doe         │ jdoe@enterprise.org    │ +1-555-019-2834│ 2023-01-12 │ Platinum │ 1250.00  │ Active │
│ 2 │ Bob Smith        │ bob.smith@techcorp.io  │ +1-555-443-9911│ 2023-08-15 │ Gold     │ 4500.00  │ Active │
│ 3 │ Claire Redfield  │ claire.r@umbrella.com  │ +1-555-776-2319│ 2024-05-20 │ Gold     │ 2100.75  │ Active │
└───┴──────────────────┴────────────────────────┴────────────────┴────────────┴──────────┴──────────┴────────┘

                         Data Quality Scorecard                         
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Metric                       ┃ Value                                 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Raw Records Identified       │ 7                                     │
│ Clean Records Retained       │ 3                                     │
│ Duplicates Pruned            │ 2                                     │
│ Null/Missing Fields Handled  │ 4                                     │
│ Dataset Completeness         │ 100.0%                                │
│ Overall Data Health Score    │ 95.0%                                 │
└──────────────────────────────┴───────────────────────────────────────┘

╭───────────────────── Data Governance Audit Log ──────────────────────╮
│ Lead Analyst Assessment:                                              │
│ Successfully identified 7 raw inputs. Pruned 2 redundant records      │
│ (John Doe sync duplicate and Claire Redfield duplicate). Dropped 2   │
│ corrupt records missing primary keys (Alice Walker missing email,     │
│ Record 5 completely empty). Standardized all dates to ISO 8601.      │
╰──────────────────────────────────────────────────────────────────────╯
✓ Cleaned structured dataset successfully exported to: cleaned_customers.csv
```

---

## 🛠️ CLI Options Reference

| Flag | Short | Default | Description |
|---|---|---|---|
| `--input` | `-i` | `None` | Path to raw text, log, or CSV file |
| `--text` | `-t` | `None` | Raw text string provided directly in command |
| `--output` | `-o` | `cleaned_output.csv` | Output file path |
| `--format` | `-f` | `csv` | Export format: `csv`, `json`, `tsv` |
| `--schema` | `-s` | `None` | Optional comma-separated target columns |
| `--rules` | `-r` | `None` | Custom data quality or filtering rules |
| `--api-key` | | `None` | Gemini API key override (otherwise uses `.env`) |
| `--model` | | `gemini-2.5-flash` | Gemini model name |
