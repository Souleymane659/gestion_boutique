# Guide de Déploiement sur AWS EC2

## 🔍 Diagnostic du Problème de Connexion

Si votre application fonctionne localement mais pas sur EC2, les causes les plus probables sont :

### 1. **Configuration de la Base de Données**
- **Local** : `localhost` ou `127.0.0.1`
- **EC2** : Adresse IP de la base de données ou RDS endpoint

### 2. **Variables d'Environnement**
Les variables d'environnement ne sont probablement pas configurées sur EC2.

### 3. **Permissions MySQL**
L'utilisateur MySQL n'a peut-être pas les permissions de connexion à distance.

## 📋 Étapes pour Corriger le Problème

### Étape 1 : Vérifier les Logs

Sur votre instance EC2, exécutez :
```bash
ssh -i votre_key.pem ec2-user@votre_ip_ec2
cd /path/to/your/app
tail -f app.log
```

Essayez de vous connecter et observez les logs pour voir l'erreur exacte.

### Étape 2 : Configurer les Variables d'Environnement

Créez un fichier `.env` sur EC2 :
```bash
nano .env
```

Ajoutez :
```
MYSQL_HOST=votre_mysql_host_ou_rds_endpoint
MYSQL_USER=votre_user_mysql
MYSQL_PASSWORD=votre_mot_de_passe_mysql
MYSQL_DB=boutique
SECRET_KEY=votre_secret_key_aleatoire
```

### Étape 3 : Modifier config.py pour EC2

Si vous utilisez une base de données externe (RDS), modifiez `config.py` :

```python
import os
import secrets

class Config:
    # Utiliser les variables d'environnement ou localhost
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'bien')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'iug2026')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'boutique')
    
    # Secret key sécurisé
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    # Configuration de session sécurisée
    SESSION_COOKIE_SECURE = False  # True en production avec HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600
    
    # Upload sécurisé
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
```

### Étape 4 : Configurer MySQL pour les Connexions Distantes

Si MySQL est sur une autre instance :

1. **Sur le serveur MySQL**, autorisez les connexions distantes :
```sql
-- Connectez-vous à MySQL
mysql -u root -p

-- Créez un utilisateur pour les connexions distantes
CREATE USER 'bien'@'%' IDENTIFIED BY 'votre_mot_de_passe';
GRANT ALL PRIVILEGES ON boutique.* TO 'bien'@'%';
FLUSH PRIVILEGES;
```

2. **Modifiez la configuration MySQL** (`/etc/mysql/mysql.conf.d/mysqld.cnf`) :
```ini
bind-address = 0.0.0.0
```

3. **Redémarrez MySQL** :
```bash
sudo systemctl restart mysql
```

### Étape 5 : Configurer le Security Group EC2

1. Allez dans la console AWS EC2
2. Sélectionnez votre instance
3. Cliquez sur "Security Groups"
4. Ajoutez une règle inbound :
   - Type : MySQL/Aurora
   - Port : 3306
   - Source : L'IP de votre instance EC2 ou 0.0.0.0/0 (pour tous)

### Étape 6 : Installer Python et les Dépendances

Sur EC2 :
```bash
sudo yum update -y
sudo yum install python3 python3-pip mysql -y
pip3 install flask mysql-connector-python werkzeug pandas openpyxl
```

### Étape 7 : Lancer l'Application

```bash
# En développement
python3 app.py

# En production (recommandé)
pip3 install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

## 🚀 Recommandation : Utiliser AWS RDS

Pour une meilleure sécurité et fiabilité, utilisez AWS RDS au lieu de MySQL local :

1. **Créez une instance RDS MySQL** dans la console AWS
2. **Configurez le security group RDS** pour autoriser les connexions depuis votre EC2
3. **Utilisez l'endpoint RDS** dans votre configuration :
```
MYSQL_HOST=votre_rds_endpoint.rds.amazonaws.com
```

## 🔧 Vérification de la Connexion

Testez la connexion MySQL depuis EC2 :
```bash
mysql -h votre_mysql_host -u bien -p boutique
```

Si cela échoue, le problème est la configuration MySQL, pas l'application.

## 📊 Monitoring des Logs

Surveillez les logs en temps réel :
```bash
tail -f app.log
```

Les logs indiqueront :
- Si l'utilisateur est trouvé dans la base de données
- Si la vérification du mot de passe échoue
- Les erreurs de connexion à la base de données

## ⚡ Solution Rapide

Si vous voulez tester rapidement, essayez ceci sur EC2 :

1. **Vérifiez que la base de données est accessible** :
```bash
mysql -h localhost -u bien -p boutique
```

2. **Vérifiez que l'utilisateur existe** :
```sql
SELECT * FROM utilisateurs WHERE username = 'votre_username';
```

3. **Réinitialisez le mot de passe** si nécessaire :
```sql
UPDATE utilisateurs SET password = 'pbkdf2:sha256:260000$votre_hash' WHERE username = 'votre_username';
```

## 🆘 Support

Si le problème persiste après ces étapes :
1. Envoyez les logs de `app.log`
2. Vérifiez la configuration de `config.py`
3. Confirmez que la base de données est accessible depuis EC2
