import secrets
import os

class Config:
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'bien'
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'iug2026')
    MYSQL_DB = 'boutique'
    
    # Secret key sécurisé - généré aléatoirement si non défini
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    # Configuration de session sécurisée
    SESSION_COOKIE_SECURE = True  # HTTPS uniquement
    SESSION_COOKIE_HTTPONLY = True  # Pas d'accès JavaScript
    SESSION_COOKIE_SAMESITE = 'Lax'  # Protection CSRF
    PERMANENT_SESSION_LIFETIME = 3600  # 1 heure
    
    # Upload sécurisé
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

