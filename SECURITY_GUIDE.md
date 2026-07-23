# Guide de Sécurité - Gestion Boutique

## ⚠️ Avertissement Important
**Aucun logiciel n'est sécurisé à 100%**. Cependant, ce guide documente les mesures de sécurité implémentées pour protéger votre application contre les attaques courantes.

## ✅ Mesures de Sécurité Implémentées

### 1. Configuration Sécurisée (`config.py`)
- **Secret Key** : Généré aléatoirement avec `secrets.token_hex(32)` au lieu d'une valeur statique
- **Variables d'environnement** : Utilisation de variables d'environnement pour les mots de passe sensibles
- **Session Cookies** :
  - `SESSION_COOKIE_SECURE` : True en production (HTTPS uniquement)
  - `SESSION_COOKIE_HTTPONLY` : Empêche l'accès JavaScript aux cookies
  - `SESSION_COOKIE_SAMESITE` : Protection CSRF
  - `PERMANENT_SESSION_LIFETIME` : Sessions limitées à 1 heure

### 2. En-têtes de Sécurité HTTP (`app.py`)
- **X-XSS-Protection** : Protection contre les attaques XSS
- **X-Content-Type-Options** : Empêche le sniffing de type MIME
- **X-Frame-Options** : Protection contre le clickjacking
- **Content-Security-Policy** : Politique de sécurité de contenu stricte
- **Strict-Transport-Security** : HSTS (à activer en production avec HTTPS)

### 3. Protection contre Brute Force (`security.py`)
- **Rate Limiting** : Maximum 5 tentatives de connexion par IP sur 15 minutes
- **Détection automatique** : Blocage temporaire après trop de tentatives

### 4. Protection CSRF (`security.py`)
- **Token CSRF** : Généré pour chaque session
- **Validation** : Vérification du token sur chaque requête POST
- **Injection automatique** : Token disponible dans tous les templates

### 5. Validation et Sanitization (`security.py`)
- **Validation des entrées** : Email, téléphone, mots de passe
- **Sanitization XSS** : Échappement des caractères HTML dangereux
- **Validation de fichiers** : Vérification de l'extension, type MIME et taille

### 6. Sécurité des Uploads
- **Extensions autorisées** : png, jpg, jpeg, gif, webp uniquement
- **Taille maximale** : 16MB
- **Validation MIME** : Vérification du type de fichier réel
- **Nom sécurisé** : Utilisation de `secure_filename`

### 7. Authentification Sécurisée
- **Hachage de mots de passe** : Utilisation de `werkzeug.security`
- **Validation des entrées** : Nettoyage des données utilisateur
- **Session sécurisée** : Timeout automatique après 1 heure

## 🔒 Mesures de Sécurité Recommandées (Non Implémentées)

### 1. HTTPS/TLS
Pour activer HTTPS en production :
```bash
# Utiliser un serveur WSGI comme Gunicorn avec SSL
pip install gunicorn
gunicorn --certfile=cert.pem --keyfile=key.pem app:app
```

### 2. Base de Données Sécurisée
- Utiliser des variables d'environnement pour les credentials
- Limiter les permissions de l'utilisateur MySQL
- Activer SSL pour la connexion MySQL

### 3. Firewall et Infrastructure
- Configurer un firewall (UFW, iptables)
- Utiliser un reverse proxy (Nginx/Apache)
- Activer fail2ban pour la protection automatique

### 4. Monitoring et Logging
- Implémenter un système de logs d'erreurs
- Surveiller les tentatives d'intrusion
- Alertes automatiques en cas d'activités suspectes

### 5. Sauvegardes
- Sauvegardes automatiques régulières de la base de données
- Chiffrement des sauvegardes
- Stockage hors site

## 🚀 Instructions de Déploiement Sécurisé

### 1. Variables d'Environnement
Créer un fichier `.env` (ne pas le commiter) :
```
MYSQL_PASSWORD=votre_mot_de_passe_robuste
SECRET_KEY=votre_secret_key_aleatoire
```

### 2. Configuration Production
Dans `config.py`, modifier :
```python
SESSION_COOKIE_SECURE = True  # HTTPS uniquement
```

### 3. Activer HSTS
Dans `app.py`, décommenter :
```python
response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
```

### 4. Utiliser un Serveur WSGI
Ne jamais utiliser `app.run()` en production :
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

## 📊 Checklist de Sécurité

- [x] Secret key aléatoire
- [x] Cookies sécurisés (HTTPOnly, Secure, SameSite)
- [x] En-têtes de sécurité HTTP
- [x] Protection CSRF
- [x] Rate limiting
- [x] Validation des entrées
- [x] Sanitization XSS
- [x] Uploads sécurisés
- [x] Hachage de mots de passe
- [ ] HTTPS/TLS en production
- [ ] Firewall configuré
- [ ] Monitoring implémenté
- [ ] Sauvegardes automatiques
- [ ] Tests de pénétration réguliers

## ⚡ Bonnes Pratiques

1. **Mettre à jour régulièrement** les dépendances
2. **Utiliser des mots de passe forts** (minimum 12 caractères, majuscules, minuscules, chiffres, symboles)
3. **Limiter les accès** : Principe du moindre privilège
4. **Surveiller les logs** : Détection précoce des attaques
5. **Former les utilisateurs** : Sensibilisation à la sécurité

## 🆘 En Cas d'Attaque

1. **Isoler le système** : Déconnecter du réseau
2. **Analyser les logs** : Identifier la source de l'attaque
3. **Sauvegarder les données** : Avant toute intervention
4. **Corriger la vulnérabilité** : Appliquer le patch
5. **Restaurer** : À partir de sauvegardes propres
6. **Notifier** : Les utilisateurs concernés si nécessaire

## 📞 Support

Pour toute question de sécurité, consultez :
- OWASP Top 10 : https://owasp.org/www-project-top-ten/
- Flask Security : https://flask.palletsprojects.com/en/latest/security/
- Python Security : https://python.readthedocs.io/en/latest/library/security_warnings.html
