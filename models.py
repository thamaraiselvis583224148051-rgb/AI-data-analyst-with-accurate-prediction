"""Data models and schemas for Senior AI Data Analyst Single-Agent System."""
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

class DetectedProblem(BaseModel):
    """Specific data quality problem detected in the input data."""
    problem_type: str = Field(description="Category: e.g., 'Inconsistent Format', 'Missing Values', 'Exact Duplicate', 'Invalid Value', 'Structural Drift'")
    description: str = Field(description="Clear explanation of the problem found")
    affected_field: Optional[str] = Field(default=None, description="Column or attribute affected, if applicable")
    severity: str = Field(default="Warning", description="'Critical', 'Warning', or 'Info'")

class CleaningOperation(BaseModel):
    """Specific deterministic cleaning operation executed."""
    step_number: int = Field(description="Order of execution")
    operation_name: str = Field(description="e.g. 'Column Name Standardization', 'Null Remediation', 'Exact Deduplication', 'ISO-8601 Date Formatting'")
    details: str = Field(description="Specific transformations performed")
    records_affected: int = Field(default=0, description="Count of rows or fields impacted")

class ReviewIssue(BaseModel):
    """Ambiguous or suspicious record preserved for human review rather than silently modified/dropped."""
    row_reference: str = Field(description="Row identifier or reference")
    field_name: str = Field(description="Column name")
    suspect_value: str = Field(description="The questionable or suspicious raw value")
    reason_for_flagging: str = Field(description="Why this cannot be automatically corrected safely without user confirmation")
    recommended_action: str = Field(description="Recommended analyst action or decision needed from the user")

class ColumnDefinition(BaseModel):
    """Standardized column definition inferred by the agent."""
    raw_name: str = Field(description="Original column or attribute name")
    standardized_name: str = Field(description="Standardized lowercase snake_case column name")
    intended_data_type: str = Field(description="e.g. 'string', 'integer', 'float', 'datetime (ISO-8601)', 'boolean', 'category'")
    description: str = Field(description="Semantic meaning of this column")
    allows_null: bool = Field(default=True, description="Whether this field can be null")

class RecordAttribute(BaseModel):
    """Single column-value attribute for an extracted record."""
    column_name: str = Field(description="Standardized lowercase snake_case column name")
    value: Optional[str] = Field(default=None, description="Cleaned value, or None if missing or null")

class RawRecordExtracted(BaseModel):
    """Single record extracted from unstructured input with standardized column keys."""
    row_id: int = Field(description="1-based identifier")
    attributes: List[RecordAttribute] = Field(description="List of column-value attributes for this record")

class AgentSemanticAnalysis(BaseModel):
    """Semantic analysis produced by the Gemini AI agent."""
    dataset_title: str = Field(description="Descriptive title for the dataset")
    executive_summary: str = Field(description="20-year Senior Data Analyst assessment of the dataset")
    detected_problems: List[DetectedProblem] = Field(description="List of detected data-quality problems")
    column_definitions: List[ColumnDefinition] = Field(description="Inferred schema and standardized column names")
    extracted_records: List[RawRecordExtracted] = Field(description="List of extracted records mapped to standardized columns")
    flagged_review_issues: List[ReviewIssue] = Field(default_factory=list, description="Preserved questionable records requiring human review")
    analyst_recommendations: List[str] = Field(default_factory=list, description="Recommendations for future data collection hygiene")

class BeforeAfterMetrics(BaseModel):
    """Before-and-after quality metrics comparing raw input with cleaned output."""
    initial_row_count: int
    cleaned_row_count: int
    initial_column_count: int
    cleaned_column_count: int
    initial_missing_cells: int
    cleaned_missing_cells: int
    imputed_cells_count: int = 0
    exact_duplicates_removed: int
    initial_health_score_pct: float
    cleaned_health_score_pct: float
    data_retention_rate_pct: float

class FullCleaningResult(BaseModel):
    """Consolidated result passed to frontend and exporters."""
    dataset_title: str
    executive_summary: str
    original_preview: str
    detected_problems: List[DetectedProblem]
    cleaning_operations: List[CleaningOperation]
    before_after_metrics: BeforeAfterMetrics
    review_issues: List[ReviewIssue]
    headers: List[str]
    column_definitions: List[ColumnDefinition]
    records: List[Dict[str, Any]]
    csv_content: str
    cleaning_report_markdown: str
