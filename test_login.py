import mysql.connector
from config import Config
from werkzeug.security import check_password_hash

conn = mysql.connector.connect(
    host=Config.MYSQL_HOST,
    user=Config.MYSQL_USER,
    password=Config.MYSQL_PASSWORD,
    database=Config.MYSQL_DB
)
cursor = conn.cursor(dictionary=True)

# Test with Admin1 user
username = 'Admin1'
password = 'iug2026'  # Default password from config

cursor.execute('SELECT * FROM utilisateurs WHERE username = %s', (username,))
user = cursor.fetchone()

if user:
    print(f"User found: {user['username']}")
    print(f"Role: {user['role']}")
    print(f"ID: {user['id']}")
    
    # Test password verification
    if check_password_hash(user['password'], password):
        print("Password verification: SUCCESS")
    else:
        print("Password verification: FAILED")
        print("Trying with other passwords...")
        
        # Try common passwords
        for test_pass in ['admin', '123456', 'password', 'Admin1']:
            if check_password_hash(user['password'], test_pass):
                print(f"Password found: {test_pass}")
                break
else:
    print("User not found")

cursor.close()
conn.close()
