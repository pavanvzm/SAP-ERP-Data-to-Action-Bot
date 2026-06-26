# SAP/ERP Data-to-Action Bot

Enterprise-grade chatbot that connects natural language to strict ERP database operations with **Human-in-the-Loop (HITL)** approval workflows.

## 🔒 Security Features

- **SQL Injection Prevention**: Parameterized queries only - no raw SQL from LLM
- **HITL Approval**: All mutations (write/update/delete) require human authorization
- **Safety Validation**: Blocks dangerous patterns, bypass attempts, mass deletions
- **Rate Limiting**: Per-IP rate limiting (100 req/min)
- **Security Headers**: CSP, HSTS, X-Frame-Options
- **Audit Logging**: Complete audit trail for all operations

## 🚀 Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Process natural language queries |
| `/api/approve` | POST | Approve/deny pending mutations |
| `/api/approvals/pending` | GET | List pending approvals |
| `/api/customers` | GET | Get customer data |
| `/api/invoices` | GET | Get invoice data |
| `/api/summary` | GET | Dashboard statistics |
| `/api/health` | GET | Health check |

## 🔧 Example Usage

```bash
# Query customers (no approval needed)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Show all enterprise customers"}'

# Update invoice (requires approval)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Mark invoice #5 as paid"}'

# Approve the mutation
curl -X POST http://localhost:8000/api/approve \
  -H "Content-Type: application/json" \
  -d '{"approval_id": 1, "decision": "approve", "authorized_by": "admin"}'
```

## ✅ Evaluation

Run the test suite:

```bash
python evals/run_evals.py
```

All 37 tests pass, covering:
- Safe queries (8/8)
- Approval required (5/5)
- SQL injection blocking (10/10)
- Bypass attempt blocking (5/5)
- Mass deletion blocking (4/4)
- Edge cases (5/5)

## 📁 Project Structure

```
erp-data-action-bot/
├── backend/
│   ├── app/
│   │   ├── main.py       # FastAPI entry point
│   │   ├── database.py   # SQLite mock ERP
│   │   ├── schemas.py    # Pydantic validation
│   │   └── agent/
│   │       ├── graph.py  # LangGraph workflow
│   │       ├── tools.py  # Safe tool execution
│   │       ├── state.py  # State definitions
│   │       └── prompts.py
│   └── requirements.txt
├── frontend/
│   └── src/app/page.tsx  # Split-panel UI
├── evals/
│   ├── dataset.json      # Test cases
│   └── run_evals.py     # Evaluation runner
└── SECURITY.md          # Security documentation
```

## 🛡️ Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   User      │────▶│  FastAPI     │────▶│   LangGraph │
│   Input     │     │  Backend     │     │   Workflow  │
└─────────────┘     └──────────────┘     └─────────────┘
                           │                    │
                           ▼                    ▼
                    ┌──────────────┐     ┌─────────────┐
                    │   Safety     │     │   HITL      │
                    │   Validator  │     │   Approval  │
                    └──────────────┘     └─────────────┘
                           │                    │
                           ▼                    ▼
                    ┌──────────────┐     ┌─────────────┐
                    │   SQLite     │◀────│   Human     │
                    │   Database   │     │   Approver  │
                    └──────────────┘     └─────────────┘
```

## License

MIT
