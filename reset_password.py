import mysql.connector
from werkzeug.security import generate_password_hash
from config import Config

conn = mysql.connector.connect(
    host=Config.MYSQL_HOST,
    user=Config.MYSQL_USER,
    password=Config.MYSQL_PASSWORD,
    database=Config.MYSQL_DB
)
cursor = conn.cursor()

# Reset password for Admin1 to 'iug2026'
new_password = 'iug2026'
hashed_password = generate_password_hash(new_password)

cursor.execute('UPDATE utilisateurs SET password = %s WHERE username = %s', (hashed_password, 'Admin1'))
conn.commit()

print(f"Password for Admin1 has been reset to '{new_password}'")

cursor.close()
conn.close()
