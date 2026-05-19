import mysql.connector
from config import Config

conn = mysql.connector.connect(
    host=Config.MYSQL_HOST,
    user=Config.MYSQL_USER,
    password=Config.MYSQL_PASSWORD,
    database=Config.MYSQL_DB
)
cursor = conn.cursor()

tables_and_pks = {
    'produits': 'id_produit',
    'clients': 'id_client',
    'fournisseurs': 'id_fournisseur',
    'ventes': 'id_vente'
}

cursor.execute("SET FOREIGN_KEY_CHECKS=0;")

for table, pk in tables_and_pks.items():
    try:
        cursor.execute(f"ALTER TABLE {table} MODIFY {pk} INT AUTO_INCREMENT;")
        print(f"Added AUTO_INCREMENT to {table}.{pk}")
    except Exception as e:
        print(f"Error on {table}: {e}")

cursor.execute("SET FOREIGN_KEY_CHECKS=1;")
cursor.close()
conn.close()
