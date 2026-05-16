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
    "hb":                      "hb",
    "albumin":                 "albumin",
    "phosphorus":              "phosphorus",
    "calcium":                 "calcium",
    "alkaline_phosphate":      "alkaline_phosphate",
    "ipth":                    "ipth",
    "vit_d":                   "vit_d",
    "ferritin":                "serum_ferritin",
    "tsat":                    "tsat",
    "serum_iron":              "serum_iron",
    "tibc":                    "tibc",
    "urr":                     "urr",
    "kt_v":                    "single_pool_ktv",
    "bicarbonate":             "serum_bicarbonate",
    "uric_acid":               "serum_uric_acid",
    "creatinine":              "serum_creatinine",
    "sodium":                  "serum_sodium",
    "potassium":               "serum_potassium",
    "crp":                     "crp",
    "systolic_bp_pre":         "bp_sys",
    "idwg":                    "idwg",
    "dry_weight":              "target_dry_weight",
    "nt_probnp":               "nt_probnp",
    "ef":                      "ejection_fraction",
    "wbc":                     "wbc_count",
    "platelets":               "platelet_count",
}
