import mysql.connector
from config import Config

conn = mysql.connector.connect(
    host=Config.MYSQL_HOST,
    user=Config.MYSQL_USER,
    password=Config.MYSQL_PASSWORD,
    database=Config.MYSQL_DB
)
cursor = conn.cursor()

try:
    # Ajouter les champs montant_paye et montant_restant à la table factures
    cursor.execute('''
        ALTER TABLE factures 
        ADD COLUMN montant_paye DECIMAL(10,2) DEFAULT 0,
        ADD COLUMN montant_restant DECIMAL(10,2) DEFAULT 0
    ''')
    conn.commit()
    print("Champs ajoutés avec succès à la table factures")
except Exception as e:
    print(f"Erreur: {e}")
    conn.rollback()

cursor.close()
conn.close()
