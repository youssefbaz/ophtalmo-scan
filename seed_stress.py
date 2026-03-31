#!/usr/bin/env python3
"""
Stress test seed: 5 médecins + 100 patients avec données ophtalmologiques réalistes.
Usage: python seed_stress.py
"""
import sqlite3, json, random, datetime, os
from werkzeug.security import generate_password_hash

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ophtalmo.db')

random.seed(42)

# ─── MÉDECINS ──────────────────────────────────────────────────────────────────
MEDECINS = [
    ("U001", "dr.martin",   "medecin123", "Dr. Martin",   "Jean"),
    ("U005", "dr.dupont",   "medecin123", "Dr. Dupont",   "Sophie"),
    ("U006", "dr.bernard",  "medecin123", "Dr. Bernard",  "Pierre"),
    ("U007", "dr.petit",    "medecin123", "Dr. Petit",    "Marie"),
    ("U008", "dr.moreau",   "medecin123", "Dr. Moreau",   "Luc"),
]

# ─── NOMS FRANÇAIS ─────────────────────────────────────────────────────────────
NOMS = [
    "Martin","Bernard","Dubois","Thomas","Robert","Richard","Petit","Durand",
    "Leroy","Moreau","Simon","Laurent","Lefebvre","Michel","Garcia","David",
    "Bertrand","Roux","Vincent","Fournier","Morel","Girard","Andre","Lefevre",
    "Mercier","Dupont","Lambert","Bonnet","François","Martinez","Clement",
    "Gauthier","Henry","Rousseau","Blanc","Guerin","Muller","Perrin","Renard",
    "Chevalier","Leclerc","Gaillard","Noel","Faure","Robin","Masson","Lemaire",
    "Perez","Brun","Mallet","Arnaud","Aubert","Giraud","Lucas","Boyer",
]

PRENOMS_M = [
    "Jean","Pierre","Michel","Philippe","Andre","Claude","Jacques","Alain",
    "Pascal","Christophe","Nicolas","Antoine","Thomas","Lucas","Hugo",
    "Mathieu","Alexandre","Julien","Sebastien","Laurent","Olivier","Romain",
    "Xavier","Patrick","Daniel","François","Frederic","Marc","Benoit","Eric",
]

PRENOMS_F = [
    "Marie","Nathalie","Isabelle","Sophie","Christine","Sylvie","Catherine",
    "Sandrine","Stephanie","Valerie","Caroline","Emilie","Laurence","Veronique",
    "Martine","Julie","Clara","Emma","Lucie","Alice","Camille","Manon","Laura",
    "Celine","Agnes","Anne","Brigitte","Monique","Francoise","Helene",
]

# ─── DONNÉES MÉDICALES ─────────────────────────────────────────────────────────
ANTECEDENTS_POOL = [
    ["Glaucome chronique angle ouvert"],
    ["Myopie forte (-6D)"],
    ["DMLA exsudative OG"],
    ["Cataracte nucléaire bilatérale"],
    ["Rétinopathie diabétique non proliférante"],
    ["Astigmatisme mixte"],
    ["Hypermétropie forte (+4D)"],
    ["Presbytie"],
    ["Kératocône OD"],
    ["Uvéite antérieure chronique"],
    ["Décollement de rétine opéré OG"],
    ["Glaucome chronique", "Diabète type 2"],
    ["DMLA sèche", "HTA"],
    ["Cataracte opérée OD", "Glaucome suspect"],
    ["Myopie forte", "Astigmatisme"],
    ["Rétinopathie diabétique", "Diabète type 2"],
    ["Neuropathie optique ischémique"],
    ["Sécheresse oculaire sévère"],
    ["Chirurgie réfractive LASIK"],
    ["Amblyopie OG", "Strabisme"],
]

ALLERGIES_POOL = [
    [], [], [], [], [],
    ["Pénicilline"], ["AINS"], ["Corticoïdes topiques"],
    ["Atropine"], ["Fluorescéine"], ["Pénicilline","Aspirine"],
]

MOTIFS_POOL = [
    "Suivi glaucome", "Contrôle annuel", "Baisse d'acuité visuelle",
    "IVT anti-VEGF mensuelle", "Contrôle tension oculaire",
    "Renouvellement ordonnance", "Bilan orthoptique", "Consultation post-opératoire",
    "Urgence oculaire", "Fond d'oeil de dépistage", "Suivi DMLA",
    "Suivi rétinopathie diabétique", "Suivi kératocône", "Gêne visuelle floue",
    "Photopsies", "Corps flottants nouveaux", "Douleur oculaire",
]

DIAGNOSTICS_POOL = [
    "Glaucome angle ouvert stabilisé sous traitement",
    "DMLA exsudative active — indication IVT",
    "Rétinopathie diabétique non proliférante modérée",
    "Cataracte nucléaire grade II — surveillance",
    "Myopie stable, correction à renouveler",
    "Acuité stable, pas de modification thérapeutique",
    "Amélioration sous traitement local",
    "Kératocône évolutif — indication cross-linking",
    "Sécheresse oculaire sévère — syndrome de l'œil sec",
    "DMLA sèche — drusen confluents",
    "Glaucome normotensif — champ visuel stable",
    "Uvéite antérieure en rémission",
    "Hypertonie oculaire isolée à surveiller",
    "Neuropathie optique — bilan en cours",
    "Post-IVT — bonne réponse anatomique",
]

TRAITEMENTS_POOL = [
    "Timolol 0.5% x2/j OU bilatéral",
    "Ranibizumab 0.5mg IVT OG — prochain RDV J+30",
    "Dorzolamide/Timolol x2/j + Brinzolamide x3/j",
    "Bevacizumab 1.25mg IVT OD",
    "Renouvellement ordonnance lunettes — verres progressifs",
    "Larmes artificielles sans conservateurs x6/j",
    "Bimatoprost 0.01% x1/j soir",
    "Aflibercept 2mg IVT mensuel — protocole treat & extend",
    "Dexaméthasone collyre x4/j décroissance",
    "Vitamine A palmitate collyre x4/j",
    "Cyclopentolate 1% + Dexaméthasone — cycloplégique",
    "Poursuite traitement actuel, RDV dans 4 mois",
]

SEGMENTS_ANT = [
    "Cornée claire, chambre antérieure calme, cristallin clair",
    "Cornée claire, chambre antérieure profonde, cristallin légèrement opacifié",
    "Conjonctive légèrement hyperhémiée, cornée claire",
    "Cornée claire, CAP : Tyndall 1+, absence de précipités rétrocornéens",
    "Cornée claire, implant en bonne position",
    "Cornée légèrement ponctuée (kératite ponctuée superficielle)",
    "RAS segment antérieur",
]

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def rnd_date(start_year=1945, end_year=1990):
    d = datetime.date(start_year, 1, 1) + datetime.timedelta(
        days=random.randint(0, (datetime.date(end_year, 12, 31) - datetime.date(start_year, 1, 1)).days)
    )
    return d.isoformat()

def rnd_past_date(days_back_max=1095):
    d = datetime.date.today() - datetime.timedelta(days=random.randint(7, days_back_max))
    return d.isoformat()

def rnd_iop():
    return str(random.randint(10, 28))

def rnd_av():
    choices = ["10/10", "9/10", "8/10", "7/10", "6/10", "5/10", "4/10", "3/10", "2/10", "1/10"]
    weights  = [20, 20, 18, 15, 10, 7, 4, 3, 2, 1]
    return random.choices(choices, weights=weights)[0]

def rnd_sph():
    v = round(random.uniform(-8.0, 4.0) * 4) / 4
    return f"{v:+.2f}" if v != 0 else "plan"

def rnd_cyl():
    v = round(random.uniform(-3.0, 0.0) * 4) / 4
    return f"{v:.2f}" if v != 0 else ""

def rnd_axe():
    return str(random.randint(0, 180))

def rnd_tel():
    return f"0{random.randint(6,7)} {random.randint(10,99):02d} {random.randint(10,99):02d} {random.randint(10,99):02d} {random.randint(10,99):02d}"

def next_patient_id(db):
    row = db.execute(
        "SELECT MAX(CAST(SUBSTR(id,2) AS INTEGER)) FROM patients WHERE id GLOB 'P[0-9]*'"
    ).fetchone()
    n = (row[0] or 0) + 1
    return f"P{n:03d}"

# ─── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    print(f"Connexion à {DATABASE}")

    # ── 1. Médecins ──────────────────────────────────────────────────────────
    existing_users = {r['id'] for r in db.execute("SELECT id FROM users").fetchall()}
    added_medecins = 0
    for uid, username, password, nom, prenom in MEDECINS:
        if uid not in existing_users:
            db.execute(
                "INSERT INTO users (id,username,password_hash,role,nom,prenom) VALUES (?,?,?,?,?,?)",
                (uid, username, generate_password_hash(password), "medecin", nom, prenom)
            )
            added_medecins += 1
    db.commit()
    print(f"  ✓ {added_medecins} nouveau(x) médecin(s) ajouté(s)")

    medecin_ids = [m[0] for m in MEDECINS]

    # ── 2. Patients ──────────────────────────────────────────────────────────
    nb_patients = 100
    patient_ids = []
    for i in range(nb_patients):
        sexe     = random.choice(["M", "F"])
        prenom   = random.choice(PRENOMS_M if sexe == "M" else PRENOMS_F)
        nom      = random.choice(NOMS)
        ddn      = rnd_date(1940, 1990)
        tel      = rnd_tel()
        email    = f"{prenom.lower()}.{nom.lower()}{random.randint(1,99)}@email.fr"
        ants     = random.choice(ANTECEDENTS_POOL)
        allergies = random.choice(ALLERGIES_POOL)
        medecin_id = random.choice(medecin_ids)

        pid = next_patient_id(db)
        db.execute(
            "INSERT INTO patients (id,nom,prenom,ddn,sexe,telephone,email,antecedents,allergies,medecin_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (pid, nom, prenom, ddn, sexe, tel, email,
             json.dumps(ants), json.dumps(allergies), medecin_id)
        )
        patient_ids.append((pid, medecin_id))

    db.commit()
    print(f"  ✓ {nb_patients} patients ajoutés")

    # ── 3. Historique (1-4 consultations par patient) ─────────────────────────
    nb_hist = 0
    for pid, medecin_id in patient_ids:
        nom_medecin = next(m[3] for m in MEDECINS if m[0] == medecin_id)
        n_consults = random.randint(1, 4)
        dates = sorted([rnd_past_date(900) for _ in range(n_consults)])
        for date in dates:
            hid = "H" + hex(random.randint(0, 0xFFFFFF))[2:].upper().zfill(6)
            has_refraction = random.random() < 0.6
            db.execute(
                "INSERT OR IGNORE INTO historique "
                "(id,patient_id,date,motif,diagnostic,traitement,"
                "tension_od,tension_og,acuite_od,acuite_og,"
                "refraction_od_sph,refraction_od_cyl,refraction_od_axe,"
                "refraction_og_sph,refraction_og_cyl,refraction_og_axe,"
                "segment_ant,notes,medecin) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (hid, pid, date,
                 random.choice(MOTIFS_POOL),
                 random.choice(DIAGNOSTICS_POOL),
                 random.choice(TRAITEMENTS_POOL),
                 rnd_iop(), rnd_iop(),
                 rnd_av(), rnd_av(),
                 rnd_sph() if has_refraction else "",
                 rnd_cyl() if has_refraction else "",
                 rnd_axe() if has_refraction else "",
                 rnd_sph() if has_refraction else "",
                 rnd_cyl() if has_refraction else "",
                 rnd_axe() if has_refraction else "",
                 random.choice(SEGMENTS_ANT) if random.random() < 0.5 else "",
                 "",
                 nom_medecin)
            )
            nb_hist += 1

    db.commit()
    print(f"  ✓ {nb_hist} consultations ajoutées")

    # ── 4. RDV (0-3 par patient) ──────────────────────────────────────────────
    nb_rdv = 0
    rdv_types = ["Consultation", "Suivi glaucome", "IVT anti-VEGF", "OCT de contrôle",
                 "Champ visuel", "Fond d'oeil", "Post-opératoire", "Urgence oculaire"]
    statuts = ["programmé", "confirmé", "programmé", "confirmé", "en_attente"]
    heures  = ["08:30","09:00","09:30","10:00","10:30","11:00","11:30","14:00","14:30","15:00","15:30","16:00","16:30"]

    for pid, medecin_id in patient_ids:
        nom_medecin = next(m[3] for m in MEDECINS if m[0] == medecin_id)
        n_rdv = random.randint(0, 3)
        for _ in range(n_rdv):
            rid = "RDV" + hex(random.randint(0, 0xFFFFFF))[2:].upper().zfill(6)
            future_days = random.randint(-60, 180)
            date = (datetime.date.today() + datetime.timedelta(days=future_days)).isoformat()
            urgent = 1 if random.random() < 0.05 else 0
            statut = "en_attente" if urgent else random.choice(statuts)
            db.execute(
                "INSERT OR IGNORE INTO rdv "
                "(id,patient_id,date,heure,type,statut,medecin,notes,urgent,demande_par) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (rid, pid, date, random.choice(heures),
                 random.choice(rdv_types), statut, nom_medecin,
                 "", urgent, "medecin")
            )
            nb_rdv += 1

    db.commit()
    print(f"  ✓ {nb_rdv} rendez-vous ajoutés")

    # ── Stats ─────────────────────────────────────────────────────────────────
    print("\n── Répartition des patients par médecin ──")
    for uid, username, _, nom, _ in MEDECINS:
        n = db.execute("SELECT COUNT(*) FROM patients WHERE medecin_id=?", (uid,)).fetchone()[0]
        print(f"  {nom:20s} ({username}): {n} patients")

    total = db.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    print(f"\n  Total: {total} patients | Mot de passe médecins: medecin123")
    db.close()


if __name__ == "__main__":
    main()
