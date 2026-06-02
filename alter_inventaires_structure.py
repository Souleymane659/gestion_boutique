import mysql.connector
from config import Config

def alter_inventaires_structure():
    conn = mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB
    )
    cursor = conn.cursor()
    
    try:
        # Vérifier si la colonne id_inventaires existe déjà comme clé étrangère
        cursor.execute('SHOW COLUMNS FROM inventaire_details LIKE "id_inventaires"')
        result = cursor.fetchone()
        
        if result:
            print("La colonne id_inventaires existe déjà dans inventaire_details")
        else:
            # Ajouter une colonne id_inventaires comme clé étrangère
            cursor.execute('''
                ALTER TABLE inventaire_details
                ADD COLUMN id_inventaires INT AFTER id_inventaire
            ''')
            print("Colonne id_inventaires ajoutée à inventaire_details")
            
            # Ajouter la contrainte de clé étrangère vers inventaires.id_inventaires
            cursor.execute('''
                ALTER TABLE inventaire_details
                ADD CONSTRAINT fk_detail_inventaire
                FOREIGN KEY (id_inventaires) REFERENCES inventaires(id_inventaires)
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
    alter_inventaires_structure()
