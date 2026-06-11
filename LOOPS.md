# HD Dashboard — Loop Protocols for Claude Code Sessions

Paste the relevant loop block at the start of each session.
Claude treats it as a standing operating procedure for that session.

---

## Session State

**Current Loop:** [DEBUG | FEATURE | DEPLOY | MIGRATION]
**Status:** [ACTIVE | PAUSED | COMPLETE]
**Component:** 
**Last action:** 
**Next action:** 

---

## Protected Files — NEVER MODIFY IN ANY LOOP

```
dashboard_logic.py       — clinical Kt/V / URR / spKt/V calculations
database.py              — SQLAlchemy base models
alerts.py                — deterministic KDIGO alert rules
ml_analytics.py          — core ML risk engines (Hgb, ESA, ACM)
dynamic_vars.py          — dynamic patient variable system
validation_engine.py     — physiological bounds and KDIGO validation
```

Any feature requiring changes to these files must be implemented
by creating a new module in `services/` that imports and wraps them.

---

## 🔴 LOOP: DEBUG

**Trigger:** Something is broken — console error, 500, wrong calculation, UI regression.

```
LOOP: DEBUG
Target: [endpoint or component, e.g. "POST /api/entry/submit" or "entry_wizard.js modal"]
Error: [paste the exact error or describe observed vs expected behaviour]
Affected files (if known): [e.g. routers/entry.py, static/js/entry_calc.js]

Cycle:
1. READ — open and review all files likely involved. Do not edit.
2. IDENTIFY — state root cause in one sentence.
3. PROPOSE — show the exact diff/change. Do not apply yet.
4. WAIT — I will confirm with "proceed" before any edit is made.
5. APPLY — make the change.
6. VERIFY — explain why the bug condition can no longer occur.
   If it can still occur, increment attempt counter (max 3) and restart from step 1.
7. AFTER 3 FAILED ATTEMPTS — stop, summarise what was tried, and surface the root cause
   hypothesis for me to decide the next move.

Clinical safety rule: if the bug touches any calculation in dashboard_logic.py
or any alert rule in alerts.py, flag it explicitly and propose the fix via
a wrapper in services/ rather than editing the protected file.

DB rule: if the fix requires a schema change, draft the Alembic migration
script and show it to me before writing any model changes.
```

---

## 🟡 LOOP: FEATURE

**Trigger:** Adding new capability — new route, new UI component, new service.

```
LOOP: FEATURE
Feature: [one sentence description]
Service boundary: [BACKEND | FRONTEND | BOTH]
Stack: FastAPI backend (port 8000), Jinja2 templates in templates/,
       Next.js frontend in frontend/, SQLAlchemy + Alembic for DB.

Cycle:
1. READ — review affected routers/, services/, templates/ or frontend/src/.
           Read the relevant existing code before proposing anything.
2. PLAN — list every file to be created or modified. No edits yet.
   Format:
     CREATE: services/my_feature.py
     MODIFY: routers/api_next.py  (add /feature endpoint)
     CREATE: templates/feature_form.html
3. WAIT — I approve the plan before any file is touched.
4. IMPLEMENT — follow this order:
   a. DB model / Alembic migration (if schema changes needed)
   b. Service logic in services/  (never in the router directly)
   c. FastAPI route in routers/   (thin — delegates to service)
   d. Jinja2 template or Next.js component
5. AFTER EACH STEP — state what you just completed and what is next.
6. CLINICAL GATE — if the feature writes session records, lab results,
   or dialysis parameters, explicitly confirm it calls validation_engine.py
   before any DB write.
7. COMPLETION — provide:
   - curl command to test the endpoint (if backend)
   - Component name or route to verify in browser (if frontend)
   - Any new .env variables required

Constraints:
- New Python functions must have PEP 484 type hints.
- New routes must use  db: Session = Depends(get_db)  — no raw sessions.
- New templates must preserve the dark-mode glassmorphic CSS theme.
- Never call alembic CLI commands that introspect live schema.
```

---

## 🟢 LOOP: DEPLOY CHECK

**Trigger:** About to push to production. Read-only audit — no edits.

```
LOOP: DEPLOY CHECK
Target: current working tree vs main branch
Deployment target: Render (uvicorn main:app)

Cycle (AUDIT ONLY — make zero edits):
1. SCAN Python files for:
   - print() debug statements left in production paths
   - hardcoded localhost:8000 or 127.0.0.1 URLs
   - commented-out debug blocks (# DEBUG, # TEMP, # TODO)
   - bare except: clauses with pass

2. SCAN JS/templates for:
   - console.log() calls not inside error handlers
   - hardcoded API URLs (should use relative paths or env vars)

3. CHECK routes — for every new endpoint in routers/:
   - Has HTTPException error handling for client errors
   - Returns typed response (not bare dict)

4. CHECK migrations:
   - alembic/versions/ — any new migration files?
   - If yes: confirm REQUIRED_DB_VERSION in main.py is updated to match.

5. CHECK clinical safety:
   - Any new code path that writes session records calls validation_engine.py?
   - Any new alert logic consistent with KDIGO rules in alerts.py?

6. CHECK environment:
   - List any new os.getenv() calls. Are these documented for Render?

7. OUTPUT — a pass/fail report:
   [ PASS / FAIL ] Debug artifacts
   [ PASS / FAIL ] Hardcoded URLs
   [ PASS / FAIL ] Error handling on new routes
   [ PASS / FAIL ] Migration + DB version alignment
   [ PASS / FAIL ] Clinical validation gates
   [ PASS / FAIL ] New env vars documented

   If all PASS: remind me to run `pytest` and `npm run build` locally before pushing.
   If any FAIL: list each failure with the exact file and line number.
```

---

## 🔵 LOOP: MIGRATION

**Trigger:** Adding a new DB column, table, or index.

```
LOOP: MIGRATION
Change: [describe the schema change, e.g. "add esa_modified_at to MonthlyRecord"]
Model file: db/models/records.py  (or relevant model file)

Cycle:
1. READ — review the existing model and the most recent alembic version file.
2. PLAN — show the column definition to be added to the SQLAlchemy model.
   Do not edit yet.
3. WAIT — I confirm the plan.
4. IMPLEMENT in this exact order:
   a. Add column to db/models/records.py (SQLAlchemy model)
   b. Generate migration stub manually (do NOT run alembic autogenerate
      against live DB — write the upgrade/downgrade SQL by hand)
   c. Update REQUIRED_DB_VERSION in main.py to match new head
5. VERIFY — show me the final migration file upgrade() and downgrade()
   functions before we consider this complete.
6. REMIND — after merge, deployment runs `python scripts/pre_deploy.py`
   which calls alembic upgrade head. Confirm this is sufficient.

Hard constraint: never run `alembic revision --autogenerate` against
a live database in this environment.
```

---

## Quick Reference

| Situation | Say to Claude |
|---|---|
| Something broke | `Enter DEBUG LOOP — target: [X], error: [paste]` |
| Building something new | `Enter FEATURE LOOP — feature: [description]` |
| About to push | `Run DEPLOY CHECK on current state` |
| DB schema change | `Enter MIGRATION LOOP — change: [description]` |
| Loop is stuck | `Summarise loop state and surface blockers` |
| Override a constraint | `OVERRIDE: [reason] — then continue loop` |
| Protect a file mid-loop | `Add [filename] to protected list for this session` |
