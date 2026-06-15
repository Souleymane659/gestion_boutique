import mysql.connector
from config import Config

conn = mysql.connector.connect(
    host=Config.MYSQL_HOST,
    user=Config.MYSQL_USER,
    password=Config.MYSQL_PASSWORD,
    database=Config.MYSQL_DB
)
cursor = conn.cursor(dictionary=True)

for table in ['produits', 'clients', 'fournisseurs', 'ventes', 'factures', 'plans_comptables', 'ecritures_comptables', 'lignes_ecritures']:
    cursor.execute(f"DESCRIBE {table}")
    print(f"--- {table} ---")
    for row in cursor.fetchall():
        print(f"{row['Field']}: {row['Type']} | Key: {row['Key']} | Extra: {row['Extra']}")

cursor.close()
conn.close()
