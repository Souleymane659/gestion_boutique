from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
from config import Config
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config.from_object(Config)

# Secret



app.secret_key = "iug2026"

# Configuration pour l'upload de fichiers
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
    if 'logged_in' in session:
        return dict(get_parametres=get_parametres)
    return dict(get_parametres=lambda: None)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM utilisateurs WHERE username = %s', (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        # Authentification avec hachage
        if user and check_password_hash(user['password'], password):
            session['logged_in'] = True
            session['username'] = user['username']
            session['role'] = user['role']
            session['nom'] = user['nom']
            session['user_id'] = user['id']
            
            flash(f"Bienvenue {user['nom']} !", 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Identifiants incorrects.', 'danger')
            
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
    cursor.execute('DELETE FROM produits WHERE id_produit = %s AND user_id = %s', (id, session.get('user_id')))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Produit supprimé avec succès !', 'success')
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
    cursor.execute('DELETE FROM clients WHERE id_client = %s AND user_id = %s', (id, session.get('user_id')))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Client supprimé avec succès !', 'success')
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
    cursor.execute('DELETE FROM fournisseurs WHERE id_fournisseur = %s AND user_id = %s', (id, session.get('user_id')))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Fournisseur supprimé avec succès !', 'success')
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
    cursor.execute('DELETE FROM stocks WHERE id_stock = %s', (id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Stock supprimé avec succès !', 'success')
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
        
        # Gestion de l'upload du logo
        logo = None
        if 'logo' in request.files:
            file = request.files['logo']
            if file and file.filename != '' and allowed_file(file.filename):
                # Créer le dossier d'upload s'il n'existe pas
                if not os.path.exists(app.config['UPLOAD_FOLDER']):
                    os.makedirs(app.config['UPLOAD_FOLDER'])
                
                filename = secure_filename(file.filename)
                # Ajouter un timestamp pour éviter les doublons
                import time
                timestamp = str(int(time.time()))
                filename = f"{timestamp}_{filename}"
                
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                logo = f"/static/uploads/{filename}"
        
        try:
            cursor.execute('SELECT * FROM parametres WHERE user_id = %s', (user_id,))
            parametres = cursor.fetchone()
            
            if parametres:
                # Si un nouveau logo est uploadé, l'utiliser, sinon garder l'ancien
                logo_to_save = logo if logo else parametres.get('logo')
                cursor.execute('''
                    UPDATE parametres 
                    SET nom_boutique = %s, logo = %s, telephone = %s, email = %s, adresse = %s, devise = %s, slogan = %s
                    WHERE user_id = %s
                ''', (nom_boutique, logo_to_save, telephone, email, adresse, devise, slogan, user_id))
            else:
                cursor.execute('''
                    INSERT INTO parametres (nom_boutique, logo, telephone, email, adresse, devise, slogan, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (nom_boutique, logo, telephone, email, adresse, devise, slogan, user_id))
            
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
        id_client = request.form['id_client']
        produits_ids = request.form.getlist('produits[]')
        quantites = request.form.getlist('quantites[]')
        
        try:
            # Démarrer une transaction
            conn.start_transaction()
            
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
    
    # Récupérer les infos de la vente
    cursor.execute('''
        SELECT v.*, c.nom as nom_client, c.prenom as prenom_client, c.telephone, c.adresse
        FROM ventes v 
        JOIN clients c ON v.id_client = c.id_client
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
    
    cursor.close()
    conn.close()
    return render_template('ventes/facture.html', vente=vente, lignes=lignes)


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
    
    cursor.execute('''
        SELECT * FROM inventaires
        WHERE user_id = %s
        ORDER BY date_inventaire DESC
    ''', (user_id,))
    inventaires = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('inventaires/index.html', inventaires=inventaires)

@app.route('/inventaires/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_inventaire():
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
                INSERT INTO inventaires (nom_produit, quantite, prix_achat, montant, user_id)
                VALUES (%s, %s, %s, %s, %s)
            ''', (nom_produit, quantite, prix_achat, montant, user_id))
            conn.commit()
            flash('Inventaire ajouté avec succès !', 'success')
        except mysql.connector.Error as err:
            flash(f"Erreur : {err}", 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('index_inventaires'))
    
    return render_template('inventaires/ajouter.html')

@app.route('/inventaires/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_inventaire(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        nom_produit = request.form['nom_produit']
        quantite = request.form['quantite']
        prix_achat = request.form['prix_achat']
        montant = float(quantite) * float(prix_achat)
        
        cursor.execute('''
            UPDATE inventaires
            SET nom_produit=%s, quantite=%s, prix_achat=%s, montant=%s
            WHERE id_inventaire=%s AND user_id=%s
        ''', (nom_produit, quantite, prix_achat, montant, id, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Inventaire modifié avec succès !', 'success')
        return redirect(url_for('index_inventaires'))
    
    cursor.execute('SELECT * FROM inventaires WHERE id_inventaire = %s AND user_id = %s', (id, user_id))
    inventaire = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if inventaire is None:
        return "Inventaire non trouvé", 404
        
    return render_template('inventaires/modifier.html', inventaire=inventaire)

@app.route('/inventaires/supprimer/<int:id>')
@login_required
def supprimer_inventaire(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM inventaires WHERE id_inventaire = %s AND user_id = %s', (id, session.get('user_id')))
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
    
    # Statistiques générales
    cursor.execute('''
        SELECT COUNT(*) as nb_articles, SUM(quantite) as total_quantite, SUM(montant) as total_montant
        FROM inventaires
        WHERE user_id = %s
    ''', (user_id,))
    stats = cursor.fetchone()
    
    # Liste des inventaires
    cursor.execute('''
        SELECT * FROM inventaires
        WHERE user_id = %s
        ORDER BY date_inventaire DESC
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
    cursor.execute('DELETE FROM caisses WHERE id_caisse = %s AND user_id = %s', (id, session.get('user_id')))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Caisse supprimée avec succès !', 'success')
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
