
import sys
from jinja2 import Environment, FileSystemLoader

sys.path.append('/Users/sachinsrivastava/Downloads/HD Dashboard')
from database import SessionLocal
from dashboard_logic import compute_dashboard, get_month_label

db = SessionLocal()
data = compute_dashboard(db, "2026-05")
db.close()

env = Environment(loader=FileSystemLoader('/Users/sachinsrivastava/Downloads/HD Dashboard/templates'))
template = env.get_template('dashboard.html')

# Mock context
class MockURL:
    path = "/"
class MockRequest:
    url = MockURL()
    def __getitem__(self, key): return {}

context = {
    "request": MockRequest(),
    "data": data,
    "month_str": "2026-05",
    "current_month": "2026-05",
    "current_month_label": "May 2026",
    "user": {"role": "admin", "username": "admin"},
    "greeting": "morning",
    "pending_entry_count": 38,
    "high_risk_count": 0,
}

try:
    html = template.render(context)
    print("Template rendered successfully!")
except Exception as e:
    print(f"Template Error: {e}")
    import traceback
    traceback.print_exc()
