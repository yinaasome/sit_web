import streamlit as st
from streamlit_javascript import st_javascript
import pymongo
from pymongo import MongoClient
import uuid
import random
import pandas as pd
import os
import altair as alt
from textblob import TextBlob
import numpy as np
from datetime import datetime, timedelta
import time
from PIL import Image
import base64

# 🛠️ Configuration de la page
st.set_page_config(page_title="Wiki Survey", layout="wide", page_icon="🗳️")

# === Configuration MongoDB ===
DB_TOKEN = st.secrets["DB_TOKEN"]
DB_NAME = "Africa"

# --- Connexion à MongoDB ---
@st.cache_resource
def get_db_connection():
    """Obtenir une connexion à MongoDB"""
    try:
        client = MongoClient(DB_TOKEN)
        db = client[DB_NAME]
        return db
    except Exception as e:
        st.error(f"Erreur de connexion à MongoDB: {e}")
        return None

# === Création des collections et index ===
def init_database():
    """Initialiser la structure de la base MongoDB"""
    try:
        db = get_db_connection()

        # Créer les collections si elles n'existent pas
        collections = [
            "navigateur", "login", "question",
            "idees", "vote", "commentaire",
            "profil", "sentiment_analytics"
        ]

        for collection in collections:
            if collection not in db.list_collection_names():
                db.create_collection(collection)

        # Créer les index
        db.login.create_index("email", unique=True)
        db.idees.create_index("id_question")
        db.vote.create_index([("id_navigateur", 1), ("id_question", 1)], unique=True)
        db.profil.create_index("id_navigateur", unique=True)
        db.sentiment_analytics.create_index("id_question", unique=True)

        # Insérer des données de test (administrateur et utilisateur avec droit d'image)
        # ATTENTION: Dans une application réelle, le mot de passe ne devrait pas être stocké en clair.
        # Utilisez une bibliothèque de hachage comme `bcrypt` pour plus de sécurité.
        db.login.update_one(
            {"email": "admin@test.com"},
            {"$set": {
                "email": "admin@test.com",
                "mot_de_passe": "admin123", # Mot de passe de démonstration
                "date_creation": datetime.now()
            }},
            upsert=True
        )
        
        # AJOUT DE L'UTILISATEUR "yinnaasome@gmail.com" AVEC LE DROIT D'IMAGE
        db.login.update_one(
            {"email": "yinnaasome@gmail.com"},
            {"$set": {
                "email": "yinnaasome@gmail.com",
                "mot_de_passe": "abc", # Mot de passe de démonstration
                "date_creation": datetime.now()
            }},
            upsert=True
        )

        print("✅ Base MongoDB initialisée avec succès")
        return True

    except Exception as e:
        print(f"❌ Erreur initialisation MongoDB: {e}")
        return False

# === Analyse de sentiment ===
def analyze_sentiment(text):
    """Analyser le sentiment d'un texte avec TextBlob"""
    try:
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity

        if polarity > 0.1:
            label = "Positif"
        elif polarity < -0.1:
            label = "Négatif"
        else:
            label = "Neutre"

        return polarity, label
    except:
        return 0.0, "Neutre"

def update_sentiment_analytics(question_id):
    """Mettre à jour les analytics de sentiment pour une question"""
    try:
        db = get_db_connection()

        # Calculer les stats pour les idées
        idees_stats_cursor = db.idees.aggregate([
            {"$match": {"id_question": question_id}},
            {"$group": {
                "_id": None,
                "avg_sentiment": {"$avg": "$sentiment_score"},
                "positifs": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Positif"]}, 1, 0]}},
                "negatifs": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Négatif"]}, 1, 0]}},
                "neutres": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Neutre"]}, 1, 0]}}
            }}
        ])
        idees_stats = next(idees_stats_cursor, {})

        # Calculer les stats pour les commentaires
        commentaires_stats_cursor = db.commentaire.aggregate([
            {"$match": {"id_question": question_id}},
            {"$group": {
                "_id": None,
                "avg_sentiment": {"$avg": "$sentiment_score"},
                "positifs": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Positif"]}, 1, 0]}},
                "negatifs": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Négatif"]}, 1, 0]}},
                "neutres": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Neutre"]}, 1, 0]}}
            }}
        ])
        commentaires_stats = next(commentaires_stats_cursor, {})

        # Insérer ou mettre à jour les analytics
        db.sentiment_analytics.update_one(
            {"id_question": question_id},
            {"$set": {
                "moyenne_sentiment_idees": idees_stats.get("avg_sentiment", 0),
                "moyenne_sentiment_commentaires": commentaires_stats.get("avg_sentiment", 0),
                "total_idees_positives": idees_stats.get("positifs", 0),
                "total_idees_negatives": idees_stats.get("negatifs", 0),
                "total_idees_neutres": idees_stats.get("neutres", 0),
                "total_commentaires_positifs": commentaires_stats.get("positifs", 0),
                "total_commentaires_negatifs": commentaires_stats.get("negatifs", 0),
                "total_commentaires_neutres": commentaires_stats.get("neutres", 0),
                "derniere_mise_a_jour": datetime.now()
            }},
            upsert=True
        )

    except Exception as e:
        st.error(f"Erreur mise à jour analytics: {e}")

# Initialisation de la base
if not init_database():
    st.error("❌ Erreur initialisation MongoDB")
    st.stop()

# Initialiser les clés nécessaires dans session_state
if "page" not in st.session_state:
    st.session_state["page"] = "home"

if "id_navigateur" not in st.session_state:
    st.session_state["id_navigateur"] = None

if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = False

if "auth" not in st.session_state:
    st.session_state.auth = False

if "utilisateur_id" not in st.session_state:
    st.session_state.utilisateur_id = None

if "email" not in st.session_state:
    st.session_state.email = None

# --- ID navigateur ---
def get_navigateur_id():
    js_code = """
        const existing = localStorage.getItem("id_navigateur");
        if (existing) {
            existing;
        } else {
            const newId = crypto.randomUUID();
            localStorage.setItem("id_navigateur", newId);
            newId;
        }
    """
    return st_javascript(js_code)

def detect_navigateur():
    js_code = "navigator.userAgent;"
    agent = st_javascript(js_code)
    if agent:
        if "Chrome" in agent and "Edg" not in agent:
            return "Chrome"
        elif "Firefox" in agent:
            return "Firefox"
        elif "Edg" in agent:
            return "Edge"
        elif "Safari" in agent and "Chrome" not in agent:
            return "Safari"
    return "Inconnu"

def init_navigateur():
    if not st.session_state["id_navigateur"]:
        id_navigateur = get_navigateur_id()
        if id_navigateur and len(id_navigateur) > 100:
            id_navigateur = id_navigateur[:100]  # Tronquer si nécessaire
        navigateur_nom = detect_navigateur()
        if id_navigateur:
            st.session_state["id_navigateur"] = id_navigateur
            db = get_db_connection()
            db.navigateur.update_one(
                {"id_navigateur": id_navigateur},
                {"$set": {
                    "id_navigateur": id_navigateur,
                    "navigateur": navigateur_nom,
                    "date_creation": datetime.now()
                }},
                upsert=True
            )

# Appel obligatoire
init_navigateur()

# =============================================================
# === FONCTIONS D'AUTHENTIFICATION (DÉPLACÉES EN HAUT) ===
# =============================================================

def creer_compte():
    """Page de création de compte pour les nouveaux utilisateurs."""
    st.subheader("Créez votre compte pour proposer une question")
    db = get_db_connection()

    email_reg = st.text_input("Email", key="email_reg")
    mot_de_passe_reg = st.text_input("Mot de passe", type="password", key="pass_reg")
    mot_de_passe_conf = st.text_input("Confirmer le mot de passe", type="password", key="pass_conf")

    if st.button("Créer le compte"):
        if not email_reg or not mot_de_passe_reg or not mot_de_passe_conf:
            st.error("Veuillez remplir tous les champs.")
            return

        if mot_de_passe_reg != mot_de_passe_conf:
            st.error("Les mots de passe ne correspondent pas.")
            return

        # Vérifier si l'email existe déjà
        if db.login.find_one({"email": email_reg}):
            st.error("Cet email est déjà utilisé. Veuillez vous connecter.")
            return

        # Enregistrer le nouvel utilisateur
        nouvel_utilisateur = {
            "email": email_reg,
            "mot_de_passe": mot_de_passe_reg,
            "date_creation": datetime.now()
        }
        user_id = db.login.insert_one(nouvel_utilisateur).inserted_id

        # Connexion automatique après la création
        st.session_state.auth = True
        st.session_state.utilisateur_id = str(user_id)
        st.session_state.email = email_reg
        st.success(f"✅ Compte créé et connexion réussie ! Bienvenue {st.session_state.email} !")
        st.rerun()

def login_page():
    """Interface de connexion pour les utilisateurs existants."""
    st.subheader("Connectez-vous pour proposer une question")
    db = get_db_connection()
    email = st.text_input("Email", key="email_login")
    mot_de_passe = st.text_input("Mot de passe", type="password", key="pass_login")

    if st.button("Se connecter"):
        utilisateur = db.login.find_one({
            "email": email,
            "mot_de_passe": mot_de_passe
        })

        if utilisateur:
            st.session_state.auth = True
            st.session_state.utilisateur_id = str(utilisateur["_id"])
            st.session_state.email = utilisateur["email"]
            st.success(f"✅ Bienvenue {st.session_state.email} !")
            time.sleep(1) # Ajout d'un petit délai pour la lisibilité
            st.rerun()
        else:
            st.error("❌ Identifiants incorrects")

def authentication_flow():
    """Gère la connexion et la création de compte via des onglets"""
    tab_login, tab_register = st.tabs(["🔒 Se connecter", "✍️ Créer un compte"])

    with tab_login:
        login_page()

    with tab_register:
        creer_compte()

# =============================================================
# === FIN DES FONCTIONS D'AUTHENTIFICATION ===
# =============================================================

# === Fonctions principales adaptées pour MongoDB ===
def creer_question():
    st.header("✍️ Créer une nouvelle question")

    # Vérifier si l'utilisateur est connecté, sinon afficher la page d'authentification
    if not st.session_state.get("auth"):
        st.info("Veuillez vous connecter ou créer un compte pour proposer une question.")
        authentication_flow()
        return

    with st.form("form_question"):
        question = st.text_input("Votre question :")
        idee1 = st.text_input("Idée 1 :")
        idee2 = st.text_input("Idée 2 :")
        submitted = st.form_submit_button("Créer")

        if submitted and question.strip() and idee1.strip() and idee2.strip():
            db = get_db_connection()

            # Insérer la question
            question_data = {
                "question": question,
                "createur_id": st.session_state.utilisateur_id, # Utiliser l'ID de l'utilisateur connecté
                "date_creation": datetime.now()
            }
            question_id = db.question.insert_one(question_data).inserted_id

            # Analyser sentiment des idées
            score1, label1 = analyze_sentiment(idee1)
            score2, label2 = analyze_sentiment(idee2)

            # Insérer les idées
            db.idees.insert_many([
                {
                    "id_question": question_id,
                    "idee_texte": idee1,
                    "creer_par_utilisateur": "non",
                    "date_creation": datetime.now(),
                    "sentiment_score": float(score1),
                    "sentiment_label": label1
                },
                {
                    "id_question": question_id,
                    "idee_texte": idee2,
                    "creer_par_utilisateur": "non",
                    "date_creation": datetime.now(),
                    "sentiment_score": float(score2),
                    "sentiment_label": label2
                }
            ])

            # Mettre à jour les analytics
            update_sentiment_analytics(question_id)

            st.success("✅ Question et idées enregistrées avec analyse de sentiment.")
        elif submitted:
            st.error("Veuillez remplir tous les champs.")

def participer():
    st.header("🗳️ Participer aux votes")
    db = get_db_connection()

    # Récupérer toutes les questions
    all_questions = list(db.question.find({}, {"_id": 1, "question": 1}))

    # Récupérer les questions déjà votées
    voted_q_ids = [v["id_question"] for v in db.vote.find(
        {"id_navigateur": st.session_state.id_navigateur},
        {"id_question": 1}
    )]

    # Questions disponibles pour le vote
    questions = [q for q in all_questions if q["_id"] not in voted_q_ids]

    if 'current_question_index' not in st.session_state:
        st.session_state.current_question_index = 0

    if st.session_state.current_question_index >= len(questions):
        st.success("✅ Vous avez terminé toutes les questions disponibles.")
        afficher_formulaire_profil()
        return

    selected_question = questions[st.session_state.current_question_index]
    st.subheader(f"Question : {selected_question['question']}")
    question_id = selected_question["_id"]

    # Récupérer les idées pour cette question
    ideas = list(db.idees.find({"id_question": question_id}, {"_id": 1, "idee_texte": 1}))

    if len(ideas) >= 2:
        choices = random.sample(ideas, 2)
        col1, col2 = st.columns(2)
        with col1:
            if st.button(choices[0]['idee_texte'], use_container_width=True):
                enregistrer_vote(choices[0]['_id'], choices[1]['_id'], question_id)
                st.session_state.current_question_index += 1
                st.rerun()
        with col2:
            if st.button(choices[1]['idee_texte'], use_container_width=True):
                enregistrer_vote(choices[1]['_id'], choices[0]['_id'], question_id)
                st.session_state.current_question_index += 1
                st.rerun()

    # Nouvelle idée avec analyse de sentiment
    st.markdown("### 💡 Proposer une nouvelle idée")
    nouvelle_idee_key = f"nouvelle_idee_{question_id}"

    if st.session_state.get(f"idee_envoyee_{question_id}"):
        st.session_state[nouvelle_idee_key] = ""
        del st.session_state[f"idee_envoyee_{question_id}"]

    nouvelle_idee = st.text_area("Votre idée innovante :", key=nouvelle_idee_key, height=80)

    if st.button("➕ Soumettre l'idée", key=f"btn_idee_{question_id}"):
        if nouvelle_idee.strip():
            score, label = analyze_sentiment(nouvelle_idee)
            db.idees.insert_one({
                "id_question": question_id,
                "idee_texte": nouvelle_idee.strip(),
                "creer_par_utilisateur": "oui",
                "date_creation": datetime.now(),
                "sentiment_score": float(score),
                "sentiment_label": label
            })

            # Mettre à jour analytics
            update_sentiment_analytics(question_id)

            st.success(f"✅ Idée ajoutée (Sentiment: {label}) !")
            st.session_state[f"idee_envoyee_{question_id}"] = True
            st.rerun()

    # Commentaire avec analyse de sentiment
    st.markdown("### 💬 Ajouter un commentaire")
    comment_key = f"commentaire_{question_id}"

    if st.session_state.get(f"commentaire_envoye_{question_id}"):
        st.session_state[comment_key] = ""
        del st.session_state[f"commentaire_envoye_{question_id}"]

    commentaire = st.text_area("Votre opinion :", key=comment_key, height=80)

    if st.button("💾 Ajouter commentaire", key=f"btn_comment_{question_id}"):
        if commentaire.strip():
            score, label = analyze_sentiment(commentaire)
            db.commentaire.insert_one({
                "id_navigateur": st.session_state["id_navigateur"],
                "id_question": question_id,
                "commentaire": commentaire.strip(),
                "date_creation": datetime.now(),
                "sentiment_score": float(score),
                "sentiment_label": label
            })

            # Mettre à jour analytics
            update_sentiment_analytics(question_id)

            st.success(f"💬 Commentaire ajouté (Sentiment: {label}) !")
            st.session_state[f"commentaire_envoye_{question_id}"] = True
            st.rerun()

def enregistrer_vote(gagnant, perdant, question_id):
    db = get_db_connection()

    # Vérifier si l'utilisateur a déjà voté
    if db.vote.find_one({
        "id_navigateur": st.session_state.id_navigateur,
        "id_question": question_id
    }):
        st.warning("⚠️ Vous avez déjà voté pour cette question.")
    else:
        # Enregistrer le vote
        db.vote.insert_one({
            "id_navigateur": st.session_state.id_navigateur,
            "id_question": question_id,
            "id_idee_gagnant": gagnant,
            "id_idee_perdant": perdant,
            "date_vote": datetime.now()
        })

        # Mettre à jour les analytics après le vote
        update_sentiment_analytics(question_id)

        st.success("✅ Merci pour votre vote !")

def afficher_formulaire_profil():
    db = get_db_connection()

    if db.profil.find_one({"id_navigateur": st.session_state.id_navigateur}):
        st.success("🎉 Merci ! Vous avez déjà rempli le formulaire.")
        return

    st.subheader("🧾 Veuillez compléter ce court formulaire")
    pays = st.text_input("Pays")
    age = st.number_input("Âge", min_value=10, max_value=120)
    sexe = st.selectbox("Sexe", ["Homme", "Femme", "Autre"])
    fonction = st.text_input("Fonction")

    if st.button("Soumettre"):
        db.profil.insert_one({
            "id_navigateur": st.session_state.id_navigateur,
            "pays": pays,
            "age": age,
            "sexe": sexe,
            "fonction": fonction,
            "date_creation": datetime.now()
        })
        st.success("✅ Profil enregistré avec succès.")

def voir_resultats():
    st.title("📊 Résultats des votes par question")

    db = get_db_connection()

    # Pipeline d'agrégation pour les résultats
    pipeline = [
        {"$lookup": {
            "from": "idees",
            "localField": "_id",
            "foreignField": "id_question",
            "as": "idees"
        }},
        {"$unwind": "$idees"},
        {"$lookup": {
            "from": "vote",
            "let": {"idee_id": "$idees._id", "question_id": "$_id"},
            "pipeline": [
                {"$match": {
                    "$expr": {
                        "$or": [
                            {"$eq": ["$id_idee_gagnant", "$$idee_id"]},
                            {"$eq": ["$id_idee_perdant", "$$idee_id"]}
                        ]
                    }
                }}
            ],
            "as": "votes"
        }},
        {"$project": {
            "question": "$question",
            "idee_texte": "$idees.idee_texte",
            "creer_par_utilisateur": "$idees.creer_par_utilisateur",
            "sentiment_score": "$idees.sentiment_score",
            "sentiment_label": "$idees.sentiment_label",
            "victoires": {"$sum": {"$cond": [{"$eq": ["$votes.id_idee_gagnant", "$idees._id"]}, 1, 0]}},
            "defaites": {"$sum": {"$cond": [{"$eq": ["$votes.id_idee_perdant", "$idees._id"]}, 1, 0]}}
        }},
        {"$group": {
            "_id": {
                "question_id": "$_id",
                "question": "$question",
                "idee_id": "$idees._id",
                "idee_texte": "$idees.idee_texte",
                "creer_par_utilisateur": "$idees.creer_par_utilisateur",
                "sentiment_score": "$idees.sentiment_score",
                "sentiment_label": "$idees.sentiment_label"
            },
            "victoires": {"$sum": "$victoires"},
            "defaites": {"$sum": "$defaites"}
        }},
        {"$group": {
            "_id": "$_id.question_id",
            "question": {"$first": "$_id.question"},
            "idees": {
                "$push": {
                    "id_idee": "$_id.idee_id",
                    "idee_texte": "$_id.idee_texte",
                    "creer_par_utilisateur": "$_id.creer_par_utilisateur",
                    "sentiment_score": "$_id.sentiment_score",
                    "sentiment_label": "$_id.sentiment_label",
                    "victoires": "$victoires",
                    "defaites": "$defaites"
                }
            }
        }},
        {"$sort": {"_id": 1}}
    ]

    resultats = list(db.question.aggregate(pipeline))

    # Organiser par question
    questions = {}
    for row in resultats:
        qid = row["_id"]
        questions[qid] = {
            "question": row["question"],
            "idees": row["idees"]
        }

    # Affichage
    for qid, bloc in questions.items():
        st.markdown(f"## ❓ {bloc['question']}")

        data = []
        for idee in bloc["idees"]:
            victoires = float(idee["victoires"])
            defaites = float(idee["defaites"])
            total = victoires + defaites
            score = round((victoires / total) * 100, 2) if total > 0 else 0.0

            type_idee = "Proposée" if idee["creer_par_utilisateur"] == "oui" else "Initiale"

            data.append({
                "Idée": idee["idee_texte"],
                "Score": float(score),
                "Type": type_idee,
                "Sentiment": idee.get("sentiment_label", "Non analysé"),
                "Score Sentiment": float(idee.get("sentiment_score", 0.0))
            })

        df = pd.DataFrame(data).sort_values(by="Score", ascending=False)

        # 🥇 Idée la plus soutenue
        if not df.empty:
            meilleure = df.iloc[0]
            st.success(f"🏅 **Idée la plus soutenue :** _{meilleure['Idée']}_ avec un score de **{meilleure['Score']:.1f}%** (Sentiment: {meilleure['Sentiment']})")

        # 🧾 Tableau enrichi avec sentiment
        st.markdown("### 📋 Détail des scores avec analyse de sentiment")
        st.dataframe(df[["Idée", "Score", "Sentiment", "Score Sentiment"]], use_container_width=True)

        # 📊 Visualisation comparative avec sentiment
        st.markdown("### ☁️ Comparaison avec analyse de sentiment")
        afficher_comparaison_par_score_et_sentiment(df)

        st.markdown("---")

def afficher_comparaison_par_score_et_sentiment(df):
    """Graphique comparatif avec scores et sentiments"""
    if df.empty:
        return

    # Graphique principal : Score vs Sentiment
    scatter = alt.Chart(df).mark_circle(size=200, opacity=0.8).encode(
        x=alt.X('Score:Q', title="Score de Vote (%)", scale=alt.Scale(domain=[0, 100])),
        y=alt.Y('Score Sentiment:Q', title="Score de Sentiment", scale=alt.Scale(domain=[-1, 1])),
        color=alt.Color('Type:N', scale=alt.Scale(domain=["Initiale", "Proposée"], range=["#1f77b4", "#ff7f0e"])),
        tooltip=['Idée', 'Score', 'Sentiment', 'Score Sentiment', 'Type']
    ).properties(
        width=600,
        height=400,
        title="Relation Score de Vote vs Sentiment"
    )

    # Lignes de référence
    hline = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(color='gray', strokeDash=[2, 2]).encode(y='y:Q')
    vline = alt.Chart(pd.DataFrame({'x': [50]})).mark_rule(color='gray', strokeDash=[2, 2]).encode(x='x:Q')

    # Histogramme des sentiments
    hist_sentiment = alt.Chart(df).mark_bar(opacity=0.7).encode(
        x=alt.X('count()', title='Nombre d\'idées'),
        y=alt.Y('Sentiment:N', title='Sentiment'),
        color=alt.Color('Sentiment:N', scale=alt.Scale(domain=['Positif', 'Neutre', 'Négatif'],
                                                      range=['#2ca02c', '#ff7f0e', '#d62728']))
    ).properties(
        width=300,
        height=200,
        title="Distribution des Sentiments"
    )

    # Combiner les graphiques
    combined = alt.hconcat(scatter + hline + vline, hist_sentiment)
    st.altair_chart(combined, use_container_width=True)

def afficher_statistiques_votes():
    """Dashboard des statistiques de votes pour une question sélectionnée"""
    st.title("📊 Statistiques des Votes")

    db = get_db_connection()

    # Récupérer la liste des questions
    questions = list(db.question.find({}, {"_id": 1, "question": 1}).sort("date_creation", -1))

    if not questions:
        st.warning("Aucune question disponible.")
        return

    # Liste déroulante pour sélectionner la question
    question_options = {f"{q['question'][:80]}..." if len(q['question']) > 80 else q['question']: q['_id'] for q in questions}

    selected_question_text = st.selectbox(
        "🔍 Sélectionnez une question à analyser :",
        options=list(question_options.keys()),
        index=0
    )

    selected_question_id = question_options[selected_question_text]

    # Pipeline d'agrégation pour les résultats de vote
    pipeline = [
        {"$match": {"id_question": selected_question_id}},
        {"$lookup": {
            "from": "idees",
            "localField": "id_idee_gagnant",
            "foreignField": "_id",
            "as": "idee_gagnant"
        }},
        {"$lookup": {
            "from": "idees",
            "localField": "id_idee_perdant",
            "foreignField": "_id",
            "as": "idee_perdant"
        }},
        {"$unwind": "$idee_gagnant"},
        {"$unwind": "$idee_perdant"},
        {"$group": {
            "_id": None,
            "total_votes": {"$sum": 1},
            "idees": {
                "$push": [
                    {"id_idee": "$idee_gagnant._id", "idee_texte": "$idee_gagnant.idee_texte", "type": "victoire"},
                    {"id_idee": "$idee_perdant._id", "idee_texte": "$idee_perdant.idee_texte", "type": "defaite"}
                ]
            }
        }},
        {"$unwind": "$idees"},
        {"$group": {
            "_id": "$idees.id_idee",
            "idee_texte": {"$first": "$idees.idee_texte"},
            "victoires": {"$sum": {"$cond": [{"$eq": ["$idees.type", "victoire"]}, 1, 0]}},
            "defaites": {"$sum": {"$cond": [{"$eq": ["$idees.type", "defaite"]}, 1, 0]}},
            "total_votes": {"$first": "$total_votes"}
        }}
    ]

    resultats = list(db.vote.aggregate(pipeline))

    if not resultats:
        st.warning("Aucune donnée de vote disponible pour cette question.")
        return

    # Préparer les données pour le graphique
    data_votes = []
    for result in resultats:
        victoires = int(result.get("victoires", 0))
        defaites = int(result.get("defaites", 0))
        total = victoires + defaites
        pourcentage = round((victoires / total) * 100, 1) if total > 0 else 0

        # Vérifier si l'idée a été créée par un utilisateur
        idee = db.idees.find_one({"_id": result["_id"]}, {"creer_par_utilisateur": 1})
        type_idee = "Proposée par utilisateur" if idee and idee.get("creer_par_utilisateur") == "oui" else "Idée initiale"

        data_votes.append({
            'Idée': result['idee_texte'][:50] + "..." if len(result['idee_texte']) > 50 else result['idee_texte'],
            'Pourcentage': float(pourcentage),
            'Victoires': victoires,
            'Défaites': defaites,
            'Total': total,
            'Type': type_idee
        })

    # Affichage des métriques principales
    if data_votes:
        col1, col2, col3 = st.columns(3)

        total_votes = sum([d['Total'] for d in data_votes])
        meilleure_idee = max(data_votes, key=lambda x: x['Pourcentage'])
        nb_idees = len(data_votes)

        with col1:
            st.metric("📊 Total des votes", int(total_votes))
        with col2:
            st.metric("💡 Nombre d'idées", int(nb_idees))
        with col3:
            st.metric("🏆 Meilleur score", f"{float(meilleure_idee['Pourcentage'])}%")

        # Graphique en barres - Pourcentage de victoires
        df_votes = pd.DataFrame(data_votes)

        chart_bars = alt.Chart(df_votes).mark_bar().encode(
            x=alt.X('Pourcentage:Q', title='Pourcentage de victoires (%)', scale=alt.Scale(domain=[0, 100])),
            y=alt.Y('Idée:N', sort='-x', title='Idées'),
            color=alt.Color('Type:N',
                          scale=alt.Scale(domain=["Idée initiale", "Proposée par utilisateur"],
                                        range=["#1f77b4", "#ff7f0e"]),
                          title="Type d'idée"),
            tooltip=['Idée:N', 'Pourcentage:Q', 'Victoires:Q', 'Défaites:Q', 'Type:N']
        ).properties(
            width=700,
            height=400,
            title=f"Pourcentage de victoires par idée"
        )

        st.altair_chart(chart_bars, use_container_width=True)

        # Graphique circulaire - Répartition des votes
        chart_pie = alt.Chart(df_votes).mark_arc(innerRadius=50, outerRadius=120).encode(
            theta=alt.Theta('Victoires:Q', title='Nombre de victoires'),
            color=alt.Color('Idée:N', legend=alt.Legend(orient="right")),
            tooltip=['Idée:N', 'Victoires:Q', 'Pourcentage:Q']
        ).properties(
            width=400,
            height=400,
            title="Répartition des victoires"
        )

        st.altair_chart(chart_pie, use_container_width=True)

        # Tableau détaillé
        st.markdown("### 📋 Détail des résultats")
        st.dataframe(
            df_votes[['Idée', 'Pourcentage', 'Victoires', 'Défaites', 'Total', 'Type']],
            use_container_width=True
        )

def afficher_analyse_sentiment_complete():
    """Dashboard complet d'analyse de sentiment avec option de comparaison"""
    st.title("🧠 Analyse de Sentiment Avancée")

    # Options de visualisation
    tab1, tab2 = st.tabs(["📊 Question Individuelle", "🔄 Comparaison Questions"])

    with tab1:
        afficher_sentiment_question_individuelle()

    with tab2:
        afficher_comparaison_sentiment_questions()

def afficher_sentiment_question_individuelle():
    """Analyse de sentiment pour une question individuelle"""
    db = get_db_connection()

    # Récupérer les questions
    questions = list(db.question.find({}, {"_id": 1, "question": 1}).sort("date_creation", -1))

    if not questions:
        st.warning("Aucune question disponible.")
        return

    # Sélection de la question
    question_options = {f"{q['question'][:80]}..." if len(q['question']) > 80 else q['question']: q['_id'] for q in questions}

    selected_question_text = st.selectbox(
        "🔍 Choisissez une question pour l'analyse de sentiment :",
        options=list(question_options.keys()),
        key="sentiment_individual"
    )

    selected_question_id = question_options[selected_question_text]

    # Récupérer toutes les données textuelles pour cette question
    idees = list(db.idees.find({"id_question": selected_question_id}, {
        "idee_texte": 1, "sentiment_score": 1, "sentiment_label": 1, "creer_par_utilisateur": 1
    }))

    commentaires = list(db.commentaire.find({"id_question": selected_question_id}, {
        "commentaire": 1, "sentiment_score": 1, "sentiment_label": 1
    }))

    if not idees and not commentaires:
        st.warning("Aucun contenu textuel disponible pour cette question.")
        return

    # Analyse globale combinée
    tous_textes = " ".join([i['idee_texte'] for i in idees] + [c['commentaire'] for c in commentaires])
    sentiment_global_score, sentiment_global_label = analyze_sentiment(tous_textes)

    # Métriques principales
    col1, col2, col3, col4 = st.columns(4)

    nb_idees = len(idees)
    nb_commentaires = len(commentaires)

    with col1:
        st.metric("💡 Idées", int(nb_idees))
    with col2:
        st.metric("💬 Commentaires", int(nb_commentaires))
    with col3:
        st.metric("🧠 Sentiment Global", sentiment_global_label)
    with col4:
        st.metric("📊 Score Global", f"{float(sentiment_global_score):.3f}")

    # Préparer les données pour visualisation
    sentiment_data = []

    for idee in idees:
        sentiment_data.append({
            'Texte': idee['idee_texte'][:100] + "..." if len(idee['idee_texte']) > 100 else idee['idee_texte'],
            'Type': 'Idée',
            'Sentiment': idee.get('sentiment_label', 'Non analysé'),
            'Score': float(idee.get('sentiment_score', 0)),
            'Origine': 'Utilisateur' if idee.get('creer_par_utilisateur') == 'oui' else 'Initial'
        })

    for comment in commentaires:
        sentiment_data.append({
            'Texte': comment['commentaire'][:100] + "..." if len(comment['commentaire']) > 100 else comment['commentaire'],
            'Type': 'Commentaire',
            'Sentiment': comment.get('sentiment_label', 'Non analysé'),
            'Score': float(comment.get('sentiment_score', 0)),
            'Origine': 'Commentaire'
        })

    df_sentiment = pd.DataFrame(sentiment_data)

    # Graphiques
    col1, col2 = st.columns(2)

    with col1:
        # Distribution des sentiments
        sentiment_counts = df_sentiment['Sentiment'].value_counts().reset_index()
        sentiment_counts.columns = ['Sentiment', 'Nombre']

        chart_sentiment = alt.Chart(sentiment_counts).mark_arc(innerRadius=40).encode(
            theta=alt.Theta('Nombre:Q'),
            color=alt.Color('Sentiment:N',
                          scale=alt.Scale(domain=['Positif', 'Neutre', 'Négatif'],
                                        range=['#2ca02c', '#ff7f0e', '#d62728'])),
            tooltip=['Sentiment:N', 'Nombre:Q']
        ).properties(
            width=300,
            height=300,
            title="Distribution des Sentiments"
        )

        st.altair_chart(chart_sentiment)

    with col2:
        # Scores par type de contenu
        chart_scores = alt.Chart(df_sentiment).mark_boxplot(extent='min-max').encode(
            x='Type:N',
            y=alt.Y('Score:Q', scale=alt.Scale(domain=[-1, 1]), title='Score de Sentiment'),
            color='Type:N'
        ).properties(
            width=300,
            height=300,
            title="Distribution des Scores par Type"
        )

        st.altair_chart(chart_scores)

    # Tableau détaillé
    st.markdown("### 📋 Analyse détaillée")
    st.dataframe(df_sentiment, use_container_width=True)

def afficher_comparaison_sentiment_questions():
    """Comparaison des sentiments entre toutes les questions"""
    st.markdown("### 🔄 Comparaison Multi-Questions")

    db = get_db_connection()

    # Récupérer les analytics de toutes les questions
    data_comparison = list(db.sentiment_analytics.aggregate([
        {"$lookup": {
            "from": "question",
            "localField": "id_question",
            "foreignField": "_id",
            "as": "question"
        }},
        {"$unwind": "$question"},
        {"$project": {
            "id_question": 1,
            "question": "$question.question",
            "moyenne_sentiment_idees": 1,
            "moyenne_sentiment_commentaires": 1,
            "total_positifs": {"$add": ["$total_idees_positives", "$total_commentaires_positifs"]},
            "total_negatifs": {"$add": ["$total_idees_negatives", "$total_commentaires_negatifs"]},
            "total_neutres": {"$add": ["$total_idees_neutres", "$total_commentaires_neutres"]}
        }}
    ]))

    if not data_comparison:
        st.warning("Aucune donnée d'analytics disponible pour la comparaison.")
        return

    # Préparer les données pour visualisation comparative
    comparison_data = []
    for row in data_comparison:
        question_courte = (row['question'][:40] + "...") if len(row['question']) > 40 else row['question']

        # Conversion des valeurs et vérification de NULL
        moyenne_idees = row.get('moyenne_sentiment_idees')
        moyenne_comms = row.get('moyenne_sentiment_commentaires')

        if moyenne_idees is not None:
            comparison_data.append({
                'Question': question_courte,
                'ID': row['id_question'],
                'Score_Sentiment': float(moyenne_idees),
                'Type_Contenu': 'Idées'
            })

        if moyenne_comms is not None:
            comparison_data.append({
                'Question': question_courte,
                'ID': row['id_question'],
                'Score_Sentiment': float(moyenne_comms),
                'Type_Contenu': 'Commentaires'
            })

    if not comparison_data:
        st.warning("Données insuffisantes pour la comparaison.")
        return

    df_comparison = pd.DataFrame(comparison_data)

    # Graphique pour les idées
    df_idees = df_comparison[df_comparison['Type_Contenu'] == 'Idées']
    if not df_idees.empty:
        chart_idees = alt.Chart(df_idees).mark_bar(color='#1f77b4').encode(
            x=alt.X('Question:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
            y=alt.Y('Score_Sentiment:Q', scale=alt.Scale(domain=[-1, 1]), title='Score Sentiment Moyen'),
            tooltip=['Question:N', 'Score_Sentiment:Q']
        ).properties(
            width=600,
            height=300,
            title="Sentiment Moyen des Idées par Question"
        )

        # Ligne de référence
        rule = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(color='red', strokeDash=[2, 2]).encode(y='y:Q')

        st.altair_chart(chart_idees + rule, use_container_width=True)

    # Graphique pour les commentaires
    df_comms = df_comparison[df_comparison['Type_Contenu'] == 'Commentaires']
    if not df_comms.empty:
        chart_comms = alt.Chart(df_comms).mark_bar(color='#ff7f0e').encode(
            x=alt.X('Question:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
            y=alt.Y('Score_Sentiment:Q', scale=alt.Scale(domain=[-1, 1]), title='Score Sentiment Moyen'),
            tooltip=['Question:N', 'Score_Sentiment:Q']
        ).properties(
            width=600,
            height=300,
            title="Sentiment Moyen des Commentaires par Question"
        )

        # Ligne de référence
        rule = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(color='red', strokeDash=[2, 2]).encode(y='y:Q')

        st.altair_chart(chart_comms + rule, use_container_width=True)

    # Graphique radar pour vue globale
    st.markdown("### 🎯 Vue Globale des Questions")

    # Préparer données pour métriques globales
    global_metrics = []
    for row in data_comparison:
        question_courte = (row['question'][:30] + "...") if len(row['question']) > 30 else row['question']
        total_elements = (row.get('total_positifs', 0) or 0) + (row.get('total_negatifs', 0) or 0) + (row.get('total_neutres', 0) or 0)

        if total_elements > 0:
            pourcentage_positif = ((row.get('total_positifs', 0) or 0) / total_elements) * 100
            pourcentage_negatif = ((row.get('total_negatifs', 0) or 0) / total_elements) * 100
            pourcentage_neutre = ((row.get('total_neutres', 0) or 0) / total_elements) * 100

            global_metrics.append({
                'Question': question_courte,
                'Positif': float(pourcentage_positif),
                'Négatif': float(pourcentage_negatif),
                'Neutre': float(pourcentage_neutre),
                'Score_Idees': float(row.get('moyenne_sentiment_idees', 0)) if row.get('moyenne_sentiment_idees') is not None else 0,
                'Score_Commentaires': float(row.get('moyenne_sentiment_commentaires', 0)) if row.get('moyenne_sentiment_commentaires') is not None else 0
            })

    if global_metrics:
        df_global = pd.DataFrame(global_metrics)

        # Graphique empilé des pourcentages
        df_melted = df_global.melt(
            id_vars=['Question'],
            value_vars=['Positif', 'Négatif', 'Neutre'],
            var_name='Sentiment',
            value_name='Pourcentage'
        )

        stacked_chart = alt.Chart(df_melted).mark_bar().encode(
            x=alt.X('Question:N', axis=alt.Axis(labelAngle=-45)),
            y=alt.Y('Pourcentage:Q', title='Pourcentage (%)'),
            color=alt.Color('Sentiment:N',
                          scale=alt.Scale(domain=['Positif', 'Neutre', 'Négatif'],
                                        range=['#2ca02c', '#ff7f0e', '#d62728'])),
            tooltip=['Question:N', 'Sentiment:N', 'Pourcentage:Q']
        ).properties(
            width=700,
            height=400,
            title="Répartition des Sentiments par Question (%)"
        )

        st.altair_chart(stacked_chart, use_container_width=True)

        # Tableau de synthèse
        st.markdown("### 📊 Tableau de Synthèse")
        st.dataframe(df_global.round(2), use_container_width=True)

def display_home_page():
    """Affiche la page d'accueil avec HTML moderne et élégant"""

    # CSS personnalisé pour une interface moderne
    st.markdown("""
    <style>
        /* Import Google Fonts */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        .main-container {
            font-family: 'Inter', sans-serif;
        }

        /* Hero Section */
        .hero-section {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 4rem 2rem;
            border-radius: 20px;
            margin-bottom: 3rem;
            text-align: center;
            position: relative;
            overflow: hidden;
        }

        .hero-section::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000"><polygon fill="rgba(255,255,255,0.1)" points="0,1000 1000,0 1000,1000"/></svg>');
            background-size: cover;
        }

        .hero-content {
            position: relative;
            z-index: 2;
        }

        .hero-title {
            font-size: 3.5rem;
            font-weight: 700;
            margin-bottom: 1rem;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }

        .hero-subtitle {
            font-size: 1.3rem;
            font-weight: 400;
            opacity: 0.95;
            max-width: 600px;
            margin: 0 auto;
            line-height: 1.6;
        }

        /* Features Grid */
        .features-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 2rem;
            margin: 3rem 0;
        }

        .feature-card {
            background: white;
            border-radius: 16px;
            padding: 2rem;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
            border: 1px solid rgba(255,255,255,0.18);
            backdrop-filter: blur(10px);
            position: relative;
            overflow: hidden;
        }

        .feature-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, #667eea, #764ba2);
        }

        .feature-card:hover {
            transform: translateY(-8px);
            box-shadow: 0 16px 48px rgba(0,0,0,0.15);
        }

        .feature-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
        }

        .feature-title {
            font-size: 1.5rem;
            font-weight: 600;
            color: #2d3748;
            margin-bottom: 1rem;
        }

        .feature-description {
            color: #718096;
            line-height: 1.6;
            font-size: 0.95rem;
        }

        /* Stats Section */
        .stats-section {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            border-radius: 20px;
            padding: 3rem 2rem;
            margin: 3rem 0;
            color: white;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 2rem;
            margin-top: 2rem;
        }

        .stat-card {
            text-align: center;
            background: rgba(255,255,255,0.2);
            border-radius: 12px;
            padding: 2rem 1rem;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
        }

        .stat-number {
            font-size: 3rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }

        .stat-label {
            font-size: 1rem;
            font-weight: 500;
            opacity: 0.9;
        }

        /* About Section */
        .about-section {
            background: white;
            border-radius: 20px;
            padding: 3rem 2rem;
            margin: 3rem 0;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }

        .about-title {
            font-size: 2.5rem;
            font-weight: 600;
            color: #2d3748;
            margin-bottom: 2rem;
            text-align: center;
        }

        .about-content {
            font-size: 1.1rem;
            line-height: 1.8;
            color: #4a5568;
        }

        .about-list {
            list-style: none;
            padding: 0;
            margin: 2rem 0;
        }

        .about-list li {
            padding: 0.5rem 0;
            padding-left: 2rem;
            position: relative;
        }

        .about-list li::before {
            content: '✨';
            position: absolute;
            left: 0;
            top: 0.5rem;
        }

        /* Admin Section */
        .admin-section {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            border-radius: 16px;
            padding: 2rem;
            margin: 2rem 0;
            color: white;
        }

        .admin-title {
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 1rem;
        }

        /* Footer */
        .footer-section {
            text-align: center;
            margin-top: 4rem;
            padding: 2rem;
            color: #718096;
            border-top: 1px solid #e2e8f0;
        }

        .footer-section p {
            margin: 0.5rem 0;
        }

        /* Animations */
        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .animate-fade-in {
            animation: fadeInUp 0.6s ease-out forwards;
        }

        /* Image Upload Styling */
        .upload-area {
            border: 2px dashed #cbd5e0;
            border-radius: 12px;
            padding: 2rem;
            text-align: center;
            background: #f7fafc;
            transition: all 0.3s ease;
        }

        .upload-area:hover {
            border-color: #4facfe;
            background: #edf2f7;
        }
    </style>
    """, unsafe_allow_html=True)

    # Hero Section
    st.markdown("""
    <div class="main-container">
        <div class="hero-section animate-fade-in">
            <div class="hero-content">
                <h1 class="hero-title">🗳️ QUE VOULONS NOUS POUR L'AFRIQUE </h1>
                <p style="text-align: justify; font-size: 1.2rem; opacity: 0.9;">
                    Plateforme Citoyenne de Vote qui explore les priorités sociales, politiques et économiques des Africains via une plateforme interactive
                    où les participants peuvent proposer, évaluer, et classer des idées pour l’avenir du continent.
                </p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Section d'upload d'image pour l'admin
    # MODIFICATION ICI : Seul "yinnaasome@gmail.com" peut voir cette section
    if st.session_state.get("auth") and st.session_state.get("email") == "yinnaasome@gmail.com":
        st.markdown("""
        <div class="admin-section">
            <h3 class="admin-title">🛠️ Administration - Gestion des Médias</h3>
            <p>En tant qu'administrateur, vous pouvez télécharger des images pour illustrer les objectifs de la plateforme.</p>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("🖼️ Gérer les images de la plateforme", expanded=False):
            col1, col2 = st.columns([2, 1])

            with col1:
                uploaded_file = st.file_uploader(
                    "Télécharger une image (objectifs de la plateforme)",
                    type=["jpg", "png", "jpeg"],
                    help="L'image sera utilisée pour illustrer les objectifs de la plateforme"
                )

                if uploaded_file is not None:
                    try:
                        img = Image.open(uploaded_file)
                        # Redimensionner l'image si nécessaire
                        if img.width > 800:
                            img = img.resize((800, int(img.height * 800 / img.width)))

                        st.image(img, caption="Aperçu de l'image téléchargée", use_column_width=True)

                        # Bouton pour sauvegarder
                        if st.button("💾 Sauvegarder cette image"):
                            # Ici vous pourriez sauvegarder l'image dans votre base de données
                            # ou dans un système de fichiers
                            st.success("✅ Image sauvegardée avec succès!")
                    except Exception as e:
                        st.error(f"❌ Erreur lors du traitement de l'image: {e}")

            with col2:
                st.markdown("""
                **💡 Conseils :**
                - Format recommandé: JPG, PNG
                - Taille optimale: 800px de largeur
                - Thème: Démocratie, participation citoyenne
                - Évitez les images trop chargées
                """)

    # Features Section
    st.markdown("""
    <div class="features-grid">
        <div class="feature-card animate-fade-in">
            <div class="feature-icon">✏️</div>
            <h3 class="feature-title">Créer & Proposer</h3>
            <p class="feature-description">
                Formulez vos questions et proposez des idées innovantes.
                Notre système d'analyse de sentiment évalue automatiquement
                la tonalité de vos contributions.
            </p>
        </div>
    """, unsafe_allow_html=True)

    # Statistics Section
    try:
        db = get_db_connection()

        total_questions = db.question.count_documents({})
        total_idees = db.idees.count_documents({})
        total_votes = db.vote.count_documents({})
        total_commentaires = db.commentaire.count_documents({})

        st.markdown(f"""
        <div class="stats-section animate-fade-in">
            <h2 style="text-align: center; font-size: 2.5rem; margin-bottom: 1rem;">
                📈 Impact de Notre Communauté
            </h2>
            <p style="text-align: center; font-size: 1.2rem; opacity: 0.9;">
                Découvrez l'engagement citoyen en temps réel
            </p>
        </div>
        """, unsafe_allow_html=True)

    except Exception as e:
        st.warning("⚠️ Impossible de charger les statistiques en temps réel")

    # About Section
    st.markdown("""
    <div class="about-section animate-fade-in">
        <h2 class="about-title">🎯 Notre Mission</h2>
        <div class="about-content">
            <p style="text-align: justify; font-size: 1.2rem; opacity: 0.9;">
                Faciliter un dialogue inclusif et constructif. Créez une plateforme en ligne qui permette à chaque citoyen africain,
                quel que soit son niveau d'éducation ou son lieu de résidence, de partager ses idées pour l'avenir de l'Afrique.
                Encourager la proposition d'idées novatrices. Au-delà des sujets traditionnels, incitez les participants à soumettre des idées audacieuses
                et créatives qui répondent aux défis contemporains, qu'ils soient climatiques, économiques ou sociaux. 
                Mettez en place un système où les participants peuvent, en quelques mots, exprimer une solution qu'ils jugent prioritaire.
                Permettre une évaluation transparente et collaborative. Plutôt que de demander aux participants de classer des listes d'idées,
                présentez-leur deux idées à la fois et demandez-leur de choisir celle qui leur semble la plus importante.
                Ce format de "comparaison par paires" est intuitif et réduit le biais, permettant de révéler de manière transparente 
                les préférences collectives.
                Synthétiser et diffuser les résultats. Une fois les données collectées, analysez les préférences et classez les idées proposées. 
                Présentez ces résultats de manière claire et  concise 
                Rejoignez notre communauté grandissante de citoyens engagés et
                contribuez à façonner un avenir plus démocratique et inclusif.
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Footer
    st.markdown("""
    <div class="footer-section">
        <p><strong>🌍 Wiki Survey - Démocratie Participative</strong></p>
        <p>Propulsé par l'intelligence artificielle et l'engagement citoyen</p>
        <p style="font-size: 0.8rem; opacity: 0.7;">
            © 2024 - Plateforme open-source pour la participation citoyenne
        </p>
    </div>
    """, unsafe_allow_html=True)

def afficher_dashboard_admin():
    """Dashboard administrateur avec gestion avancée"""
    if not st.session_state.get("auth") or st.session_state.get("email") != "admin@test.com":
        st.error("🚫 Accès réservé aux administrateurs")
        return

    st.title("🛠️ Dashboard Administrateur")

    # Onglets pour organiser les fonctionnalités admin
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Vue d'ensemble",
        "👥 Gestion Utilisateurs",
        "🗑️ Modération",
        "📈 Analytics Avancées"
    ])

    db = get_db_connection()

    with tab1:
        afficher_overview_admin(db)

    with tab2:
        afficher_gestion_utilisateurs(db)

    with tab3:
        afficher_moderation(db)

    with tab4:
        afficher_analytics_avancees(db)

def afficher_overview_admin(db):
    """Vue d'ensemble des statistiques administrateur"""
    st.subheader("📊 Vue d'ensemble de la plateforme")

    # Métriques principales
    col1, col2, col3, col4 = st.columns(4)

    total_questions = db.question.count_documents({})
    total_users = db.navigateur.count_documents({})
    total_votes_today = db.vote.count_documents({
        "date_vote": {"$gte": datetime.now() - timedelta(days=1)}
    })
    total_idees_users = db.idees.count_documents({"creer_par_utilisateur": "oui"})

    with col1:
        st.metric("📝 Questions Totales", total_questions)
    with col2:
        st.metric("👥 Utilisateurs Actifs", total_users)
    with col3:
        st.metric("🗳️ Votes (24h)", total_votes_today)
    with col4:
        st.metric("💡 Idées Utilisateurs", total_idees_users)

    # Graphiques d'évolution
    st.subheader("📈 Évolution de l'activité")

    # Activité des 30 derniers jours
    pipeline_activity = [
        {"$match": {
            "date_vote": {"$gte": datetime.now() - timedelta(days=30)}
        }},
        {"$group": {
            "_id": {
                "$dateToString": {
                    "format": "%Y-%m-%d",
                    "date": "$date_vote"
                }
            },
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]

    activity_data = list(db.vote.aggregate(pipeline_activity))

    if activity_data:
        df_activity = pd.DataFrame(activity_data)
        df_activity.columns = ['Date', 'Votes']
        df_activity['Date'] = pd.to_datetime(df_activity['Date'])

        chart_activity = alt.Chart(df_activity).mark_area(
            color='#4facfe',
            opacity=0.7,
            interpolate='cardinal'
        ).encode(
            x=alt.X('Date:T', title='Date'),
            y=alt.Y('Votes:Q', title='Nombre de votes'),
            tooltip=['Date:T', 'Votes:Q']
        ).properties(
            width=700,
            height=300,
            title="Évolution des votes (30 derniers jours)"
        )

        st.altair_chart(chart_activity, use_container_width=True)

def afficher_gestion_utilisateurs(db):
    """Interface de gestion des utilisateurs"""
    st.subheader("👥 Gestion des Utilisateurs")

    # Statistiques des profils
    profils = list(db.profil.aggregate([
        {"$group": {
            "_id": "$pays",
            "count": {"$sum": 1},
            "age_moyen": {"$avg": "$age"}
        }},
        {"$sort": {"count": -1}}
    ]))

    if profils:
        st.markdown("### 🌍 Répartition par pays")
        df_pays = pd.DataFrame(profils)
        df_pays.columns = ['Pays', 'Nombre', 'Age_Moyen']

        chart_pays = alt.Chart(df_pays.head(10)).mark_bar().encode(
            x=alt.X('Nombre:Q'),
            y=alt.Y('Pays:N', sort='-x'),
            color=alt.Color('Nombre:Q', scale=alt.Scale(scheme='viridis')),
            tooltip=['Pays:N', 'Nombre:Q', 'Age_Moyen:Q']
        ).properties(
            width=600,
            height=400,
            title="Top 10 des pays participants"
        )

        st.altair_chart(chart_pays, use_container_width=True)

    # Recherche d'utilisateurs
    st.markdown("### 🔍 Recherche d'utilisateurs")
    search_term = st.text_input("Rechercher par pays, fonction, etc.")

    if search_term:
        users = list(db.profil.find({
            "$or": [
                {"pays": {"$regex": search_term, "$options": "i"}},
                {"fonction": {"$regex": search_term, "$options": "i"}}
            ]
        }).limit(20))

        if users:
            df_users = pd.DataFrame(users)
            if not df_users.empty:
                st.dataframe(
                    df_users[['pays', 'age', 'sexe', 'fonction', 'date_creation']],
                    use_container_width=True
                )

def afficher_moderation(db):
    """Interface de modération du contenu"""
    st.subheader("🗑️ Modération du Contenu")

    # Contenu à modérer (sentiment très négatif)
    st.markdown("### ⚠️ Contenu nécessitant une attention")

    contenu_negatif = list(db.idees.find({
        "sentiment_score": {"$lt": -0.5}
    }).sort("sentiment_score", 1).limit(10))

    if contenu_negatif:
        for idx, idee in enumerate(contenu_negatif):
            with st.expander(f"Idée #{idx+1} - Score: {idee.get('sentiment_score', 0):.3f}"):
                st.write(f"**Texte:** {idee['idee_texte']}")
                st.write(f"**Sentiment:** {idee.get('sentiment_label', 'Non analysé')}")
                st.write(f"**Date:** {idee.get('date_creation', 'Inconnue')}")

                col1, col2, col3 = st.columns(3)

                with col1:
                    if st.button(f"✅ Approuver #{idx+1}", key=f"approve_{idee['_id']}"):
                        st.success("Contenu approuvé")

                with col2:
                    if st.button(f"⚠️ Signaler #{idx+1}", key=f"flag_{idee['_id']}"):
                        st.warning("Contenu signalé pour review")

                with col3:
                    if st.button(f"🗑️ Supprimer #{idx+1}", key=f"delete_{idee['_id']}"):
                        # Ici vous pouvez implémenter la suppression
                        st.error("Contenu marqué pour suppression")
    else:
        st.success("🎉 Aucun contenu nécessitant une modération urgente")

    # Statistiques de modération
    st.markdown("### 📊 Statistiques de Sentiment")

    sentiment_stats = list(db.idees.aggregate([
        {"$group": {
            "_id": "$sentiment_label",
            "count": {"$sum": 1},
            "avg_score": {"$avg": "$sentiment_score"}
        }}
    ]))

    if sentiment_stats:
        df_sentiment_stats = pd.DataFrame(sentiment_stats)
        df_sentiment_stats.columns = ['Sentiment', 'Nombre', 'Score_Moyen']
        st.dataframe(df_sentiment_stats, use_container_width=True)

def afficher_analytics_avancees(db):
    """Analytics avancées pour les administrateurs"""
    st.subheader("📈 Analytics Avancées")

    # Analyse temporelle
    st.markdown("### ⏰ Analyse Temporelle")

    # Activité par heure
    pipeline_heure = [
        {"$project": {
            "heure": {"$hour": "$date_creation"}
        }},
        {"$group": {
            "_id": "$heure",
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]

    activite_heure = list(db.idees.aggregate(pipeline_heure))

    if activite_heure:
        df_heure = pd.DataFrame(activite_heure)
        df_heure.columns = ['Heure', 'Activite']

        chart_heure = alt.Chart(df_heure).mark_bar().encode(
            x=alt.X('Heure:O', title='Heure de la journée'),
            y=alt.Y('Activite:Q', title='Nombre d\'idées'),
            color=alt.Color('Activite:Q', scale=alt.Scale(scheme='blues')),
            tooltip=['Heure:O', 'Activite:Q']
        ).properties(
            width=700,
            height=300,
            title="Activité par heure de la journée"
        )

        st.altair_chart(chart_heure, use_container_width=True)

    # Corrélation sentiment vs engagement
    st.markdown("### 🔗 Corrélation Sentiment vs Engagement")

    pipeline_correlation = [
        {"$lookup": {
            "from": "vote",
            "let": {"idee_id": "$_id"},
            "pipeline": [
                {"$match": {
                    "$expr": {
                        "$or": [
                            {"$eq": ["$id_idee_gagnant", "$$idee_id"]},
                            {"$eq": ["$id_idee_perdant", "$$idee_id"]}
                        ]
                    }
                }}
            ],
            "as": "votes"
        }},
        {"$project": {
            "sentiment_score": 1,
            "sentiment_label": 1,
            "idee_texte": 1,
            "nombre_votes": {"$size": "$votes"}
        }},
        {"$match": {
            "sentiment_score": {"$exists": True},
            "nombre_votes": {"$gt": 0}
        }}
    ]

    correlation_data = list(db.idees.aggregate(pipeline_correlation))

    if correlation_data:
        df_corr = pd.DataFrame(correlation_data)

        # Calculer la corrélation
        correlation = df_corr['sentiment_score'].corr(df_corr['nombre_votes'])

        st.metric("📊 Coefficient de corrélation", f"{correlation:.3f}")

        scatter_corr = alt.Chart(df_corr).mark_circle(size=100, opacity=0.7).encode(
            x=alt.X('sentiment_score:Q', title='Score de Sentiment'),
            y=alt.Y('nombre_votes:Q', title='Nombre de Votes'),
            color=alt.Color('sentiment_label:N'),
            tooltip=['idee_texte:N', 'sentiment_score:Q', 'nombre_votes:Q']
        ).properties(
            width=600,
            height=400,
            title="Corrélation entre Sentiment et Engagement"
        )

        st.altair_chart(scatter_corr, use_container_width=True)

# === Nouvelle fonction principale avec onglets horizontaux ===
def main():
    # Onglets principaux en haut
    onglets_principaux = st.tabs(["🏠 Accueil", "➕ Créer une question", "🗳 Participer au vote", "📈 Voir les Statistiques"])

    # Onglet Accueil
    with onglets_principaux[0]:
        display_home_page()

    # Onglet Créer question
    with onglets_principaux[1]:
        creer_question()

    # Onglet Participer au vote
    with onglets_principaux[2]:
        participer()

    # Onglet Statistiques (avec sous-onglets)
    with onglets_principaux[3]:
        sous_onglets = st.tabs(["🧠 Analyse de Sentiment", "📊 Voir les résultats", "📈 Statistiques des Votes"])

        with sous_onglets[0]:
            afficher_analyse_sentiment_complete()

        with sous_onglets[1]:
            voir_resultats()

        with sous_onglets[2]:
            afficher_statistiques_votes()


# === Point d’entrée ===
if __name__ == "__main__":

    main()


