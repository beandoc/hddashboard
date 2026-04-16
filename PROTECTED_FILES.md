# PROTECTED FILES — DO NOT MODIFY

The following files are locked. Modifying them will break production.
All changes require approval before committing.

- dashboard_logic.py   ← clinical calculation logic, locked
- database.py          ← database models, locked  
- alerts.py            ← alerting functions, locked
- ml_analytics.py      ← ML models, locked
- dynamic_vars.py      ← variable system, locked

To add a new feature:
1. Create a NEW file (e.g. new_feature.py)
2. Import it in main.py
3. Never modify the files above directly

To add a new database column:
1. Add to database.py AND run ALTER TABLE in Render Shell same day
2. Show the diff here before committing
