# Clinical Event Types
EVENT_TYPES = [
    "Admission", "Infection", "Access Issue", "Cardiovascular", "Surgery", 
    "Transfusion", "Other", "Mortality", "Transplant", "Transfer"
]

EVENT_TYPE_GROUPS = [
    ("Intradialytic Complications", [
        "Intradialytic Hypotension",
        "Fever / Rigors",
        "Cramps",
        "Nausea / Vomiting",
        "Chest Pain",
        "Headache / Dizziness",
        "Needle Dislodgement",
        "Circuit Clot / Clotted Lines",
        "Air Embolism",
        "Cardiac Arrest",
        "Seizure",
        "Anaphylaxis / Allergic Reaction",
    ]),
    ("Vascular Access", [
        "Access Thrombosis",
        "AV Fistula Revision",
        "AV Fistula Failure",
        "Catheter Change",
        "Catheter / Exit-Site Infection",
    ]),
    ("Systemic / Hospitalizations", [
        "Hospitalization",
        "Fluid Overload",
        "Blood Transfusion",
        "Sepsis / Bacteremia",
        "Cardiac Event",
        "EPO Hyporesponse",
    ]),
    ("Administrative", [
        "Missed Sessions",
        "Transfer",
        "Transplant",
        "Fall / Injury",
        "Death",
        "Other",
    ]),
]

# Variable Manager Mappings
VAR_TO_MONTHLY = {
    "uric_acid":               "serum_uric_acid",
    "crp":                     "crp",
    "kt_v":                    "single_pool_ktv",
    "bicarbonate":             "serum_bicarbonate",
    "systolic_bp_pre":         "bp_sys",
    "blood_transfusion_units": None,
    "intradialytic_hypotension": None,
}
