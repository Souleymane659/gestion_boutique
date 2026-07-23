from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, make_response
import mysql.connector
from config import Config
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import os
from werkzeug.utils import secure_filename
import secrets
from datetime import timedelta
from security import rate_limit, validate_file_upload, generate_csrf_token, validate_csrf_token, csrf_protect
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

# Configuration de session sécurisée
app.config['SESSION_COOKIE_SECURE'] = False  # True en production avec HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600

# Configuration pour l'upload de fichiers
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Middleware pour les en-têtes de sécurité
@app.after_request
def add_security_headers(response):
    # Protection XSS
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Empêcher le sniffing de type MIME
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Protection contre le clickjacking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    # Politique de sécurité de contenu (CSP)
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self'"
    # HSTS (HTTP Strict Transport Security) - à activer en HTTPS
    # response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# --- AUTHENTICATION ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin1_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        if session.get('username') != 'Admin1':
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def get_parametres():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    cursor.execute('SELECT * FROM parametres WHERE user_id = %s', (user_id,))
    parametres = cursor.fetchone()
    cursor.close()
    conn.close()
    return parametres

@app.context_processor
def inject_parametres():
    def get_classe_color(classe):
        colors = {
            '1': '#667eea',
            '2': '#f093fb',
            '3': '#4facfe',
            '4': '#43e97b',
            '5': '#fa709a',
            '6': '#ff0844',
            '7': '#11998e'
        }
        return colors.get(classe, '#667eea')
    
    def get_type_color(type_compte):
        colors = {
            'ACTIF': '#28a745',
            'PASSIF': '#17a2b8',
            'CHARGE': '#dc3545',
            'PRODUIT': '#ffc107'
        }
        return colors.get(type_compte, '#667eea')
    
    if 'logged_in' in session:
        return dict(
            get_parametres=get_parametres,
            get_classe_color=get_classe_color,
            get_type_color=get_type_color,
            csrf_token=generate_csrf_token()
        )
    return dict(
        get_parametres=lambda: None,
        get_classe_color=get_classe_color,
        get_type_color=get_type_color,
        csrf_token=generate_csrf_token()
    )

@app.route('/login', methods=['GET', 'POST'])
@rate_limit(max_attempts=10, window_minutes=15)
def login():
    logger.info(f"Tentative de connexion - Méthode: {request.method}")
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        logger.info(f"Nom d'utilisateur: {username}")
        logger.debug(f"Configuration DB: {Config.MYSQL_HOST}, {Config.MYSQL_USER}, {Config.MYSQL_DB}")
        
        # Validation basique des entrées
        if not username or not password:
            logger.warning("Champs vides")
            flash('Veuillez remplir tous les champs.', 'danger')
            return render_template('login.html')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT * FROM utilisateurs WHERE username = %s', (username,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            logger.info(f"Utilisateur trouvé: {user is not None}")
            
            if user:
                logger.debug(f"Hash du mot de passe en DB: {user['password'][:20]}...")
            
            # Authentification avec hachage
            if user and check_password_hash(user['password'], password):
                logger.info(f"Connexion réussie pour: {username}")
                session['logged_in'] = True
                session['username'] = user['username']
                session['role'] = user['role']
                session['nom'] = user['nom']
                session['user_id'] = user['id']
                session.permanent = True
                
                flash(f"Bienvenue {user['nom']} !", 'success')
                return redirect(url_for('dashboard'))
            else:
                logger.warning(f"Identifiants incorrects pour: {username}")
                flash('Identifiants incorrects.', 'danger')
                
        except Exception as e:
            logger.error(f"Erreur lors de la connexion: {str(e)}", exc_info=True)
            flash('Erreur lors de la connexion. Veuillez réessayer.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Vous avez été déconnecté.', 'success')
    return redirect(url_for('login'))


def get_db_connection():
    conn = mysql.connector.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        database=app.config['MYSQL_DB']
    )
    return conn

@app.route('/')
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    # Statistiques
    cursor.execute('SELECT COUNT(*) as nb_produits FROM produits WHERE user_id = %s', (user_id,))
    nb_produits = cursor.fetchone()['nb_produits']
    
    cursor.execute('SELECT COUNT(*) as nb_clients FROM clients WHERE user_id = %s', (user_id,))
    nb_clients = cursor.fetchone()['nb_clients']
    
    cursor.execute('SELECT COUNT(*) as nb_fournisseurs FROM fournisseurs WHERE user_id = %s', (user_id,))
    nb_fournisseurs = cursor.fetchone()['nb_fournisseurs']
    
    cursor.execute('SELECT SUM(total) as ca FROM ventes WHERE user_id = %s', (user_id,))
    res_ca = cursor.fetchone()
    ca = res_ca['ca'] if res_ca['ca'] else 0
    
    # 5 Dernières ventes
    cursor.execute('''
        SELECT v.*, c.nom as nom_client, c.prenom as prenom_client 
        FROM ventes v 
        JOIN clients c ON v.id_client = c.id_client
        WHERE v.user_id = %s
        ORDER BY v.date_vente DESC
        LIMIT 5
    ''', (user_id,))
    ventes_recentes = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('dashboard.html', 
                           nb_produits=nb_produits, 
                           nb_clients=nb_clients, 
                           nb_fournisseurs=nb_fournisseurs, 
                           ca=ca, 
                           ventes=ventes_recentes)

@app.route('/produits')
@login_required
def index_produits():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM produits WHERE user_id = %s', (session.get('user_id'),))
    produits = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('produits/index.html', produits=produits)


@app.route('/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter():

    if request.method == 'POST':
        nom_produit = request.form['nom_produit']
        prix_achat = request.form['prix_achat']
        prix_vente = request.form['prix_vente']
        quantite_stock = request.form['quantite_stock']
        user_id = session.get('user_id')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO produits (nom_produit, prix_achat, prix_vente, quantite_stock, user_id)
                VALUES (%s, %s, %s, %s, %s)
            ''', (nom_produit, prix_achat, prix_vente, quantite_stock, user_id))
            conn.commit()
            flash('Produit ajouté avec succès !', 'success')
        except mysql.connector.Error as err:
            flash(f"Erreur : {err}", 'danger')
        finally:
            cursor.close()
            conn.close()
        
        return redirect(url_for('index_produits'))

    return render_template('produits/ajouter.html')


@app.route('/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier(id):

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        nom_produit = request.form['nom_produit']
        prix_achat = request.form['prix_achat']
        prix_vente = request.form['prix_vente']
        quantite_stock = request.form['quantite_stock']

        cursor.execute('''
            UPDATE produits
            SET nom_produit=%s, prix_achat=%s, prix_vente=%s, quantite_stock=%s
            WHERE id_produit=%s AND user_id=%s
        ''', (nom_produit, prix_achat, prix_vente, quantite_stock, id, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Produit modifié avec succès !', 'success')
        return redirect(url_for('index_produits'))

    cursor.execute('SELECT * FROM produits WHERE id_produit = %s AND user_id = %s', (id, user_id))
    produit = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if produit is None:
        return "Produit non trouvé", 404
        
    return render_template('produits/modifier.html', produit=produit)


@app.route('/supprimer/<int:id>')
@login_required
def supprimer(id):

    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = session.get('user_id')
    try:
        # Démarrer une transaction
        conn.start_transaction()
        
        # Supprimer d'abord les lignes de vente associées
        cursor.execute('DELETE FROM lignes_vente WHERE id_produit = %s', (id,))
        
        # Supprimer les lignes de facture associées
        cursor.execute('DELETE FROM lignes_facture WHERE id_produit = %s', (id,))
        
        # Supprimer les lignes d'achat associées
        cursor.execute('DELETE FROM lignes_achat WHERE id_produit = %s', (id,))
        
        # Supprimer le produit
        cursor.execute('DELETE FROM produits WHERE id_produit = %s AND user_id = %s', (id, user_id))
        
        conn.commit()
        flash('Produit supprimé avec succès !', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Erreur lors de la suppression : {str(e)}', 'danger')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('index_produits'))

# --- ROUTES CLIENTS ---

@app.route('/clients')
@login_required
def index_clients():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM clients WHERE user_id = %s', (session.get('user_id'),))
    clients = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('clients/index.html', clients=clients)

@app.route('/clients/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_client():

    if request.method == 'POST':
        nom = request.form['nom']
        prenom = request.form['prenom']
        telephone = request.form['telephone']
        adresse = request.form['adresse']
        user_id = session.get('user_id')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO clients (nom, prenom, telephone, adresse, user_id)
                VALUES (%s, %s, %s, %s, %s)
            ''', (nom, prenom, telephone, adresse, user_id))
            conn.commit()
            flash('Client ajouté avec succès !', 'success')
        except mysql.connector.Error as err:
            flash(f"Erreur : {err}", 'danger')
        finally:
            cursor.close()
            conn.close()
        
        return redirect(url_for('index_clients'))

    return render_template('clients/ajouter.html')

@app.route('/clients/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_client(id):

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        nom = request.form['nom']
        prenom = request.form['prenom']
        telephone = request.form['telephone']
        adresse = request.form['adresse']

        cursor.execute('''
            UPDATE clients
            SET nom=%s, prenom=%s, telephone=%s, adresse=%s
            WHERE id_client=%s AND user_id=%s
        ''', (nom, prenom, telephone, adresse, id, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Client modifié avec succès !', 'success')
        return redirect(url_for('index_clients'))

    cursor.execute('SELECT * FROM clients WHERE id_client = %s AND user_id = %s', (id, user_id))
    client = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if client is None:
        return "Client non trouvé", 404
        
    return render_template('clients/modifier.html', client=client)

@app.route('/clients/supprimer/<int:id>')
@login_required
def supprimer_client(id):

    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = session.get('user_id')
    try:
        # Démarrer une transaction
        conn.start_transaction()
        
        # Supprimer d'abord les lignes de vente associées
        cursor.execute('DELETE FROM lignes_vente WHERE id_vente IN (SELECT id_vente FROM ventes WHERE id_client = %s AND user_id = %s)', (id, user_id))
        
        # Supprimer les ventes associées
        cursor.execute('DELETE FROM ventes WHERE id_client = %s AND user_id = %s', (id, user_id))
        
        # Supprimer le client
        cursor.execute('DELETE FROM clients WHERE id_client = %s AND user_id = %s', (id, user_id))
        
        conn.commit()
        flash('Client supprimé avec succès !', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Erreur lors de la suppression : {str(e)}', 'danger')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('index_clients'))


# --- ROUTES FOURNISSEURS ---

@app.route('/fournisseurs')
@login_required
def index_fournisseurs():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM fournisseurs WHERE user_id = %s', (session.get('user_id'),))
    fournisseurs = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('fournisseurs/index.html', fournisseurs=fournisseurs)

@app.route('/fournisseurs/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_fournisseur():

    if request.method == 'POST':
        nom_fournisseur = request.form['nom_fournisseur']
        telephone = request.form['telephone']
        adresse = request.form['adresse']
        user_id = session.get('user_id')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO fournisseurs (nom_fournisseur, telephone, adresse, user_id)
                VALUES (%s, %s, %s, %s)
            ''', (nom_fournisseur, telephone, adresse, user_id))
            conn.commit()
            flash('Fournisseur ajouté avec succès !', 'success')
        except mysql.connector.Error as err:
            flash(f"Erreur : {err}", 'danger')
        finally:
            cursor.close()
            conn.close()
        
        return redirect(url_for('index_fournisseurs'))

    return render_template('fournisseurs/ajouter.html')

@app.route('/fournisseurs/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_fournisseur(id):

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        nom_fournisseur = request.form['nom_fournisseur']
        telephone = request.form['telephone']
        adresse = request.form['adresse']

        cursor.execute('''
            UPDATE fournisseurs
            SET nom_fournisseur=%s, telephone=%s, adresse=%s
            WHERE id_fournisseur=%s AND user_id=%s
        ''', (nom_fournisseur, telephone, adresse, id, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Fournisseur modifié avec succès !', 'success')
        return redirect(url_for('index_fournisseurs'))

    cursor.execute('SELECT * FROM fournisseurs WHERE id_fournisseur = %s AND user_id = %s', (id, user_id))
    fournisseur = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if fournisseur is None:
        return "Fournisseur non trouvé", 404
        
    return render_template('fournisseurs/modifier.html', fournisseur=fournisseur)

@app.route('/fournisseurs/supprimer/<int:id>')
@login_required
def supprimer_fournisseur(id):

    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = session.get('user_id')
    try:
        # Démarrer une transaction
        conn.start_transaction()
        
        # Supprimer d'abord les lignes d'achat associées
        cursor.execute('DELETE FROM lignes_achat WHERE id_achat IN (SELECT id_achat FROM achats WHERE id_fournisseur = %s AND user_id = %s)', (id, user_id))
        
        # Supprimer les achats associés
        cursor.execute('DELETE FROM achats WHERE id_fournisseur = %s AND user_id = %s', (id, user_id))
        
        # Supprimer le fournisseur
        cursor.execute('DELETE FROM fournisseurs WHERE id_fournisseur = %s AND user_id = %s', (id, user_id))
        
        conn.commit()
        flash('Fournisseur supprimé avec succès !', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Erreur lors de la suppression : {str(e)}', 'danger')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('index_fournisseurs'))


# --- ROUTES STOCKS & MOUVEMENTS ---

@app.route('/stocks')
@login_required
def index_stocks():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    cursor.execute('''
        SELECT s.*, p.nom_produit, p.prix_vente
        FROM stocks s
        JOIN produits p ON s.id_produit = p.id_produit
        WHERE p.user_id = %s
        ORDER BY p.nom_produit
    ''', (user_id,))
    stocks = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('stocks/index.html', stocks=stocks)

@app.route('/stocks/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_stock():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        id_produit = request.form['id_produit']
        quantite = request.form['quantite']
        stock_minimum = request.form['stock_minimum']
        
        try:
            cursor.execute('''
                INSERT INTO stocks (id_produit, quantite, stock_minimum)
                VALUES (%s, %s, %s)
            ''', (id_produit, quantite, stock_minimum))
            conn.commit()
            flash('Stock ajouté avec succès !', 'success')
            return redirect(url_for('index_stocks'))
        except Exception as e:
            flash(f"Erreur : {str(e)}", 'danger')
        finally:
            cursor.close()
            conn.close()
    
    cursor.execute('SELECT * FROM produits WHERE user_id = %s', (user_id,))
    produits = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('stocks/ajouter.html', produits=produits)

@app.route('/stocks/mouvement', methods=['GET', 'POST'])
@login_required
def ajouter_mouvement():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        id_produit = request.form['id_produit']
        type_mouvement = request.form['type_mouvement']
        quantite = request.form['quantite']
        description = request.form.get('description', '')
        
        try:
            conn.start_transaction()
            
            # Ajouter le mouvement
            cursor.execute('''
                INSERT INTO mouvements_stock (id_produit, type_mouvement, quantite, description, user_id)
                VALUES (%s, %s, %s, %s, %s)
            ''', (id_produit, type_mouvement, quantite, description, user_id))
            
            # Mettre à jour le stock
            if type_mouvement == 'ENTREE':
                cursor.execute('''
                    UPDATE stocks SET quantite = quantite + %s WHERE id_produit = %s
                ''', (quantite, id_produit))
            elif type_mouvement == 'SORTIE':
                cursor.execute('''
                    UPDATE stocks SET quantite = quantite - %s WHERE id_produit = %s
                ''', (quantite, id_produit))
            elif type_mouvement == 'AJUSTEMENT':
                cursor.execute('''
                    UPDATE stocks SET quantite = %s WHERE id_produit = %s
                ''', (quantite, id_produit))
            
            conn.commit()
            flash('Mouvement de stock enregistré avec succès !', 'success')
            return redirect(url_for('index_stocks'))
        except Exception as e:
            conn.rollback()
            flash(f"Erreur : {str(e)}", 'danger')
        finally:
            cursor.close()
            conn.close()
    
    # GET
    cursor.execute('SELECT * FROM produits WHERE user_id = %s', (user_id,))
    produits = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('stocks/mouvement.html', produits=produits)

@app.route('/stocks/historique')
@login_required
def historique_stocks():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    cursor.execute('''
        SELECT m.*, p.nom_produit
        FROM mouvements_stock m
        JOIN produits p ON m.id_produit = p.id_produit
        WHERE p.user_id = %s
        ORDER BY m.date_mouvement DESC
        LIMIT 50
    ''', (user_id,))
    mouvements = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('stocks/historique.html', mouvements=mouvements)

@app.route('/stocks/mouvement/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_mouvement(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        type_mouvement = request.form['type_mouvement']
        quantite = request.form['quantite']
        description = request.form.get('description', '')
        
        try:
            conn.start_transaction()
            
            # Récupérer l'ancien mouvement pour annuler son effet sur le stock
            cursor.execute('SELECT * FROM mouvements_stock WHERE id_mouvement = %s', (id,))
            old_mouvement = cursor.fetchone()
            
            if old_mouvement:
                # Annuler l'ancien effet sur le stock
                if old_mouvement['type_mouvement'] == 'ENTREE':
                    cursor.execute('UPDATE stocks SET quantite = quantite - %s WHERE id_produit = %s', (old_mouvement['quantite'], old_mouvement['id_produit']))
                elif old_mouvement['type_mouvement'] == 'SORTIE':
                    cursor.execute('UPDATE stocks SET quantite = quantite + %s WHERE id_produit = %s', (old_mouvement['quantite'], old_mouvement['id_produit']))
                
                # Mettre à jour le mouvement
                cursor.execute('''
                    UPDATE mouvements_stock
                    SET type_mouvement=%s, quantite=%s, description=%s
                    WHERE id_mouvement=%s
                ''', (type_mouvement, quantite, description, id))
                
                # Appliquer le nouvel effet sur le stock
                if type_mouvement == 'ENTREE':
                    cursor.execute('UPDATE stocks SET quantite = quantite + %s WHERE id_produit = %s', (quantite, old_mouvement['id_produit']))
                elif type_mouvement == 'SORTIE':
                    cursor.execute('UPDATE stocks SET quantite = quantite - %s WHERE id_produit = %s', (quantite, old_mouvement['id_produit']))
                elif type_mouvement == 'AJUSTEMENT':
                    cursor.execute('UPDATE stocks SET quantite = %s WHERE id_produit = %s', (quantite, old_mouvement['id_produit']))
            
            conn.commit()
            flash('Mouvement modifié avec succès !', 'success')
            return redirect(url_for('historique_stocks'))
        except Exception as e:
            conn.rollback()
            flash(f"Erreur : {str(e)}", 'danger')
        finally:
            cursor.close()
            conn.close()
    
    cursor.execute('''
        SELECT m.*, p.nom_produit
        FROM mouvements_stock m
        JOIN produits p ON m.id_produit = p.id_produit
        WHERE m.id_mouvement = %s AND p.user_id = %s
    ''', (id, user_id))
    mouvement = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if mouvement is None:
        return "Mouvement non trouvé", 404
        
    return render_template('stocks/modifier_mouvement.html', mouvement=mouvement)

@app.route('/stocks/mouvement/supprimer/<int:id>')
@login_required
def supprimer_mouvement(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    try:
        conn.start_transaction()
        
        # Récupérer le mouvement pour annuler son effet sur le stock
        cursor.execute('''
            SELECT m.*, p.nom_produit
            FROM mouvements_stock m
            JOIN produits p ON m.id_produit = p.id_produit
            WHERE m.id_mouvement = %s AND p.user_id = %s
        ''', (id, user_id))
        mouvement = cursor.fetchone()
        
        if mouvement:
            # Annuler l'effet sur le stock
            if mouvement['type_mouvement'] == 'ENTREE':
                cursor.execute('UPDATE stocks SET quantite = quantite - %s WHERE id_produit = %s', (mouvement['quantite'], mouvement['id_produit']))
            elif mouvement['type_mouvement'] == 'SORTIE':
                cursor.execute('UPDATE stocks SET quantite = quantite + %s WHERE id_produit = %s', (mouvement['quantite'], mouvement['id_produit']))
            
            # Supprimer le mouvement
            cursor.execute('DELETE FROM mouvements_stock WHERE id_mouvement = %s', (id,))
        
        conn.commit()
        flash('Mouvement supprimé avec succès !', 'success')
    except Exception as e:
        conn.rollback()
        flash(f"Erreur : {str(e)}", 'danger')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('historique_stocks'))

@app.route('/stocks/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_stock(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        quantite = request.form['quantite']
        stock_minimum = request.form['stock_minimum']
        
        cursor.execute('''
            UPDATE stocks
            SET quantite=%s, stock_minimum=%s
            WHERE id_stock=%s
        ''', (quantite, stock_minimum, id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Stock modifié avec succès !', 'success')
        return redirect(url_for('index_stocks'))
    
    cursor.execute('''
        SELECT s.*, p.nom_produit
        FROM stocks s
        JOIN produits p ON s.id_produit = p.id_produit
        WHERE s.id_stock = %s AND p.user_id = %s
    ''', (id, user_id))
    stock = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if stock is None:
        return "Stock non trouvé", 404
        
    return render_template('stocks/modifier.html', stock=stock)

@app.route('/stocks/supprimer/<int:id>')
@login_required
def supprimer_stock(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Démarrer une transaction
        conn.start_transaction()
        
        # Supprimer d'abord les mouvements de stock associés
        cursor.execute('DELETE FROM mouvements_stock WHERE id_stock = %s', (id,))
        
        # Supprimer le stock
        cursor.execute('DELETE FROM stocks WHERE id_stock = %s', (id,))
        
        conn.commit()
        flash('Stock supprimé avec succès !', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Erreur lors de la suppression : {str(e)}', 'danger')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('index_stocks'))


# --- ROUTES ACHATS ---

@app.route('/achats')
@login_required
def index_achats():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    cursor.execute('''
        SELECT a.*, f.nom_fournisseur
        FROM achats a
        LEFT JOIN fournisseurs f ON a.id_fournisseur = f.id_fournisseur
        WHERE a.user_id = %s
        ORDER BY a.date_achat DESC
    ''', (user_id,))
    achats = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('achats/index.html', achats=achats)

@app.route('/achats/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_achat():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        id_fournisseur = request.form.get('id_fournisseur')
        produits = request.form.getlist('id_produit[]')
        quantites = request.form.getlist('quantite[]')
        prix_achats = request.form.getlist('prix_achat[]')
        
        try:
            conn.start_transaction()
            
            # Créer l'achat
            cursor.execute('''
                INSERT INTO achats (id_fournisseur, montant_total, user_id)
                VALUES (%s, 0, %s)
            ''', (id_fournisseur if id_fournisseur else None, user_id))
            id_achat = cursor.lastrowid
            
            montant_total = 0
            
            # Ajouter les lignes d'achat
            for i in range(len(produits)):
                if produits[i] and quantites[i] and prix_achats[i]:
                    quantite = int(quantites[i])
                    prix_achat = float(prix_achats[i])
                    sous_total = quantite * prix_achat
                    montant_total += sous_total
                    
                    cursor.execute('''
                        INSERT INTO lignes_achat (id_achat, id_produit, quantite, prix_achat, sous_total)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (id_achat, produits[i], quantite, prix_achat, sous_total))
                    
                    # Mettre à jour le stock
                    cursor.execute('''
                        INSERT INTO stocks (id_produit, quantite, stock_minimum)
                        VALUES (%s, %s, 5)
                        ON DUPLICATE KEY UPDATE quantite = quantite + %s
                    ''', (produits[i], quantite, quantite))
            
            # Mettre à jour le montant total
            cursor.execute('UPDATE achats SET montant_total = %s WHERE id_achat = %s', (montant_total, id_achat))
            
            conn.commit()
            flash('Achat ajouté avec succès !', 'success')
            return redirect(url_for('index_achats'))
        except Exception as e:
            conn.rollback()
            flash(f"Erreur : {str(e)}", 'danger')
        finally:
            cursor.close()
            conn.close()
    
    cursor.execute('SELECT * FROM fournisseurs WHERE user_id = %s', (user_id,))
    fournisseurs = cursor.fetchall()
    cursor.execute('SELECT * FROM produits WHERE user_id = %s', (user_id,))
    produits = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('achats/ajouter.html', fournisseurs=fournisseurs, produits=produits)

@app.route('/achats/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_achat(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        id_fournisseur = request.form.get('id_fournisseur')
        produits = request.form.getlist('id_produit[]')
        quantites = request.form.getlist('quantite[]')
        prix_achats = request.form.getlist('prix_achat[]')
        
        try:
            conn.start_transaction()
            
            # Récupérer les anciennes lignes pour annuler les stocks
            cursor.execute('SELECT * FROM lignes_achat WHERE id_achat = %s', (id,))
            old_lignes = cursor.fetchall()
            for ligne in old_lignes:
                cursor.execute('UPDATE stocks SET quantite = quantite - %s WHERE id_produit = %s', (ligne['quantite'], ligne['id_produit']))
            
            # Supprimer les anciennes lignes
            cursor.execute('DELETE FROM lignes_achat WHERE id_achat = %s', (id,))
            
            # Mettre à jour l'achat
            cursor.execute('UPDATE achats SET id_fournisseur = %s WHERE id_achat = %s', (id_fournisseur if id_fournisseur else None, id))
            
            montant_total = 0
            
            # Ajouter les nouvelles lignes d'achat
            for i in range(len(produits)):
                if produits[i] and quantites[i] and prix_achats[i]:
                    quantite = int(quantites[i])
                    prix_achat = float(prix_achats[i])
                    sous_total = quantite * prix_achat
                    montant_total += sous_total
                    
                    cursor.execute('''
                        INSERT INTO lignes_achat (id_achat, id_produit, quantite, prix_achat, sous_total)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (id, produits[i], quantite, prix_achat, sous_total))
                    
                    # Mettre à jour le stock
                    cursor.execute('''
                        INSERT INTO stocks (id_produit, quantite, stock_minimum)
                        VALUES (%s, %s, 5)
                        ON DUPLICATE KEY UPDATE quantite = quantite + %s
                    ''', (produits[i], quantite, quantite))
            
            # Mettre à jour le montant total
            cursor.execute('UPDATE achats SET montant_total = %s WHERE id_achat = %s', (montant_total, id))
            
            conn.commit()
            flash('Achat modifié avec succès !', 'success')
            return redirect(url_for('index_achats'))
        except Exception as e:
            conn.rollback()
            flash(f"Erreur : {str(e)}", 'danger')
        finally:
            cursor.close()
            conn.close()
    
    cursor.execute('''
        SELECT a.*, f.nom_fournisseur
        FROM achats a
        LEFT JOIN fournisseurs f ON a.id_fournisseur = f.id_fournisseur
        WHERE a.id_achat = %s AND a.user_id = %s
    ''', (id, user_id))
    achat = cursor.fetchone()
    
    cursor.execute('SELECT * FROM lignes_achat WHERE id_achat = %s', (id,))
    lignes = cursor.fetchall()
    
    cursor.execute('SELECT * FROM fournisseurs WHERE user_id = %s', (user_id,))
    fournisseurs = cursor.fetchall()
    cursor.execute('SELECT * FROM produits WHERE user_id = %s', (user_id,))
    produits = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    if achat is None:
        return "Achat non trouvé", 404
        
    return render_template('achats/modifier.html', achat=achat, lignes=lignes, fournisseurs=fournisseurs, produits=produits)

@app.route('/achats/supprimer/<int:id>')
@login_required
def supprimer_achat(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    try:
        conn.start_transaction()
        
        # Récupérer les lignes pour annuler les stocks
        cursor.execute('SELECT * FROM lignes_achat WHERE id_achat = %s', (id,))
        lignes = cursor.fetchall()
        for ligne in lignes:
            cursor.execute('UPDATE stocks SET quantite = quantite - %s WHERE id_produit = %s', (ligne['quantite'], ligne['id_produit']))
        
        # Supprimer les lignes
        cursor.execute('DELETE FROM lignes_achat WHERE id_achat = %s', (id,))
        
        # Supprimer l'achat
        cursor.execute('DELETE FROM achats WHERE id_achat = %s', (id,))
        
        conn.commit()
        flash('Achat supprimé avec succès !', 'success')
    except Exception as e:
        conn.rollback()
        flash(f"Erreur : {str(e)}", 'danger')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('index_achats'))


# --- ROUTES DEPENSES ---

@app.route('/depenses')
@login_required
def index_depenses():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    cursor.execute('''
        SELECT * FROM depenses
        WHERE user_id = %s
        ORDER BY date_depense DESC
    ''', (user_id,))
    depenses = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('depenses/index.html', depenses=depenses)

@app.route('/depenses/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_depense():
    if request.method == 'POST':
        libelle = request.form['libelle']
        montant = request.form['montant']
        description = request.form.get('description', '')
        user_id = session.get('user_id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO depenses (libelle, montant, description, user_id)
            VALUES (%s, %s, %s, %s)
        ''', (libelle, montant, description, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Dépense ajoutée avec succès !', 'success')
        return redirect(url_for('index_depenses'))
    
    return render_template('depenses/ajouter.html')

@app.route('/depenses/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_depense(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        libelle = request.form['libelle']
        montant = request.form['montant']
        description = request.form.get('description', '')
        
        cursor.execute('''
            UPDATE depenses
            SET libelle=%s, montant=%s, description=%s
            WHERE id_depense=%s AND user_id=%s
        ''', (libelle, montant, description, id, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Dépense modifiée avec succès !', 'success')
        return redirect(url_for('index_depenses'))
    
    cursor.execute('SELECT * FROM depenses WHERE id_depense = %s AND user_id = %s', (id, user_id))
    depense = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if depense is None:
        return "Dépense non trouvée", 404
        
    return render_template('depenses/modifier.html', depense=depense)

@app.route('/depenses/supprimer/<int:id>')
@login_required
def supprimer_depense(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = session.get('user_id')
    
    cursor.execute('DELETE FROM depenses WHERE id_depense = %s AND user_id = %s', (id, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Dépense supprimée avec succès !', 'success')
    return redirect(url_for('index_depenses'))


# --- ROUTES FACTURES ---

@app.route('/factures')
@login_required
def index_factures():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    try:
        cursor.execute('''
            SELECT f.*, CONCAT(c.nom, ' ', c.prenom) as nom_client, c.telephone, c.adresse
            FROM factures f
            LEFT JOIN clients c ON f.id_client = c.id_client
            WHERE f.user_id = %s
            ORDER BY f.date_facture DESC
        ''', (user_id,))
        factures = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('factures/index.html', factures=factures)
    except Exception as e:
        cursor.close()
        conn.close()
        flash(f"Erreur lors de la récupération des factures: {str(e)}", 'danger')
        return redirect(url_for('dashboard'))

@app.route('/factures/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_facture():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        id_client = request.form.get('id_client')
        statut = request.form.get('statut', 'NON_PAYEE')
        montant_paye = request.form.get('montant_paye', 0)
        produits = request.form.getlist('id_produit[]')
        quantites = request.form.getlist('quantite[]')
        prix_unitaires = request.form.getlist('prix_unitaire[]')
        
        try:
            conn.start_transaction()
            
            # Générer numéro de facture
            import datetime
            date_str = datetime.datetime.now().strftime('%Y%m%d')
            cursor.execute('SELECT COUNT(*) as count FROM factures WHERE DATE(date_facture) = CURDATE()')
            count = cursor.fetchone()['count']
            numero_facture = f"FAC-{date_str}-{count + 1:04d}"
            
            # Créer la facture
            cursor.execute('''
                INSERT INTO factures (numero_facture, id_client, montant_total, statut, user_id)
                VALUES (%s, %s, 0, %s, %s)
            ''', (numero_facture, id_client if id_client else None, statut, user_id))
            id_facture = cursor.lastrowid
            
            montant_total = 0
            
            # Ajouter les lignes de facture
            for i in range(len(produits)):
                if produits[i] and quantites[i] and prix_unitaires[i]:
                    quantite = int(quantites[i])
                    prix_unitaire = float(prix_unitaires[i])
                    sous_total = quantite * prix_unitaire
                    montant_total += sous_total
                    
                    cursor.execute('''
                        INSERT INTO lignes_facture (id_facture, id_produit, quantite, prix_unitaire, sous_total)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (id_facture, produits[i], quantite, prix_unitaire, sous_total))
                    
                    # Déduire du stock
                    cursor.execute('UPDATE stocks SET quantite = quantite - %s WHERE id_produit = %s', (quantite, produits[i]))
            
            # Mettre à jour le montant total
            cursor.execute('UPDATE factures SET montant_total = %s WHERE id_facture = %s', (montant_total, id_facture))
            
            # Calculer et mettre à jour le montant payé et restant
            if statut == 'PARTIELLE':
                montant_paye = float(montant_paye) if montant_paye else 0
                montant_restant = montant_total - montant_paye
                cursor.execute('UPDATE factures SET montant_paye = %s, montant_restant = %s WHERE id_facture = %s', 
                              (montant_paye, montant_restant, id_facture))
            elif statut == 'PAYEE':
                cursor.execute('UPDATE factures SET montant_paye = %s, montant_restant = %s WHERE id_facture = %s', 
                              (montant_total, 0, id_facture))
            else:  # NON_PAYEE
                cursor.execute('UPDATE factures SET montant_paye = 0, montant_restant = %s WHERE id_facture = %s', 
                              (montant_total, id_facture))
            
            conn.commit()
            flash('Facture ajoutée avec succès !', 'success')
            return redirect(url_for('index_factures'))
        except Exception as e:
            conn.rollback()
            flash(f"Erreur : {str(e)}", 'danger')
        finally:
            cursor.close()
            conn.close()
    
    cursor.execute('SELECT * FROM clients WHERE user_id = %s', (user_id,))
    clients = cursor.fetchall()
    cursor.execute('SELECT * FROM produits WHERE user_id = %s', (user_id,))
    produits = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('factures/ajouter.html', clients=clients, produits=produits)

@app.route('/factures/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_facture(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        id_client = request.form.get('id_client')
        statut = request.form.get('statut', 'NON_PAYEE')
        montant_paye = request.form.get('montant_paye', 0)
        produits = request.form.getlist('id_produit[]')
        quantites = request.form.getlist('quantite[]')
        prix_unitaires = request.form.getlist('prix_unitaire[]')
        
        try:
            conn.start_transaction()
            
            # Récupérer les anciennes lignes pour restaurer les stocks
            cursor.execute('SELECT * FROM lignes_facture WHERE id_facture = %s', (id,))
            old_lignes = cursor.fetchall()
            for ligne in old_lignes:
                cursor.execute('UPDATE stocks SET quantite = quantite + %s WHERE id_produit = %s', (ligne['quantite'], ligne['id_produit']))
            
            # Supprimer les anciennes lignes
            cursor.execute('DELETE FROM lignes_facture WHERE id_facture = %s', (id,))
            
            # Mettre à jour la facture
            cursor.execute('UPDATE factures SET id_client = %s, statut = %s WHERE id_facture = %s', (id_client if id_client else None, statut, id))
            
            montant_total = 0
            
            # Ajouter les nouvelles lignes de facture
            for i in range(len(produits)):
                if produits[i] and quantites[i] and prix_unitaires[i]:
                    quantite = int(quantites[i])
                    prix_unitaire = float(prix_unitaires[i])
                    sous_total = quantite * prix_unitaire
                    montant_total += sous_total
                    
                    cursor.execute('''
                        INSERT INTO lignes_facture (id_facture, id_produit, quantite, prix_unitaire, sous_total)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (id, produits[i], quantite, prix_unitaire, sous_total))
                    
                    # Déduire du stock
                    cursor.execute('UPDATE stocks SET quantite = quantite - %s WHERE id_produit = %s', (quantite, produits[i]))
            
            # Mettre à jour le montant total
            cursor.execute('UPDATE factures SET montant_total = %s WHERE id_facture = %s', (montant_total, id))
            
            # Calculer et mettre à jour le montant payé et restant
            if statut == 'PARTIELLE':
                montant_paye = float(montant_paye) if montant_paye else 0
                montant_restant = montant_total - montant_paye
                cursor.execute('UPDATE factures SET montant_paye = %s, montant_restant = %s WHERE id_facture = %s', 
                              (montant_paye, montant_restant, id))
            elif statut == 'PAYEE':
                cursor.execute('UPDATE factures SET montant_paye = %s, montant_restant = %s WHERE id_facture = %s', 
                              (montant_total, 0, id))
            else:  # NON_PAYEE
                cursor.execute('UPDATE factures SET montant_paye = 0, montant_restant = %s WHERE id_facture = %s', 
                              (montant_total, id))
            
            conn.commit()
            flash('Facture modifiée avec succès !', 'success')
            return redirect(url_for('index_factures'))
        except Exception as e:
            conn.rollback()
            flash(f"Erreur : {str(e)}", 'danger')
        finally:
            cursor.close()
            conn.close()
    
    cursor.execute('''
        SELECT f.*, CONCAT(c.nom, ' ', c.prenom) as nom_client, c.telephone, c.adresse
        FROM factures f
        LEFT JOIN clients c ON f.id_client = c.id_client
        WHERE f.id_facture = %s AND f.user_id = %s
    ''', (id, user_id))
    facture = cursor.fetchone()
    
    cursor.execute('SELECT * FROM lignes_facture WHERE id_facture = %s', (id,))
    lignes = cursor.fetchall()
    
    cursor.execute('SELECT * FROM clients WHERE user_id = %s', (user_id,))
    clients = cursor.fetchall()
    cursor.execute('SELECT * FROM produits WHERE user_id = %s', (user_id,))
    produits = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    if facture is None:
        return "Facture non trouvée", 404
        
    return render_template('factures/modifier.html', facture=facture, lignes=lignes, clients=clients, produits=produits)

@app.route('/factures/supprimer/<int:id>')
@login_required
def supprimer_facture(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    try:
        conn.start_transaction()
        
        # Récupérer les lignes pour restaurer les stocks
        cursor.execute('SELECT * FROM lignes_facture WHERE id_facture = %s', (id,))
        lignes = cursor.fetchall()
        for ligne in lignes:
            cursor.execute('UPDATE stocks SET quantite = quantite + %s WHERE id_produit = %s', (ligne['quantite'], ligne['id_produit']))
        
        # Supprimer les lignes
        cursor.execute('DELETE FROM lignes_facture WHERE id_facture = %s', (id,))
        
        # Supprimer la facture
        cursor.execute('DELETE FROM factures WHERE id_facture = %s', (id,))
        
        conn.commit()
        flash('Facture supprimée avec succès !', 'success')
    except Exception as e:
        conn.rollback()
        flash(f"Erreur : {str(e)}", 'danger')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('index_factures'))

@app.route('/factures/pdf/<int:id>')
@login_required
def pdf_facture(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    cursor.execute('''
        SELECT f.*, CONCAT(c.nom, ' ', c.prenom) as nom_client, c.telephone, c.adresse
        FROM factures f
        LEFT JOIN clients c ON f.id_client = c.id_client
        WHERE f.id_facture = %s AND f.user_id = %s
    ''', (id, user_id))
    facture = cursor.fetchone()
    
    cursor.execute('''
        SELECT lf.*, p.nom_produit
        FROM lignes_facture lf
        JOIN produits p ON lf.id_produit = p.id_produit
        WHERE lf.id_facture = %s
    ''', (id,))
    lignes = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    if facture is None:
        return "Facture non trouvée", 404
    
    return render_template('factures/pdf.html', facture=facture, lignes=lignes)


# --- ROUTES PARAMETRES ---

@app.route('/parametres', methods=['GET', 'POST'])
@login_required
def parametres():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        nom_boutique = request.form.get('nom_boutique')
        telephone = request.form.get('telephone')
        email = request.form.get('email')
        adresse = request.form.get('adresse')
        devise = request.form.get('devise', 'FCFA')
        slogan = request.form.get('slogan')
        
        # Gestion de l'upload des 3 logos
        logo1 = None
        logo2 = None
        logo3 = None
        
        for i in range(1, 4):
            logo_key = f'logo{i}'
            if logo_key in request.files:
                file = request.files[logo_key]
                if file and file.filename != '' and allowed_file(file.filename):
                    # Créer le dossier d'upload s'il n'existe pas
                    if not os.path.exists(app.config['UPLOAD_FOLDER']):
                        os.makedirs(app.config['UPLOAD_FOLDER'])
                    
                    filename = secure_filename(file.filename)
                    # Ajouter un timestamp pour éviter les doublons
                    import time
                    timestamp = str(int(time.time()))
                    filename = f"{timestamp}_{i}_{filename}"
                    
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    logo_path = f"/static/uploads/{filename}"
                    
                    if i == 1:
                        logo1 = logo_path
                    elif i == 2:
                        logo2 = logo_path
                    elif i == 3:
                        logo3 = logo_path
        
        try:
            cursor.execute('SELECT * FROM parametres WHERE user_id = %s', (user_id,))
            parametres = cursor.fetchone()
            
            if parametres:
                # Si de nouveaux logos sont uploadés, les utiliser, sinon garder les anciens
                logo1_to_save = logo1 if logo1 else parametres.get('logo1') or parametres.get('logo')
                logo2_to_save = logo2 if logo2 else parametres.get('logo2')
                logo3_to_save = logo3 if logo3 else parametres.get('logo3')
                cursor.execute('''
                    UPDATE parametres 
                    SET nom_boutique = %s, logo1 = %s, logo2 = %s, logo3 = %s, telephone = %s, email = %s, adresse = %s, devise = %s, slogan = %s
                    WHERE user_id = %s
                ''', (nom_boutique, logo1_to_save, logo2_to_save, logo3_to_save, telephone, email, adresse, devise, slogan, user_id))
            else:
                cursor.execute('''
                    INSERT INTO parametres (nom_boutique, logo1, logo2, logo3, telephone, email, adresse, devise, slogan, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (nom_boutique, logo1, logo2, logo3, telephone, email, adresse, devise, slogan, user_id))
            
            conn.commit()
            flash('Paramètres mis à jour avec succès !', 'success')
        except Exception as e:
            conn.rollback()
            flash(f"Erreur : {str(e)}", 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('parametres'))
    
    cursor.execute('SELECT * FROM parametres WHERE user_id = %s', (user_id,))
    parametres = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return render_template('parametres/index.html', parametres=parametres)


# --- ROUTES VENTES & FACTURES ---

@app.route('/ventes')
@login_required
def index_ventes():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    cursor.execute('''
        SELECT v.*, c.nom as nom_client, c.prenom as prenom_client 
        FROM ventes v 
        JOIN clients c ON v.id_client = c.id_client
        WHERE v.user_id = %s
        ORDER BY v.date_vente DESC
    ''', (user_id,))
    ventes = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('ventes/index.html', ventes=ventes)

@app.route('/ventes/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_vente():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')

    if request.method == 'POST':
        type_client = request.form['type_client']
        id_client = None
        client_temporaire_nom = None
        
        try:
            # Démarrer une transaction
            conn.start_transaction()
            
            # Gérer le client selon le type
            if type_client == 'existant':
                id_client = request.form['id_client']
                if not id_client:
                    raise Exception("Veuillez sélectionner un client existant")
            
            elif type_client == 'nouveau':
                nouveau_nom = request.form['nouveau_nom']
                nouveau_prenom = request.form['nouveau_prenom']
                nouveau_telephone = request.form.get('nouveau_telephone', '')
                nouveau_adresse = request.form.get('nouveau_adresse', '')
                
                if not nouveau_nom or not nouveau_prenom:
                    raise Exception("Le nom et le prénom sont obligatoires pour un nouveau client")
                
                # Créer le nouveau client
                cursor.execute('''
                    INSERT INTO clients (nom, prenom, telephone, adresse, user_id)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (nouveau_nom, nouveau_prenom, nouveau_telephone, nouveau_adresse, user_id))
                id_client = cursor.lastrowid
                flash('Nouveau client créé avec succès !', 'success')
            
            elif type_client == 'temporaire':
                client_temporaire_nom = request.form['client_temporaire_nom']
                if not client_temporaire_nom:
                    raise Exception("Le nom du client temporaire est obligatoire")
                # Pour les clients temporaires, on utilise NULL comme id_client
                # et on stockera le nom dans une autre colonne ou on utilisera un client fictif
                # Pour l'instant, on utilisera NULL
            
            produits_ids = request.form.getlist('produits[]')
            quantites = request.form.getlist('quantites[]')
            
            total_vente = 0
            # 1. Créer la vente avec AUTO_INCREMENT
            cursor.execute('INSERT INTO ventes (id_client, total, user_id) VALUES (%s, %s, %s)', (id_client, 0, user_id))
            id_vente = cursor.lastrowid

            
            # 2. Ajouter les lignes et calculer le total
            for p_id, qty in zip(produits_ids, quantites):
                if not p_id or not qty: continue
                qty = int(qty)
                
                # Récupérer prix et stock
                cursor.execute('SELECT prix_vente, quantite_stock FROM produits WHERE id_produit = %s', (p_id,))
                prod = cursor.fetchone()
                
                if prod['quantite_stock'] < qty:
                    raise Exception(f"Stock insuffisant pour le produit ID {p_id}")
                
                sous_total = prod['prix_vente'] * qty
                total_vente += sous_total
                
                # Insérer ligne
                cursor.execute('''
                    INSERT INTO lignes_vente (id_vente, id_produit, quantite, prix_unitaire)
                    VALUES (%s, %s, %s, %s)
                ''', (id_vente, p_id, qty, prod['prix_vente']))
                
                # Mettre à jour le stock
                cursor.execute('''
                    UPDATE produits SET quantite_stock = quantite_stock - %s 
                    WHERE id_produit = %s AND user_id = %s
                ''', (qty, p_id, user_id))
            
            # 3. Mettre à jour le total de la vente
            cursor.execute('UPDATE ventes SET total = %s WHERE id_vente = %s AND user_id = %s', (total_vente, id_vente, user_id))
            
            # Si c'est un client temporaire, on peut stocker le nom dans une colonne notes ou similaire
            # Pour l'instant, on va supposer que la table ventes a une colonne client_temporaire ou on peut l'ajouter
            if client_temporaire_nom:
                try:
                    cursor.execute('UPDATE ventes SET client_temporaire = %s WHERE id_vente = %s', (client_temporaire_nom, id_vente))
                except mysql.connector.Error:
                    # La colonne n'existe pas encore, on peut l'ajouter ou ignorer
                    pass
            
            conn.commit()
            flash('Vente enregistrée avec succès !', 'success')
            return redirect(url_for('facture', id=id_vente))
            
        except Exception as e:
            conn.rollback()
            flash(f"Erreur lors de la vente : {str(e)}", 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('ajouter_vente'))

    # GET
    cursor.execute('SELECT * FROM clients WHERE user_id = %s', (user_id,))
    clients = cursor.fetchall()
    cursor.execute('SELECT * FROM produits WHERE quantite_stock > 0 AND user_id = %s', (user_id,))
    produits = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('ventes/ajouter.html', clients=clients, produits=produits)

@app.route('/ventes/facture/<int:id>')
@login_required
def facture(id):

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    # Récupérer les infos de la vente avec LEFT JOIN pour gérer les clients temporaires
    cursor.execute('''
        SELECT v.*, c.nom as nom_client, c.prenom as prenom_client, c.telephone, c.adresse
        FROM ventes v 
        LEFT JOIN clients c ON v.id_client = c.id_client
        WHERE v.id_vente = %s AND v.user_id = %s
    ''', (id, user_id))
    vente = cursor.fetchone()
    
    if not vente:
        cursor.close()
        conn.close()
        return "Vente non trouvée", 404
        
    # Récupérer les lignes de la vente
    cursor.execute('''
        SELECT lv.*, p.nom_produit 
        FROM lignes_vente lv
        JOIN produits p ON lv.id_produit = p.id_produit
        WHERE lv.id_vente = %s
    ''', (id,))
    lignes = cursor.fetchall()
    
    # Récupérer les paramètres de l'utilisateur pour les infos de l'entreprise
    cursor.execute('SELECT * FROM parametres WHERE user_id = %s', (user_id,))
    parametres = cursor.fetchone()
    
    cursor.close()
    conn.close()
    return render_template('ventes/facture.html', vente=vente, lignes=lignes, parametres=parametres)


@app.route('/rapports')
@login_required
def rapports():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    try:
        # 1. Chiffre d'Affaire (CA)
        cursor.execute('SELECT SUM(total) as ca FROM ventes WHERE user_id = %s', (user_id,))
        res_ca = cursor.fetchone()
        total_ventes = res_ca['ca'] if res_ca['ca'] else 0
        
        # 2. Coût des Achats (Basé sur les ventes - COGS)
        cursor.execute('''
            SELECT SUM(lv.quantite * p.prix_achat) as total_cout
            FROM lignes_vente lv
            JOIN produits p ON lv.id_produit = p.id_produit
            JOIN ventes v ON lv.id_vente = v.id_vente
            WHERE v.user_id = %s
        ''', (user_id,))
        res_cout = cursor.fetchone()
        total_achats = res_cout['total_cout'] if res_cout['total_cout'] else 0
        
        # 3. Bénéfices
        benefices = total_ventes - total_achats
        
        # 4. Liste des factures
        cursor.execute('''
            SELECT v.*, c.nom as nom_client, c.prenom as prenom_client 
            FROM ventes v 
            JOIN clients c ON v.id_client = c.id_client
            WHERE v.user_id = %s
            ORDER BY v.date_vente DESC
        ''', (user_id,))
        factures = cursor.fetchall()
        
        stats = {
            'total_ventes': total_ventes,
            'total_achats': total_achats,
            'benefices': benefices
        }
        
        return render_template('rapports/index.html', stats=stats, factures=factures)
        
    except Exception as e:
        flash(f"Erreur lors du calcul des rapports : {str(e)}", 'danger')
        return redirect(url_for('dashboard'))
    finally:
        cursor.close()
        conn.close()


# --- ROUTES UTILISATEURS ---

@app.route('/utilisateurs')
@admin1_required
def index_utilisateurs():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT id, nom, username, role FROM utilisateurs')
    utilisateurs = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('utilisateurs/index.html', utilisateurs=utilisateurs)

@app.route('/utilisateurs/ajouter', methods=['GET', 'POST'])
@admin1_required
def ajouter_utilisateur():
    if request.method == 'POST':
        nom = request.form['nom']
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        
        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO utilisateurs (nom, username, password, role)
                VALUES (%s, %s, %s, %s)
            ''', (nom, username, hashed_password, role))
            conn.commit()
            flash('Utilisateur ajouté avec succès !', 'success')
        except mysql.connector.Error as err:
            flash(f"Erreur : {err}", 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('index_utilisateurs'))

    return render_template('utilisateurs/ajouter.html')

@app.route('/utilisateurs/modifier/<int:id>', methods=['GET', 'POST'])
@admin1_required
def modifier_utilisateur(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        nom = request.form['nom']
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        # Si le mot de passe est vide, on ne le modifie pas
        if password.strip() == "":
            cursor.execute('''
                UPDATE utilisateurs
                SET nom=%s, username=%s, role=%s
                WHERE id=%s
            ''', (nom, username, role, id))
        else:
            hashed_password = generate_password_hash(password)
            cursor.execute('''
                UPDATE utilisateurs
                SET nom=%s, username=%s, password=%s, role=%s
                WHERE id=%s
            ''', (nom, username, hashed_password, role, id))
            
        conn.commit()
        cursor.close()
        conn.close()
        flash('Utilisateur modifié avec succès !', 'success')
        return redirect(url_for('index_utilisateurs'))

    cursor.execute('SELECT id, nom, username, role FROM utilisateurs WHERE id = %s', (id,))
    utilisateur = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if utilisateur is None:
        return "Utilisateur non trouvé", 404
        
    return render_template('utilisateurs/modifier.html', utilisateur=utilisateur)

@app.route('/utilisateurs/supprimer/<int:id>')
@admin1_required
def supprimer_utilisateur(id):
    # Sécurité : empêcher le Comptable de se supprimer lui-même
    if id == session.get('user_id'):
        flash("Vous ne pouvez pas supprimer votre propre compte.", "danger")
        return redirect(url_for('index_utilisateurs'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM utilisateurs WHERE id = %s', (id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Utilisateur supprimé avec succès !', 'success')
    return redirect(url_for('index_utilisateurs'))


# --- ROUTES INVENTAIRES ---

@app.route('/inventaires')
@login_required
def index_inventaires():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    # Récupérer la liste des inventaires (en-têtes)
    cursor.execute('''
        SELECT i.*, 
               (SELECT COUNT(*) FROM inventaire_details WHERE id_inventaires = i.id_inventaires) as nb_articles,
               (SELECT SUM(montant) FROM inventaire_details WHERE id_inventaires = i.id_inventaires) as total_montant
        FROM inventaires i
        WHERE i.user_id = %s
        ORDER BY i.date_inventaire DESC, i.created_at DESC
    ''', (user_id,))
    inventaires = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('inventaires/index.html', inventaires=inventaires)

@app.route('/inventaires/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_inventaire():
    if request.method == 'POST':
        reference = request.form['reference']
        titre = request.form['titre']
        date_inventaire = request.form['date_inventaire']
        user_id = session.get('user_id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Créer l'en-tête de l'inventaire
            cursor.execute('''
                INSERT INTO inventaires (reference, titre, date_inventaire, statut, user_id)
                VALUES (%s, %s, %s, 'EN_COURS', %s)
            ''', (reference, titre, date_inventaire, user_id))
            id_inventaires = cursor.lastrowid
            conn.commit()
            flash('Inventaire créé avec succès !', 'success')
            return redirect(url_for('details_inventaire', id=id_inventaires))
        except mysql.connector.Error as err:
            flash(f"Erreur : {err}", 'danger')
        finally:
            cursor.close()
            conn.close()
    
    return render_template('inventaires/ajouter.html')

@app.route('/inventaires/<int:id>')
@login_required
def details_inventaire(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    # Récupérer l'en-tête de l'inventaire
    cursor.execute('SELECT * FROM inventaires WHERE id_inventaires = %s AND user_id = %s', (id, user_id))
    inventaire = cursor.fetchone()
    
    if not inventaire:
        cursor.close()
        conn.close()
        return "Inventaire non trouvé", 404
    
    # Récupérer les détails de l'inventaire
    cursor.execute('''
        SELECT * FROM inventaire_details
        WHERE id_inventaires = %s
        ORDER BY date_inventaire DESC
    ''', (id,))
    details = cursor.fetchall()
    
    # Calculer les totaux
    cursor.execute('''
        SELECT COUNT(*) as nb_articles, SUM(quantite) as total_quantite, SUM(montant) as total_montant
        FROM inventaire_details
        WHERE id_inventaires = %s
    ''', (id,))
    stats = cursor.fetchone()
    
    cursor.close()
    conn.close()
    return render_template('inventaires/details.html', inventaire=inventaire, details=details, stats=stats)

@app.route('/inventaires/<int:id>/ajouter_produit', methods=['GET', 'POST'])
@login_required
def ajouter_produit_inventaire(id):
    if request.method == 'POST':
        nom_produit = request.form['nom_produit']
        quantite = request.form['quantite']
        prix_achat = request.form['prix_achat']
        montant = float(quantite) * float(prix_achat)
        user_id = session.get('user_id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO inventaire_details (nom_produit, quantite, prix_achat, montant, user_id, id_inventaires)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (nom_produit, quantite, prix_achat, montant, user_id, id))
            conn.commit()
            flash('Produit ajouté à l\'inventaire avec succès !', 'success')
        except mysql.connector.Error as err:
            flash(f"Erreur : {err}", 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('details_inventaire', id=id))
    
    return render_template('inventaires/ajouter_produit.html', id_inventaire=id)

@app.route('/inventaires/modifier_produit/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_produit_inventaire(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        nom_produit = request.form['nom_produit']
        quantite = request.form['quantite']
        prix_achat = request.form['prix_achat']
        montant = float(quantite) * float(prix_achat)
        
        cursor.execute('''
            UPDATE inventaire_details
            SET nom_produit=%s, quantite=%s, prix_achat=%s, montant=%s
            WHERE id_inventaire=%s AND user_id=%s
        ''', (nom_produit, quantite, prix_achat, montant, id, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Produit modifié avec succès !', 'success')
        
        # Récupérer l'id_inventaires pour rediriger
        return redirect(url_for('details_inventaire', id=request.form['id_inventaires']))
    
    cursor.execute('SELECT * FROM inventaire_details WHERE id_inventaire = %s AND user_id = %s', (id, user_id))
    detail = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if detail is None:
        return "Produit non trouvé", 404
        
    return render_template('inventaires/modifier_produit.html', detail=detail)

@app.route('/inventaires/supprimer_produit/<int:id>')
@login_required
def supprimer_produit_inventaire(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Récupérer l'id_inventaires avant suppression
    cursor.execute('SELECT id_inventaires FROM inventaire_details WHERE id_inventaire = %s', (id,))
    result = cursor.fetchone()
    id_inventaires = result['id_inventaires'] if result else None
    
    cursor.execute('DELETE FROM inventaire_details WHERE id_inventaire = %s AND user_id = %s', (id, session.get('user_id')))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Produit supprimé avec succès !', 'success')
    
    if id_inventaires:
        return redirect(url_for('details_inventaire', id=id_inventaires))
    return redirect(url_for('index_inventaires'))

@app.route('/inventaires/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_inventaire(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        reference = request.form['reference']
        titre = request.form['titre']
        date_inventaire = request.form['date_inventaire']
        
        cursor.execute('''
            UPDATE inventaires
            SET reference=%s, titre=%s, date_inventaire=%s
            WHERE id_inventaires=%s AND user_id=%s
        ''', (reference, titre, date_inventaire, id, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Inventaire modifié avec succès !', 'success')
        return redirect(url_for('details_inventaire', id=id))
    
    cursor.execute('SELECT * FROM inventaires WHERE id_inventaires = %s AND user_id = %s', (id, user_id))
    inventaire = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if inventaire is None:
        return "Inventaire non trouvé", 404
        
    return render_template('inventaires/modifier.html', inventaire=inventaire)

@app.route('/inventaires/<int:id>/valider')
@login_required
def valider_inventaire(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = session.get('user_id')
    
    try:
        # Récupérer le statut actuel
        cursor.execute('SELECT statut FROM inventaires WHERE id_inventaires = %s AND user_id = %s', (id, user_id))
        result = cursor.fetchone()
        
        if result:
            current_statut = result[0]
            # Inverser le statut
            new_statut = 'VALIDE' if current_statut == 'EN_COURS' else 'EN_COURS'
            
            cursor.execute('''
                UPDATE inventaires
                SET statut = %s
                WHERE id_inventaires = %s AND user_id = %s
            ''', (new_statut, id, user_id))
            conn.commit()
            flash(f"Inventaire {'validé' if new_statut == 'VALIDE' else 'dévalidé'} avec succès !", 'success')
    except mysql.connector.Error as err:
        flash(f"Erreur : {err}", 'danger')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('details_inventaire', id=id))

@app.route('/inventaires/supprimer/<int:id>')
@login_required
def supprimer_inventaire(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Supprimer d'abord les détails
    cursor.execute('DELETE FROM inventaire_details WHERE id_inventaires = %s AND user_id = %s', (id, session.get('user_id')))
    # Puis supprimer l'en-tête
    cursor.execute('DELETE FROM inventaires WHERE id_inventaires = %s AND user_id = %s', (id, session.get('user_id')))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Inventaire supprimé avec succès !', 'success')
    return redirect(url_for('index_inventaires'))

@app.route('/inventaires/rapport')
@login_required
def rapport_inventaires():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    # Statistiques générales sur tous les inventaires
    cursor.execute('''
        SELECT COUNT(*) as nb_inventaires, 
               (SELECT SUM(montant) FROM inventaire_details) as total_montant_global,
               (SELECT SUM(quantite) FROM inventaire_details) as total_quantite_global
        FROM inventaires
        WHERE user_id = %s
    ''', (user_id,))
    stats = cursor.fetchone()
    
    # Liste des inventaires avec leurs totaux
    cursor.execute('''
        SELECT i.*, 
               (SELECT COUNT(*) FROM inventaire_details WHERE id_inventaires = i.id_inventaires) as nb_articles,
               (SELECT SUM(montant) FROM inventaire_details WHERE id_inventaires = i.id_inventaires) as total_montant
        FROM inventaires i
        WHERE i.user_id = %s
        ORDER BY i.date_inventaire DESC
    ''', (user_id,))
    inventaires = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('inventaires/rapport.html', stats=stats, inventaires=inventaires)


# --- ROUTES CAISSES ---

@app.route('/caisses')
@login_required
def index_caisses():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    cursor.execute('''
        SELECT * FROM caisses
        WHERE user_id = %s
        ORDER BY date_creation DESC
    ''', (user_id,))
    caisses = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('caisses/index.html', caisses=caisses)

@app.route('/caisses/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_caisse():
    if request.method == 'POST':
        nom_caisse = request.form['nom_caisse']
        type_caisse = request.form['type_caisse']
        solde = request.form.get('solde', 0)
        user_id = session.get('user_id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO caisses (nom_caisse, type_caisse, solde, user_id)
                VALUES (%s, %s, %s, %s)
            ''', (nom_caisse, type_caisse, solde, user_id))
            conn.commit()
            flash('Caisse ajoutée avec succès !', 'success')
        except mysql.connector.Error as err:
            flash(f"Erreur : {err}", 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('index_caisses'))
    
    return render_template('caisses/ajouter.html')

@app.route('/caisses/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_caisse(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        nom_caisse = request.form['nom_caisse']
        type_caisse = request.form['type_caisse']
        solde = request.form.get('solde', 0)
        
        cursor.execute('''
            UPDATE caisses
            SET nom_caisse=%s, type_caisse=%s, solde=%s
            WHERE id_caisse=%s AND user_id=%s
        ''', (nom_caisse, type_caisse, solde, id, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Caisse modifiée avec succès !', 'success')
        return redirect(url_for('index_caisses'))
    
    cursor.execute('SELECT * FROM caisses WHERE id_caisse = %s AND user_id = %s', (id, user_id))
    caisse = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if caisse is None:
        return "Caisse non trouvée", 404
        
    return render_template('caisses/modifier.html', caisse=caisse)

@app.route('/caisses/supprimer/<int:id>')
@login_required
def supprimer_caisse(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = session.get('user_id')
    try:
        # Démarrer une transaction
        conn.start_transaction()
        
        # Supprimer d'abord les mouvements de caisse associés
        cursor.execute('DELETE FROM mouvements_caisse WHERE id_caisse = %s AND user_id = %s', (id, user_id))
        
        # Supprimer la caisse
        cursor.execute('DELETE FROM caisses WHERE id_caisse = %s AND user_id = %s', (id, user_id))
        
        conn.commit()
        flash('Caisse supprimée avec succès !', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Erreur lors de la suppression : {str(e)}', 'danger')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('index_caisses'))


# --- ROUTES MOUVEMENTS CAISSE ---

@app.route('/caisses/<int:id_caisse>/mouvements')
@login_required
def mouvements_caisse(id_caisse):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    # Récupérer la caisse
    cursor.execute('SELECT * FROM caisses WHERE id_caisse = %s AND user_id = %s', (id_caisse, user_id))
    caisse = cursor.fetchone()
    
    if caisse is None:
        cursor.close()
        conn.close()
        return "Caisse non trouvée", 404
    
    # Récupérer les mouvements
    cursor.execute('''
        SELECT * FROM mouvements_caisse
        WHERE id_caisse = %s
        ORDER BY date_mouvement DESC
        LIMIT 50
    ''', (id_caisse,))
    mouvements = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('caisses/mouvements.html', caisse=caisse, mouvements=mouvements)

@app.route('/caisses/<int:id_caisse>/mouvements/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_mouvement_caisse(id_caisse):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    # Récupérer la caisse
    cursor.execute('SELECT * FROM caisses WHERE id_caisse = %s AND user_id = %s', (id_caisse, user_id))
    caisse = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if caisse is None:
        return "Caisse non trouvée", 404
    
    if request.method == 'POST':
        type_mouvement = request.form['type_mouvement']
        montant = request.form['montant']
        motif = request.form.get('motif', '')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Ajouter le mouvement
            cursor.execute('''
                INSERT INTO mouvements_caisse (id_caisse, type_mouvement, montant, motif, user_id)
                VALUES (%s, %s, %s, %s, %s)
            ''', (id_caisse, type_mouvement, montant, motif, user_id))
            
            # Mettre à jour le solde de la caisse
            if type_mouvement == 'ENTREE':
                cursor.execute('UPDATE caisses SET solde = solde + %s WHERE id_caisse = %s', (montant, id_caisse))
            elif type_mouvement == 'SORTIE':
                cursor.execute('UPDATE caisses SET solde = solde - %s WHERE id_caisse = %s', (montant, id_caisse))
            
            conn.commit()
            flash('Mouvement ajouté avec succès !', 'success')
            return redirect(url_for('mouvements_caisse', id_caisse=id_caisse))
        except Exception as e:
            conn.rollback()
            flash(f"Erreur : {str(e)}", 'danger')
        finally:
            cursor.close()
            conn.close()
    
    return render_template('caisses/ajouter_mouvement.html', caisse=caisse)


@app.route('/caisses/<int:id_caisse>/mouvements/modifier/<int:id_mouvement>', methods=['GET', 'POST'])
@login_required
def modifier_mouvement_caisse(id_caisse, id_mouvement):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    # Récupérer la caisse
    cursor.execute('SELECT * FROM caisses WHERE id_caisse = %s AND user_id = %s', (id_caisse, user_id))
    caisse = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if caisse is None:
        return "Caisse non trouvée", 404
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Récupérer le mouvement
    cursor.execute('SELECT * FROM mouvements_caisse WHERE id_mouvement = %s AND id_caisse = %s', (id_mouvement, id_caisse))
    mouvement = cursor.fetchone()
    
    if mouvement is None:
        cursor.close()
        conn.close()
        return "Mouvement non trouvé", 404
    
    if request.method == 'POST':
        type_mouvement = request.form['type_mouvement']
        montant = request.form['montant']
        motif = request.form.get('motif', '')
        
        # Annuler l'ancien mouvement sur le solde
        ancien_type = mouvement['type_mouvement']
        ancien_montant = mouvement['montant']
        
        if ancien_type == 'ENTREE':
            cursor.execute('UPDATE caisses SET solde = solde - %s WHERE id_caisse = %s', (ancien_montant, id_caisse))
        elif ancien_type == 'SORTIE':
            cursor.execute('UPDATE caisses SET solde = solde + %s WHERE id_caisse = %s', (ancien_montant, id_caisse))
        
        # Appliquer le nouveau mouvement sur le solde
        if type_mouvement == 'ENTREE':
            cursor.execute('UPDATE caisses SET solde = solde + %s WHERE id_caisse = %s', (montant, id_caisse))
        elif type_mouvement == 'SORTIE':
            cursor.execute('UPDATE caisses SET solde = solde - %s WHERE id_caisse = %s', (montant, id_caisse))
        
        # Mettre à jour le mouvement
        cursor.execute('''
            UPDATE mouvements_caisse
            SET type_mouvement=%s, montant=%s, motif=%s
            WHERE id_mouvement=%s
        ''', (type_mouvement, montant, motif, id_mouvement))
        
        conn.commit()
        cursor.close()
        conn.close()
        flash('Mouvement modifié avec succès !', 'success')
        return redirect(url_for('mouvements_caisse', id_caisse=id_caisse))
    
    cursor.close()
    conn.close()
    
    return render_template('caisses/modifier_mouvement.html', caisse=caisse, mouvement=mouvement)


@app.route('/caisses/<int:id_caisse>/mouvements/supprimer/<int:id_mouvement>')
@login_required
def supprimer_mouvement_caisse(id_caisse, id_mouvement):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    # Récupérer le mouvement
    cursor.execute('SELECT * FROM mouvements_caisse WHERE id_mouvement = %s AND id_caisse = %s', (id_mouvement, id_caisse))
    mouvement = cursor.fetchone()
    
    if mouvement is None:
        cursor.close()
        conn.close()
        flash('Mouvement non trouvé', 'danger')
        return redirect(url_for('mouvements_caisse', id_caisse=id_caisse))
    
    # Annuler le mouvement sur le solde
    if mouvement['type_mouvement'] == 'ENTREE':
        cursor.execute('UPDATE caisses SET solde = solde - %s WHERE id_caisse = %s', (mouvement['montant'], id_caisse))
    elif mouvement['type_mouvement'] == 'SORTIE':
        cursor.execute('UPDATE caisses SET solde = solde + %s WHERE id_caisse = %s', (mouvement['montant'], id_caisse))
    
    # Supprimer le mouvement
    cursor.execute('DELETE FROM mouvements_caisse WHERE id_mouvement = %s', (id_mouvement,))
    
    conn.commit()
    cursor.close()
    conn.close()
    flash('Mouvement supprimé avec succès !', 'success')
    return redirect(url_for('mouvements_caisse', id_caisse=id_caisse))


# --- RAPPORT CAISSE ---

@app.route('/caisses/rapport')
@login_required
def rapport_caisses():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    # Statistiques générales
    cursor.execute('''
        SELECT COUNT(*) as nb_caisses, SUM(solde) as total_solde
        FROM caisses
        WHERE user_id = %s
    ''', (user_id,))
    stats = cursor.fetchone()
    
    # Liste des caisses avec leurs mouvements récents
    cursor.execute('''
        SELECT c.*, 
               (SELECT COUNT(*) FROM mouvements_caisse WHERE id_caisse = c.id_caisse) as nb_mouvements
        FROM caisses c
        WHERE c.user_id = %s
        ORDER BY c.date_creation DESC
    ''', (user_id,))
    caisses = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('caisses/rapport.html', stats=stats, caisses=caisses)


# --- MODULE COMPTABILITÉ ---

@app.route('/comptabilite')
@login_required
def index_comptabilite():
    """Page d'accueil du module comptabilité"""
    return render_template('comptabilite/index.html')


# --- GESTION DU PLAN COMPTABLE ---

@app.route('/comptabilite/plan_comptable')
@login_required
def index_plan_comptable():
    """Index du Plan Comptable"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute('SELECT * FROM plans_comptables ORDER BY numero_compte')
        comptes = cursor.fetchall()
        
        # S'assurer que numero_compte est une chaîne
        for compte in comptes:
            if compte['numero_compte']:
                compte['numero_compte'] = str(compte['numero_compte'])
        
        # Filtrer par classe pour les statistiques
        classe1 = [c for c in comptes if c['numero_compte'] and c['numero_compte'][0] == '1']
        classe2 = [c for c in comptes if c['numero_compte'] and c['numero_compte'][0] == '2']
        classe3 = [c for c in comptes if c['numero_compte'] and c['numero_compte'][0] == '3']
        classe4 = [c for c in comptes if c['numero_compte'] and c['numero_compte'][0] == '4']
        classe5 = [c for c in comptes if c['numero_compte'] and c['numero_compte'][0] == '5']
        classe6 = [c for c in comptes if c['numero_compte'] and c['numero_compte'][0] == '6']
        classe7 = [c for c in comptes if c['numero_compte'] and c['numero_compte'][0] == '7']
        
        cursor.close()
        conn.close()
        
        return render_template('comptabilite/plan_comptable/index.html', 
                              comptes=comptes,
                              classe1=classe1,
                              classe2=classe2,
                              classe3=classe3,
                              classe4=classe4,
                              classe5=classe5,
                              classe6=classe6,
                              classe7=classe7)
    except Exception as e:
        flash(f"Erreur lors du chargement du plan comptable : {str(e)}", 'danger')
        return render_template('comptabilite/plan_comptable/index.html', 
                              comptes=[],
                              classe1=[],
                              classe2=[],
                              classe3=[],
                              classe4=[],
                              classe5=[],
                              classe6=[],
                              classe7=[])


@app.route('/comptabilite/plan_comptable/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_compte():
    """Ajouter un compte au Plan Comptable"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        numero_compte = request.form.get('numero_compte')
        intitule = request.form.get('intitule')
        type_compte = request.form.get('type_compte')
        
        try:
            cursor.execute('''
                INSERT INTO plans_comptables (numero_compte, intitule, type_compte)
                VALUES (%s, %s, %s)
            ''', (numero_compte, intitule, type_compte))
            conn.commit()
            flash('Compte ajouté avec succès !', 'success')
            return redirect(url_for('index_plan_comptable'))
        except Exception as e:
            conn.rollback()
            flash(f"Erreur : {str(e)}", 'danger')
        finally:
            cursor.close()
            conn.close()
    
    cursor.close()
    conn.close()
    return render_template('comptabilite/plan_comptable/ajouter.html')


@app.route('/comptabilite/plan_comptable/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_compte(id):
    """Modifier un compte du Plan Comptable"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        numero_compte = request.form.get('numero_compte')
        intitule = request.form.get('intitule')
        type_compte = request.form.get('type_compte')
        
        try:
            cursor.execute('''
                UPDATE plans_comptables 
                SET numero_compte = %s, intitule = %s, type_compte = %s
                WHERE id = %s
            ''', (numero_compte, intitule, type_compte, id))
            conn.commit()
            flash('Compte modifié avec succès !', 'success')
            return redirect(url_for('index_plan_comptable'))
        except Exception as e:
            conn.rollback()
            flash(f"Erreur : {str(e)}", 'danger')
        finally:
            cursor.close()
            conn.close()
    
    cursor.execute('SELECT * FROM plans_comptables WHERE id = %s', (id,))
    compte = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if compte is None:
        flash('Compte non trouvé', 'danger')
        return redirect(url_for('index_plan_comptable'))
    
    return render_template('comptabilite/plan_comptable/modifier.html', compte=compte)


@app.route('/comptabilite/plan_comptable/supprimer/<int:id>')
@login_required
def supprimer_compte(id):
    """Supprimer un compte du Plan Comptable"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Vérifier si le compte est utilisé dans des écritures
        cursor.execute('SELECT COUNT(*) as count FROM lignes_ecritures WHERE compte_id = %s', (id,))
        count = cursor.fetchone()['count']
        
        if count > 0:
            flash('Impossible de supprimer ce compte car il est utilisé dans des écritures comptables.', 'danger')
        else:
            cursor.execute('DELETE FROM plans_comptables WHERE id = %s', (id,))
            conn.commit()
            flash('Compte supprimé avec succès !', 'success')
    except Exception as e:
        conn.rollback()
        flash(f"Erreur : {str(e)}", 'danger')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('index_plan_comptable'))


# --- GESTION DES ÉCRITURES COMPTABLES ---

@app.route('/comptabilite/ecritures')
@login_required
def index_ecritures():
    """Index des Écritures Comptables"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('''
        SELECT e.*, 
               (SELECT COUNT(*) FROM lignes_ecritures WHERE ecriture_id = e.id) as nb_lignes,
               (SELECT COALESCE(SUM(debit), 0) FROM lignes_ecritures WHERE ecriture_id = e.id) as total_debit,
               (SELECT COALESCE(SUM(credit), 0) FROM lignes_ecritures WHERE ecriture_id = e.id) as total_credit
        FROM ecritures_comptables e
        ORDER BY e.date_ecriture DESC, e.id DESC
    ''')
    ecritures = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('comptabilite/ecritures/index.html', ecritures=ecritures)


@app.route('/comptabilite/ecritures/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_ecriture():
    """Ajouter une écriture comptable"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if request.method == 'POST':
            date_ecriture = request.form.get('date_ecriture')
            libelle = request.form.get('libelle')
            comptes = request.form.getlist('compte_id[]')
            debits = request.form.getlist('debit[]')
            credits = request.form.getlist('credit[]')
            
            try:
                conn.start_transaction()
                
                # Créer l'écriture
                cursor.execute('''
                    INSERT INTO ecritures_comptables (date_ecriture, libelle)
                    VALUES (%s, %s)
                ''', (date_ecriture, libelle))
                id_ecriture = cursor.lastrowid
                
                # Ajouter les lignes
                for i in range(len(comptes)):
                    if comptes[i] and (debits[i] or credits[i]):
                        debit = float(debits[i]) if debits[i] else 0
                        credit = float(credits[i]) if credits[i] else 0
                        
                        if debit > 0 or credit > 0:
                            cursor.execute('''
                                INSERT INTO lignes_ecritures (ecriture_id, compte_id, debit, credit)
                                VALUES (%s, %s, %s, %s)
                            ''', (id_ecriture, comptes[i], debit, credit))
                
                conn.commit()
                flash('Écriture ajoutée avec succès !', 'success')
                return redirect(url_for('index_ecritures'))
            except Exception as e:
                conn.rollback()
                flash(f"Erreur : {str(e)}", 'danger')
            finally:
                cursor.close()
                conn.close()
        
        cursor.execute('SELECT * FROM plans_comptables ORDER BY numero_compte')
        comptes = cursor.fetchall()
        
        # S'assurer que numero_compte est une chaîne
        for compte in comptes:
            if compte['numero_compte']:
                compte['numero_compte'] = str(compte['numero_compte'])
        
        cursor.close()
        conn.close()
        return render_template('comptabilite/ecritures/ajouter.html', comptes=comptes)
    except Exception as e:
        flash(f"Erreur lors du chargement du formulaire : {str(e)}", 'danger')
        return render_template('comptabilite/ecritures/ajouter.html', comptes=[])


@app.route('/comptabilite/ecritures/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_ecriture(id):
    """Modifier une écriture comptable"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        date_ecriture = request.form.get('date_ecriture')
        libelle = request.form.get('libelle')
        comptes = request.form.getlist('compte_id[]')
        debits = request.form.getlist('debit[]')
        credits = request.form.getlist('credit[]')
        
        try:
            conn.start_transaction()
            
            # Supprimer les anciennes lignes
            cursor.execute('DELETE FROM lignes_ecritures WHERE ecriture_id = %s', (id,))
            
            # Mettre à jour l'écriture
            cursor.execute('''
                UPDATE ecritures_comptables 
                SET date_ecriture = %s, libelle = %s
                WHERE id = %s
            ''', (date_ecriture, libelle, id))
            
            # Ajouter les nouvelles lignes
            for i in range(len(comptes)):
                if comptes[i] and (debits[i] or credits[i]):
                    debit = float(debits[i]) if debits[i] else 0
                    credit = float(credits[i]) if credits[i] else 0
                    
                    if debit > 0 or credit > 0:
                        cursor.execute('''
                            INSERT INTO lignes_ecritures (ecriture_id, compte_id, debit, credit)
                            VALUES (%s, %s, %s, %s)
                        ''', (id, comptes[i], debit, credit))
            
            conn.commit()
            flash('Écriture modifiée avec succès !', 'success')
            return redirect(url_for('index_ecritures'))
        except Exception as e:
            conn.rollback()
            flash(f"Erreur : {str(e)}", 'danger')
        finally:
            cursor.close()
            conn.close()
    
    cursor.execute('SELECT * FROM ecritures_comptables WHERE id = %s', (id,))
    ecriture = cursor.fetchone()
    
    cursor.execute('SELECT * FROM lignes_ecritures WHERE ecriture_id = %s', (id,))
    lignes = cursor.fetchall()
    
    cursor.execute('SELECT * FROM plans_comptables ORDER BY numero_compte')
    comptes = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    if ecriture is None:
        flash('Écriture non trouvée', 'danger')
        return redirect(url_for('index_ecritures'))
    
    return render_template('comptabilite/ecritures/modifier.html', ecriture=ecriture, lignes=lignes, comptes=comptes)


@app.route('/comptabilite/ecritures/supprimer/<int:id>')
@login_required
def supprimer_ecriture(id):
    """Supprimer une écriture comptable"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Supprimer les lignes d'abord
        cursor.execute('DELETE FROM lignes_ecritures WHERE ecriture_id = %s', (id,))
        # Supprimer l'écriture
        cursor.execute('DELETE FROM ecritures_comptables WHERE id = %s', (id,))
        conn.commit()
        flash('Écriture supprimée avec succès !', 'success')
    except Exception as e:
        conn.rollback()
        flash(f"Erreur : {str(e)}", 'danger')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('index_ecritures'))


@app.route('/comptabilite/journal')
@login_required
def journal_comptable():
    """Journal Comptable - Affiche toutes les écritures par ordre chronologique"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    try:
        # Récupérer les filtres de date
        date_debut = request.args.get('date_debut')
        date_fin = request.args.get('date_fin')
        
        # Requête pour récupérer les écritures avec leurs lignes
        query = '''
            SELECT e.id, e.date_ecriture, e.libelle,
                   l.id as ligne_id, l.compte_id, l.debit, l.credit,
                   p.numero_compte, p.intitule, p.type_compte
            FROM ecritures_comptables e
            JOIN lignes_ecritures l ON e.id = l.ecriture_id
            JOIN plans_comptables p ON l.compte_id = p.id
            WHERE 1=1
        '''
        params = []
        
        if date_debut:
            query += ' AND e.date_ecriture >= %s'
            params.append(date_debut)
        if date_fin:
            query += ' AND e.date_ecriture <= %s'
            params.append(date_fin)
        
        query += ' ORDER BY e.date_ecriture, e.id'
        
        cursor.execute(query, params)
        ecritures = cursor.fetchall()
        
        # Calculer les totaux
        total_debit = sum(e['debit'] or 0 for e in ecritures)
        total_credit = sum(e['credit'] or 0 for e in ecritures)
        
        cursor.close()
        conn.close()
        
        return render_template('comptabilite/journal.html', 
                              ecritures=ecritures, 
                              total_debit=total_debit, 
                              total_credit=total_credit,
                              date_debut=date_debut,
                              date_fin=date_fin)
    except Exception as e:
        cursor.close()
        conn.close()
        flash(f"Erreur : {str(e)}", 'danger')
        return render_template('comptabilite/journal.html', 
                              ecritures=[], 
                              total_debit=0, 
                              total_credit=0,
                              date_debut=date_debut,
                              date_fin=date_fin)


@app.route('/comptabilite/grand_livre')
@login_required
def grand_livre():
    """Grand Livre - Regroupe les écritures par compte avec soldes progressifs"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    # Récupérer les filtres
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    classe = request.args.get('classe')
    
    # Récupérer les comptes avec filtre par classe si spécifié
    if classe:
        cursor.execute('SELECT * FROM plans_comptables WHERE numero_compte LIKE %s ORDER BY numero_compte', (f'{classe}%',))
    else:
        cursor.execute('SELECT * FROM plans_comptables ORDER BY numero_compte')
    comptes = cursor.fetchall()
    
    # Pour chaque compte, récupérer ses écritures
    grand_livre = []
    for compte in comptes:
        query = '''
            SELECT e.id, e.date_ecriture, e.libelle,
                   l.debit, l.credit
            FROM ecritures_comptables e
            JOIN lignes_ecritures l ON e.id = l.ecriture_id
            WHERE l.compte_id = %s
        '''
        params = [compte['id']]
        
        if date_debut:
            query += ' AND e.date_ecriture >= %s'
            params.append(date_debut)
        if date_fin:
            query += ' AND e.date_ecriture <= %s'
            params.append(date_fin)
        
        query += ' ORDER BY e.date_ecriture, e.id'
        
        cursor.execute(query, params)
        lignes = cursor.fetchall()
        
        if lignes:
            # Calculer le solde progressif
            solde = 0
            for ligne in lignes:
                solde += (ligne['debit'] or 0) - (ligne['credit'] or 0)
                ligne['solde'] = solde
            
            # Calculer le solde final
            total_debit = sum(l['debit'] or 0 for l in lignes)
            total_credit = sum(l['credit'] or 0 for l in lignes)
            solde_final = total_debit - total_credit
            
            grand_livre.append({
                'compte': compte,
                'lignes': lignes,
                'total_debit': total_debit,
                'total_credit': total_credit,
                'solde_final': solde_final
            })
    
    cursor.close()
    conn.close()
    
    return render_template('comptabilite/grand_livre.html', 
                          grand_livre=grand_livre,
                          date_debut=date_debut,
                          date_fin=date_fin,
                          classe=classe)


@app.route('/comptabilite/balance')
@login_required
def balance_generale():
    """Balance Générale - Affiche tous les comptes avec leurs totaux et soldes"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    try:
        # Récupérer les filtres
        date_debut = request.args.get('date_debut')
        date_fin = request.args.get('date_fin')
        classe = request.args.get('classe')
        
        # Récupérer tous les comptes avec leurs totaux
        query = '''
            SELECT p.id, p.numero_compte, p.intitule, p.type_compte,
                   COALESCE(SUM(l.debit), 0) as total_debit,
                   COALESCE(SUM(l.credit), 0) as total_credit
            FROM plans_comptables p
            LEFT JOIN lignes_ecritures l ON p.id = l.compte_id
            LEFT JOIN ecritures_comptables e ON l.ecriture_id = e.id
            WHERE 1=1
        '''
        params = []
        
        if classe:
            query += ' AND p.numero_compte LIKE %s'
            params.append(f'{classe}%')
        
        if date_debut:
            query += ' AND (e.date_ecriture IS NULL OR e.date_ecriture >= %s)'
            params.append(date_debut)
        if date_fin:
            query += ' AND (e.date_ecriture IS NULL OR e.date_ecriture <= %s)'
            params.append(date_fin)
        
        query += ' GROUP BY p.id ORDER BY p.numero_compte'
        
        cursor.execute(query, params)
        comptes = cursor.fetchall()
        
        # Calculer les soldes
        total_debit_general = 0
        total_credit_general = 0
        total_solde_debiteur = 0
        total_solde_crediteur = 0
        
        for compte in comptes:
            solde = compte['total_debit'] - compte['total_credit']
            if solde > 0:
                compte['solde_debiteur'] = solde
                compte['solde_crediteur'] = 0
                total_solde_debiteur += solde
            else:
                compte['solde_debiteur'] = 0
                compte['solde_crediteur'] = abs(solde)
                total_solde_crediteur += abs(solde)
            
            total_debit_general += compte['total_debit']
            total_credit_general += compte['total_credit']
        
        cursor.close()
        conn.close()
        
        return render_template('comptabilite/balance.html', 
                              comptes=comptes,
                              total_debit_general=total_debit_general,
                              total_credit_general=total_credit_general,
                              total_solde_debiteur=total_solde_debiteur,
                              total_solde_crediteur=total_solde_crediteur,
                              date_debut=date_debut,
                              date_fin=date_fin,
                              classe=classe)
    except Exception as e:
        cursor.close()
        conn.close()
        flash(f"Erreur : {str(e)}", 'danger')
        return render_template('comptabilite/balance.html', 
                              comptes=[],
                              total_debit_general=0,
                              total_credit_general=0,
                              total_solde_debiteur=0,
                              total_solde_crediteur=0,
                              date_debut=date_debut,
                              date_fin=date_fin)


@app.route('/comptabilite/bilan')
@login_required
def bilan_comptable():
    """Bilan Comptable - Sépare Actif et Passif"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    try:
        # Récupérer les filtres de date
        date_debut = request.args.get('date_debut')
        date_fin = request.args.get('date_fin')
        
        # Récupérer les comptes de l'Actif (type_compte = 'ACTIF')
        query_actif = '''
            SELECT p.id, p.numero_compte, p.intitule,
                   COALESCE(SUM(l.debit), 0) as total_debit,
                   COALESCE(SUM(l.credit), 0) as total_credit
            FROM plans_comptables p
            LEFT JOIN lignes_ecritures l ON p.id = l.compte_id
            LEFT JOIN ecritures_comptables e ON l.ecriture_id = e.id
            WHERE p.type_compte = 'ACTIF'
        '''
        params_actif = []
        
        if date_debut:
            query_actif += ' AND (e.date_ecriture IS NULL OR e.date_ecriture >= %s)'
            params_actif.append(date_debut)
        if date_fin:
            query_actif += ' AND (e.date_ecriture IS NULL OR e.date_ecriture <= %s)'
            params_actif.append(date_fin)
        
        query_actif += ' GROUP BY p.id ORDER BY p.numero_compte'
        
        cursor.execute(query_actif, params_actif)
        actif = cursor.fetchall()
        
        # Récupérer les comptes du Passif (type_compte = 'PASSIF')
        query_passif = '''
            SELECT p.id, p.numero_compte, p.intitule,
                   COALESCE(SUM(l.debit), 0) as total_debit,
                   COALESCE(SUM(l.credit), 0) as total_credit
            FROM plans_comptables p
            LEFT JOIN lignes_ecritures l ON p.id = l.compte_id
            LEFT JOIN ecritures_comptables e ON l.ecriture_id = e.id
            WHERE p.type_compte = 'PASSIF'
        '''
        params_passif = []
        
        if date_debut:
            query_passif += ' AND (e.date_ecriture IS NULL OR e.date_ecriture >= %s)'
            params_passif.append(date_debut)
        if date_fin:
            query_passif += ' AND (e.date_ecriture IS NULL OR e.date_ecriture <= %s)'
            params_passif.append(date_fin)
        
        query_passif += ' GROUP BY p.id ORDER BY p.numero_compte'
        
        cursor.execute(query_passif, params_passif)
        passif = cursor.fetchall()
        
        # Calculer les totaux
        total_actif = 0
        for compte in actif:
            solde = compte['total_debit'] - compte['total_credit']
            compte['solde'] = solde
            total_actif += solde
        
        total_passif = 0
        for compte in passif:
            solde = compte['total_credit'] - compte['total_debit']
            compte['solde'] = solde
            total_passif += solde
        
        cursor.close()
        conn.close()
        
        return render_template('comptabilite/bilan.html', 
                              actif=actif,
                              passif=passif,
                              total_actif=total_actif,
                              total_passif=total_passif,
                              date_debut=date_debut,
                              date_fin=date_fin)
    except Exception as e:
        cursor.close()
        conn.close()
        flash(f"Erreur : {str(e)}", 'danger')
        return render_template('comptabilite/bilan.html', 
                              actif=[],
                              passif=[],
                              total_actif=0,
                              total_passif=0,
                              date_debut=date_debut,
                              date_fin=date_fin)


@app.route('/comptabilite/compte_resultat')
@login_required
def compte_resultat():
    """Compte de Résultat - Structure hiérarchique avec calculs intermédiaires"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    # Récupérer les filtres de date
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    
    # Fonction pour classifier les comptes selon leur numéro
    def classifier_compte(numero_compte):
        """Classifie un compte selon son numéro (SYSCOHADA)"""
        try:
            num = int(numero_compte.split('.')[0]) if '.' in numero_compte else int(numero_compte)
        except:
            return 'AUTRE'
        
        # Classe 7: Produits (SYSCOHADA Afrique de l'Ouest)
        # Chiffre d'affaires : comptes 701 à 707 (ventes)
        if 701 <= num <= 707:
            return 'CHIFFRE_AFFAIRES'
        elif 72 <= num < 75:
            return 'AUTRE_PRODUIT'  # Autres produits d'exploitation
        elif 75 <= num < 78:
            return 'AUTRE_PRODUIT'  # Produits financiers
        elif 78 <= num < 79:
            return 'AUTRE_PRODUIT'  # Produits exceptionnels
        # Classe 6: Charges
        elif 60 <= num < 61:
            return 'CHARGE_VARIABLE'  # Achats consommés
        elif 61 <= num < 62:
            return 'CHARGE_VARIABLE'  # Services extérieurs
        elif 62 <= num < 63:
            return 'CHARGE_FIXE'  # Autres services
        elif 63 <= num < 64:
            return 'CHARGE_FIXE'  # Charges de personnel
        elif 64 <= num < 65:
            return 'IMPOT'  # Impôts et taxes
        elif 65 <= num < 66:
            return 'CHARGE_FIXE'  # Autres charges d'exploitation
        elif 66 <= num < 67:
            return 'CHARGE_FINANCIERE'  # Charges financières
        elif 67 <= num < 68:
            return 'CHARGE_FIXE'  # Charges exceptionnelles
        elif 68 <= num < 69:
            return 'CHARGE_FIXE'  # Dotations aux amortissements
        else:
            return 'AUTRE'
    
    # Récupérer tous les comptes avec leurs soldes
    query = '''
        SELECT p.id, p.numero_compte, p.intitule, p.type_compte,
               COALESCE(SUM(l.debit), 0) as total_debit,
               COALESCE(SUM(l.credit), 0) as total_credit
        FROM plans_comptables p
        LEFT JOIN lignes_ecritures l ON p.id = l.compte_id
        LEFT JOIN ecritures_comptables e ON l.ecriture_id = e.id
        WHERE p.type_compte IN ('PRODUIT', 'CHARGE')
    '''
    params = []
    
    if date_debut:
        query += ' AND (e.date_ecriture IS NULL OR e.date_ecriture >= %s)'
        params.append(date_debut)
    if date_fin:
        query += ' AND (e.date_ecriture IS NULL OR e.date_ecriture <= %s)'
        params.append(date_fin)
    
    query += ' GROUP BY p.id ORDER BY p.numero_compte'
    
    cursor.execute(query, params)
    comptes = cursor.fetchall()
    
    # Classifier les comptes et calculer les soldes
    chiffre_affaires_comptes = []
    charges_variables = []
    charges_fixes = []
    charges_financieres = []
    impots = []
    autres_charges = []
    autres_produits = []
    
    chiffre_affaires = 0
    total_charges_variables = 0
    total_charges_fixes = 0
    total_charges_financieres = 0
    total_impots = 0
    total_autres_charges = 0
    total_autres_produits = 0
    
    for compte in comptes:
        classification = classifier_compte(compte['numero_compte'])
        
        if compte['type_compte'] == 'PRODUIT':
            solde = compte['total_credit'] - compte['total_debit']
        else:
            solde = compte['total_debit'] - compte['total_credit']
        
        compte['solde'] = solde
        
        if classification == 'CHIFFRE_AFFAIRES':
            chiffre_affaires_comptes.append(compte)
            chiffre_affaires += solde
        elif classification == 'CHARGE_VARIABLE':
            charges_variables.append(compte)
            total_charges_variables += solde
        elif classification == 'CHARGE_FIXE':
            charges_fixes.append(compte)
            total_charges_fixes += solde
        elif classification == 'CHARGE_FINANCIERE':
            charges_financieres.append(compte)
            total_charges_financieres += solde
        elif classification == 'IMPOT':
            impots.append(compte)
            total_impots += solde
        elif classification == 'AUTRE' and compte['type_compte'] == 'CHARGE':
            autres_charges.append(compte)
            total_autres_charges += solde
        elif classification == 'AUTRE_PRODUIT' or (classification == 'AUTRE' and compte['type_compte'] == 'PRODUIT'):
            autres_produits.append(compte)
            total_autres_produits += solde
    
    # Ajouter les autres charges aux charges fixes
    total_charges_fixes += total_autres_charges
    charges_fixes.extend(autres_charges)
    
    # Ajouter les autres produits au chiffre d'affaires
    chiffre_affaires += total_autres_produits
    chiffre_affaires_comptes.extend(autres_produits)
    
    # Calculer les résultats intermédiaires
    marge_brute = chiffre_affaires - total_charges_variables
    resultat_exploitation = marge_brute - total_charges_fixes
    resultat_avant_impot = resultat_exploitation - total_charges_financieres
    resultat_net = resultat_avant_impot - total_impots
    
    cursor.close()
    conn.close()
    
    return render_template('comptabilite/compte_resultat.html', 
                          chiffre_affaires=chiffre_affaires,
                          chiffre_affaires_comptes=chiffre_affaires_comptes,
                          charges_variables=charges_variables,
                          total_charges_variables=total_charges_variables,
                          marge_brute=marge_brute,
                          charges_fixes=charges_fixes,
                          total_charges_fixes=total_charges_fixes,
                          resultat_exploitation=resultat_exploitation,
                          charges_financieres=charges_financieres,
                          total_charges_financieres=total_charges_financieres,
                          resultat_avant_impot=resultat_avant_impot,
                          impots=impots,
                          resultat_net=resultat_net,
                          date_debut=date_debut,
                          date_fin=date_fin)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
