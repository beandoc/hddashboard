--
-- PostgreSQL database dump
--

\restrict pGTEtQDgi08x25Aowmw0Ybi5Og9g8RLOKfhq7XTbzDZI0y31chcYjUI54rflNqz

-- Dumped from database version 17.8 (9c8634e)
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
    status character varying,
    message_preview character varying,
    "timestamp" timestamp without time zone,
    sent_at timestamp without time zone
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
-- Name: blood_transfusions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.blood_transfusions (
    id integer NOT NULL,
    patient_id integer,
    transfusion_date date NOT NULL,
    units integer,
    reason character varying,
    "timestamp" timestamp without time zone
);


--
-- Name: blood_transfusions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.blood_transfusions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: blood_transfusions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.blood_transfusions_id_seq OWNED BY public.blood_transfusions.id;


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
-- Name: hospitalisation_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hospitalisation_events (
    id integer NOT NULL,
    patient_id integer NOT NULL,
    admission_date date NOT NULL,
    discharge_date date,
    los_days integer,
    primary_icd character varying,
    primary_diagnosis character varying,
    cause_category character varying,
    readmission_within_30d boolean,
    notes text,
    entered_by character varying,
    created_at timestamp without time zone
);


--
-- Name: hospitalisation_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.hospitalisation_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: hospitalisation_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.hospitalisation_events_id_seq OWNED BY public.hospitalisation_events.id;


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
    patient_id integer,
    record_month character varying,
    entered_by character varying,
    target_dry_weight double precision,
    idwg double precision,
    hb double precision,
    serum_ferritin double precision,
    tsat double precision,
    serum_iron double precision,
    epo_mircera_dose character varying,
    calcium double precision,
    alkaline_phosphate double precision,
    phosphorus double precision,
    albumin double precision,
    ast double precision,
    alt double precision,
    vit_d double precision,
    ipth double precision,
    av_daily_calories double precision,
    av_daily_protein double precision,
    issues character varying,
    "timestamp" timestamp without time zone,
    updated_at timestamp without time zone,
    bp_sys integer,
    bp_dia integer,
    crp double precision,
    urr double precision,
    mcv double precision,
    hb_hematocrit double precision,
    iron_iv_supplement boolean DEFAULT false,
    epo_weekly_units double precision,
    access_type character varying,
    desidustat_dose character varying,
    residual_urine_output double precision,
    single_pool_ktv double precision,
    equilibrated_ktv double precision,
    pre_dialysis_urea double precision,
    post_dialysis_urea double precision,
    serum_creatinine double precision,
    esa_type character varying,
    tibc double precision,
    iv_iron_product character varying,
    iv_iron_dose double precision,
    vitamin_d_analog_dose character varying,
    phosphate_binder_type character varying,
    serum_sodium double precision,
    serum_potassium double precision,
    serum_bicarbonate double precision,
    serum_uric_acid double precision,
    total_cholesterol double precision,
    ldl_cholesterol double precision,
    wbc_count double precision,
    platelet_count double precision,
    hba1c double precision,
    antihypertensive_count integer,
    hrqol_score double precision,
    hospitalization_this_month boolean,
    hospitalization_date date,
    hospitalization_icd_code character varying,
    iv_iron_date date,
    last_prehd_weight double precision,
    antihypertensive_details text,
    npcr double precision,
    ufr double precision,
    prealbumin double precision,
    sga_score character varying,
    mis_score integer,
    neutrophil_count double precision,
    lymphocyte_count double precision,
    il6 double precision,
    tnf_alpha double precision,
    troponin_i double precision,
    nt_probnp double precision,
    hospitalization_diagnosis text,
    hospitalization_icd_diagnosis text,
    hospitalization_details text,
    blood_transfusion_units integer,
    transfusion_date character varying,
    krcrw double precision,
    krcr double precision,
    doctor_notes text,
    reviewed_by character varying,
    reviewed_at timestamp without time zone,
    phosphate_binder_dose_mg double precision,
    phosphate_binder_freq character varying,
    pb_strength double precision,
    ejection_fraction double precision,
    diastolic_dysfunction character varying,
    echo_date date
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
    notes text,
    created_at timestamp without time zone,
    meal_type character varying
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
    reported_at timestamp without time zone,
    symptoms text,
    severity integer,
    notes text,
    session_id integer,
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
    hid_no character varying,
    name character varying NOT NULL,
    relation character varying,
    relation_type character varying,
    sex character varying,
    contact_no character varying,
    email character varying,
    diagnosis character varying,
    hd_wef_date date,
    viral_markers character varying,
    hep_b_status character varying,
    hep_b_date date,
    pneumococcal_date date,
    access_type character varying,
    access_date date,
    dry_weight double precision,
    hd_slot_1 character varying,
    hd_slot_2 character varying,
    hd_slot_3 character varying,
    whatsapp_link character varying,
    whatsapp_notify boolean,
    mail_trigger boolean,
    is_active boolean,
    created_by character varying,
    updated_by character varying,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    relation_name character varying,
    clinical_remarks text,
    dialysis_vintage_months integer DEFAULT 0,
    primary_diagnosis character varying,
    comorbidity_cvd boolean DEFAULT false,
    comorbidity_cvsd boolean DEFAULT false,
    hyperparathyroidism boolean DEFAULT false,
    influenza_date date,
    hep_b_dose1_date date,
    hep_b_dose2_date date,
    hep_b_dose3_date date,
    hep_b_dose4_date date,
    hep_b_titer_date date,
    pcv13_date date,
    ppsv23_date date,
    hz_dose1_date date,
    hz_dose2_date date,
    hd_frequency integer,
    education_level character varying,
    height double precision,
    primary_renal_disease character varying,
    date_esrd_diagnosis date,
    native_kidney_biopsy character varying,
    dm_status character varying,
    htn_status boolean,
    cad_status boolean,
    chf_status boolean,
    history_of_stroke boolean,
    smoking_status character varying,
    alcohol_consumption character varying,
    charlson_comorbidity_index integer,
    previous_krt_modality character varying,
    history_of_renal_transplant boolean,
    transplant_prospect character varying,
    viral_hbsag character varying,
    viral_anti_hcv character varying,
    viral_hiv character varying,
    date_first_cannulation date,
    history_of_access_thrombosis boolean,
    access_intervention_history text,
    catheter_type character varying,
    catheter_insertion_site character varying,
    current_survival_status character varying,
    date_of_death date,
    primary_cause_of_death character varying,
    withdrawal_from_dialysis boolean,
    date_facility_transfer date,
    native_kidney_disease character varying,
    comorbidities text,
    drug_allergies character varying,
    dialysis_modality character varying,
    previous_dialysis_modality character varying,
    healthcare_facility character varying,
    hd_day_1 character varying,
    hd_day_2 character varying,
    hd_day_3 character varying,
    blood_group character varying,
    age integer,
    ejection_fraction double precision,
    login_username character varying,
    hashed_password character varying,
    dm_end_organ_damage boolean,
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
    native_kidney_biopsy_date date,
    native_kidney_biopsy_report text,
    clinical_background text,
    echo_date date,
    echo_report text,
    diastolic_dysfunction character varying,
    handgrip_strength double precision,
    baseline_gcr double precision,
    baseline_vdcr double precision,
    is_black boolean DEFAULT false,
    withdrawal_date date,
    withdrawal_reason character varying,
    withdrawal_clinician character varying,
    date_of_transplant date
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
    medications_administered text,
    idh_episode boolean,
    idh_hypertension boolean,
    muscle_cramps boolean,
    nausea_vomiting boolean,
    chest_pain boolean,
    arrhythmia boolean,
    early_termination boolean,
    reason_early_termination character varying,
    complications_occurred boolean,
    complications_description text,
    complications_management text,
    dialysis_adherence character varying,
    doctor_concerns text,
    next_appointment_id character varying,
    interim_hb double precision,
    interim_k double precision,
    interim_ca double precision,
    interim_trigger character varying,
    intradialytic_exercise_mins integer,
    intradialytic_meals_eaten boolean,
    pre_hd_dyspnea_likert integer,
    post_hd_dyspnea_likert integer,
    is_emergency boolean DEFAULT false,
    reason_emergency character varying,
    urea_peripheral_s double precision,
    urea_arterial_a double precision,
    urea_venous_v double precision,
    access_recirculation_percent double precision,
    access_flow_qa double precision,
    dialysate_flow_direction character varying
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
    created_at timestamp without time zone,
    last_login timestamp without time zone
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
-- Name: variable_definitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.variable_definitions (
    id integer NOT NULL,
    name character varying,
    display_name character varying,
    unit character varying,
    category character varying,
    data_type character varying,
    decimal_places integer,
    threshold_low double precision,
    threshold_high double precision,
    target_low double precision,
    target_high double precision,
    description text,
    show_in_dashboard boolean,
    show_in_timeline boolean,
    is_active boolean,
    alert_direction character varying,
    created_at timestamp without time zone DEFAULT now(),
    created_by character varying DEFAULT 'system'::character varying
);


--
-- Name: variable_definitions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.variable_definitions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: variable_definitions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.variable_definitions_id_seq OWNED BY public.variable_definitions.id;


--
-- Name: variable_values; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.variable_values (
    id integer NOT NULL,
    patient_id integer,
    variable_id integer,
    record_month character varying,
    value_num double precision,
    value_text text,
    entered_by character varying,
    "timestamp" timestamp without time zone,
    entered_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: variable_values_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.variable_values_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: variable_values_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.variable_values_id_seq OWNED BY public.variable_values.id;


--
-- Name: alert_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_logs ALTER COLUMN id SET DEFAULT nextval('public.alert_logs_id_seq'::regclass);


--
-- Name: blood_transfusions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blood_transfusions ALTER COLUMN id SET DEFAULT nextval('public.blood_transfusions_id_seq'::regclass);


--
-- Name: clinical_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clinical_events ALTER COLUMN id SET DEFAULT nextval('public.clinical_events_id_seq'::regclass);


--
-- Name: dry_weight_assessments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dry_weight_assessments ALTER COLUMN id SET DEFAULT nextval('public.dry_weight_assessments_id_seq'::regclass);


--
-- Name: hospitalisation_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hospitalisation_events ALTER COLUMN id SET DEFAULT nextval('public.hospitalisation_events_id_seq'::regclass);


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
-- Name: variable_definitions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.variable_definitions ALTER COLUMN id SET DEFAULT nextval('public.variable_definitions_id_seq'::regclass);


--
-- Name: variable_values id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.variable_values ALTER COLUMN id SET DEFAULT nextval('public.variable_values_id_seq'::regclass);


--
-- Data for Name: alert_logs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.alert_logs (id, patient_id, alert_type, alert_reason, status, message_preview, "timestamp", sent_at) FROM stdin;
\.


--
-- Data for Name: blood_transfusions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.blood_transfusions (id, patient_id, transfusion_date, units, reason, "timestamp") FROM stdin;
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
-- Data for Name: hospitalisation_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.hospitalisation_events (id, patient_id, admission_date, discharge_date, los_days, primary_icd, primary_diagnosis, cause_category, readmission_within_30d, notes, entered_by, created_at) FROM stdin;
\.


--
-- Data for Name: interim_lab_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.interim_lab_records (id, patient_id, session_id, lab_date, record_month, parameter, value, unit, trigger, notes, entered_by, created_at) FROM stdin;
1	19	2	2026-05-01	2026-05	hb	8.3	g/dL	Routine Recheck (Session)	\N		2026-05-01 04:49:13.417907
2	19	2	2026-05-01	2026-05	potassium	6.4	mEq/L	Routine Recheck (Session)	\N		2026-05-01 04:49:13.417911
3	19	2	2026-05-01	2026-05	calcium	8.3	mg/dL	Routine Recheck (Session)	\N		2026-05-01 04:49:13.417914
4	19	3	2026-05-01	2026-05	hb	8.3	g/dL	Routine Recheck (Session)	\N		2026-05-01 04:49:19.487927
5	19	3	2026-05-01	2026-05	potassium	6.4	mEq/L	Routine Recheck (Session)	\N		2026-05-01 04:49:19.48793
6	19	3	2026-05-01	2026-05	calcium	8.3	mg/dL	Routine Recheck (Session)	\N		2026-05-01 04:49:19.487931
7	19	4	2026-05-01	2026-05	hb	8.3	g/dL	Routine Recheck (Session)	\N		2026-05-01 04:49:27.526688
8	19	4	2026-05-01	2026-05	potassium	6.4	mEq/L	Routine Recheck (Session)	\N		2026-05-01 04:49:27.526692
9	19	4	2026-05-01	2026-05	calcium	8.3	mg/dL	Routine Recheck (Session)	\N		2026-05-01 04:49:27.526692
10	19	5	2026-05-01	2026-05	hb	8.3	g/dL	Routine Recheck (Session)	\N		2026-05-01 04:49:30.431713
11	19	5	2026-05-01	2026-05	potassium	6.4	mEq/L	Routine Recheck (Session)	\N		2026-05-01 04:49:30.431716
12	19	5	2026-05-01	2026-05	calcium	8.3	mg/dL	Routine Recheck (Session)	\N		2026-05-01 04:49:30.431716
13	19	6	2026-05-01	2026-05	hb	8.3	g/dL	Routine Recheck (Session)	\N		2026-05-01 04:49:39.807706
14	19	6	2026-05-01	2026-05	potassium	6.4	mEq/L	Routine Recheck (Session)	\N		2026-05-01 04:49:39.807708
15	19	6	2026-05-01	2026-05	calcium	8.3	mg/dL	Routine Recheck (Session)	\N		2026-05-01 04:49:39.807709
16	19	7	2026-05-01	2026-05	hb	8.3	g/dL	Routine Recheck (Session)	\N		2026-05-01 04:49:46.815353
17	19	7	2026-05-01	2026-05	potassium	6.4	mEq/L	Routine Recheck (Session)	\N		2026-05-01 04:49:46.815356
18	19	7	2026-05-01	2026-05	calcium	8.3	mg/dL	Routine Recheck (Session)	\N		2026-05-01 04:49:46.815357
19	19	8	2026-05-01	2026-05	hb	8.3	g/dL	Routine Recheck (Session)	\N		2026-05-01 04:55:18.607422
20	19	8	2026-05-01	2026-05	potassium	6.4	mEq/L	Routine Recheck (Session)	\N		2026-05-01 04:55:18.607427
21	19	8	2026-05-01	2026-05	calcium	8.3	mg/dL	Routine Recheck (Session)	\N		2026-05-01 04:55:18.607427
\.


--
-- Data for Name: monthly_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.monthly_records (id, patient_id, record_month, entered_by, target_dry_weight, idwg, hb, serum_ferritin, tsat, serum_iron, epo_mircera_dose, calcium, alkaline_phosphate, phosphorus, albumin, ast, alt, vit_d, ipth, av_daily_calories, av_daily_protein, issues, "timestamp", updated_at, bp_sys, bp_dia, crp, urr, mcv, hb_hematocrit, iron_iv_supplement, epo_weekly_units, access_type, desidustat_dose, residual_urine_output, single_pool_ktv, equilibrated_ktv, pre_dialysis_urea, post_dialysis_urea, serum_creatinine, esa_type, tibc, iv_iron_product, iv_iron_dose, vitamin_d_analog_dose, phosphate_binder_type, serum_sodium, serum_potassium, serum_bicarbonate, serum_uric_acid, total_cholesterol, ldl_cholesterol, wbc_count, platelet_count, hba1c, antihypertensive_count, hrqol_score, hospitalization_this_month, hospitalization_date, hospitalization_icd_code, iv_iron_date, last_prehd_weight, antihypertensive_details, npcr, ufr, prealbumin, sga_score, mis_score, neutrophil_count, lymphocyte_count, il6, tnf_alpha, troponin_i, nt_probnp, hospitalization_diagnosis, hospitalization_icd_diagnosis, hospitalization_details, blood_transfusion_units, transfusion_date, krcrw, krcr, doctor_notes, reviewed_by, reviewed_at, phosphate_binder_dose_mg, phosphate_binder_freq, pb_strength, ejection_fraction, diastolic_dysfunction, echo_date) FROM stdin;
4	4	2026-04	admin	\N	2	8.4	\N	\N	\N	Mircera 100	8.7	73	1.6	2.9	13	18	\N	\N	\N	\N		2026-04-16 11:54:53.525454	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
10	10	2026-04	admin	\N	2.9	7.9	1329	\N	62	MIRCERA 100	6.8	231	3.6	3.6	63	79	\N	\N	\N	\N		2026-04-16 11:55:01.001782	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
14	14	2026-04	admin	\N	2	7.8	2492	\N	97	MIRCERA 100	7.7	109	5	3.3	9	21	\N	\N	\N	\N		2026-04-16 11:55:02.914402	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
15	15	2026-04	admin	\N	4	9.3	535	\N	\N	MIRCERA 100	9.1	133	5.3	3.1	20	15	\N	\N	\N	\N		2026-04-16 11:55:03.311108	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
16	16	2026-04	admin	\N	1.8	11.6	1800	\N	99	MIRCERA 100	\N	80	\N	3.5	3	17	\N	\N	\N	\N		2026-04-16 11:55:03.730221	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
17	17	2026-04	admin	\N	2.5	7.4	1205	\N	94	MIRCERA 100	9.4	96	2.9	3.1	18	24	\N	\N	\N	\N		2026-04-16 11:55:04.132035	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
21	21	2026-04	admin	\N	2.5	9.9	209	\N	40	EPO 4k	8.2	139	6	3.2	16	13	\N	\N	\N	\N		2026-04-16 11:55:06.368305	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
23	23	2026-04	admin	\N	2.2	9.9	864	\N	16	MIRCERA 100	8.5	129	3.7	3.4	10	10	\N	\N	\N	\N		2026-04-16 11:55:07.114179	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
24	24	2026-04	admin	\N	2	9.3	1654	\N	106	Erypeg 75	7.5	257	3.9	3.5	22	15	\N	\N	\N	\N		2026-04-16 11:55:07.489335	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
26	26	2026-04	admin	\N	2.5	10.1	272	\N	32	EPO 10K	8.3	92	2.2	2.6	15	20	\N	\N	\N	\N		2026-04-16 11:55:08.211901	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
30	30	2026-04	admin	\N	2.5	8.1	451	\N	49	Mircera 100	6.9	205	3.2	2.8	3	19	\N	\N	\N	\N		2026-04-16 11:55:11.386095	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
32	32	2026-04	admin	\N	2	7.9	1405	\N	122	Mircera 75	8.4	76	4.6	3.4	18	23	\N	\N	\N	\N		2026-04-16 11:55:12.195293	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
33	33	2026-04	admin	\N	\N	9.3	330	\N	18		8.8	133	\N	1.7	15	16	\N	\N	\N	\N		2026-04-16 11:55:12.665994	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
36	36	2026-04	admin	\N	1	7.3	\N	\N	75	Mircera 100	\N	\N	\N	2.5	20	16	\N	\N	\N	\N		2026-04-16 11:55:14.085638	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
37	37	2026-04	admin	\N	2.3	8	\N	\N	\N	Mircera 100	8.3	68	3.3	2.6	10	13	\N	\N	\N	\N		2026-04-16 11:55:14.46275	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
38	38	2026-04	admin	\N	2.5	9.4	138	\N	90		8.9	182	3.8	3.8	23	14	14.78	\N	\N	\N		2026-04-16 11:55:15.081635	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
39	39	2026-04	admin	\N	2	7.3	\N	\N	98	Mircera 100	\N	\N	\N	2.7	25	30	\N	\N	\N	\N		2026-04-16 11:55:15.529431	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
29	29	2026-04	admin	\N	0.3	7.9	120	\N	\N	Mircera 100	9.4	68	3.9	3.5	\N	\N	\N	\N	\N	\N		2026-04-16 19:29:58.25648	2026-04-16 19:29:58.258696	\N	\N	\N	\N	\N	\N	f	100	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
40	1	2025-03	\N	\N	2.3	8.2	\N	\N	\N		7.4	72	4.4	3	9	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890532	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
41	3	2025-03	\N	\N	\N	11.5	\N	\N	\N		9.1	100	5.3	3	14	25	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890537	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
42	5	2025-03	\N	\N	2	11.9	\N	\N	\N	Epo 4K	8.3	102	2.6	3.2	13	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890538	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
43	6	2025-03	\N	\N	1.6	10.1	\N	\N	\N	Ery peg 100	6.9	215	3.8	2.2	23	27	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890538	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
44	10	2025-03	\N	\N	2.2	10.3	\N	\N	\N	100 mcg	8.8	1214	8.9	3.3	4	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890541	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
45	17	2025-03	\N	\N	2.1	8.6	\N	\N	\N	100 mcg	8.4	101	7.6	3.2	21	38	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890542	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
46	12	2025-03	\N	\N	2.7	10.7	\N	\N	\N	100 mcg	6.9	192	5.8	3.2	12	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890542	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
47	13	2025-03	\N	\N	2.2	7.4	\N	\N	\N	100 mcg	6.8	175	8.5	3	12	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890543	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
48	14	2025-03	\N	\N	\N	8.2	\N	\N	\N		7.5	91	5.1	2.9	17	31	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890544	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
49	16	2025-03	\N	\N	1.4	11.9	\N	\N	\N		9.3	56	6.8	3.2	7	20	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890544	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
50	18	2025-03	\N	\N	1.9	10	\N	\N	\N		7.2	767	3.8	3	18	27	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890545	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
18	18	2026-04	admin	60	1	10	\N	\N	71	MIRCERA 100	8.4	748	4.3	4	22	30	\N	\N	\N	\N		2026-04-22 06:20:59.986019	\N	140	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	-30	\N	\N	79	60	8.1		\N		\N			143	4.8	\N	5.6	\N	\N	7700	1.18	\N	\N	\N	f	\N		\N	61		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
20	20	2026-04	admin	70.5	1	9.6	691	\N	98	Mircera (CERA) 100mcg Every 2 Weeks	8.1	61	4.1	2.5	16	18	\N	\N	\N	\N		2026-05-14 05:29:40.862403	\N	140	\N	\N	\N	\N	\N	f	10000	RC AVF Rt	None	\N	\N	\N	65	20	7.3	Mircera (CERA)	\N		\N			137	4.8	\N	5.4	108	56	7.5	2.71	\N	\N	\N	f	\N		\N	70.6		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
35	35	2026-04	admin	71	0.5	9.8	\N	\N	57	Mircera 100 	8.2	94	4.3	3.5	58	122	\N	\N	\N	\N		2026-04-22 06:33:58.148756	\N	140	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	137	72	5.1		\N		\N			135	5.2	\N	140	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	71.5		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
2	2	2026-04	admin	61	1	7	804	\N	59	M-75/15	8.4	144	3.9	2.5	52	24	\N	\N	\N	\N		2026-04-21 10:29:20.240493	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	\N	\N	\N		\N		\N			\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
9	9	2026-04	admin	40	2.5	13	425	\N	60	MIRCERA 100 MCG	8.4	64	3.7	3.5	17	13	\N	\N	\N	\N		2026-04-30 11:16:34.522853	\N	160	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	61	17	6.9		\N		\N			133	3.3	\N	4.8	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	41.5		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
28	28	2026-04	admin	65.5	0	9.2	836	\N	178	Mircera 100	8	145	4.3	3.2	21	30	\N	\N	\N	\N		2026-04-22 05:55:17.133688	\N	124	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	133	37	9.5		\N		\N			140	3.9	\N	6.4	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	65.7		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
34	34	2026-04	admin	38.9	1	9	1256	105	57	Mircera 100	8.4	117	4	3.4	14	15	\N	\N	\N	\N		2026-04-23 05:20:13.364556	\N	160	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	81	11	8.7		\N		\N			136	4.8	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	38.9		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
22	22	2026-04	admin	68.5	0	10.9	849	\N	79	Mircera (CERA) 75mcg Weekly	8.8	106	5.3	3.5	4	18	\N	\N	\N	\N		2026-05-05 06:41:02.566197	\N	\N	\N	\N	\N	\N	\N	f	15000	RC AVF Rt	None	\N	\N	\N	65	\N	8.49	Mircera (CERA)	\N		\N			139	5.4	\N	\N	\N	\N	5.9	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
1	1	2026-04	admin	74	3.5	10.8	468	\N	41	Mircera (CERA) 100mcg Monthly	7.9	61	6	3	7	19	\N	\N	\N	\N		2026-05-12 10:17:32.787348	\N	140	\N	\N	\N	\N	\N	f	5000	RC AVF Rt	None	\N	\N	\N	\N	\N	\N	Mircera (CERA)	\N		\N			\N	\N	\N	-0.05	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
31	31	2026-04	admin	44	4.15	8.3	1617	\N	30	Mircera 100	7.2	91	1.8	1.6	21	11	\N	\N	\N	\N	test notes 	2026-05-04 07:51:42.56638	\N	140	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	102	52	4.2		\N		\N			141	4.7	\N	4.5	\N	\N	4800	1.59	\N	\N	\N	f	\N		\N	48.2		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
19	19	2026-04	admin	53	2	8.5	409	\N	118	MIRCERA75	9.3	279	4.6	3.4	19	28	\N	\N	\N	\N		2026-05-05 08:22:38.086387	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	\N	\N	\N	Mircera (CERA)	\N		\N			\N	\N	\N	\N	\N	\N	\N	9.3	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
51	19	2025-03	\N	\N	1.3	9.1	\N	\N	\N		9	111	3.5	3	18	55	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890545	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
52	10	2025-04	\N	\N	2.2	8.5	\N	\N	\N	100 mcg	8.8	\N	8.9	3	19	11	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890546	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
53	13	2025-04	\N	\N	2.2	6.7	\N	\N	\N	100 mcg	6.8	\N	8.5	3	21	11	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890546	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
54	17	2025-04	\N	\N	2.1	7.8	\N	\N	\N	100 mcg	9.4	\N	9.4	3.2	21	38	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890546	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
55	12	2025-04	\N	\N	2.7	10	\N	\N	\N	100 mcg	7.3	\N	5.9	3.1	10	11	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890547	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
56	19	2025-04	\N	\N	\N	9.3	\N	\N	\N		9	\N	7.2	3.5	24	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890547	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
57	6	2025-04	\N	\N	1.6	8.9	\N	\N	\N	Ery peg 100	6.3	\N	3.3	2.3	18	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890548	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
58	16	2025-04	\N	\N	\N	10.6	\N	\N	\N		9.3	\N	6.8	3.2	11	12	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890548	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
59	5	2025-04	\N	\N	2	10.1	\N	\N	\N	Epo 4K	8.3	\N	5.2	3.3	13	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890549	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
60	14	2025-04	\N	\N	\N	8	\N	\N	\N		7.5	\N	5.1	3.1	18	22	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890549	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
61	1	2025-04	\N	\N	\N	7.4	\N	\N	\N		8.2	\N	5.7	2.5	10	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890549	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
62	3	2025-04	\N	\N	\N	12.2	\N	\N	\N		8.3	\N	6.6	3.2	16	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89055	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
63	18	2025-04	\N	\N	1.9	12.3	\N	\N	\N	-	8.7	\N	4.2	3.1	18	19	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89055	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
64	1	2025-05	\N	\N	2.3	10.2	\N	\N	\N	M-100/30	7.8	75	4.5	3	20	21	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890551	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
65	2	2025-05	\N	\N	1	10	\N	\N	\N	M-75/15	8.8	114	5.1	3	16	21	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890551	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
66	3	2025-05	\N	\N	2.5	10.3	\N	\N	\N	M-100/30	8.4	132	5.3	3.3	14	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890551	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
67	4	2025-05	\N	\N	1.5	9.3	\N	\N	\N		7.9	61	4.7	3.5	\N	\N	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890552	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
68	5	2025-05	\N	\N	2	10.1	\N	\N	\N		\N	170	\N	3.3	16	12	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890552	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
69	6	2025-05	\N	\N	1.6	9.1	\N	\N	\N	ERIPACK100/15	6.7	257	2.9	2.5	24	14	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890553	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
70	7	2025-05	\N	\N	2	13	\N	\N	\N		6.3	223	4.5	2.4	24	42	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890553	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
71	9	2025-05	\N	\N	2.5	9.5	\N	\N	\N	MIRCERA 100 MCG	8.8	68	5.3	3.3	19	19	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890553	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
72	10	2025-05	\N	\N	2.2	10.1	\N	\N	\N		6.2	565	4.7	3.1	13	10	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890554	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
73	11	2025-05	\N	\N	2.8	7.4	\N	\N	\N		8.3	118	5.3	2.5	30	20	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890554	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
74	12	2025-05	\N	\N	2.7	10.3	\N	\N	\N	MIRCERA 50	\N	160	6.6	3.2	18	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890555	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
75	13	2025-05	\N	\N	2.2	9.9	\N	\N	\N	MIRCERA100	8.9	224	3.9	\N	23	23	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890555	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
76	14	2025-05	\N	\N	2.5	8.6	\N	\N	\N	MIRCERA 100	7.9	101	6.7	3	23	23	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890555	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
77	15	2025-05	\N	\N	2.5	8.8	\N	\N	\N		9.1	92	5.7	2.8	14	12	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890556	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
78	16	2025-05	\N	\N	1.4	\N	\N	\N	\N	MIRCERA 100	\N	\N	\N	3.3	12	7	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890556	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
79	18	2025-05	\N	\N	2	11.8	\N	\N	\N	MIRCERA 100	9	781	1.6	3.3	24	33	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890557	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
80	19	2025-05	\N	\N	1.8	11.2	\N	\N	\N	MIRCERA75	8.2	150	4.9	3.1	16	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890557	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
81	20	2025-05	\N	\N	1	10.6	\N	\N	\N		8.2	51	6.2	3.1	23	31	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890557	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
82	8	2025-05	\N	\N	1.2	8.6	\N	\N	\N		9.6	87	3.3	3	15	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890558	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
83	17	2025-05	\N	\N	2.5	9.9	\N	\N	\N	MIRCERA 75	9.6	77	5.1	3.1	20	31	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890558	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
84	1	2025-07	\N	\N	2.3	11.2	\N	\N	\N	M-100/30	7.5	52	4.3	2.6	16	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890559	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
85	2	2025-07	\N	\N	1	11.5	\N	\N	\N	M-75/15	8.3	125	5.4	3.2	26	39	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890559	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
86	3	2025-07	\N	\N	2.5	10.8	\N	\N	\N	M-100/30	7.7	124	6.3	3.1	9	23	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890559	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
87	4	2025-07	\N	\N	1.5	11.6	\N	\N	\N		7.4	63	4	3.5	9	20	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89056	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
88	5	2025-07	\N	\N	2	10.3	\N	\N	\N		7.5	158	4.9	3.3	14	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89056	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
89	6	2025-07	\N	\N	1.6	8.6	\N	\N	\N	ERIPACK100/15	6.4	277	3.4	2.5	50	46	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890561	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
90	7	2025-07	\N	\N	2	13.3	\N	\N	\N		8.5	185	4	3.3	18	44	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890561	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
91	9	2025-07	\N	\N	2.5	9.8	\N	\N	\N	MIRCERA 100 MCG	8.5	57	5.2	3.3	16	26	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890561	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
92	10	2025-07	\N	\N	2.2	14.5	\N	\N	\N	MIRCERA 100	5.4	610	5.6	\N	\N	\N	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890562	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
93	11	2025-07	\N	\N	2.8	7.3	\N	\N	\N		7.3	79	5.8	2.2	17	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890562	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
94	12	2025-07	\N	\N	2.7	13.2	\N	\N	\N	MIRCERA 50	6	157	8	3.3	9	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890563	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
95	13	2025-07	\N	\N	2.2	9.1	\N	\N	\N	MIRCERA100	7.9	145	\N	3.4	\N	\N	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890563	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
96	14	2025-07	\N	\N	2.5	8.3	\N	\N	\N	MIRCERA 100	8.2	96	4.1	2.6	11	31	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890563	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
97	15	2025-07	\N	\N	2.5	7.2	\N	\N	\N	-	\N	157	\N	3.9	13	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890564	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
98	16	2025-07	\N	\N	1.4	11.3	\N	\N	\N	MIRCERA 100	9.6	55	8	3.3	12	7	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890564	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
99	17	2025-07	\N	\N	2.5	8.5	\N	\N	\N	MIRCERA 75	8	56	8.3	6.6	15	21	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890565	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
100	18	2025-07	\N	\N	2	12.4	\N	\N	\N	MIRCERA 100	8.2	164	5.5	3.1	27	39	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890565	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
101	19	2025-07	\N	\N	1.8	11.2	\N	\N	\N	MIRCERA75	8.5	158	5	3.3	15	24	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890566	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
102	20	2025-07	\N	\N	1	11.3	\N	\N	\N		7.4	57	6	6.6	13	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890566	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
103	33	2025-07	\N	\N	2	9.3	\N	\N	\N	MIRCERA 75	7.6	97	6.2	3.4	21	22	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890566	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
104	21	2025-07	\N	\N	2.5	10.7	\N	\N	\N	EPO 4k	5.8	189	5	3.3	19	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890567	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
105	22	2025-07	\N	\N	1	8.5	\N	\N	\N	Mircera 75	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890567	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
106	23	2025-07	\N	\N	1	8.3	\N	\N	\N	MIRCERA 100	8.1	139	4.7	3.1	26	21	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890568	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
107	1	2025-08	\N	\N	2.5	11.7	\N	\N	\N	M-100/30	8	78	4	3	9	20	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890568	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
108	2	2025-08	\N	\N	1	8.8	\N	\N	\N	M-75/15	8.1	101	3.3	2.6	60	49	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890569	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
109	3	2025-08	\N	\N	2.5	9.9	\N	\N	\N	M-100/30	8.3	135	5	3.4	13	17	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890569	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
110	4	2025-08	\N	\N	2	13.1	\N	\N	\N	EPO 10K	7.9	70	4.4	3.5	14	10	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890569	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
111	5	2025-08	\N	\N	2	11.1	\N	\N	\N	-	8.2	201	4	3.3	14	9	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89057	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
112	6	2025-08	\N	\N	1.6	9.7	\N	\N	\N	ERIPeg100/15	8.1	342	4.7	2.7	13	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89057	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
113	7	2025-08	\N	\N	2	10.9	\N	\N	\N	EPO10K	\N	225	4	3	18	19	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890571	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
114	9	2025-08	\N	\N	2.5	10	\N	\N	\N	MIRCERA 100 MCG	8.3	84	4.8	3.5	21	12	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890571	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
115	10	2025-08	\N	\N	2.2	10.6	\N	\N	\N	MIRCERA 100	6.8	629	4.3	3.1	13	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890571	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
116	11	2025-08	\N	\N	2.8	9.8	\N	\N	\N	MIRCERA 75	8.7	179	4.1	3.3	\N	\N	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890572	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
117	12	2025-08	\N	\N	2.7	9.5	\N	\N	\N	MIRCERA 75	7.1	115	6	3.3	11	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890572	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
118	13	2025-08	\N	\N	2.2	11.1	\N	\N	\N	MIRCERA 100	8.5	315	\N	3.7	16	11	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890573	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
119	14	2025-08	\N	\N	2	8.3	\N	\N	\N	MIRCERA 100	7	117	6.7	2.9	16	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890573	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
120	15	2025-08	\N	\N	2.5	9.2	\N	\N	\N	MIRCERA 100	8.4	102	7.5	2.8	31	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890574	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
121	16	2025-08	\N	\N	2.5	10.7	\N	\N	\N	MIRCERA 100	9.1	71	7.1	3.6	15	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890574	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
122	17	2025-08	\N	\N	2.5	8.6	\N	\N	\N	MIRCERA 100	9.6	83	4.3	3.1	13	26	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890575	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
123	18	2025-08	\N	\N	2	11.7	\N	\N	\N	MIRCERA 100	\N	720	\N	2.9	24	22	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890575	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
124	19	2025-08	\N	\N	2	12	\N	\N	\N	MIRCERA 75	7.8	226	4.7	3.1	24	22	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890575	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
125	20	2025-08	\N	\N	2.5	10	\N	\N	\N	EPO 10K	7.1	68	5.9	3.3	\N	\N	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890576	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
126	33	2025-08	\N	\N	2	9.7	\N	\N	\N	MIRCERA 75	\N	117	\N	3.4	22	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890576	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
127	21	2025-08	\N	\N	2.5	11.7	\N	\N	\N	EPO 4k	7.9	193	3.8	3.1	17	10	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890577	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
128	22	2025-08	\N	\N	1	9.4	\N	\N	\N	Mircera 75	8.1	109	4.4	2.8	15	9	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890577	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
129	23	2025-08	\N	\N	1	8.5	\N	\N	\N	MIRCERA 100	8.4	350	5.7	3.1	16	20	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890578	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
130	24	2025-08	\N	\N	2	8.4	\N	\N	\N	Erypeg 75	9.1	\N	3.8	\N	\N	\N	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890578	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
131	1	2025-09	\N	\N	3.5	10.2	\N	\N	\N	M-100/30	8	61	6	2.7	10	24	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890578	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
132	2	2025-09	\N	\N	1	9	\N	\N	\N	M-75/15	8.1	131	3.9	2.7	46	67	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890579	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
133	3	2025-09	\N	\N	2.5	9.6	\N	\N	\N	M-100/30	7.7	159	6.3	3.7	\N	25	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890579	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
134	4	2025-09	\N	\N	2	11.3	\N	\N	\N	Mircera 100	7.9	90	5.3	3.4	17	26	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89058	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
135	5	2025-09	\N	\N	2	9.7	\N	\N	\N	Mircera 75	7.5	205	4.2	3.2	14	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89058	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
136	6	2025-09	\N	\N	1.6	10.9	\N	\N	\N	ERIPeg 100/15	7.8	349	4.8	2.5	15	14	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89058	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
137	7	2025-09	\N	\N	2	12.4	\N	\N	\N	EPO 10K	7.1	268	3.7	3	15	29	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890581	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
138	9	2025-09	\N	\N	2.5	8.9	\N	\N	\N	MIRCERA 100 MCG	7.5	85	5.8	3.4	16	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890581	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
139	10	2025-09	\N	\N	2.2	10.4	\N	\N	\N	MIRCERA 100	7	609	3.7	3.2	14	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890582	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
140	11	2025-09	\N	\N	2.5	10	\N	\N	\N	MIRCERA 75	7.6	241	6.4	3.5	40	46	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890582	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
141	12	2025-09	\N	\N	2.5	11.1	\N	\N	\N	MIRCERA 75	6.8	169	7	3.2	11	20	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890582	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
142	13	2025-09	\N	\N	2.2	11.6	\N	\N	\N	MIRCERA 100	\N	262	\N	3.3	22	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890583	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
143	14	2025-09	\N	\N	2	9.3	\N	\N	\N	MIRCERA 100	7.1	118	6.1	3.3	20	31	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890583	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
144	15	2025-09	\N	\N	3.5	9.4	\N	\N	\N	MIRCERA 100	8.2	99	7.2	3	11	25	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890584	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
145	16	2025-09	\N	\N	1.8	9.7	\N	\N	\N	MIRCERA 100	7.9	77	8.2	3.3	19	20	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890584	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
146	17	2025-09	\N	\N	2.5	9.4	\N	\N	\N	MIRCERA 100	9.1	98	5.3	3.1	11	23	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890584	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
147	18	2025-09	\N	\N	2	12.2	\N	\N	\N	MIRCERA 100	7.9	789	5.1	3.1	64	86	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890585	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
148	19	2025-09	\N	\N	2	13.2	\N	\N	\N	MIRCERA 75	8.7	263	7.9	3.1	10	25	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890585	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
149	20	2025-09	\N	\N	2.5	10.6	\N	\N	\N	EPO 10K	6.5	63	5.9	2.8	18	41	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890586	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
150	21	2025-09	\N	\N	2.5	10.3	\N	\N	\N	EPO 4k	7.4	170	4.1	3.2	17	10	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890586	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
151	22	2025-09	\N	\N	1	10.3	\N	\N	\N	Mircera 75	7.7	106	3.9	2.9	21	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890587	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
152	23	2025-09	\N	\N	1	12.4	\N	\N	\N	MIRCERA 100	7.8	396	7.2	3.5	10	14	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890587	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
153	24	2025-09	\N	\N	2	9	\N	\N	\N	Erypeg 75	7	205	3.4	3.2	18	26	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890588	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
154	25	2025-09	\N	\N	2.2	9.2	\N	\N	\N	Mircera 75	7.8	84	6.7	3	13	19	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890588	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
155	26	2025-09	\N	\N	1	6.9	\N	\N	\N		7.2	93	4.6	2.2	18	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890588	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
156	27	2025-09	\N	\N	1.5	11.6	\N	\N	\N	Mircera 75	8.7	92	7.6	3	15	23	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890589	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
157	28	2025-09	\N	\N	1	\N	\N	\N	\N	Mircera 100	7.1	120	6.4	3.2	23	27	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890589	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
158	29	2025-09	\N	\N	0.3	8.4	\N	\N	\N	Mircera 100	7.1	61	4.4	2.9	21	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89059	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
159	30	2025-09	\N	\N	2.5	8.8	\N	\N	\N	Mircera 100	5.2	100	5.3	2.5	11	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89059	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
160	1	2025-10	\N	\N	3.5	9.6	\N	\N	\N	M-100/30	7.9	71	4.1	2.9	18	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890591	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
161	2	2025-10	\N	\N	1	8.8	\N	\N	\N	M-75/15	8.1	149	3.3	2.4	40	67	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890591	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
162	3	2025-10	\N	\N	2.5	9.1	\N	\N	\N	M-100/30	7.9	114	4.8	3.2	17	17	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890591	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
163	4	2025-10	\N	\N	2	11.6	\N	\N	\N	Mircera 100	8.2	62	4.5	3.5	13	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890592	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
164	5	2025-10	\N	\N	2	11.1	\N	\N	\N	Mircera 75	7.9	251	4.5	3.3	11	14	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890593	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
165	6	2025-10	\N	\N	1.6	9.2	\N	\N	\N	ERIPeg 100/15	7	340	3.6	2.4	35	26	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890593	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
166	7	2025-10	\N	\N	2	\N	\N	\N	\N	EPO 10K	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890594	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
167	9	2025-10	\N	\N	2.5	\N	\N	\N	\N	MIRCERA 100 MCG	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890594	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
168	10	2025-10	\N	\N	2.2	10.7	\N	\N	\N	MIRCERA 100	5.5	405	4.1	3	16	14	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890595	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
169	11	2025-10	\N	\N	2.5	10	\N	\N	\N	MIRCERA 75	8.5	211	5.9	3.2	18	24	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890595	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
170	12	2025-10	\N	\N	2.5	9.3	\N	\N	\N	MIRCERA 75	7.3	160	6	2.9	12	14	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890596	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
171	13	2025-10	\N	\N	2.2	11.9	\N	\N	\N	MIRCERA 100	8.2	430	3.9	3.3	13	20	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890596	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
172	14	2025-10	\N	\N	2	8.6	\N	\N	\N	MIRCERA 100	7.7	133	5.4	7.2	11	28	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890597	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
173	15	2025-10	\N	\N	3.5	9.3	\N	\N	\N	MIRCERA 100	8.6	103	9.5	2.6	12	21	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890597	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
174	16	2025-10	\N	\N	1.8	8.5	\N	\N	\N	MIRCERA 100	8.9	82	8	3.1	16	20	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890598	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
175	17	2025-10	\N	\N	2.5	9	\N	\N	\N	MIRCERA 100	9.3	97	6.8	3	7	19	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890598	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
176	18	2025-10	\N	\N	2	12.6	\N	\N	\N	MIRCERA 100	8.2	776	4.6	3	62	74	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890599	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
177	19	2025-10	\N	\N	2	12.4	\N	\N	\N	MIRCERA 75	9.1	225	7.9	6.4	18	24	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890599	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
178	20	2025-10	\N	\N	2.5	10.5	\N	\N	\N	EPO 10K	7.6	59	6.2	3	12	23	\N	\N	\N	\N	\N	2026-04-17 09:37:17.8906	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
179	21	2025-10	\N	\N	2.5	10.4	\N	\N	\N	EPO 4k	7.2	132	4.9	3.1	15	19	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890601	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
180	22	2025-10	\N	\N	1	10.5	\N	\N	\N	Mircera 75	8.6	106	3.9	2.4	16	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890601	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
181	23	2025-10	\N	\N	1	11.6	\N	\N	\N	MIRCERA 100	7.8	376	6.6	3.3	15	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890602	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
182	24	2025-10	\N	\N	2	9.1	\N	\N	\N	Erypeg 75	7.6	236	4.3	3.2	16	33	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890602	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
183	25	2025-10	\N	\N	2.2	8.8	\N	\N	\N	Mircera 75	7.3	108	4.5	3.1	63	97	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890603	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
184	26	2025-10	\N	\N	1	7.8	\N	\N	\N		7.7	89	4	2.6	18	20	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890604	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
185	28	2025-10	\N	\N	1	7.3	\N	\N	\N	Mircera 100	8	137	4.4	3	16	25	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890604	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
186	29	2025-10	\N	\N	0.3	9.2	\N	\N	\N	Mircera 100	8.8	25	4.8	3.3	21	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890604	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
187	30	2025-10	\N	\N	2.5	7.8	\N	\N	\N	Mircera 100	5.7	132	4.1	2.6	9	26	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890605	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
188	31	2025-10	\N	\N	0.5	8.8	\N	\N	\N		7.7	84	2.6	2.1	25	12	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890605	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
189	32	2025-10	\N	\N	0.3	7.2	\N	\N	\N		8.6	64	4.1	2.4	28	33	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890606	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
190	1	2025-11	\N	\N	3.5	9.9	\N	\N	\N	M-100/30	7.7	65	4.2	3	10	19	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890606	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
191	2	2025-11	retrospective_seed	\N	1.2	8.5	750	25	\N	EPO 6000u TIW	9.2	135	4.1	2.8	45	50	12	380	1400	0.8	\N	2026-04-17 09:37:17.890607	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
192	3	2025-11	\N	\N	2.5	9.4	\N	\N	\N	M-100/30	8.3	147	5.3	3.2	17	39	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890607	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
193	4	2025-11	\N	\N	2	10.8	\N	\N	\N	Mircera 100	\N	68	6.3	3.5	5	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890608	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
194	5	2025-11	\N	\N	2	11.3	\N	\N	\N	Mircera 75	7.7	276	4.1	3.3	15	22	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890608	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
195	6	2025-11	\N	\N	3	8.1	\N	\N	\N	ERIPeg 100/15	7.4	340	3.6	2.1	20	14	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890609	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
196	7	2025-11	\N	\N	2	13.5	\N	\N	\N	EPO 10K	9.2	262	2.3	3.4	28	32	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890609	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
197	9	2025-11	\N	\N	2.5	11.8	\N	\N	\N	MIRCERA 100 MCG	7.6	77	3.6	3.8	21	7	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890609	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
198	10	2025-11	\N	\N	2.9	10	\N	\N	\N	MIRCERA 100	7.2	495	3	3	9	12	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89061	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
199	11	2025-11	\N	\N	2.8	9.7	\N	\N	\N	MIRCERA 75	8.1	194	5.1	3.1	22	31	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89061	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
200	12	2025-11	\N	\N	2.5	9.5	\N	\N	\N	MIRCERA 75	7	174	6.6	3.5	14	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890611	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
201	13	2025-11	\N	\N	2.2	9.6	\N	\N	\N	MIRCERA 100	9.1	416	2.7	3.6	19	40	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890611	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
202	14	2025-11	\N	\N	2	\N	\N	\N	\N	MIRCERA 100	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890612	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
203	15	2025-11	\N	\N	4	9.3	\N	\N	\N	MIRCERA 100	8.8	93	6.8	3.1	9	21	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890612	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
204	16	2025-11	\N	\N	1.8	8.9	\N	\N	\N	MIRCERA 100	9.1	74	7	3.3	16	12	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890613	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
205	17	2025-11	\N	\N	2.5	8.4	\N	\N	\N	MIRCERA 100	8.9	81	\N	2.9	12	14	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890613	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
206	18	2025-11	\N	\N	2	11.9	\N	\N	\N	MIRCERA 100	8.7	888	3	3.4	26	37	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890614	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
207	19	2025-11	\N	\N	2	11.7	\N	\N	\N	MIRCERA 75	8.8	280	6.4	3.4	10	23	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890614	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
208	20	2025-11	\N	\N	2.5	10.9	\N	\N	\N	EPO 10K	7.7	55	6.2	3.1	12	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890614	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
209	21	2025-11	retrospective_seed	\N	2.1	9.2	180	28	\N	EPO 4000u TIW	8.4	140	5.8	3	32	28	18	310	1600	0.9	\N	2026-04-17 09:37:17.890615	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
210	22	2025-11	\N	\N	500	10.6	\N	\N	\N	Mircera 75	8	100	4.7	3.1	21	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890615	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
211	23	2025-11	\N	\N	2.2	10.7	\N	\N	\N	MIRCERA 100	8.1	260	4.4	3.7	11	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890616	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
212	24	2025-11	\N	\N	2	9.9	\N	\N	\N	Erypeg 75	7.6	255	5.7	3.5	25	41	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890616	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
213	25	2025-11	\N	\N	2.5	10	\N	\N	\N	Mircera 75	8.3	108	5	3.5	27	32	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890616	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
214	26	2025-11	\N	\N	2.5	9.9	\N	\N	\N	EPO 10K	8.5	113	6.4	2.7	8	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890617	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
215	27	2025-11	\N	\N	2.5	9.8	\N	\N	\N	Mircera 75	8.7	92	7.6	3	15	23	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890617	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
216	28	2025-11	\N	\N	500	6.1	\N	\N	\N	Mircera 100	8.6	100	2.7	2.8	10	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890618	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
217	29	2025-11	\N	\N	0.3	8.8	\N	\N	\N	Mircera 100	9.7	69	3.1	3.5	19	19	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890618	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
218	30	2025-11	\N	\N	2.5	6.8	\N	\N	\N	Mircera 100	7	148	3.9	2.9	9	30	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890618	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
219	31	2025-11	\N	\N	0.5	9.3	\N	\N	\N		5.9	105	1.8	2.1	16	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890619	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
220	32	2025-11	\N	\N	2	6.4	\N	\N	\N		8.6	61	6.3	2.8	21	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890619	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
221	34	2025-11	\N	\N	1	11.5	\N	\N	\N		8.7	81	2.7	3	13	14	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89062	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
222	1	2025-12	\N	\N	\N	9.9	\N	\N	\N	M-100/30	7.7	65	4.2	3	10	19	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89062	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
223	2	2025-12	retrospective_seed	\N	1.1	8.1	780	24	\N	EPO 6000u TIW	9.3	135	4	2.7	48	52	11	390	1380	0.8	\N	2026-04-17 09:37:17.89062	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
224	3	2025-12	\N	\N	\N	9.4	\N	\N	\N	M-100/30	8.3	147	5.3	3.2	17	39	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890621	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
225	4	2025-12	\N	\N	\N	10.8	\N	\N	\N	Mircera 100	\N	68	6.3	3.5	5	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890621	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
226	5	2025-12	\N	\N	\N	11.3	\N	\N	\N	Mircera 75	7.7	276	4.1	3.3	15	22	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890622	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
227	6	2025-12	\N	\N	\N	8.1	\N	\N	\N	ERIPeg 100/15	7.4	340	3.6	2.1	20	14	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890623	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
228	7	2025-12	\N	\N	\N	13.5	\N	\N	\N	EPO 10K	9.2	262	2.3	3.4	28	32	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890623	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
229	9	2025-12	\N	\N	\N	11.8	\N	\N	\N	MIRCERA 100 MCG	7.6	77	3.6	3.8	21	7	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890623	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
230	10	2025-12	\N	\N	\N	10	\N	\N	\N	MIRCERA 100	7.2	495	3	3	9	12	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890624	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
231	11	2025-12	\N	\N	\N	9.7	\N	\N	\N	MIRCERA 75	8.1	194	5.1	3.1	22	31	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890624	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
232	12	2025-12	\N	\N	\N	9.5	\N	\N	\N	MIRCERA 75	7	174	6.6	3.5	14	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890625	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
233	13	2025-12	\N	\N	\N	9.6	\N	\N	\N	MIRCERA 100	9.1	416	2.7	3.6	19	40	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890625	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
234	14	2025-12	\N	\N	\N	\N	\N	\N	\N	MIRCERA 100	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890626	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
235	15	2025-12	\N	\N	\N	9.3	\N	\N	\N	MIRCERA 100	8.8	93	6.8	3.1	9	21	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890626	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
236	16	2025-12	\N	\N	\N	8.9	\N	\N	\N	MIRCERA 100	9.1	74	7	3.3	16	12	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890627	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
237	17	2025-12	\N	\N	\N	8.4	\N	\N	\N	MIRCERA 100	8.9	81	\N	2.9	12	14	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890627	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
238	18	2025-12	\N	\N	\N	11.9	\N	\N	\N	MIRCERA 100	8.7	888	3	3.4	26	37	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890628	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
239	19	2025-12	\N	\N	\N	11.7	\N	\N	\N	MIRCERA 75	8.8	280	6.4	3.4	10	23	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890628	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
240	20	2025-12	\N	\N	\N	10.9	\N	\N	\N	EPO 10K	7.7	55	6.2	3.1	12	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890628	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
241	21	2025-12	retrospective_seed	\N	2.3	9.5	195	30	\N	EPO 4000u TIW	8.6	140	6.1	3.1	30	26	19	295	1650	1	\N	2026-04-17 09:37:17.890629	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
242	22	2025-12	\N	\N	\N	10.6	\N	\N	\N	Mircera 75	8	100	4.7	3.1	21	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890629	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
243	23	2025-12	\N	\N	\N	10.7	\N	\N	\N	MIRCERA 100	8.1	260	4.4	3.7	11	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89063	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
244	24	2025-12	\N	\N	\N	9.9	\N	\N	\N	Erypeg 75	7.6	255	5.7	3.5	25	41	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89063	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
245	25	2025-12	\N	\N	\N	10	\N	\N	\N	Mircera 75	8.3	108	5	3.5	27	32	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890631	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
246	26	2025-12	\N	\N	\N	9.9	\N	\N	\N	EPO 10K	8.5	113	6.4	2.7	8	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890631	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
247	27	2025-12	\N	\N	\N	9.8	\N	\N	\N	Mircera 75	8.7	92	7.6	3	15	23	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890632	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
248	28	2025-12	\N	\N	\N	6.1	\N	\N	\N	Mircera 100	8.6	100	2.7	2.8	10	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890632	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
249	29	2025-12	\N	\N	\N	8.8	\N	\N	\N	Mircera 100	9.7	69	3.1	3.5	19	19	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890633	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
250	30	2025-12	\N	\N	\N	6.8	\N	\N	\N	Mircera 100	7	148	3.9	2.9	9	30	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890633	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
251	31	2025-12	\N	\N	\N	9.3	\N	\N	\N		5.9	105	1.8	2.1	16	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890634	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
252	32	2025-12	\N	\N	\N	6.4	\N	\N	\N		8.6	61	6.3	2.8	21	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890634	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
253	34	2025-12	\N	\N	\N	11.5	\N	\N	\N		8.7	81	2.7	3	13	14	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890635	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
254	35	2025-12	\N	\N	\N	9.8	\N	\N	\N	Mircera 100	8.6	122	4.3	3.1	16	\N	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890635	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
255	21	2026-01	retrospective_seed	\N	2.5	9.8	205	32	\N	EPO 4000u TIW	8.8	\N	5.9	3.2	28	24	20	280	1700	1	\N	2026-04-17 09:37:17.890636	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
260	4	2026-02	\N	\N	2	8.4	\N	\N	\N	Mircera 100	8.7	73	1.6	2.9	13	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890638	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
261	5	2026-02	\N	\N	2	11.8	703	\N	66	Mircera 75	\N	271	4.9	3.5	13	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890638	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
262	6	2026-02	\N	\N	3	7.8	902	\N	34	ERIPeg 100/15	\N	157	\N	2.3	28	23	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890639	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
263	7	2026-02	\N	\N	2	11.4	1131	\N	157	EPO 10K	7.2	239	4.4	3.1	19	23	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890639	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
264	8	2026-02	\N	\N	1.2	11.1	\N	183	58	MIRCERA 100	7.7	100	\N	4.1	21	38	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890639	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
265	9	2026-02	\N	\N	2.5	11.1	425	\N	60	MIRCERA 100 MCG	8.5	65	4.1	3.3	16	21	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89064	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
266	10	2026-02	\N	\N	2.9	7.9	1329	\N	62	MIRCERA 100	6.8	231	3.6	3.6	63	79	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89064	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
267	11	2026-02	\N	\N	2.8	10.1	\N	\N	42	MIRCERA 75	8.7	194	4.4	3.1	21	32	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890641	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
268	12	2026-02	\N	\N	2.5	8.6	735	\N	59	MIRCERA 75	\N	177	\N	3.7	8	25	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890641	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
269	13	2026-02	\N	\N	2.2	10.6	3013	119	182	MIRCERA 100	8.9	271	2.8	3.4	24	42	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890641	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
270	14	2026-02	\N	\N	2	7.8	2492	\N	97	MIRCERA 100	7.7	109	5	3.3	9	21	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890642	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
271	15	2026-02	\N	\N	4	9.3	535	\N	\N	MIRCERA 100	9.1	133	5.3	3.1	20	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890642	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
272	16	2026-02	\N	\N	1.8	11.6	1800	\N	99	MIRCERA 100	\N	80	\N	3.5	3	17	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890643	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
273	17	2026-02	\N	\N	2.5	7.4	1205	\N	94	MIRCERA 100	9.4	96	2.9	3.1	18	24	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890643	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
274	18	2026-02	\N	\N	2	10.4	\N	\N	71	MIRCERA 100	9.7	747	2.4	2.8	11	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890643	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
275	19	2026-02	\N	\N	2	10.6	409	\N	118	MIRCERA 75	9.3	279	4.6	3.4	19	28	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890644	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
259	3	2026-02	\N	\N	2.5	12	1286	\N	49	M-100/30	8.8	136	4.2	3.4	9	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890638	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
256	2	2026-01	retrospective_seed	\N	1	7.9	795	23	\N	EPO 6000u TIW	9.4	\N	3.9	2.6	50	54	11	400	1360	0.8	\N	2026-04-17 09:37:17.890636	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
276	20	2026-02	\N	\N	2.5	11.2	691	\N	98	EPO 10K	6.8	45	3.9	2.9	26	28	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890644	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
277	21	2026-02	retrospective_seed	\N	2.4	9.6	209	31	40	EPO 4000u TIW	8.9	139	6	3.1	30	25	19	290	1680	1	\N	2026-04-17 09:37:17.890645	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
278	22	2026-02	\N	\N	2	10.9	849	\N	79	Mircera 75	8.8	106	5.3	3.5	4	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890645	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
279	23	2026-02	\N	\N	2.2	9.9	864	\N	16	MIRCERA 100	8.5	129	3.7	3.4	10	10	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890646	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
280	24	2026-02	\N	\N	2	9.3	1654	\N	106	Erypeg 75	7.5	257	3.9	3.5	22	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890646	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
282	26	2026-02	\N	\N	2.5	10.1	272	\N	32	EPO 10K	8.3	92	2.2	2.6	15	20	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890647	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
283	27	2026-02	\N	\N	2.5	10.6	\N	\N	48	Mircera 75	8.9	106	8.9	3.1	6	15	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890647	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
284	28	2026-02	\N	\N	2.5	9.3	836	\N	178	Mircera 100	8.5	140	4.1	3.3	25	41	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890648	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
285	29	2026-02	\N	\N	0.3	7.9	120	\N	120	Mircera 100	9.4	68	3.9	3.5	16	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890648	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
286	30	2026-02	\N	\N	2.5	8.1	451	\N	49	Mircera 100	6.9	205	3.2	2.8	3	19	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890649	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
287	31	2026-02	\N	\N	0.5	9.9	1617	\N	30	Mircera 100	7.1	89	3.2	1.6	25	18	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890649	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
288	32	2026-02	\N	\N	2	7.9	1405	\N	122	Mircera 75	8.4	76	4.6	3.4	18	23	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89065	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
289	33	2026-02	\N	\N	\N	9.3	330	\N	18	\N	8.8	133	\N	1.7	15	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.89065	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
291	35	2026-02	\N	\N	0.5	11.4	\N	\N	57	Mircera 100	8.2	94	4.3	3.4	16	25	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890651	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
292	36	2026-02	\N	\N	1	7.3	\N	\N	75	Mircera 100	\N	\N	\N	2.5	20	16	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890652	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
293	37	2026-02	\N	\N	2.3	8	\N	\N	\N	Mircera 100	8.3	68	3.3	2.6	10	13	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890652	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
294	38	2026-02	\N	\N	2.5	9.4	138	\N	90	\N	8.9	182	3.8	3.8	23	14	\N	\N	\N	\N	\N	2026-04-17 09:37:17.890652	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
296	21	2026-03	retrospective_seed	\N	2.3	9.4	200	30	\N	EPO 4000u TIW	8.7	\N	5.8	3	31	27	18	305	1620	0.9	\N	2026-04-17 09:37:17.890653	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
5	5	2026-04	admin	66	1	11.8	703	\N	66	Mircera 75	-0.03	271	4.9	3.5	13	18	\N	\N	\N	\N		2026-04-21 09:34:31.16758	\N	150	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	\N	\N	\N		\N		\N			135	3.6	\N	6.02	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	66.9	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
300	1	2026-05		74	\N	10.2	\N	\N	\N	Mircera (CERA) 100mcg Weekly	8.2	\N	4.9	3.5	\N	\N	\N	\N	\N	\N		2026-05-13 16:59:11.726028	\N	\N	\N	\N	\N	\N	\N	f	20000	RC AVF Rt	None	\N	\N	\N	50	\N	6.7	Mircera (CERA)	\N		\N			127	5.2	\N	\N	\N	\N	4.5	1.98	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
281	25	2026-02		49.5	2.5	9.5	603	\N	77	Mircera 75	8.4	93	5.3	3.4	24	43	\N	\N	\N	\N		2026-05-04 08:16:04.229798	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	\N	\N	\N		\N		\N			\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
11	11	2026-04	admin	96	2.6	11	\N	\N	42	MIRCERA 75	7.9	157	4.7	2.9	43	41	\N	\N	\N	\N		2026-04-22 06:48:23.428262	\N	140	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	130	52	10		\N		\N			130	4.2	\N	7.1	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	98.6		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
12	12	2026-04	admin	64.5	2	11	735	\N	59	MIRCERA 75	7.4	19	5.6	3.5	8	17	\N	\N	\N	\N		2026-04-27 06:26:45.111016	\N	144	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	134	25	11.5		\N		\N			138	4.7	\N	6.2	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	66.5		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
7	7	2026-04	admin	51	1	9.4	1131	\N	157	EPO10K	7.2	172	3.2	3	28	30	34	601	\N	\N		2026-05-04 08:54:51.908238	\N	130	\N	\N	\N	\N	\N	f	\N	RC AVF Lt	None	\N	\N	\N	109	29	9.8	Mircera (CERA)	\N	Ferric Carboxymaltose	1000		Calcium Carbonate	139	4	\N	5.1	83	21	4.9	1.45	\N	\N	\N	f	\N		2026-03-20	51.8		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
308	34	2026-03	System Admin	38.5	\N	9	\N	\N	\N	Mircera (CERA) 50mcg Monthly	\N	83	\N	3.2	17	17	\N	-0.03	\N	\N		2026-05-04 07:17:57.754176	\N	\N	\N	\N	\N	\N	\N	f	2500	RC AVF Rt	None	30	\N	\N	123	-3	11.9	Mircera (CERA)	\N		\N			141	4.3	\N	5.6	150	\N	5.06	1.36	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
13	13	2026-04	admin	47	1.5	9.6	3013	119	182	Mircera (CERA) 100mcg Weekly	7.8	131	2.6	2.9	28	21	\N	\N	\N	\N		2026-05-04 07:41:16.844166	\N	134	\N	\N	\N	\N	\N	f	20000	RC AVF Rt	None	\N	\N	\N	75	17	9.1	Mircera (CERA)	\N		\N			137	4	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	48.4		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
299	19	2026-03		53	\N	8.3	\N	\N	\N	MIRCERA 75	8.3	268	3.6	2.9	40	40	\N	\N	\N	\N		2026-05-05 08:30:28.377216	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	146	\N	11.15	Mircera (CERA)	\N		\N			139	7.4	\N	8	118	65	7.7	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
302	2	2026-05	Doctor User	61	\N	7.9	\N	\N	\N	M-75/15	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N		2026-05-03 12:23:40.247056	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	\N	\N	\N		\N		\N			\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
3	3	2026-04	admin	59.5	2.5	11.2	\N	\N	49	Mircera (CERA) 100mcg Weekly	7.9	161	4.6	3.3	13	24	\N	\N	\N	\N		2026-05-05 04:56:32.295569	\N	60	\N	\N	\N	\N	\N	f	20000	RC AVF Rt	None	\N	\N	\N	101	75	12.6	Mircera (CERA)	\N		\N			136	5.5	\N	6	\N	\N	6300	2	\N	\N	\N	f	\N		\N	56.6		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
305	13	2026-05	System Admin	47	1.3	10.6	\N	\N	\N	MIRCERA100	8.9	233	2.5	3.3	14	29	\N	\N	\N	\N		2026-05-16 04:53:27.609201	\N	125	\N	\N	\N	\N	\N	f	0	RC AVF Rt	None	\N	\N	\N	105	\N	7.48		\N		\N			\N	\N	\N	\N	162	84	5.83	\N	\N	\N	\N	f	\N		\N	48.7		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
8	8	2026-04	admin	75	0	9.8	\N	183	58	Mircera (CERA) 100mcg Monthly	7.6	88	6.2	3.9	39	38	\N	\N	\N	\N		2026-05-14 05:24:11.621613	\N	124	\N	\N	\N	\N	\N	f	5000	RC AVF Rt	None	\N	1.2	\N	106	35	11.7	Mircera (CERA)	\N		\N			138	4.8	\N	8.2	\N	\N	3.6	0.77	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
297	2	2026-03	retrospective_seed	\N	1	10.7	802	23	\N	EPO 8000u TIW	9.5	\N	3.9	2.5	50	55	11	415	1350	0.7	\N	2026-04-17 09:37:17.890654	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
304	12	2026-05	System Admin	64.5	2.5	10.6	\N	\N	\N	Mircera (CERA) 75mcg Weekly	6.8	161	7.3	3.3	6	14	\N	\N	\N	\N		2026-05-14 06:18:28.21555	\N	164	\N	\N	\N	\N	\N	f	15000	RC AVF Rt	None	\N	\N	\N	141	\N	11.9	Mircera (CERA)	\N		\N			141	5	\N	6.66	162	101	6.8	1.34	\N	\N	\N	f	\N		\N	66.2		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
303	25	2026-05	System Admin	49.5	2.8	10.7	\N	\N	\N	Mircera 75	8.5	93	1.8	3.2	12	17	\N	\N	\N	\N		2026-05-14 06:37:11.972888	\N	148	\N	\N	\N	\N	\N	f	0	RC AVF Rt	None	\N	\N	\N	74	\N	7.83	Epoetin Beta	\N		\N			136	4.2	\N	5.3	84	43	5.8	1.67	\N	\N	\N	f	\N		\N	52.3		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
290	34	2026-02		38.5	1	12.1	1256	105	57	Mircera 100	8.6	83	6.1	3.6	15	13	\N	\N	\N	\N		2026-05-04 07:20:51.913152	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	207	\N	10.9		\N		\N			142	4.5	\N	5.6	151	\N	9.6	1.37	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
309	34	2026-01	System Admin	38.5	\N	10.8	\N	\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N		2026-05-04 07:21:45.596576	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	\N	\N	\N		\N		\N			\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
310	13	2026-01	System Admin	4.8	1.5	9.7	\N	\N	1821	Mircera (CERA) 100mcg Weekly	8.5	170	3	3.2	13	26	\N	\N	\N	\N		2026-05-04 07:35:21.567499	\N	160	\N	\N	\N	\N	\N	f	20000	RC AVF Rt	None	\N	\N	\N	160	\N	12.2	Mircera (CERA)	\N		\N			136	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	50.3		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
6	6	2026-04	admin	42	2	12.7	902	\N	34	ERIPeg100/15	7.6	366	4.3	2.6	31	16	\N	\N	\N	-0.3		2026-05-04 07:43:25.382049	\N	140	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	63	26	4.7		\N		\N			136	5	\N	6.4	\N	\N	6300	1	\N	\N	\N	f	\N		\N	43.8		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
313	25	2026-03	System Admin	49	1.96	8.8	\N	\N	\N	Mircera (CERA) 75mcg Weekly	7.6	92	5	0.04	34	66	\N	\N	\N	\N		2026-05-04 08:25:18.713404	\N	151	\N	\N	\N	\N	\N	f	15000	RC AVF Rt	None	\N	\N	\N	117	\N	10.61	Mircera (CERA)	\N		\N			140	5.8	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	51		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
25	25	2026-04	admin	49.5	2.5	8.8	603	\N	77	Mircera (CERA) 75mcg Weekly	8.2	135	3.66	3.5	14	20	\N	\N	\N	\N		2026-05-04 08:25:45.179592	\N	150	\N	\N	\N	\N	\N	f	15000	RC AVF Rt	None	\N	\N	\N	107	\N	10.4	Mircera (CERA)	\N		\N			137	5.3	-3	\N	-6	\N	8.8	\N	\N	\N	\N	f	\N		\N	51.4		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
314	7	2026-03	System Admin	51	\N	8.6	\N	\N	\N	EPO 10K	6.9	160	4.2	3	23	39	\N	\N	\N	\N		2026-05-04 08:57:45.260741	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	152	\N	12		\N		\N			139	5.4	\N	5.9	91	27	7.6	1.45	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
334	24	2026-05	System Admin	71	1	10	\N	\N	\N		8.8	69	4.3	3.3	12	19	\N	\N	\N	\N		2026-05-16 05:23:29.159394	\N	126	\N	\N	\N	\N	\N	f	0	RC AVF Rt	None	\N	\N	\N	102	\N	4.87		\N		\N			139	4.7	\N	\N	99	31	7.5	2.41	7.9	\N	\N	f	\N		\N	71.4		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
318	19	2026-01	System Admin	53	\N	9.9	\N	\N	\N	MIRCERA 75	9.1	293	4.9	3.5	19	24	\N	\N	\N	\N		2026-05-05 08:34:37.064325	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	101	\N	7.98		\N		\N			141	5.6	\N	5.4	-6	\N	7.8	1.2	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
322	5	2026-03	System Admin	65.5	\N	11.9	\N	\N	\N	Mircera 75	\N	295	\N	3.6	16	13	\N	\N	\N	\N		2026-05-05 09:03:01.97351	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	104	\N	12.16		\N		\N			133	3.8	\N	\N	\N	\N	5.1	1.31	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
323	1	2026-03	System Admin	74	\N	12.6	\N	\N	\N	M-100/30	\N	60	\N	3.1	14	11	\N	\N	\N	\N		2026-05-05 09:09:40.089276	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	68	\N	8.24		\N		\N			143	4.1	\N	\N	\N	\N	6.5	1.66	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
257	1	2026-02		74	3.5	12.8	468	\N	41	M-100/30	8	55	3.8	3.2	13	13	\N	\N	\N	\N		2026-05-05 09:16:54.891185	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	83	\N	8.8		\N		\N			142	4.5	\N	7.71	\N	\N	6.9	1.46	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
27	27	2026-04	admin	55	1.7	10.9	\N	\N	48	Mircera 75	7.8	107	8.7	3.3	10	15	\N	\N	\N	\N		2026-05-05 09:27:39.277278	\N	160	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	156	41	10.7		\N		\N			137	5.6	\N	\N	129	66	6.7	1.69	\N	\N	\N	f	\N		\N	56.7		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
316	22	2026-05	System Admin	68.5	0	12.2	\N	\N	\N	Mircera (CERA) 75mcg Weekly	9.3	87	3.8	3.1	1	10	\N	\N	1500	48		2026-05-15 08:53:01.575124	\N	140	\N	\N	\N	\N	\N	f	15000	RC AVF Rt	None	\N	\N	\N	78	\N	9.41	Mircera (CERA)	\N		\N			142	5	\N	\N	\N	\N	5	1.95	\N	\N	\N	f	\N		\N	68.3		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
295	39	2026-02		69	2	8.9	\N	\N	98	Mircera 100	8.6	125	8.8	2.1	28	18	\N	\N	\N	\N		2026-05-05 09:47:27.480751	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	242	\N	5.9		\N		\N			137	5.7	\N	\N	\N	\N	8.5	0.61	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
326	23	2026-05	System Admin	42	\N	6.5	\N	\N	\N	MIRCERA 100	8.7	\N	2	2.7	13	18	\N	\N	\N	\N		2026-05-05 09:59:33.346901	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	39	\N	3.04		\N		\N			132	4.1	\N	4.4	\N	\N	8.1	1.07	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
331	39	2026-05	System Admin	69	\N	\N	\N	\N	\N	Mircera 100	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N		2026-05-05 10:19:17.456228	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	\N	\N	\N		\N		\N			\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
332	28	2026-05	System Admin	65.5	\N	\N	\N	\N	\N	Mircera 100	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N		2026-05-05 10:20:41.129331	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	\N	\N	\N		\N		\N			\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
333	24	2026-03	System Admin	71	1	9.9	\N	\N	\N	Mircera (CERA) 100mcg Weekly	\N	269	\N	3.4	16	27	\N	\N	\N	\N		2026-05-06 05:54:30.023541	\N	130	\N	\N	\N	\N	\N	f	20000	RC AVF Rt	None	\N	\N	\N	125	\N	14.04	Mircera (CERA)	\N		\N			147	5	\N	\N	\N	\N	6.1	0.63	\N	\N	\N	f	\N		\N	72.8		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
328	11	2026-05	System Admin	96	\N	10	\N	\N	\N	Mircera (CERA) 75mcg Every 2 Weeks	8.4	183	4.6	3.1	17	24	\N	\N	\N	\N		2026-05-16 05:27:28.47562	\N	\N	\N	\N	\N	\N	\N	f	7500	RC AVF Rt	None	\N	\N	\N	89	\N	8	Mircera (CERA)	\N		\N			136	4.3	\N	6.2	92	40	3	1.06	\N	\N	\N	f	\N		\N	\N		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
335	36	2026-05	System Admin	63	\N	\N	\N	\N	\N	Mircera 100	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N		2026-05-06 09:57:03.36815	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	\N	\N	\N		\N		\N			\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
311	1	2026-01	System Admin	74	\N	11.6	\N	\N	\N	M-100/30	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N		2026-05-04 07:35:32.587029	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	\N	\N	\N		\N		\N			\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
327	38	2026-05	System Admin	42	\N	9.5	\N	\N	\N	Mircera (CERA) 75mcg Monthly	7.9	168	6	3	19	11	\N	\N	1200	37		2026-05-15 08:49:54.967363	\N	\N	\N	\N	\N	\N	\N	f	3750	RC AVF Rt	None	\N	\N	\N	113	\N	12.98	Mircera (CERA)	\N		\N			142	4.9	\N	\N	154	92	2.9	1.32	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	\N		\N
330	18	2026-05	System Admin	60	1	8.3	\N	\N	\N	Mircera (CERA) 50mcg Monthly	8.1	811	3.8	3.3	56	53	\N	\N	\N	\N		2026-05-16 06:26:31.834431	\N	180	82	\N	\N	\N	\N	f	0	RC AVF Rt	None	\N	\N	\N	71	\N	7.15		\N		\N			\N	\N	\N	4.8	126	75	4.6	1.22	\N	\N	\N	f	\N		\N	62.3		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
325	34	2026-05	System Admin	38.5	0	6.8	1200	\N	\N	Mircera (CERA) 50mcg Monthly	9.4	111	1.4	3.3	14	14	\N	\N	\N	\N		2026-05-14 07:06:38.442877	\N	180	\N	\N	\N	\N	\N	f	2500	RC AVF Rt	None	\N	\N	\N	80	\N	5.09	Mircera (CERA)	\N		\N			136	3.5	\N	\N	96	44	5.9	0.56	\N	\N	\N	f	\N		\N	38.2		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
319	4	2026-05	System Admin	56	\N	\N	\N	\N	\N	Mircera 100	\N	\N	\N	\N	\N	\N	\N	\N	2000	80		2026-05-12 08:55:58.386085	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	\N	\N	\N		\N		\N			\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
324	27	2026-05	System Admin	55	2.2	9.8	\N	\N	\N	Mircera (CERA) 100mcg Every 2 Weeks	9.1	125	8.1	3	10	16	\N	\N	\N	\N		2026-05-13 06:21:34.240286	\N	140	\N	\N	\N	\N	\N	f	10000	RC AVF Rt	None	\N	\N	\N	118	\N	9.71	Mircera (CERA)	\N		\N			137	5.8	\N	5.6	119	38	5.8	1.48	\N	\N	\N	f	\N		\N	56.7		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
329	14	2026-05	System Admin	55	\N	9.4	\N	\N	\N	MIRCERA 100	8.3	89	2	3.4	49	71	\N	\N	1500	55		2026-05-15 08:54:38.103695	\N	\N	\N	\N	\N	\N	\N	f	0	RC AVF Rt	None	\N	\N	\N	68	\N	4.56		\N		\N			140	3.6	\N	\N	111	50	3.5	0.58	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
320	8	2026-05	System Admin	75	1	9.3	\N	\N	\N	Mircera (CERA) 100mcg Monthly	8	82	5.1	3.4	10	17	\N	\N	\N	\N		2026-05-14 05:16:47.417101	\N	120	\N	\N	\N	\N	\N	f	5000	RC AVF Rt	None	\N	\N	\N	103	\N	10.13	Mircera (CERA)	\N		\N			139	4.1	\N	\N	89	44	3.7	1.24	\N	\N	\N	f	\N		\N	76.5		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
337	41	2026-04	System Admin	\N	\N	7.8	\N	\N	\N	Mircera (CERA) 75mcg Weekly	8.4	102	2.9	3.4	10	25	\N	\N	\N	\N		2026-05-11 09:19:58.785788	\N	\N	\N	\N	\N	\N	\N	f	15000	RC AVF Lt		\N	\N	\N	48	\N	\N	Mircera (CERA)	\N		\N			133	4.2	\N	\N	99	45	4	0.88	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
338	41	2026-05	System Admin	59	\N	12	\N	\N	\N	Mircera (CERA) 75mcg Weekly	8.3	97	1.6	3.7	12	22	\N	\N	\N	\N		2026-05-11 09:27:07.738307	\N	\N	\N	\N	\N	\N	\N	f	15000	RC AVF Lt		\N	\N	\N	48	\N	7.28	Mircera (CERA)	\N		\N			136	4.1	\N	\N	\N	\N	5.2	0.98	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
340	40	2026-04	System Admin	62	\N	\N	\N	\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N		2026-05-11 09:45:02.566232	\N	\N	\N	\N	\N	\N	\N	f	\N	Left BC AVF		\N	\N	\N	\N	\N	\N		\N		\N			\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
315	20	2026-05	System Admin	65.5	1.1	11.2	\N	\N	\N	Mircera (CERA) 100mcg Every 2 Weeks	8.7	75	2.9	2.6	14	16	\N	\N	\N	\N		2026-05-14 05:36:07.004279	\N	160	\N	\N	\N	\N	\N	f	10000	RC AVF Rt	None	\N	\N	\N	48	\N	5.3	Mircera (CERA)	\N		\N			137	4	\N	3.2	119	62	7	1.48	\N	\N	\N	f	\N		\N	69		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
341	35	2026-05	System Admin	71	\N	10	\N	\N	\N	Mircera 100 	8.8	69	4.3	3.3	12	19	\N	\N	\N	\N		2026-05-11 10:32:25.673322	\N	\N	\N	\N	\N	\N	\N	f	\N	RC AVF Rt	None	\N	\N	\N	102	\N	4.87		\N		\N			139	4.7	\N	\N	99	31	7.5	2.41	7.9	\N	\N	f	\N		\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
258	2	2026-02	retrospective_seed	\N	1.1	12	800	24	59	EPO 8000u TIW	9.5	144	3.9	2.6	52	56	11	410	1340	0.7	\N	2026-04-17 09:37:17.890637	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
342	3	2026-03	Variable Manager	\N	\N	10.7	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-05-11 10:58:19.452051	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
343	3	2026-01	Variable Manager	\N	\N	11.5	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-05-11 10:58:51.001236	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
344	22	2026-03	Variable Manager	\N	\N	13.4	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-05-11 11:01:17.145015	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
345	22	2026-01	Variable Manager	\N	\N	10.3	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-05-11 11:01:33.717826	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
346	31	2026-03	Variable Manager	\N	\N	7.8	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-05-11 11:05:24.654361	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
347	31	2026-01	Variable Manager	\N	\N	10.9	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-05-11 11:05:59.038166	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
348	13	2026-03	Variable Manager	\N	\N	7.1	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-05-11 11:07:54.290567	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
349	24	2026-01	Variable Manager	\N	\N	9.6	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-05-11 11:08:58.206967	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
350	17	2026-05	Variable Manager	\N	\N	2	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-05-11 11:10:12.15918	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
336	9	2026-05	admin	40	2	11.3	\N	\N	\N	Mircera (CERA) 50mcg Monthly	8.7	76	2.3	3.5	17	13	\N	\N	\N	\N		2026-05-11 15:08:22.290705	\N	130	\N	\N	\N	\N	\N	f	2500	RC AVF Rt	None	100	\N	\N	61	\N	6.9	Mircera (CERA)	\N		\N		Sevelamer Carbonate	133	3.7	\N	3	\N	\N	3.6	1	\N	\N	\N	f	\N		\N	41.6		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	1200	TDS	\N	60		\N
306	7	2026-05	System Admin	51	1.4	11.6	\N	\N	\N	Mircera (CERA) 100mcg Monthly	7.6	172	3.2	3	28	30	\N	\N	\N	\N		2026-05-11 15:27:24.169293	\N	140	\N	\N	\N	\N	\N	f	5000	RC AVF Lt	None	\N	\N	\N	109	\N	9.8	Mircera (CERA)	\N	Ferric Carboxymaltose	1000			139	4.8	\N	3.6	\N	\N	7.8	1.27	\N	\N	\N	f	\N		2026-03-26	52.1		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
339	40	2026-05	System Admin	62	2.5	10.2	720	\N	\N		7.3	165	5.9	2.9	12	20	\N	\N	\N	\N		2026-05-14 06:08:30.537915	\N	165	\N	\N	\N	\N	\N	f	0	Left BC AVF		\N	\N	\N	131	\N	9.77		\N		\N			138	5.8	\N	5.3	211	116	5.7	1.74	\N	\N	\N	f	\N		\N	64.9		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
321	5	2026-05	System Admin	65.5	0.6	11.7	\N	\N	\N	Mircera (CERA) 75mcg Weekly	7.3	383	4.1	3.5	11	15	\N	\N	1300	40		2026-05-15 08:55:35.192858	\N	140	\N	\N	\N	\N	\N	f	15000	RC AVF Rt	None	\N	\N	\N	75	\N	10.6	Mircera (CERA)	\N		\N			133	3.9	\N	4.9	132	31	5.6	1.17	\N	\N	\N	f	\N		\N	66.3		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
307	3	2026-05	System Admin	57	1.5	11.2	\N	\N	\N	Mircera (CERA) 100mcg Monthly	8.1	181	4.4	3.1	12	17	\N	\N	\N	\N		2026-05-12 09:29:41.058916	\N	124	\N	\N	\N	\N	\N	f	5000	RC AVF Rt	None	50	\N	\N	83	\N	11.5	Mircera (CERA)	\N		\N		Sevelamer Carbonate	136	4.2	\N	6.1	122	57	6.3	1.78	\N	2	\N	f	\N		\N	57	[{"name": "Clinidipine", "dose": "20", "freq": "BD"}, {"name": "Prazocin", "dose": "5", "freq": "OD"}]	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	2400	TDS	800	30	None	2023-04-18
312	31	2026-05	System Admin	42.5	2	8.5	\N	\N	\N		8.2	84	3.4	2.3	21	12	\N	\N	\N	\N		2026-05-14 05:10:51.693221	\N	150	\N	\N	\N	\N	\N	f	200	RC AVF Rt	50 mg thrice in a week	100	\N	\N	\N	\N	3.6	Mircera (CERA)	\N		\N		Calcium Carbonate	139	5.3	\N	3.6	133	80	1.8	0.54	\N	\N	\N	f	\N		\N	43.4		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	500	OD	\N	60		2025-09-25
351	26	2026-05	System Admin	43	3	8.9	\N	\N	\N	Mircera (CERA) 75mcg Every 2 Weeks	\N	115	\N	2.6	21	12	\N	\N	\N	\N		2026-05-14 06:47:34.297025	\N	107	\N	\N	\N	\N	\N	f	7500	RC AVF Rt	None	\N	\N	\N	43	\N	3.4	Mircera (CERA)	\N		\N			126	\N	\N	2.7	\N	\N	7.1	2.79	\N	\N	\N	f	\N		\N	46.5		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	\N		\N
352	42	2026-05	System Admin	49	2	\N	\N	\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N		2026-05-15 06:28:37.162458	\N	200	\N	\N	\N	\N	\N	f	0	Left BC AVF		\N	\N	\N	\N	\N	\N		\N		\N			\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	51		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
298	19	2026-05		53	\N	7.9	\N	\N	\N	Mircera (CERA) 75mcg Weekly	9	265	2.7	3.3	20	32	\N	\N	1200	35		2026-05-15 08:47:56.747464	\N	170	\N	\N	\N	\N	\N	f	15000	RC AVF Rt	None	\N	\N	\N	111	\N	8.8	Mircera (CERA)	\N		\N			138	5.8	\N	4.4	\N	\N	3	0.8	\N	\N	\N	f	\N		\N	54.8		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
317	10	2026-05	System Admin	35.5	2.6	10.4	\N	\N	\N	Mircera (CERA) 100mcg Monthly	8.4	84	\N	3.3	12	12	\N	\N	1200	30		2026-05-15 08:52:09.130411	\N	141	\N	\N	\N	\N	\N	f	5000	RC AVF Rt	None	100	\N	\N	158	\N	11.6	Mircera (CERA)	\N		\N	alphacalcidol 0.25mcg 2 cap A/D	Calcium Carbonate	140	5.5	\N	7.4	-4	\N	4.2	1.36	\N	2	\N	f	\N		\N	38.6	[{"name": "Amlodipine", "dose": "10", "freq": "OD"}, {"name": "Metoprolol", "dose": "50", "freq": "BD"}]	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	3000	TDS	1000	60		\N
353	24	2025-07	System Admin	71	0	12.9	\N	\N	\N		\N	91	\N	3.8	35	46	\N	\N	\N	\N		2026-05-16 05:19:46.986046	\N	140	66	\N	\N	\N	\N	f	0	RC AVF Rt		\N	\N	\N	15	\N	0.67		\N		\N			148	5.4	\N	\N	\N	\N	6.2	2.6	\N	\N	\N	f	\N		\N	\N		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
354	11	2026-03		96	2.5	10.8	\N	\N	\N		\N	196	\N	3.3	21	23	\N	\N	\N	\N		2026-05-16 05:33:34.617766	\N	160	80	\N	\N	\N	\N	f	0	RC AVF Rt	None	\N	\N	\N	89	\N	\N		\N		\N			138	5.3	\N	\N	\N	\N	4.9	2.35	\N	\N	\N	f	\N		\N	98.7		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
355	11	2025-06		96	\N	7	\N	\N	\N		8.3	118	5.3	2.5	30	20	\N	\N	\N	\N		2026-05-16 05:46:21.229956	\N	140	\N	\N	\N	\N	\N	f	0	RC AVF Rt	None	\N	\N	\N	77	\N	9.23		\N		\N			137	4.8	\N	6.9	126	51	6.1	1.82	\N	\N	\N	f	\N		\N	\N		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
356	11	2026-01		96	1	10.2	\N	\N	\N	Mircera (CERA) 75mcg Every 2 Weeks	8.4	168	3.2	3.4	21	29	\N	\N	\N	\N		2026-05-16 05:54:32.253606	\N	148	74	\N	\N	\N	\N	f	7500	RC AVF Rt	None	\N	\N	\N	56	\N	6.04	Mircera (CERA)	\N		\N			137	4.5	\N	4.8	97	35	3.2	0.75	\N	\N	\N	f	\N		\N	98		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
357	13	2025-06		47	\N	9.9	\N	\N	\N		8.9	224	3.9	3.2	23	23	\N	\N	\N	\N		2026-05-16 06:03:13.505081	\N	160	80	\N	\N	\N	\N	f	0	RC AVF Rt	None	\N	\N	\N	94	\N	8.63		\N		\N			\N	4.9	\N	5.4	\N	\N	4.7	0.56	\N	\N	\N	f	\N		\N	\N		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
358	18	2026-03		60	1.5	10	\N	\N	\N		\N	609	\N	3.1	14	19	\N	\N	\N	\N		2026-05-16 06:14:16.507015	\N	130	64	\N	\N	\N	\N	f	0	RC AVF Rt	None	\N	\N	\N	60	\N	\N		\N		\N			149	4.5	\N	\N	\N	\N	5.6	1.29	\N	\N	\N	f	\N		\N	61.3		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
359	18	2026-01		60.5	2	9.8	\N	\N	\N	MIRCERA 100	8.6	737	4.6	3.5	26	27	\N	\N	\N	\N		2026-05-16 06:20:10.957345	\N	128	62	\N	\N	\N	\N	f	0	RC AVF Rt	None	\N	\N	\N	93	\N	7.72		\N		\N			148	4.4	\N	\N	140	73	4.6	1.54	\N	\N	\N	f	\N		\N	62.1		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
360	18	2025-06		60.5	\N	11.8	\N	\N	\N		9	781	1.6	3.3	24	33	\N	\N	\N	\N		2026-05-16 06:25:04.169815	\N	\N	\N	\N	\N	\N	\N	f	0	RC AVF Rt	None	\N	\N	\N	44	\N	4.73		\N		\N			134	2.9	\N	3.7	139	71	4.7	1.58	\N	\N	\N	f	\N		\N	\N		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
361	1	2025-06		74	\N	\N	\N	\N	\N	M-100/30	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N		2026-05-16 06:25:13.588744	\N	\N	\N	\N	\N	\N	\N	f	0	RC AVF Rt	None	\N	\N	\N	\N	\N	\N		\N		\N			\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
362	27	2026-03		54.5	2.5	10.2	\N	\N	\N	Mircera (CERA) 100mcg Every 2 Weeks	7.8	106	8.2	3.3	23	22	\N	\N	\N	\N		2026-05-16 06:53:14.972228	\N	158	88	\N	\N	\N	\N	f	10000	RC AVF Rt	None	\N	\N	\N	122	\N	9.37	Mircera (CERA)	\N		\N			142	6.4	\N	4.4	114	56	5.4	1.53	\N	\N	\N	f	\N		\N	56.2		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
363	27	2026-01		52.5	2.5	10.9	\N	\N	\N		7.5	104	5.2	3.2	12	23	\N	\N	\N	\N		2026-05-16 07:01:27.22428	\N	150	64	\N	\N	\N	\N	f	0	RC AVF Rt	None	\N	\N	\N	112	\N	7.06		\N		\N			138	6	\N	2.6	112	59	6.7	1.61	\N	\N	\N	f	\N		\N	54.3		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
364	27	2025-10		52.5	\N	13.6	\N	\N	\N	Mircera 75	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N		2026-05-16 07:04:46.976288	\N	\N	\N	\N	\N	\N	\N	f	0	RC AVF Rt	None	\N	\N	\N	\N	\N	\N		\N		\N			\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
365	27	2025-06		\N	\N	\N	\N	\N	\N		8.3	\N	7.4	3.3	\N	\N	\N	\N	\N	\N		2026-05-16 07:11:21.289447	\N	\N	\N	\N	\N	\N	\N	f	0	Left BC AVF		\N	\N	\N	228	\N	7.55		\N		\N			\N	\N	\N	3.3	\N	\N	\N	\N	\N	\N	\N	f	\N		\N	\N		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
366	27	2025-07		52.5	\N	14.1	\N	\N	\N		8.2	135	8.9	3.9	22	43	\N	\N	\N	\N		2026-05-16 07:23:06.349271	\N	\N	\N	\N	\N	\N	\N	f	0	Left BC AVF		\N	\N	\N	15	\N	1.08		\N		\N			135	5.9	\N	2.2	\N	\N	6.4	1.33	\N	\N	\N	f	\N		\N	\N		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
367	27	2025-08		52.5	\N	11.2	\N	\N	\N		7.5	\N	10.2	\N	\N	\N	\N	\N	\N	\N		2026-05-16 07:26:50.643259	\N	\N	\N	\N	\N	\N	\N	f	0	Left BC AVF		\N	\N	\N	212	\N	11.79		\N		\N			137	5.3	\N	\N	\N	\N	6	1.44	\N	\N	\N	f	\N		\N	\N		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60		\N
301	6	2026-05	admin	39.5	2.3	12.4	\N	\N	\N		7.3	346	2.7	2.7	30	14	\N	\N	\N	\N		2026-05-16 07:34:33.055702	\N	150	\N	\N	\N	\N	\N	f	0	RC AVF Rt	None	100	\N	\N	31	\N	2.5		\N		\N		Calcium Carbonate	130	4.5	\N	3.8	102	51	4.1	1.36	\N	1	\N	f	\N		\N	41.3	[{"name": "Clinidipine", "dose": "20", "freq": "BD"}]	\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60	None	2026-03-06
368	6	2026-03		39.5	\N	11.8	\N	\N	\N	Mircera (CERA) 100mcg Weekly	6.5	276	4.4	2.4	16	15	\N	\N	\N	\N		2026-05-16 07:39:05.677227	\N	\N	\N	\N	\N	\N	\N	f	20000	RC AVF Rt	None	\N	\N	\N	\N	\N	\N	Mircera (CERA)	\N		\N			131	5.8	\N	6.4	101	43	6.5	2.05	\N	\N	\N	f	\N		\N	\N		\N	\N	\N		\N	\N	\N	\N	\N	\N	\N				\N	\N	\N	\N	\N	\N	\N	\N		\N	60	None	2026-03-06
\.


--
-- Data for Name: patient_meal_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.patient_meal_records (id, patient_id, date, calories, protein, notes, created_at, meal_type) FROM stdin;
\.


--
-- Data for Name: patient_reminders; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.patient_reminders (id, patient_id, reminder_date, message, is_completed, created_at) FROM stdin;
1	8	2026-04-29	test reminder	t	2026-04-29 01:42:03.324489
\.


--
-- Data for Name: patient_symptom_reports; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.patient_symptom_reports (id, patient_id, reported_at, symptoms, severity, notes, session_id, dialysis_recovery_time_mins, tiredness_score, energy_level_score, daily_activity_impact, cognitive_alertness, post_hd_mood, sleepiness_severity, missed_social_or_work_event) FROM stdin;
\.


--
-- Data for Name: patients; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.patients (id, hid_no, name, relation, relation_type, sex, contact_no, email, diagnosis, hd_wef_date, viral_markers, hep_b_status, hep_b_date, pneumococcal_date, access_type, access_date, dry_weight, hd_slot_1, hd_slot_2, hd_slot_3, whatsapp_link, whatsapp_notify, mail_trigger, is_active, created_by, updated_by, created_at, updated_at, relation_name, clinical_remarks, dialysis_vintage_months, primary_diagnosis, comorbidity_cvd, comorbidity_cvsd, hyperparathyroidism, influenza_date, hep_b_dose1_date, hep_b_dose2_date, hep_b_dose3_date, hep_b_dose4_date, hep_b_titer_date, pcv13_date, ppsv23_date, hz_dose1_date, hz_dose2_date, hd_frequency, education_level, height, primary_renal_disease, date_esrd_diagnosis, native_kidney_biopsy, dm_status, htn_status, cad_status, chf_status, history_of_stroke, smoking_status, alcohol_consumption, charlson_comorbidity_index, previous_krt_modality, history_of_renal_transplant, transplant_prospect, viral_hbsag, viral_anti_hcv, viral_hiv, date_first_cannulation, history_of_access_thrombosis, access_intervention_history, catheter_type, catheter_insertion_site, current_survival_status, date_of_death, primary_cause_of_death, withdrawal_from_dialysis, date_facility_transfer, native_kidney_disease, comorbidities, drug_allergies, dialysis_modality, previous_dialysis_modality, healthcare_facility, hd_day_1, hd_day_2, hd_day_3, blood_group, age, ejection_fraction, login_username, hashed_password, dm_end_organ_damage, history_of_pvd, history_of_dementia, history_of_cpd, history_of_ctd, history_of_pud, liver_disease, hemiplegia, solid_tumor, leukemia, lymphoma, native_kidney_biopsy_date, native_kidney_biopsy_report, clinical_background, echo_date, echo_report, diastolic_dysfunction, handgrip_strength, baseline_gcr, baseline_vdcr, is_black, withdrawal_date, withdrawal_reason, withdrawal_clinician, date_of_transplant) FROM stdin;
16	100095703018	Rajesh Kumar	\N	M/O	Female	9582039323	rajeshchhillar3@gmail.com	CKD5D	2019-09-23	NEG	\N	\N	\N	AVF	\N	48.5	Morning	Morning	\N	\N	t	f	t	admin	\N	2026-04-16 11:55:03.229934	2026-05-01 08:08:55.065688	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Tuesday	Friday	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N
2	20131558744519	Aloknath bala		F/O	Male	9755036039	piyalibala17971@gmail.com	CKD5D	2024-08-01			\N	\N	RC AVF Rt	\N	61				https://wa.me/919755036039	t	f	f	admin	\N	2026-04-16 11:54:52.210578	2026-05-14 08:51:51.365511	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2		\N		\N			f	f	f	f			\N		f		Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N				\N						\N	60	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N
30	20131701374916	Yogesh Patil 	\N	W/O 	Female 	7557818112	9009143156a@gmail.com	CKD5D	2025-09-11	NEG 	\N	\N	\N	AVF	2023-06-20	43	30/12/2025	02/01/2026	06/01/2026	\N	t	f	f	admin	\N	2026-04-16 11:55:10.965247	2026-05-14 06:51:07.38249	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N
8	20194841219	Vinit Mahadik	None	F/O	Male	9975699405	Vinaysinhvmahadik@gmail.com	CKD5D	2025-05-12		Immune	\N	\N	RC AVF Rt	2024-03-24	75	Morning	Morning	\N	https://wa.me/919975699405	t	f	t	admin	\N	2026-04-16 11:54:59.692242	2026-05-14 04:19:07.928855	\N	\N	0	\N	f	f	f	\N	2026-01-03	2026-02-03	2026-04-03	2026-06-03	\N	\N	\N	\N	\N	2	Graduate	180		\N		None	f	f	f	f	Ex-smoker	Occasional	4		f		Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N				\N		Monday	Thursday	\N	A+	64	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
1	400040426619	Ajit Shinde		F/O	Male	9763222914	anandraoshinde07@gmail.com	CKD5D	2024-03-08			\N	\N	RC AVF Rt	2023-09-16	74				https://wa.me/919763222914	f	f	t	admin	\N	2026-04-16 11:54:51.718101	2026-05-05 09:10:29.790798	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2		\N		\N		None	f	f	f	f			4		f		Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N			HD	\N						63	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
23	20131612326816	Mahantesh W	\N	W/O	Female 	9740465357	mahanteshmantu1993@gmail.com	CKD5D	2025-05-17	NEG	\N	\N	\N	RC AVF Rt	2025-06-26	42	31/12/2025	3/1/2026	07/01/2026	\N	t	f	f	admin	\N	2026-04-16 11:55:06.687956	2026-05-14 08:52:18.085273	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N
28	20131466164418	Pravesh Kumar Tiwari 		M/O	Male	9682302668	praveshkumartiwari4@gmail.com	CKD5D	2025-06-01		Immune	\N	\N	RC AVF Rt	2025-06-20	65.5	Morning	Morning	\N	https://wa.me/919682302668	t	f	t	admin	\N	2026-04-16 11:55:09.075186	2026-04-22 06:57:30.08438	\N	\N	0	\N	f	f	f	2025-05-27	2025-06-06	2025-07-10	2025-08-10	2025-12-10	\N	\N	\N	\N	\N	2		\N		\N			f	f	f	f			\N		f		Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N				\N		Wednesday	Saturday	\N	AB+	75	60	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N
25	201315232906	Maruti Chavan	Prashant Chavan 	F/O	Male	9881063118		CKD5D	2025-08-01		Immune	\N	\N	RC AVF Rt	2025-08-04	49.5	Morning	Morning	\N	https://wa.me/919881063118	t	f	t	admin	\N	2026-04-16 11:55:07.426888	2026-05-14 06:24:43.203676	\N	\N	0	\N	f	f	f	2025-09-10	2025-08-29	2025-09-29	2025-10-29	2026-02-04	\N	2025-11-09	\N	2025-10-10	2026-05-08	2	Illiterate	163		\N		None	f	f	f	f	Never	Occasional	4		f	NO	Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N			HD	\N		Monday	Thursday	\N	B+	66	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
32	20131704557122	Sunil Halyal		Self	Male	8073070889		CKD5D	\N			\N	\N	AVF	\N	57.5				https://wa.me/918073070889	t	f	f	admin	\N	2026-04-16 11:55:11.703297	2026-05-11 11:16:41.814094	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N
4	2013151873822	D B Jadhav		SELF	Male	8788092169	Kavitajadhav00171@gmail.com	CKD5D	2019-01-21			\N	\N	RC AVF Rt	2025-11-24	56	Morning	Morning	\N	https://wa.me/918788092169	t	f	t	admin	\N	2026-04-16 11:54:53.024939	2026-05-01 06:50:09.583525	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2		\N		\N		None	f	f	f	f			2		f		Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N			HD	\N		Tuesday	Friday	\N		\N	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N
15	20285725722	Rajeev  Joshi		Self	Male	9906905849	rajeev193@rediffmail.com	CKD5D	2025-05-03			\N	\N	RC AVF Rt	2025-05-07	101.5				https://wa.me/919906905849	f	f	f	admin	\N	2026-04-16 11:55:02.823413	2026-05-13 13:12:51.030427	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2	Graduate	\N	Diabetic Nephropathy	\N	Done	Type 2	f	f	f	f	Never	None	\N		f	Listed	Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N			HD	\N	Pune					\N	60	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N
14	100097007019	Rahul Kumar	None	F/O	Male	7983375787	rahulverma28210@gmail.com	CKD5D	2022-11-02		Immune	\N	\N	RC AVF Rt	\N	55	Morning	Morning	\N	https://wa.me/917983375787	t	f	t	admin	\N	2026-04-16 11:55:02.407949	2026-05-01 07:54:25.776295	\N	\N	0	\N	f	f	f	2024-06-06	2024-03-05	2024-04-05	2024-05-05	2024-08-05	\N	\N	\N	2024-04-10	2024-06-10	2		\N		\N		None	f	f	f	f			3		f		Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N				\N		Tuesday	Friday	\N	A+	58	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N		\N	\N	\N	\N	f	\N	\N	\N	\N
39	20285513618	Girish Shyam 		M/O	Female	8132808075		CKD5D	\N			\N	\N	RC AVF Rt	\N	69				https://wa.me/918132808075	t	f	f	admin	\N	2026-04-16 11:55:15.009956	2026-05-11 11:12:12.406436	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N
31	2013279901018	Dilip Dhormale		M/O	Female	8830560612	rupalidhormale9@gmail.com	CKD5D	2025-09-26		Immune	\N	\N	RC AVF Rt	2025-11-20	42.5	Morning	Morning	\N	https://wa.me/918830560612	t	t	t	admin	\N	2026-04-16 11:55:11.322696	2026-05-14 04:48:51.663932	\N	\N	0	\N	f	f	f	2026-05-04	2025-11-15	2025-12-15	2026-01-15	2026-02-15	\N	2026-01-03	2026-05-04	2026-05-07	\N	2	Illiterate	152	Chronic Glomerulonephritis	2025-09-20	Not Done	None	t	f	f	f	Never	None	5		f	NO	Negative	Negative	Negative	2026-02-02	f				Active	\N		f	\N	\N	Hypothyroidism		HD	\N		Monday	Thursday	\N	B+	72	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			2025-09-25	No RWMA, EF 60%	Normal	\N	\N	\N	f	\N			\N
36	2013449590222	Jaspal Singh	\N	Self	Male	7087805874		CKD5D	2025-11-19	NEG 	\N	\N	\N	RC AVF Rt	\N	63	31/12/2025	3/1/2026	07/01/2026	\N	t	f	f	admin	\N	2026-04-16 11:55:13.460151	2026-05-11 11:12:38.38204	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N
17	20131572020218	Mukesh Singh	\N	M/O	Female	9149529560	msingh74150@gmail.com	CKD5D	2023-01-30	NEG	\N	\N	\N	AVF	\N	51.5	29/12/2025	01/01/2026	3/1/2026	\N	t	f	f	admin	\N	2026-04-16 11:55:03.643054	2026-05-11 11:14:26.186059	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N
26	2013650212918	Rajgouda Patil	\N	M/O	Female 	8887610207		CKD5D	2022-08-23	NEG 	\N	\N	\N	RC AVF Rt	\N	43	Morning	Morning	\N	\N	t	f	t	admin	\N	2026-04-16 11:55:07.825595	2026-05-14 06:47:34.301311	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Monday	Thursday	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N
33	10003794119	Shivam Raj	None	F/O	Male	9351941297		CKD5D	\N			\N	\N		2025-06-23	\N	30/12/2025	06/01/2026	13/01/2026	https://wa.me/919351941297	t	f	f	admin	\N	2026-04-16 11:55:12.094512	2026-05-13 06:09:53.449513	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2		\N		\N		None	f	f	f	f			2		f				Negative	\N	f				Deceased	2026-04-10	CKD5S Sepsis	f	\N	\N				\N		\N	\N	\N		\N	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
38	202938711720	P V Karande	PV karande	S/O	Male	9527295565		CKD5D	2025-07-12		Immune	\N	\N	Left BC AVF	\N	45.5	Morning	Morning	\N	https://wa.me/919527295565	t	f	t	admin	\N	2026-04-16 11:55:14.399822	2026-05-15 12:07:34.189882	\N	\N	0	\N	f	f	f	2025-07-09	2025-06-30	2025-07-30	2025-08-30	2025-12-30	\N	\N	\N	\N	\N	2	Primary	164		\N		None	f	f	f	f	Never	None	2		f		Negative	Negative	Negative	2026-02-10	f				Active	\N		f	\N	\N			HD	\N		Friday	Tuesday	\N	A+	16	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
12	100091954116	Prashant K		W/O	Female	8866273645	prashantkhalash11@gmail.com	CKD5D	2022-02-20		Immune	\N	\N	RC AVF Rt	2022-05-05	64.5	Morning	Morning	\N	https://wa.me/918866273645	t	f	t	admin	\N	2026-04-16 11:55:01.580029	2026-05-14 06:12:24.882965	\N	\N	0	\N	f	f	f	2024-02-13	2021-02-13	2021-03-13	2021-04-17	2021-08-14	\N	\N	\N	2024-05-24	2024-07-24	2	Secondary	161		\N		None	f	f	f	f	Never	None	2		f		Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N				\N		Monday	Thursday	\N	B+	34	60	prashant	$2b$12$AFehvOlrorYZhAeZWXHFV.2P/7abwNj0RCsS/1h1b0VAgA5ugv942	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
21	10003143018	Nandeep C S	None	M/O	Female	9847799636	pushpashyjan270@gmail.com	CKD5D	2025-10-26			\N	\N		\N	76	30/12/2025	02/01/2026	06/01/2026	https://wa.me/919847799636	t	f	f	admin	\N	2026-04-16 11:55:05.761536	2026-05-11 11:14:41.576106	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2		\N		\N		None	f	f	f	f			2		f				Negative	\N	f				Active	\N		f	\N	\N				\N		\N	\N	\N		\N	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
37	20131700046316	Y Srinivaslu 		W/O	Female	9476300310		CKD5D	\N			\N	\N	Right IJV Permcath	\N	64.5				https://wa.me/919476300310	f	f	f	admin	\N	2026-04-16 11:55:14.003863	2026-05-14 07:13:55.785964	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N
40	20285509616	Shobna Mehta	Pratul Mehta	W/O	Female	9642377031	sonamehta15@gmail.com	CKD5D	2024-12-01		Immune	\N	\N	Left BC AVF	2024-12-01	62				https://wa.me/919642377031	f	t	t	\N	\N	2026-05-07 05:51:18.259389	2026-05-14 07:31:56.448767	\N	\N	0	\N	f	f	f	2026-05-14	2026-05-14	\N	\N	\N	\N	2026-05-14	\N	2026-04-25	\N	2	Post-Graduate	164	Diabetic Nephropathy	2024-10-31	Not Done	Type 2	t	f	f	f	Never	None	4		f	NO	Negative	Negative	Negative	2025-03-20	f				Active	\N		f	\N	\N	Hypothyroidism		HD	\N					B+	55	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			2026-05-13	No RWMA, Trivial TR, Mild MR	Normal	\N	\N	\N	f	\N			\N
11	100071098516	P J SHAJI		W/O	Female	9673118974	alwin.shaji2003@gmail.com	CKD5D	2025-05-06		Immune	\N	\N	RC AVF Rt	2025-05-27	96	Morning	Morning	\N	https://wa.me/919673118974	t	f	t	admin	\N	2026-04-16 11:55:00.925482	2026-05-06 06:20:05.644504	\N	\N	0	\N	f	f	f	2025-05-08	2025-04-08	2025-05-08	2025-06-08	2025-09-08	\N	2025-07-18	\N	2025-07-21	2025-09-21	2	Secondary	153	Diabetic Nephropathy	2025-05-05	Not Done	Type 2	t	f	f	f	Never	None	4		f	NO	Negative	Negative	Negative	2025-09-20	f				Active	\N		f	\N	\N	Hypothyroidism, OSA, Morbid Obesity	NIL	HD	\N		Wednesday	Saturday	\N	B+	50	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
9	2013170087816	Joyson R	None	W/O	Female	7780226264	sonymoses29@gmail.com	CKD5D	2021-09-10		Immune	\N	\N	RC AVF Rt	2022-01-01	40	Morning	Morning	Morning	https://wa.me/917780226264	t	f	t	admin	\N	2026-04-16 11:55:00.098663	2026-05-07 06:10:23.058131	\N	\N	0	\N	f	f	f	2025-04-16	2022-06-05	2022-07-05	2022-08-05	2022-12-05	\N	2025-06-16	\N	2024-02-08	2024-04-08	3	Graduate	148	Chronic Glomerulonephritis	2021-09-01	Done	None	t	f	f	f	Never	None	2		f	Listed	Negative	Negative	Negative	2022-12-10	f				Active	\N		f	\N	\N	Hypothyroidism, Central venous stenosis		HD	\N		Tuesday	Thursday	Saturday	O+	34	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
18	20131557270518	RP Deshmukh		M/O	Female	8788007080	deshmukhnamrata90@gmail.com	CKD5D	2023-05-23		Immune	\N	\N	RC AVF Rt	2023-03-01	60	Morning	Morning	\N	https://wa.me/918788007080	t	f	t	admin	\N	2026-04-16 11:55:04.054038	2026-05-16 06:26:31.837473	\N	\N	0	\N	f	f	f	2023-06-15	2024-07-16	2024-08-16	2024-09-16	2024-12-16	\N	\N	\N	2024-07-19	2023-09-16	2	Secondary	160	Diabetic Nephropathy	2023-01-01	Not Done	None	t	f	f	f	Never	None	6		f	NO	Negative	Negative	Negative	2023-05-23	t				Active	\N		f	\N	\N	COPD		HD	\N		Wednesday	Saturday	\N	O+	70	60	\N	\N	f	f	f	t	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
5	20131518323419	D S Byas		F/O	Male	9567693581	dattusingh01051988@gmail.com	CKD5D	2023-04-24		In Progress	\N	\N	RC AVF Rt	2025-07-24	65.5	Morning	Morning	\N	https://wa.me/919567693581	t	f	t	admin	\N	2026-04-16 11:54:53.441219	2026-05-01 05:33:49.175391	\N	\N	0	\N	f	f	f	\N	2023-08-07	\N	\N	\N	\N	\N	\N	\N	\N	2		\N		\N		Type 2	t	f	f	f	Never		\N		f		Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N				\N		Tuesday	Friday	\N	A+	70	60	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N
19	2013458450618	Sagar Sapkal	None	M/O	Female	8605310932	sapkal020@gmail.com	CKD5D	2017-01-01		Immune	\N	\N	RC AVF Rt	\N	53	Morning	Morning	\N	https://wa.me/918605310932	t	f	t	admin	\N	2026-04-16 11:55:04.487141	2026-05-05 05:00:32.647462	\N	\N	0	\N	f	f	f	2024-05-18	2024-05-17	2024-05-17	2024-07-17	2024-11-08	\N	2024-05-28	\N	2024-05-21	2024-07-21	2	Primary	158		\N		None	f	f	f	f	Never	None	3		f		Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N			HD	\N		Tuesday	Friday	\N	B+	52	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
7	20131570165319	Gyanendra singh		F/O	Male	9993808970	rameshparihar056@gmail.com	CKD5D	2023-07-24		Non-Immune	\N	\N	RC AVF Lt	2023-10-07	51	Morning	Morning	\N	https://wa.me/919993808970	f	t	t	admin	\N	2026-04-16 11:54:59.358906	2026-05-11 05:25:22.35806	\N	\N	0	\N	f	f	f	2026-05-11	2025-12-01	2026-01-01	2026-04-10	2026-08-10	\N	2026-05-11	\N	2025-07-26	2026-09-26	2	Graduate	163	Unknown/Undetermined	2022-01-01	Not Done	None	t	t	f	f	Ex-smoker	None	5	Conservative Management	f	Inactive	Negative	Positive	Negative	2023-11-10	f				Active	\N		f	\N	\N	HCV Infection( Dec 2024) DAA- treated	NIL	HD	\N	CHSC	Monday	Thursday	\N	B+	64	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N		Normal	\N	\N	\N	f	\N			\N
22	20131558631822	Arun Chougale 		Other	Male	8798086001	raghunathchougale704@gmail.com	CKD5D	2025-05-31		Immune	\N	\N	RC AVF Rt	2025-07-01	68.5	Morning	Morning	\N	https://wa.me/918798086001	t	f	t	admin	\N	2026-04-16 11:55:06.304139	2026-05-15 06:56:31.650106	\N	\N	0	\N	f	f	f	2025-07-10	2025-06-28	2025-07-28	2025-08-28	2026-02-28	\N	2025-09-23	\N	2025-06-26	\N	2	Secondary	168		\N	Done	None	t	f	f	f	Never	None	2		f		Negative	Negative	Negative	2025-05-31	f				Active	\N		f	\N	\N			HDF	\N		Tuesday	Friday	\N	O+	36	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	2025-06-16			\N			\N	\N	\N	f	\N			\N
20	20111677219	Vijay Kumar 		F/O	Male	7001676325	sonuvijaykumar@gmail.com	CKD5D	2025-01-29		Immune	\N	\N	RC AVF Rt	2025-01-29	65.5	Morning	Morning	\N	https://wa.me/917001676325	t	f	t	admin	\N	2026-04-16 11:55:05.20528	2026-05-14 05:36:06.504377	\N	\N	0	\N	f	f	f	2025-01-30	2025-01-03	2025-02-02	2025-03-02	2025-07-02	\N	2025-07-21	\N	2025-06-28	2025-09-10	2	Illiterate	164		\N		None	f	f	f	f	Never	Occasional	5		f		Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N			HD	\N		Monday	Thursday	\N	A+	71	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
41	20131579890722	Kamalnath 		Self	Male	9424936071			2026-03-14		Immune	\N	\N	RC AVF Lt	\N	59				https://wa.me/919424936071	f	f	t	\N	\N	2026-05-11 09:05:43.398533	2026-05-13 06:33:08.451754	\N	\N	0	\N	f	f	f	2026-04-05	2026-04-07	2026-05-11	\N	\N	\N	2026-03-31	\N	2026-06-06	\N	2	Secondary	163		\N	Done	None	t	f	f	f	Never	None	2		f		Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N				\N					B+	35	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	2023-02-23			\N		Normal	\N	\N	\N	f	\N			\N
35	20300892419	Satish Barki		F/O	Male	9596946665	barkisatish@gmail.com	CKD5D	2025-08-07		Immune	\N	\N	RC AVF Rt	2025-10-30	71	Morning	Morning	\N	https://wa.me/919596946665	f	f	t	admin	admin	2026-04-16 11:55:12.921519	2026-05-06 08:46:58.245883	\N	\N	0	\N	f	f	f	2026-03-05	2025-08-11	2025-09-06	2025-10-11	2025-03-13	\N	\N	\N	2025-03-30	\N	2		\N		\N	Not Done	Type 2	f	f	f	f	Never	None	6	Conservative Management	f	Inactive	Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N			HD	\N	Pune	Wednesday	Saturday	\N	AB+	72	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
24	100094113719	R N Barik 	None	Other	Male	9815698922	barikbrundaban6@gmail.com	CKD5D	2025-08-07		Immune	\N	\N	RC AVF Rt	2023-09-18	71	30/12/2025	02/01/2026	06/01/2026	https://wa.me/919815698922	t	f	t	admin	\N	2026-04-16 11:55:07.039039	2026-05-16 05:09:32.20921	\N	\N	0	\N	f	f	f	2026-03-05	2025-08-11	2025-09-06	2025-10-11	\N	\N	2025-10-11	\N	2025-03-30	\N	2	Secondary	164		\N		None	t	f	f	f	Ex-smoker	Regular	5		f		Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N			HD	\N		\N	\N	\N	AB+	72	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
13	20131542744016	R B Pathak		W/O	Female	9541907011		CKD5D	\N		Immune	\N	\N	RC AVF Rt	2026-02-19	47	Morning	Morning	Morning	https://wa.me/919541907011	t	f	t	admin	\N	2026-04-16 11:55:02.013196	2026-05-13 14:13:06.898739	\N	\N	0	\N	f	f	f	2024-07-12	2023-07-08	2023-08-08	2023-09-08	2024-01-08	\N	2024-03-10	\N	2024-07-14	2024-08-14	3	Graduate	\N		\N		None	f	f	f	f	Never	None	2		f	Active	Negative	Negative	Negative	\N	t				Active	\N		f	\N	\N				\N		Monday	Wednesday	Saturday	B+	34	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
6	2013280323516	Ganesh Balgude		W/O	Female	7219786978	balgudeganesh71@gmail.com	CKD5D	2023-09-29		Immune	\N	\N	RC AVF Rt	2023-10-13	39.5	Morning	Morning	Morning	https://wa.me/917219786978	t	f	t	admin	\N	2026-04-16 11:54:58.459451	2026-05-16 07:34:33.058915	\N	\N	0	\N	f	f	f	2024-10-19	2025-01-23	2025-02-25	2025-03-25	2025-06-25	\N	2025-03-11	2025-05-11	2024-07-14	2024-09-14	3	Secondary	150	Diabetic Nephropathy	2023-11-25	Done	Type 2	t	f	f	f	Never	None	4		f	Listed	Negative	Negative	Negative	2023-12-01	f				Active	\N		f	\N	\N	Diabetic Retinopathy (PDR)	NIL	HD	\N		Monday	Wednesday	Saturday	O+	41	60	\N	\N	t	f	f	f	f	f	None	f	None	f	f	2023-11-01	Diabetic Nephropathy		2026-03-06	No RWMA, Mild MR, Normal RA RV dimension	None	\N	\N	\N	f	\N			\N
34	20131545488116	Mijanur Rahman 		W/O	Female	8942991635		CKD5D	2025-10-10		Immune	\N	\N	RC AVF Rt	2025-03-20	38.5	Morning	Morning	\N	https://wa.me/918942991635	f	t	t	admin	\N	2026-04-16 11:55:12.604867	2026-05-16 06:29:59.484183	\N	\N	0	\N	f	f	f	2026-03-14	2025-05-15	2025-06-15	2025-07-15	2025-11-15	\N	\N	\N	2026-02-14	2026-05-05	2	Graduate	155	Chronic Glomerulonephritis	2023-11-10	Done	None	t	f	f	f	Never	None	3		f	Listed	Negative	Negative	Negative	2025-10-10	f				Active	\N		f	\N	\N	ANCA Vasculitis		HDF	\N		Monday	Thursday	\N	O+	23	60	\N	\N	f	f	f	f	t	f	None	f	None	f	f	2023-11-10	ANCA Vasculitis		2025-03-03	No RWMA, Valves- normal	Normal	\N	\N	\N	f	\N			\N
10	20131612349216	Mahingappa	None	W/O	Female	6360503698	gouravvatirakannavar@gmail.com	CKD5D	2020-01-01		Immune	\N	\N	RC AVF Rt	2019-11-01	35.5	30/12/2025	02/01/2026	06/01/2026	https://wa.me/916360503698	t	f	t	admin	\N	2026-04-16 11:55:00.512287	2026-05-12 07:38:39.424618	\N	\N	0	\N	f	f	f	2025-04-12	2024-07-12	2024-08-12	2024-09-12	2025-03-12	\N	2024-07-12	2024-09-12	2024-07-15	2024-07-14	2	Secondary	169	Chronic Glomerulonephritis	2019-01-01	Not Done	None	t	f	f	f	Never	None	2		f	NO	Negative	Negative	Negative	2019-12-01	f				Active	\N		f	\N	\N	Hyperparathyroidism , Brown's tumour (optd)		HD	\N		\N	\N	\N	B-	25	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N		CKD5D, Recurrent Brown's Tumour	\N			\N	\N	\N	f	\N			\N
3	20131558799119	Arjun Ubale		F/O	Male	9322660277	sahebaravaubale771@gmail.com	CKD5D	2023-02-06		Immune	\N	\N	RC AVF Rt	2023-03-17	57	Morning	Morning	\N	https://wa.me/919322660277	t	f	t	admin	\N	2026-04-16 11:54:52.620323	2026-05-12 09:29:41.062961	\N	\N	0	\N	f	f	f	2023-06-07	2024-03-05	2024-04-05	2024-05-05	2024-08-05	\N	2023-08-07	\N	2024-04-10	2024-06-10	2	Secondary	160	Obstructive Uropathy	2023-02-01	Not Done	Type 2	t	f	t	f	Never	Occasional	5		f	NO	Negative	Negative	Negative	2023-05-18	f	Left RC AVF- Primary Faliure ( Mar 23)			Active	\N		f	\N	\N			HDF	\N		Tuesday	Friday	\N	O+	56	30	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			2023-04-18	LVEF 30%, global hypokinesia, tricuspid regurgitation	None	\N	\N	\N	f	\N			\N
42	100082457616	Ratnamala Khude	R S Khude	W/O	Male	9205562697		CKD5D	2023-01-19		Immune	\N	\N	Left BC AVF	2023-02-02	49				https://wa.me/919205562697	f	f	t	\N	\N	2026-05-14 10:10:24.112557	2026-05-15 06:19:32.345133	\N	\N	0	\N	f	f	f	2025-10-10	2023-06-15	2023-07-15	2023-08-15	2023-12-15	\N	2026-05-15	\N	\N	\N	2	Graduate	160		\N		None	f	f	f	f	Never	None	2		f		Negative	Negative	Negative	2023-04-10	f				Active	\N		f	\N	\N			HD	\N					O+	34	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N		Normal	\N	\N	\N	f	\N			\N
43	20131464830716	Sangeeta Pandey 	Binod Pandey	Self	Female	7737584444	vaibhav9125@gmail.com		2025-08-13		Immune	\N	\N	Left BC AVF	2025-10-23	42				https://wa.me/917737584444	f	f	t	\N	\N	2026-05-15 06:38:43.691208	2026-05-15 06:38:43.691211	\N	\N	0	\N	f	f	f	2026-04-25	2024-05-27	2024-06-27	2025-07-27	2024-11-11	\N	\N	\N	2026-05-11	\N	2	Post-Graduate	164		\N		None	t	f	f	f	Never	None	2		f		Negative	Negative	Negative	2026-01-10	f				Active	\N		f	\N	\N			HD	\N					B+	41	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N		Normal	\N	\N	\N	f	\N			\N
29	20131522950516	Shivshankar B M	None	W/O	Female	9483318368		CKD5D	2025-07-23			\N	\N		2025-11-11	49.5	31/12/2025	3/1/2026	07/01/2026	https://wa.me/919483318368	t	f	t	admin	\N	2026-04-16 11:55:10.554909	2026-05-15 10:31:45.927106	\N	\N	0	\N	f	f	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2		\N		\N		None	f	f	f	f			2		f				Negative	\N	f				Transplanted	\N		f	\N	\N				\N		\N	\N	\N		\N	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
44	20286641619	Popat S Shinde	Pravin Popat Shinde 	F/O	Male	9545651507			2025-12-10		Immune	\N	\N	Rt BC AVF	\N	83				https://wa.me/919545651507	f	f	t	\N	\N	2026-05-15 06:50:15.779827	2026-05-15 12:08:09.054053	\N	\N	0	\N	f	f	f	2026-03-10	2026-02-27	2026-03-27	2026-04-27	\N	\N	\N	\N	\N	\N	2	Secondary	164		\N		None	f	f	f	f	Ex-smoker	None	5		f		Negative	Negative	Negative	\N	f				Active	\N		f	\N	\N				\N					O+	75	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N		Normal	\N	\N	\N	f	\N			\N
27	100077113516	D k Uttam		W/O	Female	9449430367	devenpreet@gmail.com	CKD5D	2025-09-03			\N	\N	Left BC AVF	\N	52.5	Morning	Morning	\N	https://wa.me/919449430367	t	f	t	admin	\N	2026-04-16 11:55:08.14659	2026-05-16 07:07:57.669014	\N	\N	0	\N	f	f	f	2025-09-18	2025-10-14	2025-11-14	2025-12-15	2026-03-16	\N	2025-12-22	\N	2026-01-27	\N	2	Secondary	160		\N		None	f	f	f	f	Never	None	2		f		Positive	Negative	Negative	\N	f				Active	\N		f	\N	\N	Chronic Hepatitis B		HD	\N		Wednesday	Saturday	\N	O+	48	60	\N	\N	f	f	f	f	f	f	None	f	None	f	f	\N			\N			\N	\N	\N	f	\N			\N
\.


--
-- Data for Name: research_projects; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.research_projects (id, title, description, status, created_at) FROM stdin;
1	test research	test	Active	2026-05-01 11:55:02.339501
2	sarcopenia	test2	Active	2026-05-02 08:43:40.555835
\.


--
-- Data for Name: research_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.research_records (id, project_id, patient_id, test_type, test_date, data, notes, entered_by, created_at) FROM stdin;
1	1	3	HANDGRIP_STRENGTH	2026-05-01	{"dominant_hand_kg": "2", "nondominant_hand_kg": "1", "dynamometer_model": "tets"}	tets	admin	2026-05-01 11:55:24.855241
\.


--
-- Data for Name: session_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.session_records (id, patient_id, session_date, record_month, entered_by, "timestamp", provider, dialysis_type, scheduled_treatment_duration, duration_hours, duration_minutes, weight_pre, weight_post, uf_volume, actual_uf_volume, uf_rate, bp_pre_sys, bp_pre_dia, bp_during_sys, bp_during_dia, bp_peak_sys, bp_peak_dia, bp_nadir_sys, bp_nadir_dia, bp_post_sys, bp_post_dia, blood_flow_rate, actual_blood_flow_rate, dialysate_flow, dialyzer_type, dialyzer_surface_area, dialyzer_membrane_flux, dialysate_buffer, dialysate_sodium, dialysate_potassium, dialysate_calcium, dialysate_bicarbonate, dialysate_temperature, arterial_line_pressure, venous_line_pressure, transmembrane_pressure, anticoagulation, anticoagulation_dose, access_location, access_condition, needle_gauge, cannulation_technique, vascular_interventions, access_complications, medications_administered, idh_episode, idh_hypertension, muscle_cramps, nausea_vomiting, chest_pain, arrhythmia, early_termination, reason_early_termination, complications_occurred, complications_description, complications_management, dialysis_adherence, doctor_concerns, next_appointment_id, interim_hb, interim_k, interim_ca, interim_trigger, intradialytic_exercise_mins, intradialytic_meals_eaten, pre_hd_dyspnea_likert, post_hd_dyspnea_likert, is_emergency, reason_emergency, urea_peripheral_s, urea_arterial_a, urea_venous_v, access_recirculation_percent, access_flow_qa, dialysate_flow_direction) FROM stdin;
1	5	2026-04-21	2026-04		2026-04-21 08:50:42.720239	\N	\N	\N	4	\N	66.9	65.8	\N	\N	\N	140	68	\N	\N	\N	\N	\N	\N	138	78	\N	\N	500		\N	\N	\N	\N	\N	\N	\N	\N	100	100	\N		5000		Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
2	19	2026-05-01	2026-05		2026-05-01 04:49:13.370017	\N	\N	\N	\N	\N	54.8	53	\N	\N	\N	170	80	\N	\N	\N	\N	\N	\N	190	88	\N	\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	-100	130	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	8.3	6.4	8.3	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
3	19	2026-05-01	2026-05		2026-05-01 04:49:19.471785	\N	\N	\N	\N	\N	54.8	53	\N	\N	\N	170	80	\N	\N	\N	\N	\N	\N	190	88	\N	\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	-100	130	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	8.3	6.4	8.3	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
4	19	2026-05-01	2026-05		2026-05-01 04:49:27.506209	\N	\N	\N	\N	\N	54.8	53	\N	\N	\N	170	80	\N	\N	\N	\N	\N	\N	190	88	\N	\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	-100	130	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	8.3	6.4	8.3	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
5	19	2026-05-01	2026-05		2026-05-01 04:49:30.416969	\N	\N	\N	\N	\N	54.8	53	\N	\N	\N	170	80	\N	\N	\N	\N	\N	\N	190	88	\N	\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	-100	130	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	8.3	6.4	8.3	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
6	19	2026-05-01	2026-05		2026-05-01 04:49:39.791978	\N	\N	\N	\N	\N	54.8	53	\N	\N	\N	170	80	\N	\N	\N	\N	\N	\N	190	88	\N	\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	-100	130	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	8.3	6.4	8.3	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
7	19	2026-05-01	2026-05		2026-05-01 04:49:46.794763	\N	\N	\N	\N	\N	54.8	53	\N	\N	\N	170	80	\N	\N	\N	\N	\N	\N	190	88	\N	\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	-100	130	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	8.3	6.4	8.3	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
8	19	2026-05-01	2026-05		2026-05-01 04:55:18.561327	\N	\N	\N	\N	\N	54.8	53	\N	\N	\N	170	80	\N	\N	\N	\N	\N	\N	190	88	\N	\N	\N		\N	\N	\N	\N	\N	\N	\N	\N	-100	130	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	8.3	6.4	8.3	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
9	20	2026-05-04	2026-05		2026-05-04 06:01:08.822019	\N	\N	\N	\N	\N	66.6	\N	\N	\N	\N	112	64	\N	\N	\N	\N	\N	\N	\N	\N	250	250	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	4700			16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
10	20	2026-05-04	2026-05		2026-05-04 06:01:08.880533	\N	\N	\N	\N	\N	66.6	\N	\N	\N	\N	112	64	\N	\N	\N	\N	\N	\N	\N	\N	250	250	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	4700			16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
11	25	2026-05-04	2026-05		2026-05-04 06:45:47.438101	\N	\N	\N	\N	\N	52.3	\N	\N	\N	\N	148	82	\N	\N	\N	\N	\N	\N	\N	\N	250	250	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	120	\N	Heparin	5000	RC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
12	12	2026-05-04	2026-05		2026-05-04 06:53:27.048899	\N	\N	\N	\N	\N	67	\N	\N	\N	\N	164	100	\N	\N	\N	\N	\N	\N	\N	\N	250	250	500	f80	\N	\N	\N	\N	\N	\N	\N	\N	\N	100	\N	Heparin	5000	RC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
13	13	2026-05-04	2026-05		2026-05-04 07:00:10.239142	\N	\N	\N	\N	\N	48.3	\N	\N	\N	\N	125	90	\N	\N	\N	\N	\N	\N	\N	\N	250	250	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	100	\N	Heparin	2000	RC AVF Lt	Good	17G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
14	7	2026-05-04	2026-05		2026-05-04 07:04:51.994448	\N	\N	\N	\N	\N	52.4	\N	\N	\N	\N	140	80	\N	\N	\N	\N	\N	\N	\N	\N	200	200	500		\N	\N	\N	\N	\N	\N	\N	\N	\N	100	\N	Heparin	4600	RC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
15	6	2026-05-04	2026-05		2026-05-04 07:45:57.787534	\N	\N	\N	\N	\N	40.7	\N	\N	\N	\N	180	\N	\N	\N	\N	\N	\N	\N	\N	\N	250	250	460		\N	\N	\N	\N	\N	\N	\N	\N	\N	100	\N	Heparin	3000	RC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
16	31	2026-05-04	2026-05		2026-05-04 07:55:22.505275	\N	\N	\N	\N	\N	4.2	\N	\N	\N	\N	190	70	\N	\N	\N	\N	\N	\N	\N	\N	250	230	500		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	None (heparin-free)	\N							\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
17	31	2026-05-04	2026-05		2026-05-04 08:00:11.163557	\N	\N	\N	\N	\N	42.2	\N	\N	\N	\N	190	66	\N	\N	\N	\N	\N	\N	\N	\N	250	250	500		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	None (heparin-free)	\N							\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
18	25	2026-05-04	2026-05		2026-05-04 08:03:10.069181	\N	\N	\N	\N	\N	52.3	\N	\N	\N	\N	148	82	\N	\N	\N	\N	\N	\N	\N	\N	250	230	500		\N	\N	\N	\N	\N	\N	\N	\N	\N	85	\N	Heparin	5000	RC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
19	19	2026-05-05	2026-05		2026-05-05 04:31:14.856979	\N	\N	\N	\N	\N	55.1	\N	\N	\N	\N	180	80	\N	\N	\N	\N	\N	\N	\N	\N	200	200	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	140	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
20	19	2026-05-05	2026-05		2026-05-05 04:31:14.967262	\N	\N	\N	\N	\N	55.1	\N	\N	\N	\N	180	80	\N	\N	\N	\N	\N	\N	\N	\N	200	200	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	140	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
21	19	2026-05-05	2026-05		2026-05-05 04:31:14.989969	\N	\N	\N	\N	\N	55.1	\N	\N	\N	\N	180	80	\N	\N	\N	\N	\N	\N	\N	\N	200	200	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	140	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
22	19	2026-05-05	2026-05		2026-05-05 04:37:57.965459	\N	\N	\N	\N	\N	55.1	\N	\N	\N	\N	180	80	\N	\N	\N	\N	\N	\N	\N	\N	200	200	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	140	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
23	3	2026-05-05	2026-05		2026-05-05 04:47:30.096428	\N	\N	\N	4	\N	58.5	\N	\N	\N	\N	124	68	\N	\N	\N	\N	\N	\N	\N	\N	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	150	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
24	9	2026-05-05	2026-05		2026-05-05 06:17:11.506009	\N	\N	\N	4	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	250	250	\N	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	140	\N		\N	BC AVF Rt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
25	22	2026-05-05	2026-05		2026-05-05 06:24:36.442913	\N	\N	\N	4	\N	67.8	67.8	\N	\N	\N	140	80	\N	\N	\N	\N	\N	\N	\N	\N	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	140	\N	Heparin	5000	BC AVF Rt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
26	9	2026-05-05	2026-05		2026-05-05 06:45:15.940656	\N	\N	\N	4	\N	41.5	\N	\N	\N	\N	120	80	\N	\N	\N	\N	\N	\N	\N	\N	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	150	\N	Heparin	3000	BC AVF Rt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
27	9	2026-05-05	2026-05		2026-05-05 06:45:16.576713	\N	\N	\N	4	\N	41.5	\N	\N	\N	\N	120	80	\N	\N	\N	\N	\N	\N	\N	\N	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	150	\N	Heparin	3000	BC AVF Rt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
28	11	2026-05-06	2026-05		2026-05-06 06:25:35.280911	\N	\N	\N	4	\N	95	\N	\N	\N	\N	168	\N	\N	\N	\N	\N	\N	\N	\N	\N	250	250	500	Elisio 15	\N	\N	\N	\N	\N	\N	\N	\N	\N	140	\N	Heparin	6000	RC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
29	6	2026-05-06	2026-05		2026-05-06 08:09:28.727676	\N	\N	\N	4	\N	40.7	41	\N	\N	\N	166	90	\N	\N	\N	\N	\N	\N	144	70	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	160	\N		\N	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
30	6	2026-05-06	2026-05		2026-05-06 08:13:04.871956	\N	\N	\N	4	\N	40.7	41	\N	\N	\N	166	90	\N	\N	\N	\N	\N	\N	144	90	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	150	\N	Heparin	3000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
31	6	2026-05-06	2026-05		2026-05-06 08:13:59.798444	\N	\N	\N	4	\N	40.7	41	\N	\N	\N	166	90	\N	\N	\N	\N	\N	\N	144	90	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	150	\N	Heparin	3000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
32	13	2026-05-06	2026-05		2026-05-06 08:21:00.661322	\N	\N	\N	4	\N	48.3	47.1	\N	\N	\N	114	79	\N	\N	\N	\N	\N	\N	142	90	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	100	\N	Heparin	3000	BC AVF Lt	Good	17G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
33	13	2026-05-06	2026-05		2026-05-06 08:21:00.83233	\N	\N	\N	4	\N	48.3	47.1	\N	\N	\N	114	79	\N	\N	\N	\N	\N	\N	142	90	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	100	\N	Heparin	3000	BC AVF Lt	Good	17G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
34	13	2026-05-06	2026-05		2026-05-06 08:25:32.606046	\N	\N	\N	4	\N	48.3	47.1	\N	\N	\N	114	79	\N	\N	\N	\N	\N	\N	142	90	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	100	\N	Heparin	3000	BC AVF Lt	Good	17G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
35	35	2026-05-06	2026-05		2026-05-06 09:53:43.623864	\N	\N	\N	4	\N	71.6	71.1	\N	\N	\N	126	132	\N	\N	\N	\N	\N	\N	160	64	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	100	\N	None (heparin-free)	\N	RC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
36	35	2026-05-06	2026-05		2026-05-06 09:55:12.011623	\N	\N	\N	4	\N	71.6	71.1	\N	\N	\N	126	132	\N	\N	\N	\N	\N	\N	160	64	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	100	\N	None (heparin-free)	\N	RC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
37	40	2026-05-11	2026-05		2026-05-11 09:29:40.962105	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	250	250	\N		\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
38	41	2026-05-13	2026-05		2026-05-13 06:53:56.608202	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N		\N							\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
39	8	2026-05-14	2026-05		2026-05-14 04:30:54.523582	\N	\N	\N	4	\N	76.5	75.7	\N	\N	\N	120	68	\N	\N	\N	\N	\N	\N	148	78	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	5000	BC AVF Rt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
40	8	2026-05-14	2026-05		2026-05-14 04:33:05.652589	\N	\N	\N	4	\N	76.5	75.7	\N	\N	\N	120	68	\N	\N	\N	\N	\N	\N	148	78	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	5000	BC AVF Rt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
41	20	2026-05-14	2026-05		2026-05-14 04:39:24.312783	\N	\N	\N	4	\N	69	68.2	\N	\N	\N	160	80	\N	\N	\N	\N	\N	\N	162	84	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	5000	BC AVF Rt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
42	20	2026-05-14	2026-05		2026-05-14 04:39:40.320036	\N	\N	\N	4	\N	69	68.2	\N	\N	\N	160	80	\N	\N	\N	\N	\N	\N	162	84	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	5000	BC AVF Rt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
43	31	2026-05-14	2026-05		2026-05-14 04:52:11.732832	\N	\N	\N	\N	\N	42.9	40	\N	\N	\N	150	68	\N	\N	\N	\N	\N	\N	144	70	200	200	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	None (heparin-free)	\N	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
44	34	2026-05-14	2026-05		2026-05-14 05:44:35.355011	\N	\N	\N	\N	\N	38.2	38.2	\N	\N	\N	180	100	\N	\N	\N	\N	\N	\N	160	90	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	3000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
45	34	2026-05-14	2026-05		2026-05-14 05:53:30.459034	\N	\N	\N	\N	\N	38.2	38.2	\N	\N	\N	180	100	\N	\N	\N	\N	\N	\N	164	90	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	3000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
46	34	2026-05-14	2026-05		2026-05-14 06:02:34.997149	\N	\N	\N	4	\N	38.2	38.2	\N	\N	\N	180	100	\N	\N	\N	\N	\N	\N	160	90	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	3000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
47	34	2026-05-14	2026-05		2026-05-14 06:03:15.606396	\N	\N	\N	4	\N	38.2	38.2	\N	\N	\N	180	100	\N	\N	\N	\N	\N	\N	160	90	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	3000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
48	40	2026-05-14	2026-05		2026-05-14 06:06:05.752243	\N	\N	\N	4	\N	64.9	62.2	\N	\N	\N	165	86	\N	\N	\N	\N	\N	\N	158	86	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	3000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
49	12	2026-05-14	2026-05		2026-05-14 06:11:46.726109	\N	\N	\N	4	\N	67.2	65.2	\N	\N	\N	160	90	\N	\N	\N	\N	\N	\N	132	86	300	300	\N	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
50	12	2026-05-14	2026-05		2026-05-14 06:21:32.617927	\N	\N	\N	4	\N	67.2	65.2	\N	\N	\N	160	90	\N	\N	\N	\N	\N	\N	132	86	300	300	\N	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
51	12	2026-05-14	2026-05		2026-05-14 06:21:48.035313	\N	\N	\N	4	\N	67.2	65.2	\N	\N	\N	160	90	\N	\N	\N	\N	\N	\N	132	86	300	300	\N	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	\N
52	25	2026-05-14	2026-05		2026-05-14 06:40:46.726742	\N	\N	\N	4	\N	52.6	51	\N	\N	\N	120	68	\N	\N	\N	\N	\N	\N	160	80	250	250	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	Heparin	5000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
53	26	2026-05-14	2026-05		2026-05-14 06:51:33.282668	\N	\N	\N	4	\N	46.5	46.6	\N	\N	\N	107	54	\N	\N	\N	\N	\N	\N	142	58	200	200	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	None (heparin-free)	\N	BC AVF Rt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
54	26	2026-05-14	2026-05		2026-05-14 06:51:33.4671	\N	\N	\N	4	\N	46.5	46.6	\N	\N	\N	107	54	\N	\N	\N	\N	\N	\N	142	58	200	200	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	None (heparin-free)	\N	BC AVF Rt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
55	25	2026-05-14	2026-05	ss	2026-05-14 10:15:51.514691	\N	\N	\N	4	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	250	250	500	FX80	\N	\N	\N	\N	\N	\N	\N	\N	-150	120	\N	Heparin	\N	BC AVF Lt	Good	16G	Rope-ladder		NIL	\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	1	1	f	\N	\N	\N	\N	\N	\N	Countercurrent
56	42	2026-05-12	2026-05		2026-05-15 06:23:59.214897	\N	\N	\N	4	\N	50.7	48.8	\N	\N	\N	164	84	\N	\N	\N	\N	\N	\N	156	76	280	280	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	140	\N	Heparin	3000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
57	42	2026-05-12	2026-05		2026-05-15 06:23:59.67209	\N	\N	\N	4	\N	50.7	48.8	\N	\N	\N	164	84	\N	\N	\N	\N	\N	\N	156	76	280	280	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	140	\N	Heparin	3000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
58	42	2026-05-12	2026-05		2026-05-15 06:24:09.212915	\N	\N	\N	4	\N	50.7	48.8	\N	\N	\N	164	84	\N	\N	\N	\N	\N	\N	156	76	280	280	500	Fx80	\N	\N	\N	\N	\N	\N	\N	\N	\N	140	\N	Heparin	3000	BC AVF Lt	Good	16G	Rope-ladder			\N	f	\N	f	\N	\N	\N	f	\N	f	\N	\N	\N	\N	\N	\N	\N	\N	Routine Recheck (Session)	\N	f	\N	\N	f	\N	\N	\N	\N	\N	\N	Countercurrent
\.


--
-- Data for Name: sustainability_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.sustainability_records (id, record_month, electricity_kwh, water_m3, biomedical_waste_kg, general_waste_kg, total_sessions_override, avg_transport_dist_km, "timestamp", updated_by) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (id, username, full_name, hashed_password, role, is_active, created_at, last_login) FROM stdin;
2	staff	Staff User	$2b$12$BuHGpefclJ/0uBh6pH7hne4smEikgRwbzJMeEsvNvpIpduazrOWKa	staff	t	2026-04-30 02:48:05.284582	2026-05-13 01:45:03.623034
3	doctor	Doctor User	$2b$12$tK8FltIJGki2pFhHI3SI/eCBWHfJGjWcIJN/BzFLK.HA5K5.oEsQy	doctor	t	2026-04-30 02:48:05.284587	2026-05-07 05:32:21.649951
1	admin	System Admin	$2b$12$kaa85WE5VcVlJRk/ROY5Qegl4nnxEiir8KEw/vApzyvj8S2yFE/aG	admin	t	2026-04-16 08:51:58.81807	2026-05-16 08:21:33.733208
\.


--
-- Data for Name: variable_definitions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.variable_definitions (id, name, display_name, unit, category, data_type, decimal_places, threshold_low, threshold_high, target_low, target_high, description, show_in_dashboard, show_in_timeline, is_active, alert_direction, created_at, created_by) FROM stdin;
1	crp	C-Reactive Protein	mg/dL	Inflammation	numeric	2	\N	2	\N	\N	\N	f	t	t	\N	2026-04-16 19:55:53.014174	system
2	bt_units	Blood Transfusion	Units	Anemia	numeric	2	\N	1	\N	\N	\N	f	t	t	\N	2026-04-16 19:55:53.014174	system
3	kt_v	Kt/V		Adequacy	numeric	2	1.2	\N	\N	\N	\N	t	t	t	\N	2026-04-16 19:55:53.014174	system
4	bicarbonate	Bicarbonate	mmol/L	Electrolytes	numeric	2	22	26	\N	\N	\N	f	t	t	\N	2026-04-16 19:55:53.014174	system
5	sbp_pre	Pre-dialysis SBP	mmHg	Vitals	numeric	2	\N	160	\N	\N	\N	t	t	t	\N	2026-04-16 19:55:53.014174	system
6	idh_events	IDH Events	Count	Safety	numeric	2	\N	1	\N	\N	\N	f	t	t	\N	2026-04-16 19:55:53.014174	system
7	uric_acid	Uric Acid	mg/dL	Metabolic	numeric	2	\N	7	\N	\N	\N	f	t	t	\N	2026-04-16 19:55:53.014174	system
8	blood_transfusion_units	Blood Transfusion	units/month	Clinical	integer	0	\N	0	\N	\N	Number of packed red cell units transfused this month.	t	t	t	high	2026-04-16 19:55:53.192426	system
9	systolic_bp_pre	Pre-dialysis SBP	mmHg	Vitals	integer	0	90	160	\N	\N	Average pre-dialysis systolic blood pressure this month.	f	t	t	both	2026-04-16 19:55:53.192428	system
10	intradialytic_hypotension	Intradialytic Hypotension	episodes/month	Clinical	integer	0	\N	2	\N	\N	Number of IDH episodes requiring intervention this month.	t	t	t	high	2026-04-16 19:55:53.192431	system
\.


--
-- Data for Name: variable_values; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.variable_values (id, patient_id, variable_id, record_month, value_num, value_text, entered_by, "timestamp", entered_at) FROM stdin;
\.


--
-- Name: alert_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.alert_logs_id_seq', 1, false);


--
-- Name: blood_transfusions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.blood_transfusions_id_seq', 1, false);


--
-- Name: clinical_events_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.clinical_events_id_seq', 1, false);


--
-- Name: dry_weight_assessments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.dry_weight_assessments_id_seq', 1, false);


--
-- Name: hospitalisation_events_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.hospitalisation_events_id_seq', 1, false);


--
-- Name: interim_lab_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.interim_lab_records_id_seq', 21, true);


--
-- Name: monthly_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.monthly_records_id_seq', 368, true);


--
-- Name: patient_meal_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.patient_meal_records_id_seq', 1, false);


--
-- Name: patient_reminders_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.patient_reminders_id_seq', 1, true);


--
-- Name: patient_symptom_reports_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.patient_symptom_reports_id_seq', 1, false);


--
-- Name: patients_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.patients_id_seq', 44, true);


--
-- Name: research_projects_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.research_projects_id_seq', 2, true);


--
-- Name: research_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.research_records_id_seq', 1, true);


--
-- Name: session_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.session_records_id_seq', 58, true);


--
-- Name: sustainability_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.sustainability_records_id_seq', 1, false);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.users_id_seq', 3, true);


--
-- Name: variable_definitions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.variable_definitions_id_seq', 10, true);


--
-- Name: variable_values_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.variable_values_id_seq', 1, false);


--
-- Name: alert_logs alert_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_logs
    ADD CONSTRAINT alert_logs_pkey PRIMARY KEY (id);


--
-- Name: blood_transfusions blood_transfusions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blood_transfusions
    ADD CONSTRAINT blood_transfusions_pkey PRIMARY KEY (id);


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
-- Name: hospitalisation_events hospitalisation_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hospitalisation_events
    ADD CONSTRAINT hospitalisation_events_pkey PRIMARY KEY (id);


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
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: variable_definitions variable_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.variable_definitions
    ADD CONSTRAINT variable_definitions_pkey PRIMARY KEY (id);


--
-- Name: variable_values variable_values_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.variable_values
    ADD CONSTRAINT variable_values_pkey PRIMARY KEY (id);


--
-- Name: ix_alert_logs_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_logs_id ON public.alert_logs USING btree (id);


--
-- Name: ix_blood_transfusions_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_blood_transfusions_id ON public.blood_transfusions USING btree (id);


--
-- Name: ix_clinical_events_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clinical_events_id ON public.clinical_events USING btree (id);


--
-- Name: ix_dry_weight_assessments_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dry_weight_assessments_id ON public.dry_weight_assessments USING btree (id);


--
-- Name: ix_hospitalisation_events_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_hospitalisation_events_id ON public.hospitalisation_events USING btree (id);


--
-- Name: ix_hospitalisation_events_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_hospitalisation_events_patient_id ON public.hospitalisation_events USING btree (patient_id);


--
-- Name: ix_interim_lab_records_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_interim_lab_records_id ON public.interim_lab_records USING btree (id);


--
-- Name: ix_monthly_records_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monthly_records_id ON public.monthly_records USING btree (id);


--
-- Name: ix_monthly_records_record_month; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_monthly_records_record_month ON public.monthly_records USING btree (record_month);


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
-- Name: ix_variable_definitions_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_variable_definitions_id ON public.variable_definitions USING btree (id);


--
-- Name: ix_variable_definitions_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_variable_definitions_name ON public.variable_definitions USING btree (name);


--
-- Name: ix_variable_values_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_variable_values_id ON public.variable_values USING btree (id);


--
-- Name: ix_variable_values_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_variable_values_patient_id ON public.variable_values USING btree (patient_id);


--
-- Name: ix_variable_values_record_month; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_variable_values_record_month ON public.variable_values USING btree (record_month);


--
-- Name: ix_variable_values_variable_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_variable_values_variable_id ON public.variable_values USING btree (variable_id);


--
-- Name: alert_logs alert_logs_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_logs
    ADD CONSTRAINT alert_logs_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: blood_transfusions blood_transfusions_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blood_transfusions
    ADD CONSTRAINT blood_transfusions_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


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
-- Name: hospitalisation_events hospitalisation_events_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hospitalisation_events
    ADD CONSTRAINT hospitalisation_events_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


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
-- Name: variable_values variable_values_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.variable_values
    ADD CONSTRAINT variable_values_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: variable_values variable_values_variable_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.variable_values
    ADD CONSTRAINT variable_values_variable_id_fkey FOREIGN KEY (variable_id) REFERENCES public.variable_definitions(id);


--
-- PostgreSQL database dump complete
--

\unrestrict pGTEtQDgi08x25Aowmw0Ybi5Og9g8RLOKfhq7XTbzDZI0y31chcYjUI54rflNqz

