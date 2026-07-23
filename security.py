"""
Module de sécurité pour l'application
Contient les fonctions de validation, sanitization et protection contre les attaques
"""

import re
from functools import wraps
from flask import request, session, abort
from datetime import datetime, timedelta
import hashlib

# Dictionnaire pour stocker les tentatives de connexion (en production, utiliser Redis)
login_attempts = {}

def is_strong_password(password):
    """Vérifie si le mot de passe respecte les critères de sécurité"""
    if len(password) < 8:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'[0-9]', password):
        return False
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    return True

def sanitize_input(input_string):
    """Sanitize les entrées utilisateur pour prévenir XSS"""
    if not input_string:
        return input_string
    # Échapper les caractères HTML dangereux
    dangerous_chars = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#x27;',
        '/': '&#x2F;'
    }
    return ''.join(dangerous_chars.get(char, char) for char in str(input_string))

def validate_email(email):
    """Valide le format d'un email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    """Valide le format d'un numéro de téléphone"""
    # Accepte les formats internationaux et locaux
    pattern = r'^\+?[0-9]{10,15}$'
    return re.match(pattern, phone.replace(' ', '')) is not None

def rate_limit(max_attempts=10, window_minutes=15):
    """
    Décorateur pour limiter les tentatives de connexion
    Prévient les attaques brute force
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip_address = request.remote_addr
            now = datetime.now()
            
            # Nettoyer les anciennes tentatives
            login_attempts[ip_address] = [
                attempt for attempt in login_attempts.get(ip_address, [])
                if attempt > now - timedelta(minutes=window_minutes)
            ]
            
            # Vérifier si trop de tentatives échouées
            if len(login_attempts.get(ip_address, [])) >= max_attempts:
                return "Trop de tentatives. Réessayez dans {} minutes.".format(window_minutes), 429
            
            # Exécuter la fonction
            result = f(*args, **kwargs)
            
            # Si la connexion a réussi (pas de redirection vers login), nettoyer les tentatives
            if isinstance(result, tuple) and len(result) == 2:
                status_code = result[1]
                if status_code == 302:  # Redirection réussie
                    login_attempts[ip_address] = []
            elif hasattr(result, 'status_code'):
                if result.status_code == 302:  # Redirection réussie
                    login_attempts[ip_address] = []
            else:
                # Si c'est une redirection (Flask Response)
                try:
                    if result.status_code == 302:
                        login_attempts[ip_address] = []
                except:
                    pass
            
            return result
        return decorated_function
    return decorator

def validate_file_upload(file):
    """
    Valide le fichier uploadé pour prévenir les attaques par fichier malveillant
    """
    if not file:
        return False, "Aucun fichier fourni"
    
    # Vérifier l'extension
    filename = file.filename
    if not filename or '.' not in filename:
        return False, "Nom de fichier invalide"
    
    extension = filename.rsplit('.', 1)[1].lower()
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    if extension not in allowed_extensions:
        return False, "Extension non autorisée"
    
    # Vérifier le type MIME
    allowed_mimes = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}
    if file.content_type not in allowed_mimes:
        return False, "Type de fichier non autorisé"
    
    # Vérifier la taille (max 16MB)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > 16 * 1024 * 1024:
        return False, "Fichier trop volumineux (max 16MB)"
    
    return True, "Fichier valide"

def generate_csrf_token():
    """Génère un token CSRF"""
    if 'csrf_token' not in session:
        session['csrf_token'] = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    return session['csrf_token']

def validate_csrf_token(token):
    """Valide le token CSRF"""
    return 'csrf_token' in session and session['csrf_token'] == token

def csrf_protect(f):
    """Décorateur pour protéger contre les attaques CSRF"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
            if not validate_csrf_token(token):
                abort(403, "Erreur CSRF - Token invalide")
        return f(*args, **kwargs)
    return decorated_function

import secrets
