"""
LangGraph workflow orchestration for the ERP Data-to-Action Bot.

This module implements the state machine that processes user requests:
1. Extract intent from natural language
2. Validate safety
3. Execute read operations directly OR route mutations to approval
4. Return results or pending approval status
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Callable
from datetime import datetime

from app.agent.state import AgentState, WorkflowStatus
from app.agent.tools import SafetyValidator, execute_tool, ToolResult
from app.agent.prompts import get_system_prompt, get_user_prompt

logger = logging.getLogger(__name__)


class IntentExtractor:
    """
    Extracts structured intent from natural language messages.
    
    Uses pattern matching to identify user intent without requiring
    an LLM for basic operations, making responses faster and more reliable.
    """
    
    # Pattern to intent mapping
    INTENT_PATTERNS = [
        # QUERY_CUSTOMERS
        (r"(show|list|get|display|find|search)\s*(all\s+)?(customers?|clients?|companies?|accounts?)", "QUERY_CUSTOMERS"),
        (r"(customer|client|company|account)\s+(info|details|information|list)", "QUERY_CUSTOMERS"),
        (r"who\s+are\s+(our\s+)?(customers?|clients?|companies?)", "QUERY_CUSTOMERS"),
        
        # QUERY_INVOICES
        (r"(show|list|get|display|find|search)\s*(all\s+)?(invoices?|bills?|payments?)(?!.*(customer|client))", "QUERY_INVOICES"),
        (r"(invoice|bill|payment)\s+(info|details|status|list)", "QUERY_INVOICES"),
        (r"(overdue|late|unpaid|pending|paid)\s+(invoices?|bills?|payments?)", "QUERY_INVOICES"),
        (r"invoice\s+#?(\d+)", "QUERY_INVOICES"),
        
        # QUERY_SUMMARY
        (r"(dashboard|summary|overview|statistics?|stats|report)", "QUERY_SUMMARY"),
        (r"what('s|s\s+is)?\s+(the\s+)?(total|overall|summary)", "QUERY_SUMMARY"),
        (r"how\s+many\s+(customers?|invoices?)", "QUERY_SUMMARY"),
        
        # UPDATE_INVOICE_STATUS
        (r"(mark|set|change|update)\s+(invoice\s+#?\d+|\d+)\s+(as\s+)?(paid|pending|overdue)", "UPDATE_INVOICE_STATUS"),
        (r"(pay|payment)\s+(invoice\s+#?\d+|\d+)", "UPDATE_INVOICE_STATUS"),
        (r"(mark|set)\s+(invoice\s+#?\d+|\d+)\s+(as\s+)?paid", "UPDATE_INVOICE_STATUS"),
        
        # UPDATE_CUSTOMER_CREDIT
        (r"(update|change|set|increase|decrease)\s+(credit|limit)", "UPDATE_CUSTOMER_CREDIT"),
        (r"(customer|client)\s+credit", "UPDATE_CUSTOMER_CREDIT"),
        
        # DELETE_INVOICE
        (r"(delete|remove|cancel)\s+(invoice|bill)", "DELETE_INVOICE"),
        
        # DRAFT_EMAIL
        (r"(send|draft|compose|create)\s+(email|notification|message|letter)", "DRAFT_EMAIL"),
        (r"(overdue|payment)\s+(notice|reminder|email)", "DRAFT_EMAIL"),
    ]
    
    # Parameter extraction patterns
    PARAM_PATTERNS = {
        "invoice_id": r"invoice\s+#?(\d+)",
        "status": r"\b(paid|pending|overdue)\b",
        "tier": r"\b(standard|premium|enterprise)\b",
    }
    
    def extract(self, message: str) -> Dict[str, Any]:
        """
        Extract intent from user message.
        
        Returns:
            Dict with action, confidence, parameters, reasoning, requires_approval
        """
        message_lower = message.lower()
        
        # Safety check first
        is_safe, reason = SafetyValidator.validate(message)
        if not is_safe:
            return {
                "action": "UNKNOWN",
                "confidence": 0.0,
                "parameters": {},
                "reasoning": f"Blocked: {reason}",
                "requires_approval": False,
                "is_safe": False,
                "safety_notes": reason
            }
        
        # Try to match patterns
        for pattern, action in self.INTENT_PATTERNS:
            match = re.search(pattern, message_lower)
            if match:
                params = self._extract_parameters(message, message_lower)
                return {
                    "action": action,
                    "confidence": 0.85,
                    "parameters": params,
                    "reasoning": f"Pattern matched: {action}",
                    "requires_approval": action in [
                        "UPDATE_INVOICE_STATUS",
                        "UPDATE_CUSTOMER_CREDIT",
                        "DELETE_INVOICE",
                        "DRAFT_EMAIL"
                    ],
                    "is_safe": True,
                    "safety_notes": None
                }
        
        # No pattern matched
        return {
            "action": "UNKNOWN",
            "confidence": 0.3,
            "parameters": {},
            "reasoning": "No clear intent pattern matched",
            "requires_approval": False,
            "is_safe": True,
            "safety_notes": None
        }
    
    def _extract_parameters(self, message: str, message_lower: str) -> Dict[str, Any]:
        """Extract parameters from the message."""
        params = {}
        
        # Extract invoice ID
        invoice_match = re.search(r"invoice\s+#?(\d+)", message_lower)
        if invoice_match:
            params["invoice_id"] = int(invoice_match.group(1))
        
        # Extract status
        status_match = re.search(r"\b(paid|pending|overdue)\b", message_lower)
        if status_match:
            params["new_status"] = status_match.group(1).upper()
        
        # Extract customer name
        customer_match = re.search(r"(for|to|customer\s+)?([A-Za-z\s]+?)(corp|inc|llc|ltd)?", message)
        if customer_match and customer_match.group(2):
            params["customer_name"] = customer_match.group(2).strip().title()
        
        # Extract credit limit
        credit_match = re.search(r"(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)", message)
        if credit_match and "credit" in message_lower:
            params["new_credit_limit"] = float(credit_match.group(1).replace(",", ""))
        
        # Extract tier
        tier_match = re.search(r"\b(standard|premium|enterprise)\b", message_lower)
        if tier_match:
            params["tier"] = tier_match.group(1).upper()
        
        return params


class WorkflowGraph:
    """
    LangGraph-style workflow orchestrator.
    
    Manages the state machine that processes user requests through
    intent extraction, safety validation, and execution/routing.
    """
    
    def __init__(self, database: Any):
        self.database = database
        self.intent_extractor = IntentExtractor()
    
    def process(self, message: str, conversation_id: str = "") -> AgentState:
        """
        Process a user message through the workflow.
        
        Args:
            message: The user's natural language message
            conversation_id: Optional conversation ID for context
            
        Returns:
            AgentState with processing results
        """
        state: AgentState = {
            "conversation_id": conversation_id,
            "messages": [{"role": "user", "content": message}],
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
        
        # Step 1: Extract intent
        state = self._extract_intent(state)
        
        # Step 2: Route based on intent
        if not state.get("is_safe", True):
            state["status"] = WorkflowStatus.ERROR
            state["error"] = state.get("safety_notes", "Safety validation failed")
            return state
        
        intent = state.get("current_intent", {})
        if intent.get("requires_approval"):
            state = self._route_to_approval(state)
        else:
            state = self._execute_query(state)
        
        return state
    
    def _extract_intent(self, state: AgentState) -> AgentState:
        """Extract intent from the latest user message."""
        messages = state.get("messages", [])
        if not messages:
            return state
        
        latest_message = messages[-1].get("content", "")
        
        # Use the intent extractor
        intent = self.intent_extractor.extract(latest_message)
        
        state["current_intent"] = intent
        state["intent_confidence"] = intent.get("confidence", 0.0)
        state["is_safe"] = intent.get("is_safe", True)
        state["safety_notes"] = intent.get("safety_notes")
        
        return state
    
    def _route_to_approval(self, state: AgentState) -> AgentState:
        """Route a mutation to the approval workflow."""
        intent = state.get("current_intent", {})
        action = intent.get("action", "UNKNOWN")
        params = intent.get("parameters", {})
        
        # Create pending approval
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            approval_id = loop.run_until_complete(
                self.database.create_pending_approval(
                    action=action,
                    details=params,
                    requested_by="chat_user"
                )
            )
            state["pending_approval_id"] = approval_id
            state["status"] = WorkflowStatus.AWAITING_APPROVAL
            state["action_payload"] = {
                "action": action,
                "parameters": params,
                "approval_id": approval_id
            }
        except Exception as e:
            state["status"] = WorkflowStatus.ERROR
            state["error"] = f"Failed to create approval: {str(e)}"
        
        return state
    
    def _execute_query(self, state: AgentState) -> AgentState:
        """Execute a read query."""
        intent = state.get("current_intent", {})
        action = intent.get("action", "UNKNOWN")
        params = intent.get("parameters", {})
        
        # Map action to tool
        tool_map = {
            "QUERY_CUSTOMERS": "get_customers",
            "QUERY_INVOICES": "get_invoices",
            "QUERY_SUMMARY": "get_summary",
        }
        
        tool_name = tool_map.get(action)
        
        if not tool_name:
            state["status"] = WorkflowStatus.ERROR
            state["error"] = f"Unknown action: {action}"
            return state
        
        # Execute tool
        result = execute_tool(tool_name, params, self.database)
        
        if result.success:
            state["status"] = WorkflowStatus.COMPLETED
            state["query_result"] = result.data
            state["messages"].append({
                "role": "assistant",
                "content": result.message or "Query executed successfully"
            })
        else:
            state["status"] = WorkflowStatus.ERROR
            state["error"] = result.error
        
        return state
    
    def approve_action(
        self,
        approval_id: int,
        approved_by: str,
        execute_mutation: bool = True
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Process an approval decision.
        
        Args:
            approval_id: ID of the pending approval
            approved_by: User approving the action
            execute_mutation: Whether to execute the mutation
            
        Returns:
            Tuple of (success, message, result_data)
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Get the pending approval
        pending = loop.run_until_complete(self.database.get_pending_approvals())
        approval = next((p for p in pending if p.id == approval_id), None)
        
        if not approval:
            return False, f"Approval #{approval_id} not found", None
        
        # Execute the mutation if requested
        result_data = None
        if execute_mutation:
            try:
                # Parse details
                try:
                    details = json.loads(approval.query) if approval.query else {}
                except (json.JSONDecodeError, TypeError):
                    details = {}
                
                details["authorized_by"] = approved_by
                
                result = execute_tool("mutation", details, self.database)
                
                if result.success:
                    loop.run_until_complete(
                        self.database.approve_operation(approval_id, approved_by)
                    )
                    result_data = result.data
                else:
                    return False, f"Execution failed: {result.error}", None
                    
            except Exception as e:
                return False, f"Execution error: {str(e)}", None
        
        # Mark as approved
        loop.run_until_complete(self.database.approve_operation(approval_id, approved_by))
        
        return True, f"Action approved and executed by {approved_by}", result_data
    
    def deny_action(self, approval_id: int, denied_by: str) -> Tuple[bool, str]:
        """Deny an approval request."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self.database.deny_operation(approval_id, denied_by))
            return True, f"Action #{approval_id} denied by {denied_by}"
        except Exception as e:
            return False, f"Failed to deny: {str(e)}"


# Global workflow instance
_workflow: Optional[WorkflowGraph] = None


async def get_workflow() -> WorkflowGraph:
    """Get or create the global workflow instance."""
    global _workflow
    if _workflow is None:
        db = await get_database()
        _workflow = WorkflowGraph(db)
    return _workflow


# Import at module level for circular dependency
from app.database import get_database
