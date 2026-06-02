import mysql.connector
from config import Config

def alter_inventaires_sections():
    conn = mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB
    )
    cursor = conn.cursor()
    
    try:
        # Créer la table inventaires_sections
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventaires_sections (
                id_section INT AUTO_INCREMENT PRIMARY KEY,
                nom_section VARCHAR(255) NOT NULL,
                annee INT NOT NULL,
                description TEXT,
                user_id INT,
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES utilisateurs(id)
            )
        ''')
        print("Table inventaires_sections créée avec succès")
        
        # Ajouter la colonne id_section à la table inventaires
        cursor.execute('''
            ALTER TABLE inventaires
            ADD COLUMN id_section INT
        ''')
        print("Colonne id_section ajoutée à la table inventaires")
        
        # Ajouter la contrainte de clé étrangère
        cursor.execute('''
            ALTER TABLE inventaires
            ADD CONSTRAINT fk_inventaire_section
            FOREIGN KEY (id_section) REFERENCES inventaires_sections(id_section)
        ''')
        print("Contrainte de clé étrangère ajoutée")
        
        conn.commit()
        print("\nModification de la base de données terminée avec succès!")
        
    except mysql.connector.Error as err:
        print(f"Erreur : {err}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    alter_inventaires_sections()
