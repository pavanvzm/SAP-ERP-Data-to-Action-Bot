"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IntentAction(str, Enum):
    """Supported intent actions."""
    QUERY_CUSTOMERS = "QUERY_CUSTOMERS"
    QUERY_INVOICES = "QUERY_INVOICES"
    QUERY_SUMMARY = "QUERY_SUMMARY"
    UPDATE_INVOICE_STATUS = "UPDATE_INVOICE_STATUS"
    UPDATE_CUSTOMER_CREDIT = "UPDATE_CUSTOMER_CREDIT"
    DELETE_INVOICE = "DELETE_INVOICE"
    DRAFT_EMAIL = "DRAFT_EMAIL"
    UNKNOWN = "UNKNOWN"


class OperationStatus(str, Enum):
    """Status of an operation in the workflow."""
    PROCESSING = "processing"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTED = "executed"
    COMPLETED = "completed"
    DENIED = "denied"
    ERROR = "error"


class InvoiceStatus(str, Enum):
    """Valid invoice statuses."""
    PAID = "PAID"
    PENDING = "PENDING"
    OVERDUE = "OVERDUE"


class CustomerTier(str, Enum):
    """Valid customer tiers."""
    STANDARD = "STANDARD"
    PREMIUM = "PREMIUM"
    ENTERPRISE = "ENTERPRISE"


class ApprovalDecision(str, Enum):
    """Approval decision types."""
    APPROVE = "approve"
    DENY = "deny"


# =============================================================================
# Request Schemas
# =============================================================================

class ChatRequest(BaseModel):
    """Request schema for chat endpoint."""
    message: str = Field(..., min_length=1, max_length=1000, description="User message")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for continuity")


class ApprovalRequest(BaseModel):
    """Request schema for approval endpoint."""
    approval_id: int = Field(..., gt=0, description="ID of the approval to process")
    decision: ApprovalDecision = Field(..., description="Decision: approve or deny")
    authorized_by: str = Field(..., min_length=1, max_length=100, description="Approver identifier")


# =============================================================================
# Response Schemas
# =============================================================================

class ExtractedIntent(BaseModel):
    """Extracted intent from user message."""
    action: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    parameters: List[Dict[str, Any]] = Field(default_factory=list)
    reasoning: str = ""
    requires_approval: bool = False
    is_safe: bool = True
    safety_notes: Optional[str] = None


class ApprovalDetails(BaseModel):
    """Details for pending approval."""
    action_type: str
    target_table: str
    operation: str
    changes: Dict[str, Any]
    estimated_impact: str


class ChatResponse(BaseModel):
    """Response schema for chat endpoint."""
    conversation_id: str
    message: str
    intent: Optional[ExtractedIntent] = None
    status: OperationStatus
    data: Optional[Dict[str, Any]] = None
    pending_approval_id: Optional[int] = None
    requires_approval: bool = False
    approval_details: Optional[ApprovalDetails] = None
    error: Optional[str] = None


class ApprovalResponse(BaseModel):
    """Response schema for approval endpoint."""
    success: bool
    approval_id: int
    decision: str
    message: str
    executed_result: Optional[Dict[str, Any]] = None


class PendingApproval(BaseModel):
    """Details of a pending approval."""
    id: int
    action: str
    details: str
    requested_by: str
    timestamp: str
    payload: Optional[Dict[str, Any]] = None


class PendingApprovalsResponse(BaseModel):
    """Response listing all pending approvals."""
    approvals: List[PendingApproval]
    count: int


class CustomerResponse(BaseModel):
    """Response schema for customer data."""
    customers: List[Dict[str, Any]]
    count: int


class InvoiceResponse(BaseModel):
    """Response schema for invoice data."""
    invoices: List[Dict[str, Any]]
    count: int


class DashboardSummary(BaseModel):
    """Dashboard summary statistics."""
    customers: Dict[str, Any]
    invoices: Dict[str, Any]


class HealthCheckResponse(BaseModel):
    """Response schema for health check."""
    status: str
    version: str
    timestamp: str
    database_connected: bool
    llm_configured: bool


class EmailDraftResponse(BaseModel):
    """Response schema for email draft."""
    subject: str
    body: str
    recipients: List[str]
    cc: Optional[List[str]] = None


class ChatStreamEvent(BaseModel):
    """Event for streaming chat responses."""
    event: str
    data: Any
