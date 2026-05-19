import mysql.connector
from werkzeug.security import generate_password_hash
from config import Config

def hash_existing_passwords():
    conn = mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB
    )
    cursor = conn.cursor(dictionary=True)

    cursor.execute('SELECT id, mot_de_passe FROM utilisateurs')
    utilisateurs = cursor.fetchall()

    for user in utilisateurs:
        # Check if it's already hashed (bcrypt hashes start with 'scrypt:' or 'pbkdf2:' in werkzeug)
        # werkzeug generates pbkdf2:sha256 or scrypt: by default.
        if not user['mot_de_passe'].startswith('scrypt:') and not user['mot_de_passe'].startswith('pbkdf2:'):
            hashed_pw = generate_password_hash(user['mot_de_passe'])
            cursor.execute('UPDATE utilisateurs SET mot_de_passe = %s WHERE id = %s', (hashed_pw, user['id']))
            print(f"Hashed password for user ID {user['id']}")

    conn.commit()
    cursor.close()
    conn.close()
    print("All passwords hashed successfully.")

if __name__ == '__main__':
    hash_existing_passwords()
