from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
from config import Config
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config.from_object(Config)

# Secret



app.secret_key = "iug2026"

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
            flash("Vous n'avez pas l'autorisation d'accéder à cette page.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

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
        if user and check_password_hash(user['mot_de_passe'], password):
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
    boutique_id = session.get('user_id')
    
    # Statistiques
    cursor.execute('SELECT COUNT(*) as nb_produits FROM produits WHERE user_id = %s', (boutique_id,))
    nb_produits = cursor.fetchone()['nb_produits']
    
    cursor.execute('SELECT COUNT(*) as nb_clients FROM clients WHERE user_id = %s', (boutique_id,))
    nb_clients = cursor.fetchone()['nb_clients']
    
    cursor.execute('SELECT COUNT(*) as nb_fournisseurs FROM fournisseurs WHERE user_id = %s', (boutique_id,))
    nb_fournisseurs = cursor.fetchone()['nb_fournisseurs']
    
    cursor.execute('SELECT SUM(total) as ca FROM ventes WHERE user_id = %s', (boutique_id,))
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
    ''', (boutique_id,))
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
        boutique_id = session.get('user_id')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO produits (nom_produit, prix_achat, prix_vente, quantite_stock, user_id)
                VALUES (%s, %s, %s, %s, %s)
            ''', (nom_produit, prix_achat, prix_vente, quantite_stock, boutique_id))
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
    boutique_id = session.get('user_id')
    
    if request.method == 'POST':
        nom_produit = request.form['nom_produit']
        prix_achat = request.form['prix_achat']
        prix_vente = request.form['prix_vente']
        quantite_stock = request.form['quantite_stock']

        cursor.execute('''
            UPDATE produits
            SET nom_produit=%s, prix_achat=%s, prix_vente=%s, quantite_stock=%s
            WHERE id_produit=%s AND user_id=%s
        ''', (nom_produit, prix_achat, prix_vente, quantite_stock, id, boutique_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Produit modifié avec succès !', 'success')
        return redirect(url_for('index_produits'))

    cursor.execute('SELECT * FROM produits WHERE id_produit = %s AND user_id = %s', (id, boutique_id))
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
        email = request.form['email']
        adresse = request.form['adresse']
        boutique_id = session.get('user_id')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO clients (nom, prenom, telephone, email, adresse, user_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (nom, prenom, telephone, email, adresse, boutique_id))
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
    boutique_id = session.get('user_id')
    
    if request.method == 'POST':
        nom = request.form['nom']
        prenom = request.form['prenom']
        telephone = request.form['telephone']
        email = request.form['email']
        adresse = request.form['adresse']

        cursor.execute('''
            UPDATE clients
            SET nom=%s, prenom=%s, telephone=%s, email=%s, adresse=%s
            WHERE id_client=%s AND user_id=%s
        ''', (nom, prenom, telephone, email, adresse, id, boutique_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Client modifié avec succès !', 'success')
        return redirect(url_for('index_clients'))

    cursor.execute('SELECT * FROM clients WHERE id_client = %s AND user_id = %s', (id, boutique_id))
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
        email = request.form['email']
        adresse = request.form['adresse']
        boutique_id = session.get('user_id')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO fournisseurs (nom_fournisseur, telephone, email, adresse, user_id)
                VALUES (%s, %s, %s, %s, %s)
            ''', (nom_fournisseur, telephone, email, adresse, boutique_id))
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
    boutique_id = session.get('user_id')
    
    if request.method == 'POST':
        nom_fournisseur = request.form['nom_fournisseur']
        telephone = request.form['telephone']
        email = request.form['email']
        adresse = request.form['adresse']

        cursor.execute('''
            UPDATE fournisseurs
            SET nom_fournisseur=%s, telephone=%s, email=%s, adresse=%s
            WHERE id_fournisseur=%s AND user_id=%s
        ''', (nom_fournisseur, telephone, email, adresse, id, boutique_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Fournisseur modifié avec succès !', 'success')
        return redirect(url_for('index_fournisseurs'))

    cursor.execute('SELECT * FROM fournisseurs WHERE id_fournisseur = %s AND user_id = %s', (id, boutique_id))
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


# --- ROUTES VENTES & FACTURES ---

@app.route('/ventes')
@login_required
def index_ventes():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    boutique_id = session.get('user_id')
    cursor.execute('''
        SELECT v.*, c.nom as nom_client, c.prenom as prenom_client 
        FROM ventes v 
        JOIN clients c ON v.id_client = c.id_client
        WHERE v.user_id = %s
        ORDER BY v.date_vente DESC
    ''', (boutique_id,))
    ventes = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('ventes/index.html', ventes=ventes)

@app.route('/ventes/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_vente():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    boutique_id = session.get('user_id')

    if request.method == 'POST':
        id_client = request.form['id_client']
        produits_ids = request.form.getlist('produits[]')
        quantites = request.form.getlist('quantites[]')
        
        try:
            # Démarrer une transaction
            conn.start_transaction()
            
            total_vente = 0
            # 1. Créer la vente avec AUTO_INCREMENT
            cursor.execute('INSERT INTO ventes (id_client, total, user_id) VALUES (%s, %s, %s)', (id_client, 0, boutique_id))
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
                ''', (qty, p_id, boutique_id))
            
            # 3. Mettre à jour le total de la vente
            cursor.execute('UPDATE ventes SET total = %s WHERE id_vente = %s AND user_id = %s', (total_vente, id_vente, boutique_id))
            
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
    cursor.execute('SELECT * FROM clients WHERE user_id = %s', (boutique_id,))
    clients = cursor.fetchall()
    cursor.execute('SELECT * FROM produits WHERE quantite_stock > 0 AND user_id = %s', (boutique_id,))
    produits = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('ventes/ajouter.html', clients=clients, produits=produits)

@app.route('/ventes/facture/<int:id>')
@login_required
def facture(id):

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    boutique_id = session.get('user_id')
    
    # Récupérer les infos de la vente
    cursor.execute('''
        SELECT v.*, c.nom as nom_client, c.prenom as prenom_client, c.telephone, c.email, c.adresse
        FROM ventes v 
        JOIN clients c ON v.id_client = c.id_client
        WHERE v.id_vente = %s AND v.user_id = %s
    ''', (id, boutique_id))
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
    boutique_id = session.get('user_id')
    
    try:
        # 1. Chiffre d'Affaire (CA)
        cursor.execute('SELECT SUM(total) as ca FROM ventes WHERE user_id = %s', (boutique_id,))
        res_ca = cursor.fetchone()
        total_ventes = res_ca['ca'] if res_ca['ca'] else 0
        
        # 2. Coût des Achats (Basé sur les ventes - COGS)
        cursor.execute('''
            SELECT SUM(lv.quantite * p.prix_achat) as total_cout
            FROM lignes_vente lv
            JOIN produits p ON lv.id_produit = p.id_produit
            JOIN ventes v ON lv.id_vente = v.id_vente
            WHERE v.user_id = %s
        ''', (boutique_id,))
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
        ''', (boutique_id,))
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
    cursor.execute('SELECT id, nom, username, role FROM utilisateurs WHERE boutique_id = %s', (session.get('user_id'),))
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
                INSERT INTO utilisateurs (nom, username, mot_de_passe, role, boutique_id)
                VALUES (%s, %s, %s, %s, %s)
            ''', (nom, username, hashed_password, role, session.get('user_id')))
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
                WHERE id=%s AND boutique_id=%s
            ''', (nom, username, role, id, session.get('user_id')))
        else:
            hashed_password = generate_password_hash(password)
            cursor.execute('''
                UPDATE utilisateurs
                SET nom=%s, username=%s, mot_de_passe=%s, role=%s
                WHERE id=%s AND boutique_id=%s
            ''', (nom, username, hashed_password, role, id, session.get('user_id')))
            
        conn.commit()
        cursor.close()
        conn.close()
        flash('Utilisateur modifié avec succès !', 'success')
        return redirect(url_for('index_utilisateurs'))

    cursor.execute('SELECT id, nom, username, role FROM utilisateurs WHERE id = %s AND boutique_id = %s', (id, session.get('user_id')))
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
    cursor.execute('DELETE FROM utilisateurs WHERE id = %s AND boutique_id = %s', (id, session.get('user_id')))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Utilisateur supprimé avec succès !', 'success')
    return redirect(url_for('index_utilisateurs'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
