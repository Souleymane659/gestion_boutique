import mysql.connector
from config import Config

def alter_ventes_client_temporaire():
    conn = mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB
    )
    cursor = conn.cursor()
    
    try:
        # Ajouter la colonne client_temporaire à la table ventes
        cursor.execute('''
            ALTER TABLE ventes
            ADD COLUMN client_temporaire VARCHAR(255) DEFAULT NULL
        ''')
        print("Colonne client_temporaire ajoutée à la table ventes")
        
        conn.commit()
        print("\nModification de la base de données terminée avec succès!")
        
    except mysql.connector.Error as err:
        if "Duplicate column name" in str(err):
            print("La colonne client_temporaire existe déjà dans la table ventes")
        else:
            print(f"Erreur : {err}")
            conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    alter_ventes_client_temporaire()
