import mysql.connector
from config import Config

conn = mysql.connector.connect(
    host=Config.MYSQL_HOST,
    user=Config.MYSQL_USER,
    password=Config.MYSQL_PASSWORD,
    database=Config.MYSQL_DB
)
cursor = conn.cursor(dictionary=True)

# Créer la table plans_comptables
cursor.execute('''
    CREATE TABLE IF NOT EXISTS plans_comptables (
        id INT AUTO_INCREMENT PRIMARY KEY,
        numero_compte VARCHAR(20) NOT NULL UNIQUE,
        intitule VARCHAR(255) NOT NULL,
        type_compte ENUM('ACTIF', 'PASSIF', 'CHARGE', 'PRODUIT') NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')
print("Table plans_comptables créée ou existe déjà.")

# Créer la table ecritures_comptables
cursor.execute('''
    CREATE TABLE IF NOT EXISTS ecritures_comptables (
        id INT AUTO_INCREMENT PRIMARY KEY,
        date_ecriture DATE NOT NULL,
        libelle VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')
print("Table ecritures_comptables créée ou existe déjà.")

# Créer la table lignes_ecritures
cursor.execute('''
    CREATE TABLE IF NOT EXISTS lignes_ecritures (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ecriture_id INT NOT NULL,
        compte_id INT NOT NULL,
        debit DECIMAL(15, 2) DEFAULT 0,
        credit DECIMAL(15, 2) DEFAULT 0,
        FOREIGN KEY (ecriture_id) REFERENCES ecritures_comptables(id) ON DELETE CASCADE,
        FOREIGN KEY (compte_id) REFERENCES plans_comptables(id)
    )
''')
print("Table lignes_ecritures créée ou existe déjà.")

# Insérer des comptes par défaut
comptes_default = [
    ('101', 'Capital', 'PASSIF'),
    ('201', 'Emprunts', 'PASSIF'),
    ('301', 'Fournisseurs', 'PASSIF'),
    ('401', 'Clients', 'ACTIF'),
    ('501', 'Caisse', 'ACTIF'),
    ('502', 'Banque', 'ACTIF'),
    ('601', 'Achats de marchandises', 'CHARGE'),
    ('602', 'Achats de matières premières', 'CHARGE'),
    ('603', 'Achats de fournitures', 'CHARGE'),
    ('604', 'Loyer', 'CHARGE'),
    ('605', 'Salaires', 'CHARGE'),
    ('606', 'Charges diverses', 'CHARGE'),
    ('701', 'Ventes de marchandises', 'PRODUIT'),
    ('702', 'Ventes de services', 'PRODUIT'),
    ('703', 'Revenus divers', 'PRODUIT')
]

for compte in comptes_default:
    cursor.execute('''
        INSERT INTO plans_comptables (numero_compte, intitule, type_compte)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE intitule=VALUES(intitule), type_compte=VALUES(type_compte)
    ''', compte)

print("Comptes par défaut insérés.")

conn.commit()
cursor.close()
conn.close()

print("Tables comptables créées avec succès !")
