"""
In-memory SQLite mock ERP database with seed data.
"""

import aiosqlite
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class AuditLog:
    """Represents an audit log entry."""
    id: int
    timestamp: str
    action: str
    query: str
    authorized_by: Optional[str]
    status: str
    details: Optional[str] = None


class ERPDatabase:
    """
    In-memory SQLite database simulating an ERP system.
    
    Tables:
    - customers: Customer information with credit limits
    - invoices: Invoice records with payment status
    - audit_logs: Security audit trail
    - pending_approvals: Operations awaiting human approval
    """
    
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._next_audit_id = 1
        self._next_approval_id = 1
    
    async def initialize(self) -> None:
        """Initialize database with schema and seed data."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        
        await self._create_schema()
        await self._seed_data()
        logger.info("Database initialized successfully")
    
    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
    
    async def _create_schema(self) -> None:
        """Create database tables."""
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                credit_limit REAL NOT NULL DEFAULT 0,
                tier TEXT NOT NULL DEFAULT 'STANDARD'
            );
            
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                due_date TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );
            
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                query TEXT NOT NULL,
                authorized_by TEXT,
                status TEXT NOT NULL,
                details TEXT
            );
            
            CREATE TABLE IF NOT EXISTS pending_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                details TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                payload TEXT
            );
        """)
        await self._db.commit()
    
    async def _seed_data(self) -> None:
        """Seed initial test data."""
        # Check if already seeded
        cursor = await self._db.execute("SELECT COUNT(*) FROM customers")
        count = (await cursor.fetchone())[0]
        if count > 0:
            return
        
        # Seed customers
        customers = [
            ("Acme Corp", "contact@acmecorp.com", "+1-555-0101", 500000.0, "ENTERPRISE"),
            ("Globex Corporation", "billing@globex.com", "+1-555-0102", 250000.0, "PREMIUM"),
            ("Initech", "accounts@initech.com", "+1-555-0103", 100000.0, "STANDARD"),
            ("Umbrella Corp", "finance@umbrella.com", "+1-555-0104", 750000.0, "ENTERPRISE"),
            ("Stark Industries", "legal@stark.com", "+1-555-0105", 1000000.0, "ENTERPRISE"),
            ("Wayne Enterprises", "contact@wayne.com", "+1-555-0106", 500000.0, "ENTERPRISE"),
            ("Cyberdyne Systems", "orders@cyberdyne.com", "+1-555-0107", 300000.0, "PREMIUM"),
            ("Soylent Corp", "info@soylent.com", "+1-555-0108", 150000.0, "STANDARD"),
            ("Massive Dynamic", "finance@massive.com", "+1-555-0109", 800000.0, "ENTERPRISE"),
            ("Hooli", "tech@hooli.com", "+1-555-0110", 200000.0, "PREMIUM"),
        ]
        
        await self._db.executemany(
            "INSERT INTO customers (name, email, phone, credit_limit, tier) VALUES (?, ?, ?, ?, ?)",
            customers
        )
        
        # Seed invoices
        today = datetime.now()
        invoices = [
            (1, 15000.0, "PAID", (today - timedelta(days=30)).isoformat(), "Q1 Services"),
            (1, 22500.0, "PENDING", (today + timedelta(days=15)).isoformat(), "Q2 Services"),
            (2, 8500.0, "OVERDUE", (today - timedelta(days=10)).isoformat(), "Software License"),
            (3, 3200.0, "PENDING", (today + timedelta(days=7)).isoformat(), "Consulting"),
            (4, 45000.0, "PENDING", (today + timedelta(days=30)).isoformat(), "Research Materials"),
            (5, 125000.0, "PAID", (today - timedelta(days=60)).isoformat(), "Hardware Supply"),
            (6, 7800.0, "OVERDUE", (today - timedelta(days=5)).isoformat(), "Security Services"),
            (7, 15000.0, "PENDING", (today + timedelta(days=20)).isoformat(), "Cloud Infrastructure"),
            (8, 4500.0, "PENDING", (today + timedelta(days=10)).isoformat(), "Product Supply"),
            (9, 95000.0, "PAID", (today - timedelta(days=45)).isoformat(), "Marketing Campaign"),
            (10, 18000.0, "PENDING", (today + timedelta(days=25)).isoformat(), "Tech Support"),
            (1, 12000.0, "OVERDUE", (today - timedelta(days=15)).isoformat(), "Equipment Rental"),
            (2, 5200.0, "PENDING", (today + timedelta(days=5)).isoformat(), "Training Session"),
            (3, 8900.0, "PENDING", (today + timedelta(days=12)).isoformat(), "Software License"),
            (4, 23000.0, "OVERDUE", (today - timedelta(days=20)).isoformat(), "Lab Equipment"),
            (5, 67000.0, "PENDING", (today + timedelta(days=18)).isoformat(), "Patent Filing"),
            (6, 11200.0, "PENDING", (today + timedelta(days=22)).isoformat(), "Asset Management"),
            (7, 34000.0, "PENDING", (today + timedelta(days=28)).isoformat(), "System Integration"),
            (8, 5600.0, "OVERDUE", (today - timedelta(days=8)).isoformat(), "Quality Testing"),
            (9, 28000.0, "PENDING", (today + timedelta(days=14)).isoformat(), "R&D Materials"),
            (10, 9200.0, "PENDING", (today + timedelta(days=8)).isoformat(), "Logistics Support"),
        ]
        
        await self._db.executemany(
            "INSERT INTO invoices (customer_id, amount, status, due_date, description, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            [(i[0], i[1], i[2], i[3], i[4], today.isoformat()) for i in invoices]
        )
        
        await self._db.commit()
        logger.info(f"Seeded {len(customers)} customers and {len(invoices)} invoices")
    
    # -------------------------------------------------------------------------
    # Customer Operations
    # -------------------------------------------------------------------------
    
    async def get_customers(
        self,
        tier: Optional[str] = None,
        min_credit: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Get all customers with optional filters."""
        query = "SELECT * FROM customers WHERE 1=1"
        params = []
        
        if tier:
            query += " AND tier = ?"
            params.append(tier)
        if min_credit is not None:
            query += " AND credit_limit >= ?"
            params.append(min_credit)
        
        query += " ORDER BY name"
        
        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    
    async def get_customer_by_id(self, customer_id: int) -> Optional[Dict[str, Any]]:
        """Get a single customer by ID."""
        cursor = await self._db.execute(
            "SELECT * FROM customers WHERE id = ?", (customer_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    
    async def update_customer_credit(
        self,
        customer_id: int,
        new_limit: float,
        authorized_by: str
    ) -> bool:
        """Update customer's credit limit."""
        await self._db.execute(
            "UPDATE customers SET credit_limit = ? WHERE id = ?",
            (new_limit, customer_id)
        )
        await self._db.commit()
        await self._log_audit(
            action="UPDATE_CUSTOMER_CREDIT",
            query=f"UPDATE customers SET credit_limit = {new_limit} WHERE id = {customer_id}",
            authorized_by=authorized_by,
            status="APPROVED"
        )
        return True
    
    # -------------------------------------------------------------------------
    # Invoice Operations
    # -------------------------------------------------------------------------
    
    async def get_invoices(
        self,
        status: Optional[str] = None,
        customer_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get all invoices with optional filters."""
        query = """
            SELECT i.*, c.name as customer_name 
            FROM invoices i 
            JOIN customers c ON i.customer_id = c.id 
            WHERE 1=1
        """
        params = []
        
        if status:
            query += " AND i.status = ?"
            params.append(status)
        if customer_id:
            query += " AND i.customer_id = ?"
            params.append(customer_id)
        
        query += " ORDER BY i.due_date"
        
        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    
    async def update_invoice_status(
        self,
        invoice_id: int,
        new_status: str,
        authorized_by: str
    ) -> bool:
        """Update invoice status."""
        await self._db.execute(
            "UPDATE invoices SET status = ? WHERE id = ?",
            (new_status, invoice_id)
        )
        await self._db.commit()
        await self._log_audit(
            action="UPDATE_INVOICE_STATUS",
            query=f"UPDATE invoices SET status = '{new_status}' WHERE id = {invoice_id}",
            authorized_by=authorized_by,
            status="APPROVED"
        )
        return True
    
    # -------------------------------------------------------------------------
    # Summary Statistics
    # -------------------------------------------------------------------------
    
    async def get_summary(self) -> Dict[str, Any]:
        """Get dashboard summary statistics."""
        # Customer count by tier
        cursor = await self._db.execute("""
            SELECT tier, COUNT(*) as count 
            FROM customers 
            GROUP BY tier
        """)
        tier_counts = {row["tier"]: row["count"] for row in await cursor.fetchall()}
        
        # Invoice stats
        cursor = await self._db.execute("""
            SELECT status, COUNT(*) as count, SUM(amount) as total 
            FROM invoices 
            GROUP BY status
        """)
        invoice_stats = {
            row["status"]: {"count": row["count"], "total": row["total"]}
            for row in await cursor.fetchall()
        }
        
        # Total customers
        cursor = await self._db.execute("SELECT COUNT(*) as count FROM customers")
        total_customers = (await cursor.fetchone())["count"]
        
        # Total invoices
        cursor = await self._db.execute("SELECT COUNT(*) as count FROM invoices")
        total_invoices = (await cursor.fetchone())["count"]
        
        return {
            "customers": {
                "total": total_customers,
                "by_tier": tier_counts
            },
            "invoices": {
                "total": total_invoices,
                "by_status": invoice_stats
            }
        }
    
    # -------------------------------------------------------------------------
    # Approval Workflow
    # -------------------------------------------------------------------------
    
    async def create_pending_approval(
        self,
        action: str,
        details: Dict[str, Any],
        requested_by: str
    ) -> int:
        """Create a new pending approval request."""
        approval_id = self._next_approval_id
        self._next_approval_id += 1
        
        await self._db.execute(
            """INSERT INTO pending_approvals 
               (id, action, details, requested_by, timestamp, payload) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                approval_id,
                action,
                json.dumps(details),
                requested_by,
                datetime.now().isoformat(),
                json.dumps(details)
            )
        )
        await self._db.commit()
        
        await self._log_audit(
            action=action,
            query=f"PENDING: {json.dumps(details)}",
            authorized_by=requested_by,
            status="PENDING"
        )
        
        return approval_id
    
    async def get_pending_approvals(self) -> List[AuditLog]:
        """Get all pending approval requests."""
        cursor = await self._db.execute(
            "SELECT * FROM pending_approvals ORDER BY timestamp DESC"
        )
        rows = await cursor.fetchall()
        return [
            AuditLog(
                id=row["id"],
                timestamp=row["timestamp"],
                action=row["action"],
                query=row["details"],
                authorized_by=row["requested_by"],
                status="PENDING",
                details=row["payload"]
            )
            for row in rows
        ]
    
    async def approve_operation(self, approval_id: int, approved_by: str) -> bool:
        """Mark an approval as processed."""
        await self._db.execute(
            "DELETE FROM pending_approvals WHERE id = ?",
            (approval_id,)
        )
        await self._db.commit()
        
        await self._log_audit(
            action="APPROVAL_GRANTED",
            query=f"Approved request #{approval_id}",
            authorized_by=approved_by,
            status="APPROVED"
        )
        return True
    
    async def deny_operation(self, approval_id: int, denied_by: str) -> bool:
        """Deny an approval request."""
        await self._db.execute(
            "DELETE FROM pending_approvals WHERE id = ?",
            (approval_id,)
        )
        await self._db.commit()
        
        await self._log_audit(
            action="APPROVAL_DENIED",
            query=f"Denied request #{approval_id}",
            authorized_by=denied_by,
            status="DENIED"
        )
        return True
    
    # -------------------------------------------------------------------------
    # Audit Logging
    # -------------------------------------------------------------------------
    
    async def _log_audit(
        self,
        action: str,
        query: str,
        authorized_by: Optional[str],
        status: str,
        details: Optional[str] = None
    ) -> None:
        """Log an audit entry."""
        await self._db.execute(
            """INSERT INTO audit_logs 
               (id, timestamp, action, query, authorized_by, status, details) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                self._next_audit_id,
                datetime.now().isoformat(),
                action,
                query,
                authorized_by,
                status,
                details
            )
        )
        self._next_audit_id += 1
        await self._db.commit()
    
    async def get_audit_logs(
        self,
        limit: int = 100,
        action_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent audit logs."""
        query = "SELECT * FROM audit_logs"
        params = []
        
        if action_filter:
            query += " WHERE action = ?"
            params.append(action_filter)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# Global database instance
_db_instance: Optional[ERPDatabase] = None


async def get_database() -> ERPDatabase:
    """Get the global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = ERPDatabase()
        await _db_instance.initialize()
    return _db_instance
