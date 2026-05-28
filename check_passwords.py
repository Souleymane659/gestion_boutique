import mysql.connector
from config import Config

conn = mysql.connector.connect(
    host=Config.MYSQL_HOST,
    user=Config.MYSQL_USER,
    password=Config.MYSQL_PASSWORD,
    database=Config.MYSQL_DB
)
cursor = conn.cursor(dictionary=True)

cursor.execute('SELECT id, username, password FROM utilisateurs LIMIT 3')
users = cursor.fetchall()

for user in users:
    print(f"User: {user['username']}")
    print(f"Password: {user['password']}")
    print(f"Password length: {len(user['password'])}")
    print("---")

cursor.close()
conn.close()
