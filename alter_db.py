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
    cursor.execute("ALTER TABLE utilisateurs ADD boutique_id INT;")
    print("Column boutique_id added.")
except Exception as e:
    print(f"Column might already exist: {e}")

cursor.execute("UPDATE utilisateurs SET boutique_id = 1;")
conn.commit()

print("Utilisateurs updated with boutique_id = 1.")

cursor.close()
conn.close()
