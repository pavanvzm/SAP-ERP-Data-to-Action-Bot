"""
Core execution tools for the ERP agent.

This module provides tools for database operations, email drafting,
and safety validation - all without allowing raw SQL from LLM.
"""

import re
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Safety Validation
# =============================================================================

class SafetyValidator:
    """
    Validates operations for safety before execution.
    
    Blocks:
    - SQL injection patterns
    - Mass deletions/updates
    - Bypass attempts
    - Dangerous system commands
    """
    
    # Dangerous SQL keywords that should never be in user input
    DANGEROUS_SQL_PATTERNS = [
        r"\bDROP\s+TABLE\b",
        r"\bDROP\s+DATABASE\b",
        r"\bTRUNCATE\b",
        r"\bDELETE\s+FROM\b(?!\s+\w+\s+WHERE\s+\w+\s*=\s*\d+)",
        r"\bUNION\s+SELECT\b",
        r"\bOR\s+1\s*=\s*1\b",
        r"'?\s*OR\s+'?\s*1\s*=\s*1",
        r"--",
        r"/\*",
        r"\bALTER\b",
        r"\bCREATE\s+TABLE\b",
        r"\bEXEC\b",
        r"\bEXECUTE\b",
        r"\bXP_",
    ]
    
    # Patterns that indicate bypass attempts
    BYPASS_PATTERNS = [
        r"\bskip\s+(approval|validation|safety)\b",
        r"\bbypass\s+(approval|validation|safety)\b",
        r"\bi\s+am\s+(admin|administrator|root)\b",
        r"\btrust\s+me\b",
        r"\boverride\s+safety\b",
        r"\bignore\s+(warning|error|safety)\b",
        r"\bdisable\s+(security|safety|validation)\b",
        r"\bfire\s+anyway\b",
        r"\bproceed\s+anyway\b",
        r"\bdo\s+it\s+anyway\b",
    ]
    
    # Dangerous action keywords
    MASS_OPERATION_PATTERNS = [
        r"\b(all|every)\s+(customer|invoice|order|record)",
        r"\bdelete\s+all\b",
        r"\bupdate\s+all\b",
        r"\btruncate\s+all\b",
        r"\bdrop\s+all\b",
    ]
    
    @classmethod
    def validate(cls, message: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a user message for dangerous patterns.
        
        Returns:
            Tuple of (is_safe, reason_if_unsafe)
        """
        if not message:
            return False, "Empty message"
        
        message_lower = message.lower()
        
        # Check for SQL injection patterns
        for pattern in cls.DANGEROUS_SQL_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                return False, f"Dangerous SQL pattern detected: {pattern}"
        
        # Check for bypass attempts
        for pattern in cls.BYPASS_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                return False, f"Bypass attempt detected: {pattern}"
        
        # Check for mass operations
        for pattern in cls.MASS_OPERATION_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                return False, f"Mass operation detected: {pattern}"
        
        return True, None


# =============================================================================
# Tool Execution Result
# =============================================================================

@dataclass
class ToolResult:
    """Result from executing a tool."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    message: Optional[str] = None


# =============================================================================
# Tool Definitions
# =============================================================================

def get_tool_definitions() -> List[Dict[str, Any]]:
    """
    Get the definitions of all available tools.
    
    These are the ONLY operations the agent can perform.
    No raw SQL is ever executed.
    """
    return [
        {
            "name": "get_customers",
            "description": "Get list of customers. Optional filter by tier (STANDARD, PREMIUM, ENTERPRISE).",
            "parameters": {
                "type": "object",
                "properties": {
                    "tier": {
                        "type": "string",
                        "enum": ["STANDARD", "PREMIUM", "ENTERPRISE"],
                        "description": "Filter by customer tier"
                    },
                    "min_credit": {
                        "type": "number",
                        "description": "Minimum credit limit"
                    }
                }
            }
        },
        {
            "name": "get_invoices",
            "description": "Get list of invoices. Optional filter by status or customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["PAID", "PENDING", "OVERDUE"],
                        "description": "Filter by invoice status"
                    },
                    "customer_id": {
                        "type": "integer",
                        "description": "Filter by customer ID"
                    }
                }
            }
        },
        {
            "name": "get_summary",
            "description": "Get dashboard summary statistics.",
            "parameters": {"type": "object", "properties": {}}
        },
        {
            "name": "mutation",
            "description": "Execute a database mutation. ALWAYS requires approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["UPDATE_INVOICE_STATUS", "UPDATE_CUSTOMER_CREDIT", "DELETE_INVOICE"],
                        "description": "The mutation action to perform"
                    },
                    "invoice_id": {"type": "integer", "description": "Invoice ID for invoice operations"},
                    "new_status": {
                        "type": "string",
                        "enum": ["PAID", "PENDING", "OVERDUE"],
                        "description": "New status for invoice"
                    },
                    "customer_id": {"type": "integer", "description": "Customer ID"},
                    "new_credit_limit": {"type": "number", "description": "New credit limit"},
                    "authorized_by": {"type": "string", "description": "Approver identifier"}
                },
                "required": ["action"]
            }
        },
        {
            "name": "draft_email",
            "description": "Draft an email notification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template": {
                        "type": "string",
                        "enum": ["OVERDUE_NOTICE", "PAYMENT_CONFIRMATION", "CREDIT_UPDATE"],
                        "description": "Email template type"
                    },
                    "recipient": {"type": "string", "description": "Recipient email"},
                    "data": {"type": "object", "description": "Template data"}
                },
                "required": ["template", "recipient"]
            }
        }
    ]


def execute_tool(
    tool_name: str,
    parameters: Dict[str, Any],
    database: Any
) -> ToolResult:
    """
    Execute a tool with the given parameters.
    
    This is the ONLY way to interact with the database.
    All operations use parameterized queries - no raw SQL.
    """
    try:
        if tool_name == "get_customers":
            return _get_customers(parameters, database)
        elif tool_name == "get_invoices":
            return _get_invoices(parameters, database)
        elif tool_name == "get_summary":
            return _get_summary(parameters, database)
        elif tool_name == "mutation":
            return _execute_mutation(parameters, database)
        elif tool_name == "draft_email":
            return _draft_email(parameters, database)
        else:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")
    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return ToolResult(success=False, error=str(e))


def _get_customers(params: Dict[str, Any], database: Any) -> ToolResult:
    """Get customers from database."""
    tier = params.get("tier")
    min_credit = params.get("min_credit")
    
    customers = database.get_customers_sync(tier=tier, min_credit=min_credit)
    
    return ToolResult(
        success=True,
        data={"customers": customers, "count": len(customers)},
        message=f"Found {len(customers)} customers"
    )


def _get_invoices(params: Dict[str, Any], database: Any) -> ToolResult:
    """Get invoices from database."""
    status = params.get("status")
    customer_id = params.get("customer_id")
    
    invoices = database.get_invoices_sync(status=status, customer_id=customer_id)
    
    return ToolResult(
        success=True,
        data={"invoices": invoices, "count": len(invoices)},
        message=f"Found {len(invoices)} invoices"
    )


def _get_summary(params: Dict[str, Any], database: Any) -> ToolResult:
    """Get dashboard summary."""
    summary = database.get_summary_sync()
    return ToolResult(success=True, data=summary)


def _execute_mutation(params: Dict[str, Any], database: Any) -> ToolResult:
    """Execute a database mutation."""
    import asyncio
    
    action = params.get("action")
    authorized_by = params.get("authorized_by", "system")
    
    if not authorized_by:
        return ToolResult(success=False, error="No authorization provided")
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if action == "UPDATE_INVOICE_STATUS":
        invoice_id = params.get("invoice_id")
        new_status = params.get("new_status")
        
        if not invoice_id or not new_status:
            return ToolResult(success=False, error="Missing invoice_id or new_status")
        
        if new_status not in ["PAID", "PENDING", "OVERDUE"]:
            return ToolResult(success=False, error=f"Invalid status: {new_status}")
        
        loop.run_until_complete(database.update_invoice_status(invoice_id, new_status, authorized_by))
        return ToolResult(success=True, message=f"Invoice {invoice_id} updated to {new_status}")
    
    elif action == "UPDATE_CUSTOMER_CREDIT":
        customer_id = params.get("customer_id")
        new_credit = params.get("new_credit_limit")
        
        if not customer_id or new_credit is None:
            return ToolResult(success=False, error="Missing customer_id or new_credit_limit")
        
        loop.run_until_complete(database.update_customer_credit(customer_id, new_credit, authorized_by))
        return ToolResult(success=True, message=f"Customer {customer_id} credit updated to {new_credit}")
    
    else:
        return ToolResult(success=False, error=f"Unknown mutation action: {action}")


def _draft_email(params: Dict[str, Any], database: Any) -> ToolResult:
    """Draft an email notification."""
    template = params.get("template")
    recipient = params.get("recipient")
    data = params.get("data", {})
    
    templates = {
        "OVERDUE_NOTICE": {
            "subject": "Payment Overdue Notice - Invoice #{invoice_id}",
            "body": "Dear {customer_name},\n\nThis is a reminder that Invoice #{invoice_id} for {amount} is overdue.\n\nPlease process payment at your earliest convenience.\n\nBest regards,\nAccounts Receivable"
        },
        "PAYMENT_CONFIRMATION": {
            "subject": "Payment Received - Invoice #{invoice_id}",
            "body": "Dear {customer_name},\n\nWe have received your payment of {amount} for Invoice #{invoice_id}.\n\nThank you for your business.\n\nBest regards,\nAccounts Receivable"
        },
        "CREDIT_UPDATE": {
            "subject": "Credit Limit Update Notification",
            "body": "Dear {customer_name},\n\nYour credit limit has been updated to {new_credit_limit}.\n\nIf you have any questions, please contact our credit department.\n\nBest regards,\nAccounts Department"
        }
    }
    
    if template not in templates:
        return ToolResult(success=False, error=f"Unknown template: {template}")
    
    tpl = templates[template]
    subject = tpl["subject"].format(**data)
    body = tpl["body"].format(**data)
    
    return ToolResult(
        success=True,
        data={"subject": subject, "body": body, "recipients": [recipient]}
    )
