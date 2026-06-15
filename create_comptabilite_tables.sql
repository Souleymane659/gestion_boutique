-- Script SQL pour créer les tables comptables

-- Table plans_comptables
CREATE TABLE IF NOT EXISTS plans_comptables (
    id INT AUTO_INCREMENT PRIMARY KEY,
    numero_compte VARCHAR(20) NOT NULL UNIQUE,
    intitule VARCHAR(255) NOT NULL,
    type_compte ENUM('ACTIF', 'PASSIF', 'CHARGE', 'PRODUIT') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table ecritures_comptables
CREATE TABLE IF NOT EXISTS ecritures_comptables (
    id INT AUTO_INCREMENT PRIMARY KEY,
    date_ecriture DATE NOT NULL,
    libelle VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table lignes_ecritures
CREATE TABLE IF NOT EXISTS lignes_ecritures (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ecriture_id INT NOT NULL,
    compte_id INT NOT NULL,
    debit DECIMAL(15, 2) DEFAULT 0,
    credit DECIMAL(15, 2) DEFAULT 0,
    FOREIGN KEY (ecriture_id) REFERENCES ecritures_comptables(id) ON DELETE CASCADE,
    FOREIGN KEY (compte_id) REFERENCES plans_comptables(id)
);

-- Insérer quelques comptes par défaut pour le plan comptable
INSERT INTO plans_comptables (numero_compte, intitule, type_compte) VALUES
('101', 'Capital', 'PASSIF'),
('201', 'Emprunts', 'PASSIF'),
('301', 'Fournisseurs', 'PASSIF'),
('401', 'Clients', 'ACTIF'),
('501', 'Caisse', 'ACTIF'),
('502', 'Banque', 'ACTIF'),
('601', 'Achats de marchandises', 'CHARGE'),
('602', 'Achats de matières premières', 'CHARGE'),
('603', 'Achats de fournitures', 'CHARGE'),
('604', 'Loyer', 'CHARGE'),
('605', 'Salaires', 'CHARGE'),
('606', 'Charges diverses', 'CHARGE'),
('701', 'Ventes de marchandises', 'PRODUIT'),
('702', 'Ventes de services', 'PRODUIT'),
('703', 'Revenus divers', 'PRODUIT')
ON DUPLICATE KEY UPDATE intitule=VALUES(intitule), type_compte=VALUES(type_compte);
