import os
import sys
from datetime import datetime
from database import SessionLocal, Patient, MonthlyRecord, User, create_tables
from main import pwd_context

# Raw data from user
DATA = """Ajit Shinde	F/O	Male	400040426619	9763222914	CKD5D	08/03/2024	NEG	AVF	16/09/2023	74	3.5	10.8	468		41	M-100/30	7.9	61	6	3	7	19						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा).	This is an automated email	anandraoshinde07@gmail.com	30/12/2025	02/01/2026	06/01/2026
Aloknath bala	F/O	Male	20131558744519	9755036039	CKD5D	01/08/2024	Positive	AVF	Dec 2024	61	1	7	804		59	M-75/15	8.4	144	3.9	2.5	52	24						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा).	This is an automated email.	piyalibala17971@gmail.com	30/12/2025	02/01/2026	06/01/2026
Arjun Ubale	F/O	Male	20131558799119	9322660277	CKD5D	06/02/2023	NEG	AVF	02/03/2023	59.5	2.5	11.8	1286		49	M-100/30	8.8	136	4.2	3.4	9	15						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	sahebaravaubale771@gmail.com	30/12/2025	02/01/2026	06/01/2026
D B Jadhav	SELF	Male	2013151873822	8788092169	CKD5D	21 Jan 2019	NEG	AVF	24/11/25	56	2	8.4				Mircera 100	8.7	73	1.6	2.9	13	18						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	Kavitajadhav00171@gmail.com	29/12/2025	31/12/2025	03/01/2026
D S Byas	F/O	Male	20131518323419	9567693581	CKD5D	Jun 2024	NEG	AVF	07/24/25	65.5	2	11.8	703		66	Mircera 75	-	271	4.9	3.5	13	18						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	dattusingh01051988@gmail.com	30/12/2025	02/01/2026	06/01/2026
Ganesh Balgude	W/O	Female	2013280323516	7219786978	CKD5D	29/09/23	NEG	AVF	13/10/23	42	3	7.8	902		34	ERIPeg100/15	-	157	-	2.3	28	23						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	balgudeganesh71@gmail.com	29/12/2025	01/01/2026	05/01/2026
Gyanendra singh	F/O	Male	20131570165319	9993808970	CKD5D	07/24/23	Positive	AVF	07/10/23	54	2	11.4	1131		157	EPO10K	7.2	239	4.4	3.1	19	23						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email	rameshparihar056@gmail.com	29/12/2025	01/01/2026	05/01/2026
Vinit Mahadik	F/O	Male	20194841219	9975699405	CKD5D	12/5/2025	NEG	AVF	24/03/2024	75	1.2	11.1		183	58	MIRCERA 100	7.7	100	-	4.1	21	38						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	Vinaysinhvmahadik@gmail.com	30/12/2025	02/01/2026	06/01/2026
Joyson R	W/O	Female	2013170087816	7780226264	CKD5D	10/09/21	NEG	AVF	oct 2022	39.5	2.5	11.1	425		60	MIRCERA 100 MCG	8.5	65	4.1	3.3	16	21						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	sonymoses29@gmail.com	30/12/2025	01/01/2026	3/1/2026
Mahingappa	W/O	Female	20131612349216	6360503698	CKD5D	Oct 2021	NEG	AVF	Nov 2024	35.5	2.9	7.9	1329		62	MIRCERA 100	6.8	231	3.6	3.6	63	79						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email	gouravvatirakannavar@gmail.com	30/12/2025	02/01/2026	06/01/2026
P J SHAJI	M/O	Female	100071098516	9673118974	CKD5D	06/05/25	NEG	AVF	08/05/25	97	2.8	10.1			42	MIRCERA 75	8.7	194	4.4	3.1	21	32						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	alwin.shaji2003@gmail.com	31/12/2025	3/1/2026	07/01/2026
Prashant K	W/O	Female	100091954116	8866273645	CKD5D	20 Feb 2022	NEG	AVF	05/05/22	63.5	2.5	8.6	735		59	MIRCERA 75	-	177	-	3.7	8	25						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	prashantkhalash11@gmail.com	29/12/2025	01/01/2026	05/01/2026
R B Pathak	W/O	Female	20131542744016	9541907011	CKD5D	07/2023	NEG	Permacath 	March 2025	46.5	2.2	10.6	3013	119	182	MIRCERA100	8.9	271	2.8	3.4	24	42						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	abhilashapathak211191@gmail.com	29/12/2025	01/01/2026	3/1/2026
Rahul Kumar	F/O	Male	100097007019	7983375787	CKD5D	02/11/2022	NEG	AVF	May 2025	55	2	7.8	2492		97	MIRCERA 100	7.7	109	5	3.3	9	21						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	rahulverma28210@gmail.com	30/12/2025	02/01/2026	06/01/2026
Rajeev  Joshi	Self	Male	20285725722	9906905849	CKD5D	03/05/25	NEG	AVF	07/05/2025	101.5	4	9.3	535			MIRCERA 100	9.1	133	5.3	3.1	20	15						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	rajeev193@rediffmail.com	29/12/2025	01/01/2026	3/1/2026
Rajesh Kumar	M/O	Female	100095703018	9582039323	CKD5D	23/09/2019	NEG	AVF	Oct 2019	48.5	1.8	11.6	1800		99	MIRCERA 100	-	80	-	3.5	3	17						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	rajeshchhillar3@gmail.com	30/12/2025	02/01/2026	06/01/2026
Mukesh Singh	M/O	Female	20131572020218	9149529560	CKD5D	30/01/2023	NEG	AVF	Jun 2023	51.5	2.5	7.4	1205		94	MIRCERA 100	9.4	96	2.9	3.1	18	24						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	msingh74150@gmail.com	29/12/2025	01/01/2026	3/1/2026
RP Deshmukh	M/O	Female	20131557270518	8788007080	CKD5D	23/05/2023	NEG	AVF	Aug 2024	62	2	10.4			71	MIRCERA 100	9.7	747	2.4	2.8	11	15						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	deshmukhnamrata90@gmail.com	31/12/2025	3/1/2026	07/01/2026
Sagar Sapkal	M/O	Female	2013458450618	8605310932	CKD5D	Sep 2017	NEG	AVF	June 2022	54	2	10.6	409		118	MIRCERA75	9.3	279	4.6	3.4	19	28						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	sapkal020@gmail.com	29/12/2025	31/12/2025	02/01/2026
Vijay Kumar 	F/o	Male 	20111677219	7001676325	CKD5D	29/01/25	NEG	AVF	29/01/25	71	2.5	11.2	691		98	EPO 10K	6.8	45	3.9	2.9	26	28						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	sonuvijaykumar@gmail.com	29/12/2025	01/01/2026	05/01/2026
Nandeep C S	M/O	Female 	10003143018	9847799636	CKD5D	26/10/2025	NEG	AVF	July 2023	76	2.5	9.9	209		40	EPO 4k	8.2	139	6	3.2	16	13						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	pushpashyjan270@gmail.com	30/12/2025	02/01/2026	06/01/2026
Arun Chougale 	Self 	Male	20131558631822	8798086001	CKD5D	31/05/2025	NEG	AVF	01/07/2025	81	500	10.9	849		79	Mircera 75	8.8	106	5.3	3.5	4	18						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	raghunathchougale704@gmail.com	29/12/2025	01/01/2026	05/01/2026
Mahantesh W	W/O	Female 	20131612326816	9740465357	CKD5D	17/05/2025	NEG	AVF	26 Jun 2025	42	2.2	9.9	864		16	MIRCERA 100	8.5	129	3.7	3.4	10	10						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	mahanteshmantu1993@gmail.com	31/12/2025	3/1/2026	07/01/2026
R.N.Barik 	F/O 	Male	100094113719	9815698922	CKD5D	08/082022	NEG	AVF	18/09/2023	64	2	9.3	1654		106	Erypeg 75	7.5	257	3.9	3.5	22	15						Please check for your HD slots dates/ कृपया अपनी डायलिसिस  स्लॉट तिथियों की जांच करें/ (कृपया तुमच्या HD स्लॉटच्या तारखा तपासा)	This is an automated email.	barikbrundaban6@gmail.com	30/12/2025	02/01/2026	06/01/2026
Prashant Chavan 	F/O 	Male	201315232906	9881063118	CKD5D	01/08/2025	NEG	AVF 	04/08/2025	47.5	2.5	9.5	603		77	Mircera 75	8.4	93	5.3	3.4	24	43									29/12/2025	01/01/2026	05/01/2026
Rajgouda Patil	M/O	Female 	2013650212918	8887610207	CKD5D	23/08/2022	NEG 	AVF	Aug 2024	43.5	2.5	10.1	272		32	EPO 10K	8.3	92	2.2	2.6	15	20									30/12/2025	02/01/2026	06/01/2026
D k Uttam	W/O	Female	100077113516	9449430367	CKD5D	03/09/2025	Positive 	AVF	05/062024	51.5	2.5	10.6			48	Mircera 75	8.9	106	8.9	3.1	6	15								devenpreet@gmail.com	31/12/2025	3/1/2026	07/01/2026
Pravesh Kumar Tiwari 	M/O	Female 	20131466164418	9682302668	CKD5D	01/06/2025	NEG	AVF	20/06/2025	62	500	9.3	836		178	Mircera 100	8.5	140	4.1	3.3	25	41								praveshkumartiwari4@gmail.com	31/12/2025	3/1/2026	07/01/2026
Shivshankar B M	W/O	Female 	20131522950516	9483318368	CKD5D	23/07/2025	NEG 	AVF	11/11/2025	49.5	0.3	7.9	120		120	Mircera 100	9.4	68	3.9	3.5	16	18									31/12/2025	3/1/2026	07/01/2026
Yogesh Patil 	W/O 	Female 	20131701374916	7557818112	CKD5D	11/09/2025	NEG 	AVF	20/06/2023	43	2.5	8.1	451		49	Mircera 100	6.9	205	3.2	2.8	3	19								9009143156a@gmail.com	30/12/2025	02/01/2026	06/01/2026
Dilip Dhormalr	M/O	Female 	2013279901018	8830560612	CKD5D	26/09/2025	NEG 	AVF 	20/11/2025	51	0.5	9.9	1617		30	Mircera 100	7.1	89	3.2	1.6	25	18									29/12/2025	01/01/2026	05/01/2026
Sunil Halyal	Self	Male	20131704557122	8073070889	CKD5D	26/09/2025	NEG 	AVF	08/11/2025	57.5	2	7.9	1405		122	Mircera 75	8.4	76	4.6	3.4	18	23								suniladiveppahalyal@gmail.com	29/12/2025	31/12/2025	02/01/2026
Shivam Raj	F/O	Male	10003794119	9351941297	CKD5D	May 2024	NEG 	AVF	23/06/2025			9.3	330		18		8.8	133	-	1.7	15	16									30/12/2025	06/01/2026	13/01/2026
Mijanur Rahman 	W/O	Female	20131545488116	8942991635	CKD5D	10/10/2025	NEG 	AVF	May 2025	41	1	9.3	1256	105	57	Mircera 100	8.4	67	3.3	2.7	13	16									29/12/2025	01/01/2026	05/01/2026
Sathish Barki	F/O	Male	20300892419	9596946665	CKD5D	Aug 2025	NEG 	AVF	30/10/2025	70	0.5	11.4			57	Mircera 100 	8.2	94	4.3	3.4	16	25								barkisatish@gmail.com	31/12/2025	3/1/2026	07/01/2026
Jaspal Singh	Self	Male	2013449590222	7087805874	CKD5D	19/11/2025	NEG 	AVF	June 2022	63	1	7.3			75	Mircera 100	-	-	-	2.5	20	16									31/12/2025	3/1/2026	07/01/2026
Y Srinivaslu 	W/O	Female	20131700046316	9476300310	CKD5D	29/11/2025	NEG 	P/Cath 	17/12/2025	64.5	2.3	8				Mircera 100	8.3	68	3.3	2.6	10	13								srinivasuluimiss@gmail.com	29/12/2025	01/01/2026	05/01/2026
P.V.Karande	S/O	Male	202938711720	9527295565	CKD5D	12/07/2025	NEG 	Permacath 	20/10/2025	42	2.5	9.4	138		90		8.9	182	3.8	3.8	23	14	14.78							karandepv@gmail.com	29/12/2025	01/01/2026	05/01/2026
Girish Shyam 	M/O	Female	20285513618	8132808075	CKD5D	28/11/2025	NEG	Permacath 	01/12/2025	69	2	7.3			98	Mircera 100	-	-	-	2.7	25	30									31/12/2025	3/1/2026	07/01/2026"""

def parse_date(date_str):
    if not date_str or not date_str.strip(): return None
    date_str = date_str.strip()
    # Try common formats
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d %b %Y", "%m/%d/%y"):
        try: return datetime.strptime(date_str, fmt).date()
        except: continue
    return None

def parse_float(val):
    if not val or not val.strip(): return None
    try: return float(val.strip())
    except: return None

def import_data():
    db = SessionLocal()
    create_tables()
    
    # Clear existing patients and records
    db.query(MonthlyRecord).delete()
    db.query(Patient).delete()
    db.commit()

    lines = DATA.strip().split("\n")
    for line in lines:
        cols = line.split("\t")
        if len(cols) < 30: continue
        
        # Mapping columns
        # 0:Name, 1:Relation, 2:Sex, 3:HID, 4:Contact, 5:Diagnosis, 6:HD wef, 7:Viral, 8:Access, 9:Access Date, 10:Dry Weight
        # 11:IDWG, 12:Hb, 13:Ferritin, 14:TSAT, 15:Age, 16:EPO, 17:Ca, 18:ALP, 19:Phos, 20:Albumin, 21:AST, 22:ALT
        # 23:VitD, 24:iPTH, 25:Cal, 26:Prot, 27:Issues, 28:WA, 29:Mail, 30:Email, 31:Slot1, 32:Slot2, 33:Slot3
        
        name = cols[0]
        relation = cols[1]
        sex = cols[2]
        hid = cols[3]
        contact = cols[4]
        diagnosis = cols[5]
        wef = parse_date(cols[6])
        viral = cols[7]
        access = cols[8]
        acc_date = parse_date(cols[9])
        dry_w = parse_float(cols[10])
        
        p = Patient(
            name=name, relation_type=relation, sex=sex, hid_no=hid, contact_no=contact,
            diagnosis=diagnosis, hd_wef_date=wef, viral_markers=viral,
            access_type=access, access_date=acc_date, dry_weight=dry_w,
            hd_slot_1=cols[31] if len(cols) > 31 else "",
            hd_slot_2=cols[32] if len(cols) > 32 else "",
            hd_slot_3=cols[33] if len(cols) > 33 else "",
            email=cols[30] if len(cols) > 30 else "",
            whatsapp_notify=True, # Assuming True based on context
            is_active=True,
            age=int(cols[15]) if len(cols) > 15 and cols[15].strip().isdigit() else None,
            created_by="admin"
        )
        db.add(p)
        db.commit()
        
        # Add a record for current month
        month_str = datetime.now().strftime("%Y-%m")
        r = MonthlyRecord(
            patient_id=p.id, record_month=month_str, entered_by="admin",
            idwg=parse_float(cols[11]), hb=parse_float(cols[12]),
            serum_ferritin=parse_float(cols[13]), tsat=parse_float(cols[14]),
            serum_iron=None, epo_mircera_dose=cols[16],
            calcium=parse_float(cols[17]), alkaline_phosphate=parse_float(cols[18]),
            phosphorus=parse_float(cols[19]), albumin=parse_float(cols[20]),
            ast=parse_float(cols[21]), alt=parse_float(cols[22]),
            vit_d=parse_float(cols[23]) if len(cols) > 23 else None,
            ipth=parse_float(cols[24]) if len(cols) > 24 else None,
            av_daily_calories=parse_float(cols[25]) if len(cols) > 25 else None,
            av_daily_protein=parse_float(cols[26]) if len(cols) > 26 else None,
            issues=cols[27] if len(cols) > 27 else ""
        )
        db.add(r)
        
    db.commit()
    print(f"✅ Imported {len(lines)} patients with real data.")

if __name__ == "__main__":
    import_data()
