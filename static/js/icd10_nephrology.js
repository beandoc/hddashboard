/**
 * ICD-10-CM / ICD-10 (WHO) codes — Nephrology & Hemodialysis
 * Curated for HD unit use: renal diagnoses, HD complications, comorbidities,
 * procedure encounter codes, electrolyte disorders, infections, cardiac.
 *
 * Each entry: { code, label, synonyms, category, chapter }
 * synonyms: lowercase search terms a clinician would actually type
 */
window.ICD10_NEPHROLOGY = [

  // ─────────────────────────────────────────────────────────────────────────
  // CHRONIC KIDNEY DISEASE
  // ─────────────────────────────────────────────────────────────────────────
  { code:"N18.1",  label:"CKD Stage 1",                                     synonyms:["ckd1","chronic kidney disease stage 1","ckd stage 1"],                                  category:"CKD", chapter:"Renal" },
  { code:"N18.2",  label:"CKD Stage 2 (mild)",                              synonyms:["ckd2","ckd stage 2","mild ckd"],                                                         category:"CKD", chapter:"Renal" },
  { code:"N18.3",  label:"CKD Stage 3 (moderate)",                          synonyms:["ckd3","ckd stage 3","moderate ckd"],                                                      category:"CKD", chapter:"Renal" },
  { code:"N18.31", label:"CKD Stage 3a",                                    synonyms:["ckd 3a","stage 3a"],                                                                     category:"CKD", chapter:"Renal" },
  { code:"N18.32", label:"CKD Stage 3b",                                    synonyms:["ckd 3b","stage 3b"],                                                                     category:"CKD", chapter:"Renal" },
  { code:"N18.4",  label:"CKD Stage 4 (severe)",                            synonyms:["ckd4","ckd stage 4","severe ckd"],                                                        category:"CKD", chapter:"Renal" },
  { code:"N18.5",  label:"CKD Stage 5",                                     synonyms:["ckd5","ckd stage 5","pre-dialysis","esrd pre-dialysis"],                                  category:"CKD", chapter:"Renal" },
  { code:"N18.6",  label:"End Stage Renal Disease (ESRD) on dialysis",      synonyms:["esrd","end stage renal disease","ckd5d","dialysis dependent","renal failure dialysis"],   category:"CKD", chapter:"Renal" },
  { code:"N18.9",  label:"CKD unspecified",                                 synonyms:["ckd unspecified","chronic kidney disease nos"],                                           category:"CKD", chapter:"Renal" },

  // ─────────────────────────────────────────────────────────────────────────
  // PRIMARY RENAL DISEASES (Causes of CKD)
  // ─────────────────────────────────────────────────────────────────────────
  { code:"N02.9",  label:"Recurrent & persistent haematuria",               synonyms:["haematuria","hematuria","blood in urine","microscopic haematuria"],                       category:"Primary Renal", chapter:"Renal" },
  { code:"N03.9",  label:"Chronic nephritic syndrome, unspecified",         synonyms:["chronic nephritic","nephritic syndrome","chronic glomerulonephritis"],                    category:"Primary Renal", chapter:"Renal" },
  { code:"N04.9",  label:"Nephrotic syndrome, unspecified",                 synonyms:["nephrotic syndrome","heavy proteinuria","hypoalbuminaemia nephrotic","oedema nephrotic"], category:"Primary Renal", chapter:"Renal" },
  { code:"N04.0",  label:"Nephrotic syndrome — minimal change disease",     synonyms:["minimal change","mcns","minimal change nephrotic","lipoid nephrosis"],                   category:"Primary Renal", chapter:"Renal" },
  { code:"N04.2",  label:"Nephrotic syndrome — focal segmental glomerulosclerosis", synonyms:["fsgs","focal segmental","focal glomerulosclerosis"],                             category:"Primary Renal", chapter:"Renal" },
  { code:"N04.3",  label:"Nephrotic syndrome — diffuse mesangial proliferative GN", synonyms:["mesangial proliferative","diffuse mesangial"],                                   category:"Primary Renal", chapter:"Renal" },
  { code:"N04.4",  label:"Nephrotic syndrome — diffuse endocapillary proliferative GN", synonyms:["endocapillary proliferative","post-streptococcal"],                          category:"Primary Renal", chapter:"Renal" },
  { code:"N04.5",  label:"Nephrotic syndrome — diffuse mesangiocapillary GN", synonyms:["membranoproliferative","mpgn","mesangiocapillary"],                                    category:"Primary Renal", chapter:"Renal" },
  { code:"N04.6",  label:"Nephrotic syndrome — dense deposit disease",      synonyms:["dense deposit","c3 glomerulopathy","c3gn"],                                              category:"Primary Renal", chapter:"Renal" },
  { code:"N05.9",  label:"Unspecified nephritic syndrome",                  synonyms:["unspecified nephritic","gn nos","glomerulonephritis nos"],                                category:"Primary Renal", chapter:"Renal" },
  { code:"N06.9",  label:"Isolated proteinuria with unspecified morphological lesion", synonyms:["isolated proteinuria","proteinuria nos"],                                     category:"Primary Renal", chapter:"Renal" },
  { code:"N07.9",  label:"Hereditary nephropathy",                          synonyms:["hereditary nephropathy","alport syndrome","alports","thin basement membrane"],           category:"Primary Renal", chapter:"Renal" },
  { code:"N10",    label:"Acute pyelonephritis",                            synonyms:["pyelonephritis","uti upper tract","kidney infection","acute pyelonephritis"],             category:"Primary Renal", chapter:"Renal" },
  { code:"N11.9",  label:"Chronic tubulo-interstitial nephritis",           synonyms:["chronic interstitial nephritis","tubulo-interstitial nephritis","cin"],                  category:"Primary Renal", chapter:"Renal" },
  { code:"N13.30", label:"Unspecified hydronephrosis",                      synonyms:["hydronephrosis","pelviureteric junction obstruction","puj obstruction"],                  category:"Primary Renal", chapter:"Renal" },
  { code:"N14.1",  label:"Nephropathy induced by other drugs",              synonyms:["drug nephropathy","nsaid nephropathy","contrast nephropathy","analgesic nephropathy"],    category:"Primary Renal", chapter:"Renal" },
  { code:"N15.1",  label:"Renal & perinephric abscess",                     synonyms:["renal abscess","perinephric abscess","perirenal abscess"],                               category:"Primary Renal", chapter:"Renal" },
  { code:"N20.0",  label:"Calculus of kidney (nephrolithiasis)",            synonyms:["kidney stone","renal calculus","nephrolithiasis","urolithiasis"],                         category:"Primary Renal", chapter:"Renal" },
  { code:"N20.1",  label:"Calculus of ureter",                              synonyms:["ureteric stone","ureteric calculus","ureterolithiasis"],                                 category:"Primary Renal", chapter:"Renal" },
  { code:"N26.9",  label:"Renal fibrosis / small kidneys",                  synonyms:["small kidneys","renal fibrosis","bilateral small kidneys","chronic scarred kidneys"],    category:"Primary Renal", chapter:"Renal" },
  { code:"N28.0",  label:"Ischaemic nephropathy / renal artery stenosis",   synonyms:["ischaemic nephropathy","renovascular hypertension","renal artery stenosis","ras"],       category:"Primary Renal", chapter:"Renal" },

  // ─────────────────────────────────────────────────────────────────────────
  // GLOMERULAR DISEASE — SECONDARY
  // ─────────────────────────────────────────────────────────────────────────
  { code:"M32.14", label:"Lupus nephritis",                                 synonyms:["lupus nephritis","sle nephritis","lupus kidney","systemic lupus nephritis"],             category:"Glomerular", chapter:"Renal" },
  { code:"M31.31", label:"Wegener's granulomatosis (GPA) with renal involvement", synonyms:["wegeners","gpa","anca vasculitis","granulomatosis polyangiitis"],                  category:"Glomerular", chapter:"Renal" },
  { code:"M31.7",  label:"Microscopic polyangiitis",                        synonyms:["mpa","microscopic polyangiitis","anca mpa","pauci-immune"],                              category:"Glomerular", chapter:"Renal" },
  { code:"N08",    label:"Glomerular disorders in diseases classified elsewhere", synonyms:["secondary glomerulonephritis","glomerular disease secondary"],                     category:"Glomerular", chapter:"Renal" },
  { code:"N08*",   label:"Diabetic nephropathy",                            synonyms:["diabetic nephropathy","diabetic kidney disease","diabetic ckd","dkd"],                   category:"Glomerular", chapter:"Renal" },
  { code:"D59.3",  label:"Haemolytic uraemic syndrome (HUS)",               synonyms:["hus","haemolytic uraemic syndrome","atypical hus","ahus"],                               category:"Glomerular", chapter:"Renal" },
  { code:"D69.0",  label:"Thrombotic thrombocytopenic purpura (TTP)",       synonyms:["ttp","thrombotic thrombocytopenic purpura","microangiopathy"],                           category:"Glomerular", chapter:"Renal" },
  { code:"E85.3",  label:"Secondary systemic amyloidosis — renal",          synonyms:["amyloidosis","renal amyloid","aa amyloidosis","al amyloidosis"],                         category:"Glomerular", chapter:"Renal" },
  { code:"B02.21", label:"Post-infectious glomerulonephritis",              synonyms:["post streptococcal gn","post-infectious gn","psgn","iggn"],                              category:"Glomerular", chapter:"Renal" },

  // ─────────────────────────────────────────────────────────────────────────
  // ACUTE KIDNEY INJURY
  // ─────────────────────────────────────────────────────────────────────────
  { code:"N17.0",  label:"Acute kidney injury with tubular necrosis (ATN)", synonyms:["aki","acute kidney injury","atn","acute tubular necrosis","acute renal failure"],        category:"AKI", chapter:"Renal" },
  { code:"N17.1",  label:"AKI with acute cortical necrosis",                synonyms:["cortical necrosis","bilateral cortical necrosis"],                                       category:"AKI", chapter:"Renal" },
  { code:"N17.2",  label:"AKI with medullary necrosis",                     synonyms:["medullary necrosis","papillary necrosis"],                                               category:"AKI", chapter:"Renal" },
  { code:"N17.8",  label:"AKI — other",                                     synonyms:["aki other","acute renal failure other"],                                                 category:"AKI", chapter:"Renal" },
  { code:"N17.9",  label:"AKI unspecified",                                 synonyms:["aki nos","acute kidney injury unspecified","acute renal failure nos"],                   category:"AKI", chapter:"Renal" },
  { code:"N19",    label:"Unspecified kidney failure",                       synonyms:["renal failure","kidney failure","uraemia"],                                              category:"AKI", chapter:"Renal" },

  // ─────────────────────────────────────────────────────────────────────────
  // DIALYSIS — ENCOUNTER & PROCEDURE CODES
  // ─────────────────────────────────────────────────────────────────────────
  { code:"Z49.01", label:"Encounter for fitting extracorporeal dialysis catheter", synonyms:["hd catheter","tunnelled catheter insertion","permcath","fitting dialysis catheter","avf creation encounter"], category:"Dialysis Encounter", chapter:"Renal" },
  { code:"Z49.02", label:"Encounter for fitting peritoneal dialysis catheter (CAPD)", synonyms:["capd catheter","peritoneal catheter","pd catheter insertion","z49.02"],         category:"Dialysis Encounter", chapter:"Renal" },
  { code:"Z49.31", label:"Adequacy testing for haemodialysis",              synonyms:["adequacy testing","ktv measurement","hd adequacy","dialysis adequacy"],                  category:"Dialysis Encounter", chapter:"Renal" },
  { code:"Z49.32", label:"Adequacy testing for peritoneal dialysis",        synonyms:["pd adequacy","peritoneal equilibration test","pet test"],                                category:"Dialysis Encounter", chapter:"Renal" },
  { code:"Z99.2",  label:"Dependence on renal dialysis",                    synonyms:["on dialysis","dialysis dependent","maintenance haemodialysis","long-term haemodialysis"], category:"Dialysis Encounter", chapter:"Renal" },

  // ─────────────────────────────────────────────────────────────────────────
  // FLUID OVERLOAD / PULMONARY
  // ─────────────────────────────────────────────────────────────────────────
  { code:"J81.0",  label:"Acute pulmonary oedema",                          synonyms:["apo","acute pulmonary oedema","acute pulmonary edema","flash oedema","flash pulmonary"],  category:"Fluid Overload", chapter:"Cardiorespiratory" },
  { code:"J81.1",  label:"Chronic pulmonary oedema",                        synonyms:["chronic pulmonary oedema","chronic pulmonary edema"],                                    category:"Fluid Overload", chapter:"Cardiorespiratory" },
  { code:"R60.0",  label:"Localised oedema",                                synonyms:["leg oedema","ankle swelling","peripheral oedema","pitting oedema"],                      category:"Fluid Overload", chapter:"Cardiorespiratory" },
  { code:"R60.1",  label:"Generalised oedema (anasarca)",                   synonyms:["anasarca","generalised oedema","total body oedema","volume overload"],                   category:"Fluid Overload", chapter:"Cardiorespiratory" },
  { code:"E87.70", label:"Fluid overload, unspecified",                     synonyms:["fluid overload","hypervolaemia","volume overload","fluid retention"],                    category:"Fluid Overload", chapter:"Cardiorespiratory" },
  { code:"J90",    label:"Pleural effusion",                                 synonyms:["pleural effusion","pleural fluid","hydrothorax"],                                        category:"Fluid Overload", chapter:"Cardiorespiratory" },
  { code:"R18.0",  label:"Malignant ascites",                               synonyms:["ascites","abdominal fluid","peritoneal fluid"],                                          category:"Fluid Overload", chapter:"Cardiorespiratory" },

  // ─────────────────────────────────────────────────────────────────────────
  // CARDIAC
  // ─────────────────────────────────────────────────────────────────────────
  { code:"I50.20", label:"Systolic heart failure, unspecified",             synonyms:["systolic heart failure","reduced ef","hfref","lv dysfunction"],                          category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I50.30", label:"Diastolic heart failure, unspecified",            synonyms:["diastolic heart failure","hfpef","preserved ef","diastolic dysfunction"],                category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I50.9",  label:"Heart failure, unspecified (CCF)",                synonyms:["ccf","cardiac failure","congestive cardiac failure","heart failure","chf"],              category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I21.9",  label:"Acute myocardial infarction, unspecified",        synonyms:["mi","heart attack","ami","myocardial infarction","nstemi","stemi"],                      category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I21.3",  label:"STEMI — unspecified site",                        synonyms:["stemi","st elevation mi","st elevation myocardial infarction"],                          category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I21.4",  label:"NSTEMI",                                          synonyms:["nstemi","non-st elevation mi","non st elevation myocardial infarction"],                 category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I20.0",  label:"Unstable angina",                                 synonyms:["unstable angina","acs","acute coronary syndrome","crescendo angina"],                    category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I25.10", label:"Coronary artery disease",                         synonyms:["cad","coronary artery disease","ischaemic heart disease","ihd"],                         category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I48.0",  label:"Paroxysmal atrial fibrillation",                  synonyms:["paroxysmal af","paf","intermittent atrial fibrillation"],                                category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I48.11", label:"Longstanding persistent atrial fibrillation",     synonyms:["persistent af","longstanding af","atrial fibrillation persistent"],                     category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I48.20", label:"Chronic atrial fibrillation",                     synonyms:["chronic af","permanent af","atrial fibrillation","af"],                                  category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I49.9",  label:"Cardiac arrhythmia, unspecified",                 synonyms:["arrhythmia","cardiac arrhythmia","palpitations","irregular heartbeat"],                  category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I10",    label:"Essential hypertension",                          synonyms:["hypertension","high blood pressure","htn","bp elevated"],                                category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I11.0",  label:"Hypertensive heart disease with heart failure",   synonyms:["hypertensive heart failure","hypertensive cardiac failure"],                            category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I12.9",  label:"Hypertensive CKD without heart failure",          synonyms:["hypertensive nephrosclerosis","hypertensive renal disease","hypertensive ckd"],          category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I13.10", label:"Hypertensive heart and CKD",                      synonyms:["hypertensive cardiorenal","cardiorenal syndrome","hypertensive heart ckd"],              category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I34.0",  label:"Mitral regurgitation",                            synonyms:["mitral regurgitation","mr","mitral incompetence","mitral valve regurgitation"],          category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I35.0",  label:"Aortic stenosis",                                 synonyms:["aortic stenosis","as","calcific aortic stenosis","aortic valve stenosis"],               category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I42.0",  label:"Dilated cardiomyopathy",                          synonyms:["dilated cardiomyopathy","dcm","lv dilation","cardiomegaly dilated"],                     category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I42.9",  label:"Cardiomyopathy, unspecified",                     synonyms:["cardiomyopathy","cardiac myopathy","uraemic cardiomyopathy"],                            category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I26.09", label:"Pulmonary embolism without acute cor pulmonale",  synonyms:["pe","pulmonary embolism","pulmonary thromboembolism","dvt pe"],                          category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"R00.1",  label:"Bradycardia",                                     synonyms:["bradycardia","slow heart rate","heart block","low pulse"],                               category:"Cardiac", chapter:"Cardiorespiratory" },

  // ─────────────────────────────────────────────────────────────────────────
  // HYPERTENSIVE EMERGENCIES
  // ─────────────────────────────────────────────────────────────────────────
  { code:"I16.0",  label:"Hypertensive urgency",                            synonyms:["hypertensive urgency","severe hypertension","bp crisis"],                                category:"Hypertension", chapter:"Cardiorespiratory" },
  { code:"I16.1",  label:"Hypertensive emergency",                          synonyms:["hypertensive emergency","malignant hypertension","hypertensive crisis","accelerated hypertension"], category:"Hypertension", chapter:"Cardiorespiratory" },
  { code:"I16.9",  label:"Hypertensive crisis, unspecified",                synonyms:["hypertensive crisis","uncontrolled hypertension","hypertension emergency nos"],          category:"Hypertension", chapter:"Cardiorespiratory" },

  // ─────────────────────────────────────────────────────────────────────────
  // ELECTROLYTE & METABOLIC DISORDERS
  // ─────────────────────────────────────────────────────────────────────────
  { code:"E87.5",  label:"Hyperkalaemia",                                   synonyms:["hyperkalemia","hyperkalaemia","high potassium","raised k","k+ high","serum potassium high"], category:"Electrolyte", chapter:"Metabolic" },
  { code:"E87.6",  label:"Hypokalaemia",                                    synonyms:["hypokalaemia","hypokalemia","low potassium","low k","k+ low"],                            category:"Electrolyte", chapter:"Metabolic" },
  { code:"E87.0",  label:"Hyperosmolality / hypernatraemia",                synonyms:["hypernatraemia","hypernatremia","high sodium","raised sodium","na+ high"],               category:"Electrolyte", chapter:"Metabolic" },
  { code:"E87.1",  label:"Hypo-osmolality / hyponatraemia",                 synonyms:["hyponatraemia","hyponatremia","low sodium","dilutional hyponatraemia","siadh"],           category:"Electrolyte", chapter:"Metabolic" },
  { code:"E83.52", label:"Hypercalcaemia",                                  synonyms:["hypercalcaemia","hypercalcemia","high calcium","raised calcium","ca high"],               category:"Electrolyte", chapter:"Metabolic" },
  { code:"E83.51", label:"Hypocalcaemia",                                   synonyms:["hypocalcaemia","hypocalcemia","low calcium","low ca","tetany","ca low"],                  category:"Electrolyte", chapter:"Metabolic" },
  { code:"E83.39", label:"Hyperphosphataemia",                              synonyms:["hyperphosphataemia","hyperphosphatemia","high phosphorus","raised phosphate","phosphate high"], category:"Electrolyte", chapter:"Metabolic" },
  { code:"E83.30", label:"Hypophosphataemia",                               synonyms:["hypophosphataemia","hypophosphatemia","low phosphate","low phosphorus"],                  category:"Electrolyte", chapter:"Metabolic" },
  { code:"E87.2",  label:"Metabolic acidosis",                              synonyms:["metabolic acidosis","bicarbonate low","acidaemia","low bicarb"],                          category:"Electrolyte", chapter:"Metabolic" },
  { code:"E87.3",  label:"Metabolic alkalosis",                             synonyms:["metabolic alkalosis","bicarbonate high","alkalosis"],                                    category:"Electrolyte", chapter:"Metabolic" },
  { code:"N25.81", label:"Secondary hyperparathyroidism of renal origin",   synonyms:["secondary hyperparathyroidism","shpt","renal osteodystrophy","high pth","ipth elevated"],category:"Electrolyte", chapter:"Metabolic" },
  { code:"M83.3",  label:"Renal osteodystrophy",                            synonyms:["renal osteodystrophy","renal bone disease","ckd-mbd"],                                   category:"Electrolyte", chapter:"Metabolic" },
  { code:"E55.9",  label:"Vitamin D deficiency",                            synonyms:["vitamin d deficiency","vit d low","25-ohd low","cholecalciferol deficiency"],             category:"Electrolyte", chapter:"Metabolic" },
  { code:"E83.10", label:"Hypomagnesaemia",                                 synonyms:["hypomagnesaemia","hypomagnesemia","low magnesium","low mg"],                             category:"Electrolyte", chapter:"Metabolic" },

  // ─────────────────────────────────────────────────────────────────────────
  // ANAEMIA / HAEMATOLOGY
  // ─────────────────────────────────────────────────────────────────────────
  { code:"D63.1",  label:"Anaemia in chronic kidney disease",               synonyms:["ckd anaemia","renal anaemia","anaemia of ckd","epo deficiency anaemia","low hb ckd"],     category:"Anaemia", chapter:"Haematology" },
  { code:"D50.9",  label:"Iron deficiency anaemia",                         synonyms:["iron deficiency anaemia","ida","iron deficiency","iron deficient","ferritin low"],        category:"Anaemia", chapter:"Haematology" },
  { code:"D51.9",  label:"Vitamin B12 deficiency anaemia",                  synonyms:["b12 deficiency","b12 anaemia","vitamin b12 low","cobalamin deficiency"],                  category:"Anaemia", chapter:"Haematology" },
  { code:"D52.9",  label:"Folate deficiency anaemia",                       synonyms:["folate deficiency","folic acid deficiency","folate anaemia"],                             category:"Anaemia", chapter:"Haematology" },
  { code:"D56.9",  label:"Thalassaemia, unspecified",                       synonyms:["thalassaemia","thalassemia","thal","haemoglobin disorder"],                               category:"Anaemia", chapter:"Haematology" },
  { code:"D64.9",  label:"Anaemia, unspecified",                            synonyms:["anaemia","anemia","low haemoglobin","low hgb","low hb","anaemia nos"],                    category:"Anaemia", chapter:"Haematology" },
  { code:"D89.1",  label:"Cryoglobulinaemia",                               synonyms:["cryoglobulinaemia","cryoglobulinemia","mixed cryoglobulinemia"],                          category:"Anaemia", chapter:"Haematology" },
  { code:"T45.1X5A","label":"Adverse effect of antineoplastic drugs — EPO hyporesponse", synonyms:["epo hyporesponse","epo resistance","esa hyporesponse","epoetin resistance"], category:"Anaemia", chapter:"Haematology" },
  { code:"D68.9",  label:"Coagulation defect, unspecified",                 synonyms:["coagulopathy","bleeding disorder","coagulation defect","platelet dysfunction"],           category:"Anaemia", chapter:"Haematology" },
  { code:"K92.1",  label:"Melaena / GI bleeding",                           synonyms:["gi bleed","melaena","melena","haematemesis","upper gi bleed","lower gi bleed","rectal bleed"], category:"Anaemia", chapter:"Haematology" },

  // ─────────────────────────────────────────────────────────────────────────
  // INFECTION / SEPSIS
  // ─────────────────────────────────────────────────────────────────────────
  { code:"A41.9",  label:"Sepsis, unspecified organism",                    synonyms:["sepsis","blood infection","bacteremia","bacteraemia","septicaemia","septicemia"],         category:"Infection", chapter:"Infection" },
  { code:"A41.01", label:"Sepsis due to MSSA",                              synonyms:["mssa sepsis","staphylococcal sepsis","staph aureus sepsis","mrsa sepsis"],                category:"Infection", chapter:"Infection" },
  { code:"A41.02", label:"Sepsis due to MRSA",                              synonyms:["mrsa","mrsa sepsis","methicillin resistant staph aureus"],                               category:"Infection", chapter:"Infection" },
  { code:"A41.3",  label:"Sepsis due to Haemophilus influenzae",            synonyms:["haemophilus sepsis","haemophilus influenzae"],                                           category:"Infection", chapter:"Infection" },
  { code:"A41.4",  label:"Sepsis due to anaerobes",                         synonyms:["anaerobic sepsis","clostridium sepsis"],                                                 category:"Infection", chapter:"Infection" },
  { code:"A41.51", label:"Sepsis due to Escherichia coli",                  synonyms:["e coli sepsis","ecoli sepsis","gram negative sepsis e coli"],                            category:"Infection", chapter:"Infection" },
  { code:"A41.52", label:"Sepsis due to Pseudomonas",                       synonyms:["pseudomonas sepsis","pseudomonal sepsis","gram negative pseudomonas"],                    category:"Infection", chapter:"Infection" },
  { code:"A41.59", label:"Sepsis due to other gram-negative organisms",     synonyms:["gram negative sepsis","klebsiella sepsis","gram-negative bacteraemia"],                  category:"Infection", chapter:"Infection" },
  { code:"T82.7XXA","label":"Infection of vascular prosthetic device (access)", synonyms:["avf infection","avg infection","catheter infection","line infection","access infection","tcc infection","fistula infection"], category:"Infection", chapter:"Infection" },
  { code:"T80.211",  label:"CRBSI — Bloodstream infection due to central venous catheter", synonyms:["crbsi","catheter related bloodstream infection","catheter related blood stream infection","line sepsis","central line infection","permcath sepsis","tcc sepsis","tunnelled catheter sepsis","haemodialysis catheter infection","dialysis line infection","line-related bacteraemia","clabsi","t80.211"], category:"Infection", chapter:"Infection" },
  { code:"T80.211A", label:"CRBSI — initial encounter (T80.211A)",                         synonyms:["crbsi initial","crbsi acute","t80.211a","bloodstream infection central line initial"], category:"Infection", chapter:"Infection" },
  { code:"T80.211D", label:"CRBSI — subsequent encounter (T80.211D)",                       synonyms:["crbsi subsequent","t80.211d","bloodstream infection central line subsequent"],       category:"Infection", chapter:"Infection" },
  { code:"T80.211S", label:"CRBSI — sequela (T80.211S)",                                    synonyms:["crbsi sequela","t80.211s","bloodstream infection central line sequela"],            category:"Infection", chapter:"Infection" },
  { code:"J18.9",  label:"Pneumonia, unspecified organism",                 synonyms:["pneumonia","chest infection","lrti","lower respiratory tract infection","lung infection"],category:"Infection", chapter:"Infection" },
  { code:"J18.1",  label:"Lobar pneumonia",                                 synonyms:["lobar pneumonia","consolidation","lobar consolidation"],                                 category:"Infection", chapter:"Infection" },
  { code:"J06.9",  label:"Acute upper respiratory infection (URTI)",        synonyms:["urti","upper respiratory infection","cold","pharyngitis","uri"],                         category:"Infection", chapter:"Infection" },
  { code:"N39.0",  label:"Urinary tract infection",                         synonyms:["uti","urinary tract infection","cystitis","urine infection","urosepsis"],                 category:"Infection", chapter:"Infection" },
  { code:"N10",    label:"Acute pyelonephritis",                            synonyms:["pyelonephritis","kidney infection","upper uti","uti with fever"],                        category:"Infection", chapter:"Infection" },
  { code:"B18.1",  label:"Chronic viral hepatitis B",                       synonyms:["hepatitis b","hbv","hbsag positive","chronic hep b"],                                    category:"Infection", chapter:"Infection" },
  { code:"B18.2",  label:"Chronic viral hepatitis C",                       synonyms:["hepatitis c","hcv","anti-hcv positive","chronic hep c","hcv positive"],                  category:"Infection", chapter:"Infection" },
  { code:"B20",    label:"HIV disease",                                     synonyms:["hiv","aids","hiv positive","retroviral disease"],                                        category:"Infection", chapter:"Infection" },
  { code:"A04.7",  label:"Enterocolitis due to Clostridioides difficile",   synonyms:["c diff","c difficile","cdiff","clostridium difficile","cdad"],                            category:"Infection", chapter:"Infection" },
  { code:"L03.90", label:"Cellulitis, unspecified",                         synonyms:["cellulitis","skin infection","soft tissue infection","wound infection"],                  category:"Infection", chapter:"Infection" },

  // ─────────────────────────────────────────────────────────────────────────
  // VASCULAR ACCESS COMPLICATIONS
  // ─────────────────────────────────────────────────────────────────────────
  { code:"T82.898A","label":"Other complication of vascular prosthetic devices", synonyms:["avf complication","fistula complication","avf stenosis","graft complication"],       category:"Vascular Access", chapter:"Vascular" },
  { code:"T82.818A","label":"Breakdown of vascular prosthetic device (thrombosis)", synonyms:["avf thrombosis","graft thrombosis","fistula clot","access thrombosis","avf clot"], category:"Vascular Access", chapter:"Vascular" },
  { code:"T82.7XXA","label":"Infection of vascular prosthetic device",      synonyms:["access site infection","exit site infection","catheter exit site","tcc exit site"],       category:"Vascular Access", chapter:"Vascular" },
  { code:"I77.1",  label:"Stricture of artery (AVF stenosis)",              synonyms:["avf stenosis","fistula stenosis","access stenosis","anastomotic stenosis","juxta anastomotic stenosis"], category:"Vascular Access", chapter:"Vascular" },
  { code:"I82.40", label:"Acute venous thrombosis, unspecified deep vein",  synonyms:["dvt","deep vein thrombosis","venous thrombosis","subclavian thrombosis","axillary thrombosis"], category:"Vascular Access", chapter:"Vascular" },
  { code:"I73.9",  label:"Peripheral vascular disease / steal syndrome",    synonyms:["steal syndrome","haemodialysis steal","ischaemia fistula","avf steal","hand ischaemia"], category:"Vascular Access", chapter:"Vascular" },
  { code:"I77.89", label:"Aneurysm of vascular access",                     synonyms:["avf aneurysm","fistula aneurysm","graft aneurysm","pseudoaneurysm access"],              category:"Vascular Access", chapter:"Vascular" },

  // ─────────────────────────────────────────────────────────────────────────
  // NEUROLOGICAL
  // ─────────────────────────────────────────────────────────────────────────
  { code:"I63.9",  label:"Cerebral infarction (Stroke / CVA)",              synonyms:["stroke","cva","cerebral infarction","ischaemic stroke","cerebrovascular accident"],      category:"Neurological", chapter:"Neurological" },
  { code:"I61.9",  label:"Intracerebral haemorrhage",                       synonyms:["ich","intracerebral haemorrhage","brain bleed","haemorrhagic stroke"],                    category:"Neurological", chapter:"Neurological" },
  { code:"G40.909","label":"Seizure / epilepsy",                            synonyms:["seizure","fit","convulsion","epilepsy","tonic clonic","generalised seizure"],             category:"Neurological", chapter:"Neurological" },
  { code:"G93.1",  label:"Anoxic brain damage",                             synonyms:["anoxic brain damage","hypoxic encephalopathy","post cardiac arrest"],                    category:"Neurological", chapter:"Neurological" },
  { code:"G93.41", label:"Metabolic encephalopathy / uraemic encephalopathy", synonyms:["uraemic encephalopathy","metabolic encephalopathy","uraemic coma","altered sensorium uraemia"], category:"Neurological", chapter:"Neurological" },
  { code:"R55",    label:"Syncope and collapse",                             synonyms:["syncope","collapse","faint","vasovagal","idh collapse","pre-syncope"],                   category:"Neurological", chapter:"Neurological" },
  { code:"G62.9",  label:"Peripheral neuropathy (uraemic)",                 synonyms:["peripheral neuropathy","uraemic neuropathy","restless legs","rls","polyneuropathy"],      category:"Neurological", chapter:"Neurological" },

  // ─────────────────────────────────────────────────────────────────────────
  // DIABETES
  // ─────────────────────────────────────────────────────────────────────────
  { code:"E11.65", label:"Type 2 DM with hyperglycaemia",                   synonyms:["diabetes hyperglycaemia","high blood sugar","hhs","hyperglycaemia","dka t2"],             category:"Diabetes", chapter:"Metabolic" },
  { code:"E11.649","label":"Type 2 DM with hypoglycaemia",                  synonyms:["hypoglycaemia","low blood sugar","hypoglycemia","low glucose","insulin reaction"],        category:"Diabetes", chapter:"Metabolic" },
  { code:"E10.10", label:"Type 1 DM with ketoacidosis",                     synonyms:["dka","diabetic ketoacidosis","type 1 dka","t1dm dka"],                                   category:"Diabetes", chapter:"Metabolic" },
  { code:"E11.22", label:"Type 2 DM with diabetic CKD",                     synonyms:["diabetic nephropathy","t2dm ckd","diabetic kidney disease","dkd"],                       category:"Diabetes", chapter:"Metabolic" },
  { code:"E11.41", label:"Type 2 DM with diabetic mononeuropathy",          synonyms:["diabetic neuropathy","peripheral neuropathy diabetes","diabetic foot"],                  category:"Diabetes", chapter:"Metabolic" },
  { code:"E11.51", label:"Type 2 DM with diabetic peripheral angiopathy",   synonyms:["diabetic peripheral vascular disease","diabetic pvd","diabetic foot ischaemia"],         category:"Diabetes", chapter:"Metabolic" },

  // ─────────────────────────────────────────────────────────────────────────
  // INTRADIALYTIC / DIALYSIS-RELATED
  // ─────────────────────────────────────────────────────────────────────────
  { code:"I95.1",  label:"Intradialytic hypotension (orthostatic)",         synonyms:["idh","intradialytic hypotension","low bp dialysis","hypotension dialysis","idh episode"],category:"Intradialytic", chapter:"Renal" },
  { code:"R73.09", label:"Post-dialysis hyperglycaemia",                    synonyms:["post dialysis hyperglycaemia","high glucose post hd"],                                   category:"Intradialytic", chapter:"Renal" },
  { code:"T80.0XXA","label":"Air embolism following infusion",              synonyms:["air embolism","venous air embolism","dialysis air embolism"],                            category:"Intradialytic", chapter:"Renal" },
  { code:"T80.89XA","label":"Other complications of infusion / dialysis",   synonyms:["dialysis complication","circuit clot","clotted lines","membrane rupture","dialyser rupture"], category:"Intradialytic", chapter:"Renal" },
  { code:"Y84.1",  label:"Kidney dialysis as cause of abnormal reaction",   synonyms:["dialysis reaction","dialyser reaction","pyrexia dialysis","fever dialysis"],             category:"Intradialytic", chapter:"Renal" },
  { code:"R25.2",  label:"Cramps",                                          synonyms:["cramps","muscle cramps","dialysis cramps","calf cramps"],                                category:"Intradialytic", chapter:"Renal" },

  // ─────────────────────────────────────────────────────────────────────────
  // TRANSPLANT
  // ─────────────────────────────────────────────────────────────────────────
  { code:"Z94.0",  label:"Kidney transplant status",                        synonyms:["renal transplant","kidney transplant","transplanted kidney","post transplant"],           category:"Transplant", chapter:"Renal" },
  { code:"T86.10", label:"Kidney transplant rejection",                     synonyms:["transplant rejection","renal graft rejection","acute rejection","chronic rejection"],     category:"Transplant", chapter:"Renal" },
  { code:"T86.12", label:"Kidney transplant failure",                       synonyms:["graft failure","transplant failure","failed kidney transplant","graft loss"],             category:"Transplant", chapter:"Renal" },
  { code:"T86.19", label:"Other complication of kidney transplant",         synonyms:["transplant complication","post transplant complication","bk virus","calcineurin toxicity"], category:"Transplant", chapter:"Renal" },

  // ─────────────────────────────────────────────────────────────────────────
  // GASTROINTESTINAL
  // ─────────────────────────────────────────────────────────────────────────
  { code:"K92.0",  label:"Haematemesis",                                    synonyms:["haematemesis","hematemesis","vomiting blood","upper gi bleed"],                          category:"GI", chapter:"GI" },
  { code:"K57.30", label:"Diverticulitis of large intestine",               synonyms:["diverticulitis","diverticular disease","colonic diverticulitis"],                        category:"GI", chapter:"GI" },
  { code:"K85.90", label:"Acute pancreatitis",                              synonyms:["pancreatitis","acute pancreatitis","pancreatic inflammation"],                           category:"GI", chapter:"GI" },
  { code:"K74.60", label:"Liver cirrhosis",                                 synonyms:["cirrhosis","liver cirrhosis","hepatic cirrhosis","chronic liver disease"],               category:"GI", chapter:"GI" },
  { code:"K76.1",  label:"Chronic passive congestion of liver",             synonyms:["congestive hepatopathy","cardiac hepatopathy","hepatic congestion","hepatomegaly cardiac"], category:"GI", chapter:"GI" },
  { code:"R11.2",  label:"Nausea and vomiting",                             synonyms:["nausea vomiting","vomiting","nausea","emesis"],                                          category:"GI", chapter:"GI" },
  { code:"K21.0",  label:"Gastro-oesophageal reflux disease",               synonyms:["gerd","gord","reflux","oesophagitis","heartburn"],                                       category:"GI", chapter:"GI" },

  // ─────────────────────────────────────────────────────────────────────────
  // AUTOIMMUNE / SYSTEMIC
  // ─────────────────────────────────────────────────────────────────────────
  { code:"M32.9",  label:"Systemic lupus erythematosus (SLE)",              synonyms:["sle","lupus","systemic lupus","lupus erythematosus"],                                    category:"Autoimmune", chapter:"Systemic" },
  { code:"M30.0",  label:"Polyarteritis nodosa",                            synonyms:["pan","polyarteritis nodosa","systemic vasculitis"],                                      category:"Autoimmune", chapter:"Systemic" },
  { code:"M31.6",  label:"Other giant cell arteritis",                      synonyms:["anca vasculitis","anti-gbm","goodpasture syndrome","anti-gbm nephritis"],                category:"Autoimmune", chapter:"Systemic" },
  { code:"M05.79", label:"Rheumatoid arthritis with rheumatoid factor",     synonyms:["rheumatoid arthritis","ra","rheumatoid"],                                               category:"Autoimmune", chapter:"Systemic" },
  { code:"M34.9",  label:"Systemic sclerosis (scleroderma)",                synonyms:["scleroderma","systemic sclerosis","crest","progressive systemic sclerosis"],             category:"Autoimmune", chapter:"Systemic" },
  { code:"E85.1",  label:"Neuropathic heredofamilial amyloidosis",          synonyms:["amyloidosis","hereditary amyloid","familial amyloid polyneuropathy"],                    category:"Autoimmune", chapter:"Systemic" },
  { code:"E85.4",  label:"Organ-limited amyloidosis (renal)",               synonyms:["renal amyloid","organ limited amyloidosis","amyloid kidney"],                           category:"Autoimmune", chapter:"Systemic" },

  // ─────────────────────────────────────────────────────────────────────────
  // RESPIRATORY
  // ─────────────────────────────────────────────────────────────────────────
  { code:"J44.1",  label:"COPD with acute exacerbation",                    synonyms:["copd","chronic obstructive pulmonary disease","copd exacerbation","emphysema exacerbation"], category:"Respiratory", chapter:"Cardiorespiratory" },
  { code:"J45.901","label":"Uncontrolled asthma",                           synonyms:["asthma","bronchospasm","uncontrolled asthma","acute asthma"],                            category:"Respiratory", chapter:"Cardiorespiratory" },
  { code:"R06.00", label:"Dyspnoea, unspecified",                           synonyms:["dyspnoea","breathlessness","shortness of breath","sob","dyspnea"],                       category:"Respiratory", chapter:"Cardiorespiratory" },

  // ─────────────────────────────────────────────────────────────────────────
  // ORTHOPAEDIC / BONE
  // ─────────────────────────────────────────────────────────────────────────
  { code:"M80.08XA","label":"Age-related osteoporosis with fracture",       synonyms:["osteoporosis fracture","pathological fracture","fragility fracture","osteoporotic fracture"], category:"Bone", chapter:"Musculoskeletal" },
  { code:"M54.5",  label:"Low back pain",                                   synonyms:["back pain","low back pain","lumbar pain","lumbago"],                                     category:"Bone", chapter:"Musculoskeletal" },
  { code:"M10.9",  label:"Gout, unspecified",                               synonyms:["gout","gouty arthritis","uric acid arthritis","tophaceous gout"],                        category:"Bone", chapter:"Musculoskeletal" },

  // ─────────────────────────────────────────────────────────────────────────
  // NUTRITION / MALNUTRITION
  // ─────────────────────────────────────────────────────────────────────────
  { code:"E46",    label:"Unspecified protein-energy malnutrition",         synonyms:["malnutrition","protein energy malnutrition","pem","cachexia","wasting","low albumin malnutrition"], category:"Nutrition", chapter:"Metabolic" },
  { code:"E44.0",  label:"Moderate protein-energy malnutrition",            synonyms:["moderate malnutrition","mia syndrome","malnutrition inflammation"],                      category:"Nutrition", chapter:"Metabolic" },
  { code:"R64",    label:"Cachexia (wasting syndrome)",                     synonyms:["cachexia","dialysis wasting","protein wasting","muscle wasting","sarcopenia"],           category:"Nutrition", chapter:"Metabolic" },
  { code:"E03.9",  label:"Hypothyroidism, unspecified",                     synonyms:["hypothyroidism","low thyroid","underactive thyroid","tsh high"],                         category:"Nutrition", chapter:"Metabolic" },
  { code:"E05.90", label:"Hyperthyroidism, unspecified",                    synonyms:["hyperthyroidism","overactive thyroid","thyrotoxicosis","tsh low"],                       category:"Nutrition", chapter:"Metabolic" },

  // ─────────────────────────────────────────────────────────────────────────
  // ACUTE GLOMERULAR DISEASE (from ICD master list — N00, N01)
  // ─────────────────────────────────────────────────────────────────────────
  { code:"N00.9",  label:"Acute nephritic syndrome, unspecified",           synonyms:["acute nephritic","acute gn","post-infectious gn","acute glomerulonephritis","haematuria proteinuria hypertension"], category:"Glomerular", chapter:"Renal" },
  { code:"N00.7",  label:"Acute nephritic syndrome — crescentic GN",        synonyms:["crescentic gn","diffuse crescentic glomerulonephritis","anti-gbm","anca crescentic"],   category:"Glomerular", chapter:"Renal" },
  { code:"N01.9",  label:"Rapidly progressive nephritic syndrome (RPGN)",   synonyms:["rpgn","rapidly progressive gn","crescentic gn","rapidly progressive glomerulonephritis","crescentic nephritis"], category:"Glomerular", chapter:"Renal" },
  { code:"N01.7",  label:"RPGN — diffuse crescentic glomerulonephritis",    synonyms:["rpgn crescentic","crescentic rpgn","anca rpgn","anti-gbm rpgn"],                        category:"Glomerular", chapter:"Renal" },

  // ─────────────────────────────────────────────────────────────────────────
  // TUBULO-INTERSTITIAL NEPHRITIS — SPECIFIC SUBTYPES
  // ─────────────────────────────────────────────────────────────────────────
  { code:"N11.0",  label:"Reflux nephropathy (chronic pyelonephritis)",     synonyms:["reflux nephropathy","vesicoureteral reflux","vur nephropathy","reflux associated nephropathy","chronic pyelonephritis reflux"], category:"Primary Renal", chapter:"Renal" },
  { code:"N11.1",  label:"Chronic obstructive pyelonephritis",              synonyms:["obstructive pyelonephritis","obstructive nephropathy","chronic obstruction kidney"],    category:"Primary Renal", chapter:"Renal" },
  { code:"N12",    label:"Tubulo-interstitial nephritis, unspecified",      synonyms:["interstitial nephritis","tubulointerstitial nephritis","tin","acute interstitial nephritis"], category:"Primary Renal", chapter:"Renal" },
  { code:"N14.0",  label:"Analgesic nephropathy",                           synonyms:["analgesic nephropathy","paracetamol nephropathy","phenacetin kidney","nsaid analgesic nephropathy"], category:"Primary Renal", chapter:"Renal" },
  { code:"N14.4",  label:"Toxic nephropathy (non-drug)",                    synonyms:["toxic nephropathy","environmental toxin kidney","heavy metal kidney","industrial nephropathy"], category:"Primary Renal", chapter:"Renal" },
  { code:"N15.0",  label:"Balkan nephropathy",                              synonyms:["balkan nephropathy","endemic nephropathy","aristolochic acid nephropathy"],              category:"Primary Renal", chapter:"Renal" },
  { code:"N16.5",  label:"Tubulo-interstitial nephritis in transplant rejection", synonyms:["rejection nephritis","transplant nephritis","acute rejection interstitial","chronic rejection tubulo-interstitial"], category:"Primary Renal", chapter:"Renal" },

  // ─────────────────────────────────────────────────────────────────────────
  // OBSTRUCTIVE / STRUCTURAL RENAL CONDITIONS
  // ─────────────────────────────────────────────────────────────────────────
  { code:"N13.6",  label:"Pyonephrosis",                                    synonyms:["pyonephrosis","infected hydronephrosis","infected kidney","suppurative hydronephrosis"], category:"Primary Renal", chapter:"Renal" },
  { code:"N13.0",  label:"Hydronephrosis — PUJ obstruction",               synonyms:["hydronephrosis","puj obstruction","pelviureteric junction","ureteropelvic obstruction"], category:"Primary Renal", chapter:"Renal" },
  { code:"N25.1",  label:"Nephrogenic diabetes insipidus",                  synonyms:["nephrogenic di","ndi","polyuria polydipsia","nephrogenic diabetes insipidus"],           category:"Primary Renal", chapter:"Renal" },
  { code:"N28.1",  label:"Simple renal cyst",                               synonyms:["renal cyst","kidney cyst","simple cyst kidney","bosniak 1"],                             category:"Primary Renal", chapter:"Renal" },
  { code:"N23",    label:"Renal colic",                                     synonyms:["renal colic","ureteric colic","kidney stone pain","flank pain calculus","ureteric stone pain"], category:"Primary Renal", chapter:"Renal" },
  { code:"N99.0",  label:"Postprocedural renal failure",                    synonyms:["postprocedural renal failure","post-op arf","post-operative kidney failure","aci post procedure","surgery related aki"], category:"AKI", chapter:"Renal" },

  // ─────────────────────────────────────────────────────────────────────────
  // SECONDARY HYPERTENSION (renovascular / renal)
  // ─────────────────────────────────────────────────────────────────────────
  { code:"I15.0",  label:"Renovascular hypertension",                       synonyms:["renovascular hypertension","renal artery stenosis hypertension","ras hypertension","fibromuscular dysplasia hypertension"], category:"Hypertension", chapter:"Cardiorespiratory" },
  { code:"I15.1",  label:"Hypertension secondary to renal disorders",       synonyms:["renal hypertension","secondary hypertension renal","hypertension ckd secondary","hypertension kidney disease"], category:"Hypertension", chapter:"Cardiorespiratory" },

  // ─────────────────────────────────────────────────────────────────────────
  // URAEMIC PERICARDITIS (dialysis-specific cardiac complication)
  // ─────────────────────────────────────────────────────────────────────────
  { code:"I30.9",  label:"Acute pericarditis, unspecified",                 synonyms:["pericarditis","acute pericarditis","uraemic pericarditis","dialysis pericarditis","pericardial inflammation"], category:"Cardiac", chapter:"Cardiorespiratory" },
  { code:"I30.0",  label:"Acute nonspecific idiopathic pericarditis",       synonyms:["idiopathic pericarditis","viral pericarditis","nonspecific pericarditis"],               category:"Cardiac", chapter:"Cardiorespiratory" },

  // ─────────────────────────────────────────────────────────────────────────
  // BONE MINERAL — DIALYSIS-SPECIFIC
  // ─────────────────────────────────────────────────────────────────────────
  { code:"M83.4",  label:"Aluminium bone disease (dialysate aluminium)",    synonyms:["aluminium bone disease","dialysis aluminium toxicity","adynamic bone disease","aluminium related bone disease"], category:"Bone", chapter:"Musculoskeletal" },
  { code:"M83.3",  label:"Adult osteomalacia due to malnutrition",          synonyms:["osteomalacia malnutrition","nutritional osteomalacia","renal osteomalacia","low vitamin d osteomalacia"], category:"Bone", chapter:"Musculoskeletal" },

  // ─────────────────────────────────────────────────────────────────────────
  // ANAEMIA — ADDITIONAL
  // ─────────────────────────────────────────────────────────────────────────
  { code:"D63.8",  label:"Anaemia in other chronic diseases",               synonyms:["anaemia chronic disease","anaemia of inflammation","acd","chronic disease anaemia"],     category:"Anaemia", chapter:"Haematology" },
  { code:"D60.0",  label:"Chronic pure red cell aplasia (EPO-related)",     synonyms:["pure red cell aplasia","prca","epo related prca","anti-epo antibodies","epoetin aplasia"], category:"Anaemia", chapter:"Haematology" },

  // ─────────────────────────────────────────────────────────────────────────
  // ADMINISTRATIVE / STATUS CODES
  // ─────────────────────────────────────────────────────────────────────────
  { code:"Z99.2",  label:"Dependence on renal dialysis",                    synonyms:["maintenance dialysis","haemodialysis status","on haemodialysis"],                        category:"Status", chapter:"Administrative" },
  { code:"Z87.39", label:"Personal history of urinary calculi",             synonyms:["history kidney stones","previous renal calculi"],                                       category:"Status", chapter:"Administrative" },
  { code:"Z82.49", label:"Family history of ischaemic heart disease",       synonyms:["family history ihd","family history heart disease","fh cad"],                           category:"Status", chapter:"Administrative" },
  { code:"Z79.4",  label:"Long-term use of insulin",                        synonyms:["insulin dependent","long term insulin","on insulin"],                                   category:"Status", chapter:"Administrative" },
];

/**
 * Search the list.
 * @param {string} query - user input
 * @param {number} limit - max results (default 12)
 * @returns {Array} matching entries sorted by relevance
 */
window.searchICD10 = function(query, limit = 12) {
  const q = query.toLowerCase().trim();
  if (!q || q.length < 2) return [];
  const results = [];
  for (const entry of window.ICD10_NEPHROLOGY) {
    let score = 0;
    if (entry.code.toLowerCase() === q)                           score = 100;
    else if (entry.code.toLowerCase().startsWith(q))             score = 80;
    else if (entry.label.toLowerCase().startsWith(q))            score = 70;
    else if (entry.label.toLowerCase().includes(q))              score = 50;
    else if (entry.synonyms.some(s => s === q))                  score = 60;
    else if (entry.synonyms.some(s => s.startsWith(q)))          score = 40;
    else if (entry.synonyms.some(s => s.includes(q)))            score = 25;
    if (score > 0) results.push({ ...entry, _score: score });
  }
  results.sort((a, b) => b._score - a._score);
  return results.slice(0, limit);
};
