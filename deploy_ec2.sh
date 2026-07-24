#!/bin/bash

# Script de déploiement automatisé pour AWS EC2
# Usage: ./deploy_ec2.sh

set -e

echo "🚀 Début du déploiement sur EC2..."

# Couleurs pour les messages
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Fonction pour afficher les messages
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Vérifier si on est sur EC2
if [ ! -f /etc/ec2-version ]; then
    log_warn "Ce script est conçu pour EC2. Exécution en mode local."
fi

# Mise à jour du système
log_info "Mise à jour du système..."
sudo yum update -y || sudo apt-get update -y

# Installation de Python et pip
log_info "Installation de Python et pip..."
if command -v yum &> /dev/null; then
    sudo yum install python3 python3-pip python3-devel mysql -y
elif command -v apt-get &> /dev/null; then
    sudo apt-get install python3 python3-pip python3-dev mysql-client -y
else
    log_error "Gestionnaire de paquets non reconnu"
    exit 1
fi

# Installation des dépendances Python
log_info "Installation des dépendances Python..."
pip3 install --upgrade pip
pip3 install flask mysql-connector-python werkzeug pandas openpyxl gunicorn

# Création du dossier d'upload
log_info "Création du dossier d'upload..."
mkdir -p static/uploads
chmod 755 static/uploads

# Configuration des variables d'environnement
log_info "Configuration des variables d'environnement..."
if [ ! -f .env ]; then
    log_warn "Fichier .env non trouvé. Création d'un fichier par défaut..."
    cat > .env << EOF
MYSQL_HOST=localhost
MYSQL_USER=bien
MYSQL_PASSWORD=iug2026
MYSQL_DB=boutique
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
EOF
    log_warn "⚠️  Veuillez modifier le fichier .env avec vos vraies credentials !"
fi

# Vérification de la connexion MySQL
log_info "Test de la connexion MySQL..."
if command -v mysql &> /dev/null; then
    if mysql -h ${MYSQL_HOST:-localhost} -u ${MYSQL_USER:-bien} -p${MYSQL_PASSWORD:-iug2026} -e "USE ${MYSQL_DB:-boutique};" 2>/dev/null; then
        log_info "✅ Connexion MySQL réussie"
    else
        log_error "❌ Échec de la connexion MySQL. Vérifiez vos credentials."
        log_warn "Exécutez: mysql -h ${MYSQL_HOST:-localhost} -u ${MYSQL_USER:-bien} -p"
    fi
else
    log_warn "Client MySQL non installé. Installation..."
    if command -v yum &> /dev/null; then
        sudo yum install mysql -y
    elif command -v apt-get &> /dev/null; then
        sudo apt-get install mysql-client -y
    fi
fi

# Migration de la base de données pour les logos multiples
log_info "Vérification de la migration de la base de données..."
if [ -f "migrations/add_multiple_logos.sql" ]; then
    log_warn "Exécutez manuellement la migration SQL:"
    log_warn "mysql -u bien -p boutique < migrations/add_multiple_logos.sql"
fi

# Configuration du firewall
log_info "Configuration du firewall..."
if command -v firewall-cmd &> /dev/null; then
    sudo firewall-cmd --permanent --add-service=http
    sudo firewall-cmd --permanent --add-service=https
    sudo firewall-cmd --permanent --add-port=8000/tcp
    sudo firewall-cmd --reload
elif command -v ufw &> /dev/null; then
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    sudo ufw allow 8000/tcp
    sudo ufw --force enable
fi

# Installation de Supervisor (pour gérer le processus en production)
log_info "Installation de Supervisor..."
if command -v yum &> /dev/null; then
    sudo yum install supervisor -y
elif command -v apt-get &> /dev/null; then
    sudo apt-get install supervisor -y
fi

# Configuration de Supervisor
log_info "Configuration de Supervisor..."
sudo mkdir -p /etc/supervisor/conf.d
sudo tee /etc/supervisor/conf.d/gestion_boutique.conf > /dev/null << EOF
[program:gestion_boutique]
directory=$(pwd)
command=gunicorn -w 4 -b 0.0.0.0:8000 app:app
user=ec2-user
autostart=true
autorestart=true
stderr_logfile=/var/log/gestion_boutique.err.log
stdout_logfile=/var/log/gestion_boutique.out.log
environment=PYTHONPATH="$(pwd)"
EOF

# Démarrage de l'application avec Supervisor
log_info "Démarrage de l'application..."
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start gestion_boutique

# Vérification que l'application tourne
log_info "Vérification de l'application..."
sleep 3
if sudo supervisorctl status gestion_boutique | grep -q "RUNNING"; then
    log_info "✅ Application démarrée avec succès"
else
    log_error "❌ Échec du démarrage de l'application"
    log_warn "Vérifiez les logs: sudo tail -f /var/log/gestion_boutique.err.log"
fi

# Affichage des informations de déploiement
echo ""
log_info "📊 Informations de déploiement:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌐 URL de l'application: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8000"
echo "📁 Répertoire de travail: $(pwd)"
echo "📝 Logs de l'application: sudo tail -f /var/log/gestion_boutique.out.log"
echo "🔧 Logs d'erreurs: sudo tail -f /var/log/gestion_boutique.err.log"
echo "🔄 Redémarrer: sudo supervisorctl restart gestion_boutique"
echo "⏹️  Arrêter: sudo supervisorctl stop gestion_boutique"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

log_info "✅ Déploiement terminé !"
log_warn "⚠️  N'oubliez pas de:"
echo "   1. Configurer le Security Group AWS pour autoriser le port 8000"
echo "   2. Exécuter la migration SQL: mysql -u bien -p boutique < migrations/add_multiple_logos.sql"
echo "   3. Modifier le fichier .env avec vos vraies credentials"
echo "   4. Configurer HTTPS en production"
