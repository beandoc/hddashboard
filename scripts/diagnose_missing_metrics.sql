-- ============================================================
-- Diagnostic: Why HBsAg/HCV/HIV, Transplant Prospects, and
-- Cadaveric Waitlist show 0 on the dashboard
-- Run each block in the Supabase SQL Editor.
-- ============================================================

-- 1. Confirm active patient count
SELECT COUNT(*) AS active_patients FROM patients WHERE is_active = true;

-- 2. How many active patients have a row in patient_viral_markers?
SELECT
    (SELECT COUNT(*) FROM patients WHERE is_active = true) AS active_patients,
    (SELECT COUNT(*) FROM patient_viral_markers vm
        JOIN patients p ON p.id = vm.patient_id WHERE p.is_active = true) AS have_viral_row,
    (SELECT COUNT(*) FROM patients p WHERE p.is_active = true
        AND NOT EXISTS (SELECT 1 FROM patient_viral_markers vm WHERE vm.patient_id = p.id)) AS missing_viral_row;

-- 3. Among patients who DO have a viral row — what values are actually stored?
SELECT
    viral_hbsag,
    viral_anti_hcv,
    viral_hiv,
    COUNT(*) AS n
FROM patient_viral_markers vm
JOIN patients p ON p.id = vm.patient_id AND p.is_active = true
GROUP BY viral_hbsag, viral_anti_hcv, viral_hiv
ORDER BY n DESC
LIMIT 30;

-- 4. How many have any 'positive' (case-insensitive) in any viral marker?
SELECT COUNT(*) AS infectious_count
FROM patient_viral_markers vm
JOIN patients p ON p.id = vm.patient_id AND p.is_active = true
WHERE
    LOWER(COALESCE(vm.viral_hbsag, '')) LIKE '%positive%'
    OR LOWER(COALESCE(vm.viral_anti_hcv, '')) LIKE '%positive%'
    OR LOWER(COALESCE(vm.viral_hiv, '')) LIKE '%positive%';

-- 5. How many active patients have a row in patient_renal_profile?
SELECT
    (SELECT COUNT(*) FROM patients WHERE is_active = true) AS active_patients,
    (SELECT COUNT(*) FROM patient_renal_profile rp
        JOIN patients p ON p.id = rp.patient_id WHERE p.is_active = true) AS have_renal_row,
    (SELECT COUNT(*) FROM patients p WHERE p.is_active = true
        AND NOT EXISTS (SELECT 1 FROM patient_renal_profile rp WHERE rp.patient_id = p.id)) AS missing_renal_row;

-- 6. What transplant_prospect values are stored?
SELECT
    COALESCE(transplant_prospect, '(null)') AS transplant_prospect,
    COUNT(*) AS n
FROM patient_renal_profile rp
JOIN patients p ON p.id = rp.patient_id AND p.is_active = true
GROUP BY transplant_prospect
ORDER BY n DESC;

-- 7. How many match the dashboard criteria?
SELECT
    COUNT(*) FILTER (WHERE rp.transplant_prospect IN ('Active','Listed','Inactive')) AS transplant_prospects,
    COUNT(*) FILTER (WHERE rp.transplant_prospect = 'Listed') AS cadaveric_waitlist
FROM patient_renal_profile rp
JOIN patients p ON p.id = rp.patient_id AND p.is_active = true;

-- 8. Check migration ran — does alembic_version include 0002?
SELECT version_num FROM alembic_version;
