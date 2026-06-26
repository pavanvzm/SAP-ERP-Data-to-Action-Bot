"""
FastAPI entry point and HITL endpoints for the ERP Data-to-Action Bot.
"""

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.database import ERPDatabase, get_database
from app.schemas import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResponse,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatStreamEvent,
    DashboardSummary,
    EmailDraftResponse,
    ExtractedIntent,
    HealthCheckResponse,
    PendingApproval,
    PendingApprovalsResponse,
    WorkflowStateResponse,
)
from app.agent.graph import WorkflowGraph, get_workflow
from app.agent.state import AgentState, WorkflowStatus


# =============================================================================
# Logging Configuration
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# Lifespan Management
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown."""
    # Startup
    logger.info("Starting ERP Data-to-Action Bot...")
    db = await get_database()
    logger.info("Database initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    await db.close()


# =============================================================================
# FastAPI Application
# =============================================================================

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Enterprise ERP Data-to-Action Bot with Human-in-the-Loop Approval",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# WebSocket Connection Manager
# =============================================================================

class ConnectionManager:
    """Manages active WebSocket connections."""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, conversation_id: str):
        await websocket.accept()
        self.active_connections[conversation_id] = websocket
    
    def disconnect(self, conversation_id: str):
        if conversation_id in self.active_connections:
            del self.active_connections[conversation_id]
    
    async def send_json(self, conversation_id: str, data: Any):
        if conversation_id in self.active_connections:
            await self.active_connections[conversation_id].send_json(data)


manager = ConnectionManager()


# =============================================================================
# Helper Functions
# =============================================================================

def state_to_response(state: AgentState) -> ChatResponse:
    """Convert workflow state to API response."""
    intent = state.get("current_intent", {})
    
    # Build message
    message = "Operation completed."
    if state.get("error"):
        message = state.get("error", "An error occurred")
    elif state.get("status") == WorkflowStatus.AWAITING_APPROVAL:
        message = "Your request requires human approval. Please wait for authorization."
    elif state.get("query_result"):
        result = state.get("query_result", {})
        if "customers" in result:
            message = f"Query executed successfully. Found {len(result['customers'])} results."
        elif "invoices" in result:
            message = f"Query executed successfully. Found {len(result['invoices'])} results."
        else:
            message = "Query executed successfully."
    
    # Build data
    data = state.get("query_result")
    
    # Build approval details
    approval_details = None
    if state.get("status") == WorkflowStatus.AWAITING_APPROVAL:
        action = intent.get("action", "UNKNOWN")
        params = intent.get("parameters", {})
        approval_details = {
            "action_type": action,
            "target_table": "invoices" if "INVOICE" in action else "customers",
            "operation": action.split("_")[0] if "_" in action else "UNKNOWN",
            "changes": params,
            "estimated_impact": f"{action} with parameters: {params}"
        }
    
    return ChatResponse(
        conversation_id=state.get("conversation_id", ""),
        message=message,
        intent=ExtractedIntent(
            action=intent.get("action", "UNKNOWN"),
            confidence=intent.get("confidence", 0.0),
            parameters=intent.get("parameters", []),
            reasoning=intent.get("reasoning", ""),
            requires_approval=intent.get("requires_approval", False),
            is_safe=intent.get("is_safe", True),
            safety_notes=intent.get("safety_notes")
        ) if intent else None,
        status=state.get("status", WorkflowStatus.ERROR).value,
        data=data,
        pending_approval_id=state.get("pending_approval_id"),
        requires_approval=intent.get("requires_approval", False) if intent else False,
        approval_details=approval_details,
        error=state.get("error")
    )


# =============================================================================
# Chat Endpoints
# =============================================================================

@app.post("/api/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Process a chat message and return the response.
    
    This endpoint handles the main chat interaction, extracting intent,
    executing queries or creating approval requests as needed.
    """
    # Generate conversation ID if not provided
    conversation_id = request.conversation_id or str(uuid.uuid4())
    
    # Get workflow
    workflow = await get_workflow()
    db = await get_database()
    
    # Create initial state
    state: AgentState = {
        "conversation_id": conversation_id,
        "messages": [{"role": "user", "content": request.message}],
        "current_intent": None,
        "intent_confidence": 0.0,
        "sql_query": None,
        "query_params": None,
        "query_result": None,
        "action_payload": None,
        "status": WorkflowStatus.PROCESSING,
        "pending_approval_id": None,
        "approved_by": None,
        "email_draft": None,
        "error": None,
        "is_safe": True,
        "safety_notes": None
    }
    
    # Process through workflow
    state = workflow.process(request.message, conversation_id)
    
    return state_to_response(state)


@app.get("/api/health", response_model=HealthCheckResponse, tags=["Health"])
async def health_check() -> HealthCheckResponse:
    """Check the health of the API."""
    db = await get_database()
    
    return HealthCheckResponse(
        status="healthy",
        version=settings.app_version,
        timestamp=datetime.now().isoformat(),
        database_connected=True,
        llm_configured=bool(settings.openai_api_key)
    )


# =============================================================================
# Approval Endpoints
# =============================================================================

@app.post("/api/approve", response_model=ApprovalResponse, tags=["Approval"])
async def approve_action(request: ApprovalRequest) -> ApprovalResponse:
    """
    Process an approval decision for a pending action.
    
    This endpoint is the Human-in-the-Loop (HITL) mechanism that allows
    authorized users to approve or deny database mutations.
    """
    workflow = await get_workflow()
    
    if request.decision == ApprovalDecision.APPROVE:
        success, message, result = workflow.approve_action(
            approval_id=request.approval_id,
            approved_by=request.authorized_by,
            execute_mutation=True
        )
    else:
        success, message = workflow.deny_action(
            approval_id=request.approval_id,
            denied_by=request.authorized_by
        )
        result = None
    
    return ApprovalResponse(
        success=success,
        approval_id=request.approval_id,
        decision=request.decision.value,
        message=message,
        executed_result=result
    )


@app.get("/api/approvals/pending", response_model=PendingApprovalsResponse, tags=["Approval"])
async def get_pending_approvals() -> PendingApprovalsResponse:
    """Get all pending approval requests."""
    db = await get_database()
    pending = await db.get_pending_approvals()
    
    approvals = []
    for log in pending:
        approvals.append(PendingApproval(
            id=log.id,
            action=log.action,
            details=log.query,
            requested_by=log.authorized_by,
            timestamp=log.timestamp,
            payload=None
        ))
    
    return PendingApprovalsResponse(
        approvals=approvals,
        count=len(approvals)
    )


# =============================================================================
# Data Endpoints
# =============================================================================

@app.get("/api/customers", tags=["Data"])
async def get_customers(
    tier: Optional[str] = Query(None, description="Filter by customer tier"),
    min_credit: Optional[float] = Query(None, description="Minimum credit limit")
) -> Dict[str, Any]:
    """Get all customers with optional filters."""
    db = await get_database()
    customers = await db.get_customers(tier=tier, min_credit=min_credit)
    return {"customers": customers, "count": len(customers)}


@app.get("/api/invoices", tags=["Data"])
async def get_invoices(
    status: Optional[str] = Query(None, description="Filter by invoice status"),
    customer_id: Optional[int] = Query(None, description="Filter by customer ID")
) -> Dict[str, Any]:
    """Get all invoices with optional filters."""
    db = await get_database()
    invoices = await db.get_invoices(status=status, customer_id=customer_id)
    return {"invoices": invoices, "count": len(invoices)}


@app.get("/api/summary", response_model=DashboardSummary, tags=["Data"])
async def get_summary() -> DashboardSummary:
    """Get dashboard summary statistics."""
    db = await get_database()
    summary = await db.get_summary()
    return DashboardSummary(**summary)


@app.get("/api/audit-logs", tags=["Admin"])
async def get_audit_logs(
    limit: int = Query(100, ge=1, le=1000),
    action: Optional[str] = Query(None, description="Filter by action type")
) -> Dict[str, Any]:
    """Get recent audit logs."""
    db = await get_database()
    logs = await db.get_audit_logs(limit=limit, action_filter=action)
    return {"logs": logs, "count": len(logs)}


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@app.websocket("/api/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str):
    """
    WebSocket endpoint for streaming chat responses.
    """
    await manager.connect(websocket, conversation_id)
    
    try:
        # Send connection confirmation
        await websocket.send_json({
            "event": "connected",
            "conversation_id": conversation_id
        })
        
        while True:
            # Receive message
            data = await websocket.receive_json()
            message = data.get("message", "")
            
            if not message:
                continue
            
            # Process message
            workflow = await get_workflow()
            state = workflow.process(message, conversation_id)
            
            # Send intent event
            state = workflow._extract_intent(state)
            if state.get("current_intent"):
                intent = state["current_intent"]
                action_val = intent.get("action", {})
                action_str = action_val.value if hasattr(action_val, 'value') else str(action_val)
                await websocket.send_json({
                    "event": "intent",
                    "data": {
                        "action": action_str,
                        "confidence": intent.get("confidence", 0.0),
                        "requires_approval": intent.get("requires_approval", False)
                    }
                })
            
            # Process based on action
            intent = state.get("current_intent")
            if intent:
                action = intent.get("action")
                
                if action and action.value in ("QUERY_CUSTOMERS", "QUERY_INVOICES", "QUERY_SUMMARY"):
                    state = workflow._execute_query(state)
                elif action and action.value == "DRAFT_EMAIL":
                    # Handle email draft
                    await websocket.send_json({
                        "event": "message",
                        "data": {
                            "role": "assistant",
                            "content": "Email draft created. Awaiting approval."
                        }
                    })
                else:
                    # Mutation - route to approval
                    state = workflow._route_to_approval(state)
                    await websocket.send_json({
                        "event": "approval_required",
                        "data": {
                            "approval_id": state.get("pending_approval_id"),
                            "action": action.value if hasattr(action, 'value') else str(action)
                        }
                    })
            
            # Send final state
            response = state_to_response(state)
            await websocket.send_json({
                "event": "response",
                "data": response.model_dump()
            })
            
    except WebSocketDisconnect:
        manager.disconnect(conversation_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.send_json({
            "event": "error",
            "data": {"message": str(e)}
        })
        manager.disconnect(conversation_id)


# =============================================================================
# Root Endpoint
# =============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "description": settings.description,
        "docs_url": "/api/docs",
        "health_url": "/api/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
