"""LangGraph state definitions for the agent workflow."""

from typing import Any, Dict, List, Literal, Optional, TypedDict
from enum import Enum


class WorkflowStatus(str, Enum):
    """Status states for the workflow."""
    IDLE = "idle"
    PROCESSING = "processing"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    DENIED = "denied"
    ERROR = "error"


class AgentState(TypedDict, total=False):
    """
    State definition for the LangGraph agent workflow.
    
    This state is passed through all nodes in the workflow and
    accumulates information as the agent processes the user's request.
    """
    # Conversation context
    conversation_id: str
    messages: List[Dict[str, Any]]
    
    # Intent extraction results
    current_intent: Optional[Dict[str, Any]]
    intent_confidence: float
    
    # Query execution
    sql_query: Optional[str]
    query_params: Optional[Dict[str, Any]]
    query_result: Optional[Any]
    
    # Action payload for mutations
    action_payload: Optional[Dict[str, Any]]
    
    # Workflow status
    status: WorkflowStatus
    
    # Approval tracking
    pending_approval_id: Optional[int]
    approved_by: Optional[str]
    
    # Email draft (for DRAFT_EMAIL action)
    email_draft: Optional[Dict[str, Any]]
    
    # Error handling
    error: Optional[str]
    
    # Safety validation
    is_safe: bool
    safety_notes: Optional[str]
