--
-- PostgreSQL database dump
--

\restrict QBNHpvVmVG0RRbgBSYKlsyNNKbEJoMhq3eUjBm06qKlfPOMcxkMqd0hYBLTH5yH

-- Dumped from database version 18.3 (Debian 18.3-1.pgdg12+1)
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alert_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_logs (
    id integer NOT NULL,
    patient_id integer,
    alert_type character varying,
    alert_reason character varying,
    sent_at timestamp without time zone,
    status character varying,
    message_preview text
);


--
-- Name: alert_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.alert_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: alert_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.alert_logs_id_seq OWNED BY public.alert_logs.id;


--
-- Name: clinical_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clinical_events (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    event_date date NOT NULL,
    event_type character varying NOT NULL,
    severity character varying,
    notes text,
    created_by character varying,
    created_at timestamp without time zone
);


--
-- Name: clinical_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.clinical_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: clinical_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.clinical_events_id_seq OWNED BY public.clinical_events.id;


--
-- Name: dry_weight_assessments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dry_weight_assessments (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    assessment_date date NOT NULL,
    ivc_diameter_max double precision,
    ivc_collapsibility_index double precision,
    bia_fluid_overload_litres double precision,
    bia_overhydration_percent double precision,
    bia_total_body_water double precision,
    bia_phase_angle double precision,
    nt_probnp double precision,
    edema_status character varying,
    bp_lability character varying,
    recommended_dry_weight double precision,
    assessment_notes text,
    "timestamp" timestamp without time zone,
    performed_by character varying
);


--
-- Name: dry_weight_assessments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dry_weight_assessments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dry_weight_assessments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dry_weight_assessments_id_seq OWNED BY public.dry_weight_assessments.id;


--
-- Name: interim_lab_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.interim_lab_records (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    session_id integer,
    lab_date date NOT NULL,
    record_month character varying,
    parameter character varying NOT NULL,
    value double precision NOT NULL,
    unit character varying,
    trigger character varying,
    notes text,
    entered_by character varying,
    created_at timestamp without time zone
);


--
-- Name: interim_lab_records_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.interim_lab_records_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: interim_lab_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.interim_lab_records_id_seq OWNED BY public.interim_lab_records.id;


--
-- Name: monthly_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.monthly_records (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    record_month character varying NOT NULL,
    "timestamp" timestamp without time zone,
    entered_by character varying,
    idwg double precision,
    target_dry_weight double precision,
    last_prehd_weight double precision,
    residual_urine_output double precision,
    urr double precision,
    single_pool_ktv double precision,
    equilibrated_ktv double precision,
    npcr double precision,
    ufr double precision,
    pre_dialysis_urea double precision,
    post_dialysis_urea double precision,
    serum_creatinine double precision,
    hb double precision,
    esa_type character varying,
    epo_mircera_dose character varying,
    epo_weekly_units double precision,
    desidustat_dose character varying,
    serum_ferritin double precision,
    tsat double precision,
    serum_iron double precision,
    tibc double precision,
    iv_iron_product character varying,
    iv_iron_dose double precision,
    iv_iron_date date,
    calcium double precision,
    phosphorus double precision,
    alkaline_phosphate double precision,
    ipth double precision,
    vit_d double precision,
    vitamin_d_analog_dose character varying,
    phosphate_binder_type character varying,
    serum_sodium double precision,
    serum_potassium double precision,
    serum_bicarbonate double precision,
    serum_uric_acid double precision,
    albumin double precision,
    prealbumin double precision,
    sga_score character varying,
    mis_score integer,
    av_daily_calories double precision,
    av_daily_protein double precision,
    total_cholesterol double precision,
    ldl_cholesterol double precision,
    wbc_count double precision,
    neutrophil_count double precision,
    lymphocyte_count double precision,
    platelet_count double precision,
    hba1c double precision,
    ast double precision,
    alt double precision,
    crp double precision,
    il6 double precision,
    tnf_alpha double precision,
    antihypertensive_count integer,
    antihypertensive_details text,
    bp_sys double precision,
    bp_dia double precision,
    troponin_i double precision,
    nt_probnp double precision,
    access_type character varying,
    hrqol_score double precision,
    hospitalization_this_month boolean,
    hospitalization_date date,
    hospitalization_diagnosis text,
    hospitalization_icd_code character varying,
    hospitalization_icd_diagnosis text,
    hospitalization_details text,
    blood_transfusion_units integer,
    transfusion_date character varying,
    issues text
);


--
-- Name: monthly_records_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.monthly_records_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: monthly_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.monthly_records_id_seq OWNED BY public.monthly_records.id;


--
-- Name: patient_meal_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_meal_records (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    date date,
    calories double precision,
    protein double precision,
    meal_type character varying,
    notes text,
    created_at timestamp without time zone
);


--
-- Name: patient_meal_records_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_meal_records_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_meal_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_meal_records_id_seq OWNED BY public.patient_meal_records.id;


--
-- Name: patient_reminders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_reminders (
    id integer NOT NULL,
    patient_id integer,
    reminder_date date NOT NULL,
    message text NOT NULL,
    is_completed boolean,
    created_at timestamp without time zone
);


--
-- Name: patient_reminders_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_reminders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_reminders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_reminders_id_seq OWNED BY public.patient_reminders.id;


--
-- Name: patient_symptom_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_symptom_reports (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    session_id integer,
    reported_at timestamp without time zone,
    symptoms text,
    severity integer,
    notes text,
    dialysis_recovery_time_mins integer,
    tiredness_score integer,
    energy_level_score integer,
    daily_activity_impact integer,
    cognitive_alertness character varying,
    post_hd_mood character varying,
    sleepiness_severity integer,
    missed_social_or_work_event boolean
);


--
-- Name: patient_symptom_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patient_symptom_reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patient_symptom_reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patient_symptom_reports_id_seq OWNED BY public.patient_symptom_reports.id;


--
-- Name: patients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patients (
    id integer NOT NULL,
    hid_no character varying NOT NULL,
    name character varying NOT NULL,
    relation character varying,
    relation_type character varying,
    sex character varying,
    contact_no character varying,
    email character varying,
    diagnosis character varying,
    hd_wef_date date,
    education_level character varying,
    height double precision,
    primary_renal_disease character varying,
    native_kidney_disease character varying,
    date_esrd_diagnosis date,
    native_kidney_biopsy character varying,
    native_kidney_biopsy_date date,
    native_kidney_biopsy_report text,
    dm_status character varying,
    dm_end_organ_damage boolean,
    htn_status boolean,
    cad_status boolean,
    chf_status boolean,
    history_of_stroke boolean,
    history_of_pvd boolean,
    history_of_dementia boolean,
    history_of_cpd boolean,
    history_of_ctd boolean,
    history_of_pud boolean,
    liver_disease character varying,
    hemiplegia boolean,
    solid_tumor character varying,
    leukemia boolean,
    lymphoma boolean,
    smoking_status character varying,
    alcohol_consumption character varying,
    charlson_comorbidity_index integer,
    comorbidities text,
    drug_allergies character varying,
    clinical_background text,
    dialysis_modality character varying,
    previous_dialysis_modality character varying,
    previous_krt_modality character varying,
    history_of_renal_transplant boolean,
    transplant_prospect character varying,
    viral_markers character varying,
    viral_hbsag character varying,
    viral_anti_hcv character varying,
    viral_hiv character varying,
    hep_b_status character varying,
    hep_b_dose1_date date,
    hep_b_dose2_date date,
    hep_b_dose3_date date,
    hep_b_dose4_date date,
    hep_b_titer_date date,
    pcv13_date date,
    ppsv23_date date,
    hz_dose1_date date,
    hz_dose2_date date,
    influenza_date date,
    access_type character varying,
    access_date date,
    date_first_cannulation date,
    history_of_access_thrombosis boolean,
    access_intervention_history text,
    catheter_type character varying,
    catheter_insertion_site character varying,
    age integer,
    ejection_fraction double precision,
    diastolic_dysfunction character varying,
    handgrip_strength double precision,
    echo_date date,
    echo_report text,
    dry_weight double precision,
    healthcare_facility character varying,
    hd_frequency integer,
    hd_day_1 character varying,
    hd_day_2 character varying,
    hd_day_3 character varying,
    hd_slot_1 character varying,
    hd_slot_2 character varying,
    hd_slot_3 character varying,
    blood_group character varying,
    current_survival_status character varying,
    date_of_death date,
    primary_cause_of_death character varying,
    withdrawal_from_dialysis boolean,
    date_facility_transfer date,
    whatsapp_link character varying,
    whatsapp_notify boolean,
    mail_trigger boolean,
    is_active boolean,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    login_username character varying,
    hashed_password character varying
);


--
-- Name: patients_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patients_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patients_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patients_id_seq OWNED BY public.patients.id;


--
-- Name: research_projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.research_projects (
    id integer NOT NULL,
    title character varying NOT NULL,
    description text,
    status character varying,
    created_at timestamp without time zone
);


--
-- Name: research_projects_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.research_projects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: research_projects_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.research_projects_id_seq OWNED BY public.research_projects.id;


--
-- Name: research_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.research_records (
    id integer NOT NULL,
    project_id integer NOT NULL,
    patient_id integer NOT NULL,
    test_type character varying NOT NULL,
    test_date date,
    data text,
    notes text,
    entered_by character varying,
    created_at timestamp without time zone
);


--
-- Name: research_records_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.research_records_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: research_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.research_records_id_seq OWNED BY public.research_records.id;


--
-- Name: session_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.session_records (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    session_date date NOT NULL,
    record_month character varying NOT NULL,
    entered_by character varying,
    "timestamp" timestamp without time zone,
    provider character varying,
    dialysis_type character varying,
    scheduled_treatment_duration double precision,
    duration_hours integer,
    duration_minutes integer,
    weight_pre double precision,
    weight_post double precision,
    uf_volume double precision,
    actual_uf_volume double precision,
    uf_rate double precision,
    bp_pre_sys double precision,
    bp_pre_dia double precision,
    bp_during_sys double precision,
    bp_during_dia double precision,
    bp_peak_sys double precision,
    bp_peak_dia double precision,
    bp_nadir_sys double precision,
    bp_nadir_dia double precision,
    bp_post_sys double precision,
    bp_post_dia double precision,
    blood_flow_rate double precision,
    actual_blood_flow_rate double precision,
    dialysate_flow double precision,
    dialyzer_type character varying,
    dialyzer_surface_area double precision,
    dialyzer_membrane_flux character varying,
    dialysate_buffer character varying,
    dialysate_sodium double precision,
    dialysate_potassium double precision,
    dialysate_calcium double precision,
    dialysate_bicarbonate double precision,
    dialysate_temperature double precision,
    arterial_line_pressure double precision,
    venous_line_pressure double precision,
    transmembrane_pressure double precision,
    anticoagulation character varying,
    anticoagulation_dose double precision,
    access_location character varying,
    access_condition character varying,
    needle_gauge character varying,
    cannulation_technique character varying,
    vascular_interventions text,
    access_complications text,
    urea_peripheral_s double precision,
    urea_arterial_a double precision,
    urea_venous_v double precision,
    access_recirculation_percent double precision,
    access_flow_qa double precision,
    medications_administered text,
    idh_episode boolean,
    idh_hypertension boolean,
    pre_hd_dyspnea_likert integer,
    post_hd_dyspnea_likert integer,
    muscle_cramps boolean,
    nausea_vomiting boolean,
    chest_pain boolean,
    arrhythmia boolean,
    early_termination boolean,
    reason_early_termination character varying,
    intradialytic_exercise_mins integer,
    intradialytic_meals_eaten boolean,
    complications_occurred boolean,
    complications_description text,
    complications_management text,
    dialysis_adherence character varying,
    doctor_concerns text,
    next_appointment_id character varying,
    is_emergency boolean,
    reason_emergency character varying,
    interim_hb double precision,
    interim_k double precision,
    interim_ca double precision,
    interim_trigger character varying
);


--
-- Name: session_records_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.session_records_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: session_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.session_records_id_seq OWNED BY public.session_records.id;


--
-- Name: sustainability_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sustainability_records (
    id integer NOT NULL,
    record_month character varying NOT NULL,
    electricity_kwh double precision,
    water_m3 double precision,
    biomedical_waste_kg double precision,
    general_waste_kg double precision,
    total_sessions_override integer,
    avg_transport_dist_km double precision,
    "timestamp" timestamp without time zone,
    updated_by character varying
);


--
-- Name: sustainability_records_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sustainability_records_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sustainability_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sustainability_records_id_seq OWNED BY public.sustainability_records.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying NOT NULL,
    full_name character varying,
    hashed_password character varying NOT NULL,
    role character varying,
    is_active boolean,
    last_login timestamp without time zone,
    created_at timestamp without time zone
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: alert_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_logs ALTER COLUMN id SET DEFAULT nextval('public.alert_logs_id_seq'::regclass);


--
-- Name: clinical_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clinical_events ALTER COLUMN id SET DEFAULT nextval('public.clinical_events_id_seq'::regclass);


--
-- Name: dry_weight_assessments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dry_weight_assessments ALTER COLUMN id SET DEFAULT nextval('public.dry_weight_assessments_id_seq'::regclass);


--
-- Name: interim_lab_records id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interim_lab_records ALTER COLUMN id SET DEFAULT nextval('public.interim_lab_records_id_seq'::regclass);


--
-- Name: monthly_records id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monthly_records ALTER COLUMN id SET DEFAULT nextval('public.monthly_records_id_seq'::regclass);


--
-- Name: patient_meal_records id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_meal_records ALTER COLUMN id SET DEFAULT nextval('public.patient_meal_records_id_seq'::regclass);


--
-- Name: patient_reminders id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_reminders ALTER COLUMN id SET DEFAULT nextval('public.patient_reminders_id_seq'::regclass);


--
-- Name: patient_symptom_reports id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_symptom_reports ALTER COLUMN id SET DEFAULT nextval('public.patient_symptom_reports_id_seq'::regclass);


--
-- Name: patients id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients ALTER COLUMN id SET DEFAULT nextval('public.patients_id_seq'::regclass);


--
-- Name: research_projects id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_projects ALTER COLUMN id SET DEFAULT nextval('public.research_projects_id_seq'::regclass);


--
-- Name: research_records id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_records ALTER COLUMN id SET DEFAULT nextval('public.research_records_id_seq'::regclass);


--
-- Name: session_records id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.session_records ALTER COLUMN id SET DEFAULT nextval('public.session_records_id_seq'::regclass);


--
-- Name: sustainability_records id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sustainability_records ALTER COLUMN id SET DEFAULT nextval('public.sustainability_records_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Data for Name: alert_logs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.alert_logs (id, patient_id, alert_type, alert_reason, sent_at, status, message_preview) FROM stdin;
\.


--
-- Data for Name: clinical_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.clinical_events (id, patient_id, event_date, event_type, severity, notes, created_by, created_at) FROM stdin;
\.


--
-- Data for Name: dry_weight_assessments; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.dry_weight_assessments (id, patient_id, assessment_date, ivc_diameter_max, ivc_collapsibility_index, bia_fluid_overload_litres, bia_overhydration_percent, bia_total_body_water, bia_phase_angle, nt_probnp, edema_status, bp_lability, recommended_dry_weight, assessment_notes, "timestamp", performed_by) FROM stdin;
\.


--
-- Data for Name: interim_lab_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.interim_lab_records (id, patient_id, session_id, lab_date, record_month, parameter, value, unit, trigger, notes, entered_by, created_at) FROM stdin;
\.


--
-- Data for Name: monthly_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.monthly_records (id, patient_id, record_month, "timestamp", entered_by, idwg, target_dry_weight, last_prehd_weight, residual_urine_output, urr, single_pool_ktv, equilibrated_ktv, npcr, ufr, pre_dialysis_urea, post_dialysis_urea, serum_creatinine, hb, esa_type, epo_mircera_dose, epo_weekly_units, desidustat_dose, serum_ferritin, tsat, serum_iron, tibc, iv_iron_product, iv_iron_dose, iv_iron_date, calcium, phosphorus, alkaline_phosphate, ipth, vit_d, vitamin_d_analog_dose, phosphate_binder_type, serum_sodium, serum_potassium, serum_bicarbonate, serum_uric_acid, albumin, prealbumin, sga_score, mis_score, av_daily_calories, av_daily_protein, total_cholesterol, ldl_cholesterol, wbc_count, neutrophil_count, lymphocyte_count, platelet_count, hba1c, ast, alt, crp, il6, tnf_alpha, antihypertensive_count, antihypertensive_details, bp_sys, bp_dia, troponin_i, nt_probnp, access_type, hrqol_score, hospitalization_this_month, hospitalization_date, hospitalization_diagnosis, hospitalization_icd_code, hospitalization_icd_diagnosis, hospitalization_details, blood_transfusion_units, transfusion_date, issues) FROM stdin;
\.


--
-- Data for Name: patient_meal_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.patient_meal_records (id, patient_id, date, calories, protein, meal_type, notes, created_at) FROM stdin;
\.


--
-- Data for Name: patient_reminders; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.patient_reminders (id, patient_id, reminder_date, message, is_completed, created_at) FROM stdin;
\.


--
-- Data for Name: patient_symptom_reports; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.patient_symptom_reports (id, patient_id, session_id, reported_at, symptoms, severity, notes, dialysis_recovery_time_mins, tiredness_score, energy_level_score, daily_activity_impact, cognitive_alertness, post_hd_mood, sleepiness_severity, missed_social_or_work_event) FROM stdin;
\.


--
-- Data for Name: patients; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.patients (id, hid_no, name, relation, relation_type, sex, contact_no, email, diagnosis, hd_wef_date, education_level, height, primary_renal_disease, native_kidney_disease, date_esrd_diagnosis, native_kidney_biopsy, native_kidney_biopsy_date, native_kidney_biopsy_report, dm_status, dm_end_organ_damage, htn_status, cad_status, chf_status, history_of_stroke, history_of_pvd, history_of_dementia, history_of_cpd, history_of_ctd, history_of_pud, liver_disease, hemiplegia, solid_tumor, leukemia, lymphoma, smoking_status, alcohol_consumption, charlson_comorbidity_index, comorbidities, drug_allergies, clinical_background, dialysis_modality, previous_dialysis_modality, previous_krt_modality, history_of_renal_transplant, transplant_prospect, viral_markers, viral_hbsag, viral_anti_hcv, viral_hiv, hep_b_status, hep_b_dose1_date, hep_b_dose2_date, hep_b_dose3_date, hep_b_dose4_date, hep_b_titer_date, pcv13_date, ppsv23_date, hz_dose1_date, hz_dose2_date, influenza_date, access_type, access_date, date_first_cannulation, history_of_access_thrombosis, access_intervention_history, catheter_type, catheter_insertion_site, age, ejection_fraction, diastolic_dysfunction, handgrip_strength, echo_date, echo_report, dry_weight, healthcare_facility, hd_frequency, hd_day_1, hd_day_2, hd_day_3, hd_slot_1, hd_slot_2, hd_slot_3, blood_group, current_survival_status, date_of_death, primary_cause_of_death, withdrawal_from_dialysis, date_facility_transfer, whatsapp_link, whatsapp_notify, mail_trigger, is_active, created_at, updated_at, login_username, hashed_password) FROM stdin;
\.


--
-- Data for Name: research_projects; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.research_projects (id, title, description, status, created_at) FROM stdin;
1	Test Research project	Testing research hub	Active	2026-05-01 10:26:23.028635
\.


--
-- Data for Name: research_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.research_records (id, project_id, patient_id, test_type, test_date, data, notes, entered_by, created_at) FROM stdin;
\.


--
-- Data for Name: session_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.session_records (id, patient_id, session_date, record_month, entered_by, "timestamp", provider, dialysis_type, scheduled_treatment_duration, duration_hours, duration_minutes, weight_pre, weight_post, uf_volume, actual_uf_volume, uf_rate, bp_pre_sys, bp_pre_dia, bp_during_sys, bp_during_dia, bp_peak_sys, bp_peak_dia, bp_nadir_sys, bp_nadir_dia, bp_post_sys, bp_post_dia, blood_flow_rate, actual_blood_flow_rate, dialysate_flow, dialyzer_type, dialyzer_surface_area, dialyzer_membrane_flux, dialysate_buffer, dialysate_sodium, dialysate_potassium, dialysate_calcium, dialysate_bicarbonate, dialysate_temperature, arterial_line_pressure, venous_line_pressure, transmembrane_pressure, anticoagulation, anticoagulation_dose, access_location, access_condition, needle_gauge, cannulation_technique, vascular_interventions, access_complications, urea_peripheral_s, urea_arterial_a, urea_venous_v, access_recirculation_percent, access_flow_qa, medications_administered, idh_episode, idh_hypertension, pre_hd_dyspnea_likert, post_hd_dyspnea_likert, muscle_cramps, nausea_vomiting, chest_pain, arrhythmia, early_termination, reason_early_termination, intradialytic_exercise_mins, intradialytic_meals_eaten, complications_occurred, complications_description, complications_management, dialysis_adherence, doctor_concerns, next_appointment_id, is_emergency, reason_emergency, interim_hb, interim_k, interim_ca, interim_trigger) FROM stdin;
\.


--
-- Data for Name: sustainability_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.sustainability_records (id, record_month, electricity_kwh, water_m3, biomedical_waste_kg, general_waste_kg, total_sessions_override, avg_transport_dist_km, "timestamp", updated_by) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (id, username, full_name, hashed_password, role, is_active, last_login, created_at) FROM stdin;
\.


--
-- Name: alert_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.alert_logs_id_seq', 1, true);


--
-- Name: clinical_events_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.clinical_events_id_seq', 1, true);


--
-- Name: dry_weight_assessments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.dry_weight_assessments_id_seq', 1, true);


--
-- Name: interim_lab_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.interim_lab_records_id_seq', 1, true);


--
-- Name: monthly_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.monthly_records_id_seq', 1, true);


--
-- Name: patient_meal_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.patient_meal_records_id_seq', 1, true);


--
-- Name: patient_reminders_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.patient_reminders_id_seq', 1, true);


--
-- Name: patient_symptom_reports_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.patient_symptom_reports_id_seq', 1, true);


--
-- Name: patients_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.patients_id_seq', 1, true);


--
-- Name: research_projects_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.research_projects_id_seq', 1, true);


--
-- Name: research_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.research_records_id_seq', 1, true);


--
-- Name: session_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.session_records_id_seq', 1, true);


--
-- Name: sustainability_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.sustainability_records_id_seq', 1, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.users_id_seq', 1, true);


--
-- Name: alert_logs alert_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_logs
    ADD CONSTRAINT alert_logs_pkey PRIMARY KEY (id);


--
-- Name: clinical_events clinical_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clinical_events
    ADD CONSTRAINT clinical_events_pkey PRIMARY KEY (id);


--
-- Name: dry_weight_assessments dry_weight_assessments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dry_weight_assessments
    ADD CONSTRAINT dry_weight_assessments_pkey PRIMARY KEY (id);


--
-- Name: interim_lab_records interim_lab_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interim_lab_records
    ADD CONSTRAINT interim_lab_records_pkey PRIMARY KEY (id);


--
-- Name: monthly_records monthly_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monthly_records
    ADD CONSTRAINT monthly_records_pkey PRIMARY KEY (id);


--
-- Name: patient_meal_records patient_meal_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_meal_records
    ADD CONSTRAINT patient_meal_records_pkey PRIMARY KEY (id);


--
-- Name: patient_reminders patient_reminders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_reminders
    ADD CONSTRAINT patient_reminders_pkey PRIMARY KEY (id);


--
-- Name: patient_symptom_reports patient_symptom_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_symptom_reports
    ADD CONSTRAINT patient_symptom_reports_pkey PRIMARY KEY (id);


--
-- Name: patients patients_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT patients_pkey PRIMARY KEY (id);


--
-- Name: research_projects research_projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_projects
    ADD CONSTRAINT research_projects_pkey PRIMARY KEY (id);


--
-- Name: research_records research_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_records
    ADD CONSTRAINT research_records_pkey PRIMARY KEY (id);


--
-- Name: session_records session_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.session_records
    ADD CONSTRAINT session_records_pkey PRIMARY KEY (id);


--
-- Name: sustainability_records sustainability_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sustainability_records
    ADD CONSTRAINT sustainability_records_pkey PRIMARY KEY (id);


--
-- Name: sustainability_records sustainability_records_record_month_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sustainability_records
    ADD CONSTRAINT sustainability_records_record_month_key UNIQUE (record_month);


--
-- Name: monthly_records uq_patient_month; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monthly_records
    ADD CONSTRAINT uq_patient_month UNIQUE (patient_id, record_month);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_alert_logs_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_logs_id ON public.alert_logs USING btree (id);


--
-- Name: ix_clinical_events_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clinical_events_id ON public.clinical_events USING btree (id);


--
-- Name: ix_dry_weight_assessments_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dry_weight_assessments_id ON public.dry_weight_assessments USING btree (id);


--
-- Name: ix_interim_lab_records_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_interim_lab_records_id ON public.interim_lab_records USING btree (id);


--
-- Name: ix_interim_patient_month; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_interim_patient_month ON public.interim_lab_records USING btree (patient_id, record_month);


--
-- Name: ix_monthly_patient_month; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monthly_patient_month ON public.monthly_records USING btree (patient_id, record_month);


--
-- Name: ix_monthly_records_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monthly_records_id ON public.monthly_records USING btree (id);


--
-- Name: ix_patient_meal_records_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_meal_records_id ON public.patient_meal_records USING btree (id);


--
-- Name: ix_patient_reminders_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_reminders_id ON public.patient_reminders USING btree (id);


--
-- Name: ix_patient_symptom_reports_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_symptom_reports_id ON public.patient_symptom_reports USING btree (id);


--
-- Name: ix_patients_hid_no; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_patients_hid_no ON public.patients USING btree (hid_no);


--
-- Name: ix_patients_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patients_id ON public.patients USING btree (id);


--
-- Name: ix_patients_login_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_patients_login_username ON public.patients USING btree (login_username);


--
-- Name: ix_research_projects_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_research_projects_id ON public.research_projects USING btree (id);


--
-- Name: ix_research_records_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_research_records_id ON public.research_records USING btree (id);


--
-- Name: ix_session_records_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_session_records_id ON public.session_records USING btree (id);


--
-- Name: ix_sustainability_records_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sustainability_records_id ON public.sustainability_records USING btree (id);


--
-- Name: ix_users_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_id ON public.users USING btree (id);


--
-- Name: ix_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);


--
-- Name: alert_logs alert_logs_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_logs
    ADD CONSTRAINT alert_logs_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: clinical_events clinical_events_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clinical_events
    ADD CONSTRAINT clinical_events_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: dry_weight_assessments dry_weight_assessments_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dry_weight_assessments
    ADD CONSTRAINT dry_weight_assessments_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: interim_lab_records interim_lab_records_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interim_lab_records
    ADD CONSTRAINT interim_lab_records_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: interim_lab_records interim_lab_records_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interim_lab_records
    ADD CONSTRAINT interim_lab_records_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.session_records(id);


--
-- Name: monthly_records monthly_records_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monthly_records
    ADD CONSTRAINT monthly_records_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_meal_records patient_meal_records_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_meal_records
    ADD CONSTRAINT patient_meal_records_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_reminders patient_reminders_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_reminders
    ADD CONSTRAINT patient_reminders_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_symptom_reports patient_symptom_reports_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_symptom_reports
    ADD CONSTRAINT patient_symptom_reports_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_symptom_reports patient_symptom_reports_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_symptom_reports
    ADD CONSTRAINT patient_symptom_reports_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.session_records(id);


--
-- Name: research_records research_records_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_records
    ADD CONSTRAINT research_records_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: research_records research_records_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_records
    ADD CONSTRAINT research_records_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.research_projects(id);


--
-- Name: session_records session_records_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.session_records
    ADD CONSTRAINT session_records_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- PostgreSQL database dump complete
--

\unrestrict QBNHpvVmVG0RRbgBSYKlsyNNKbEJoMhq3eUjBm06qKlfPOMcxkMqd0hYBLTH5yH

