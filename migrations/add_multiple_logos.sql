-- Migration pour ajouter des logos multiples dans la table parametres
-- Exécuter ce script dans MySQL pour modifier la structure de la table

USE boutique;

-- Ajouter les colonnes logo2 et logo3
ALTER TABLE parametres ADD COLUMN logo2 VARCHAR(255) DEFAULT NULL AFTER logo;
ALTER TABLE parametres ADD COLUMN logo3 VARCHAR(255) DEFAULT NULL AFTER logo2;

-- Si la colonne logo existe déjà, on peut la renommer en logo1 pour plus de clarté
ALTER TABLE parametres CHANGE COLUMN logo logo1 VARCHAR(255) DEFAULT NULL;
