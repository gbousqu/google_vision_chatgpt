import streamlit as st

import sys

import subprocess
import sys

from datetime import datetime
from google.cloud import bigquery
from google.cloud import vision_v1

from google.oauth2 import service_account
import io
import os
from openai import OpenAI
from google.cloud import texttospeech
import json
import base64

import html
import time

from streamlit.components.v1 import html as st_html

#à faire 
#ajouter un système de tiroir javascript pour afficher la partie édition des prompts user/system
#modifier la couleur des boutons d'action


temps_d_attente = 2 #pour attendre que bigquery se mette à jour après modification, création, suppression de données et avant de recharger la page

if "bigquery_client" not in st.session_state:
    # Charger les informations du compte de service à partir des secrets de Streamlit
    gcp_service_account = st.secrets["gcp_service_account"]
    service_account_info = json.loads(gcp_service_account)
    # Créer des identifiants à partir des informations du compte de service
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    # Créer un client BigQuery avec ces identifiants
    client = bigquery.Client(credentials=credentials)
    st.session_state.bigquery_client = bigquery.Client(credentials=credentials)

client = st.session_state.bigquery_client


json_string = st.secrets["secret_json"].replace('\\\\', '\\')
secret_data = json.loads(json_string)

if 'detected_text' not in st.session_state:
    st.session_state['detected_text'] = ""

if 'corrected_text' not in st.session_state:
    st.session_state['corrected_text'] = ""

#pour le débogage
def affiche_session_state():
    print("detected_text : ", len(st.session_state['detected_text']))
    print("corrected_text : ", len(st.session_state['corrected_text']))
    print("####################")


# Si l'utilisateur n'est pas encore connecté
if not st.session_state.get('logged_in', False):
    # Créer un formulaire de connexion
    with st.form(key='login_form'):
        username = st.text_input('Nom d\'utilisateur')
        password = st.text_input('Mot de passe', type='password')
        submit_button = st.form_submit_button(label='Se connecter')

        # Lorsque le bouton de soumission est cliqué
        if submit_button:
            # Parcourir chaque élément dans secret_data
            for data in secret_data:
                # Vérifier si le nom d'utilisateur et le mot de passe sont corrects
                if username == data['name'] and password == data['pw']:
                    # Si c'est le cas, définir 'logged_in' à True dans l'état de session
                    st.session_state['username'] = username
                    st.session_state['logged_in'] = True
                    st.experimental_rerun()
            if st.session_state.get('logged_in', False) == False:
                # Si aucune correspondance n'a été trouvée, afficher un message d'erreur
                st.error('Nom d\'utilisateur ou mot de passe incorrect.')
else:

    username = st.session_state['username']

    st.markdown('[Obtenir une clé API OpenAI](https://platform.openai.com/api-keys)', unsafe_allow_html=True)
    openai_api_key = st.text_input("Entrez votre clé OpenAI", type="password")
    os.environ['OPENAI_API_KEY'] = openai_api_key
    if openai_api_key:
        clientOpenAI = OpenAI()

    # Lire le contenu du fichier CSS
    with open('styles_streamlit.css', 'r') as f:
        css = f.read()
    # Inclure le CSS dans le script Streamlit
    st.markdown(f'<style>{css}</style>', unsafe_allow_html=True)

    st.title('OCR : google vision + GPT')

    # Charger les informations du compte de service à partir des secrets de Streamlit
    gcp_service_account = st.secrets["gcp_service_account"]
    service_account_info = json.loads(gcp_service_account)
    # Créer des identifiants à partir des informations du compte de service
    credentials = service_account.Credentials.from_service_account_info(service_account_info)

    # Initialise le client Vision avec les informations d'identification
    clientGoogleVision = vision_v1.ImageAnnotatorClient(credentials=credentials)

    # Crée un emplacement réservé pour l'image
    image_placeholder = st.empty()

    uploaded_file = st.file_uploader("Choisissez une image avec du texte à transcrire", type=["jpg", "jpeg","png"])

    #print("avant affichage uploaded_file");affiche_session_state()

    if uploaded_file is not None:

    # Si le fichier précédemment téléchargé est différent du fichier actuellement téléchargé
        if 'last_uploaded_file' not in st.session_state or st.session_state['last_uploaded_file'] != uploaded_file.getvalue():
            #print(f"on vient de charger une image")
            st.session_state['detected_text'] = ""
            st.session_state['corrected_text'] = ""
            st.session_state['last_uploaded_file'] = uploaded_file.getvalue()

        #print("uploaded_file is not none");affiche_session_state()

        # st.image(uploaded_file, caption='Image téléchargée.')
            # Convertit l'image téléchargée en base64 pour l'insérer dans le HTML
        image_base64 = base64.b64encode(uploaded_file.getvalue()).decode()

        # Affiche l'image dans l'emplacement réservé
        image_placeholder.markdown(
            f'<div style="display: flex; justify-content: center;"><img src="data:image/png;base64,{image_base64}" style="width: 20%;"></div>',
            unsafe_allow_html=True,
        )

        if 'confidence_threshold' not in st.session_state:
            st.session_state.confidence_threshold = 0.8

        confidence_threshold = st.slider("Visualisez les mots incertains en choisissant un seuil de confiance", 0.0, 1.0, st.session_state.confidence_threshold)

        st.session_state.confidence_threshold = confidence_threshold

        # Prépare l'image pour l'API Google Vision
        image = vision_v1.Image(content=uploaded_file.getvalue())        
     
        image_context = vision_v1.ImageContext(language_hints=["fr"])


        #le bouton "lancer la transcription par Google Vision" est affiché si une image a été téléchargée

        if st.button('Lancer la transcription par Google Vision', type='primary'):
            # Appelle l'API Google Vision pour détecter le texte dans l'image
            response = clientGoogleVision.document_text_detection(image=image)

            # Initialise le texte
            detected_text = ""

            # Parcourt chaque page dans la réponse
            for page in response.full_text_annotation.pages:
                # Parcourt chaque bloc dans la page
                for block in page.blocks:
                    # Parcourt chaque paragraphe dans le bloc
                    for paragraph in block.paragraphs:
                        # Parcourt chaque mot dans le paragraphe
                        for word in paragraph.words:
                            # Concatène chaque symbole dans le mot pour obtenir le texte du mot
                            word_text = ''.join([symbol.text for symbol in word.symbols])
                            # Calcule la confiance moyenne du mot
                            word_confidence = sum([symbol.confidence for symbol in word.symbols]) / len(word.symbols)
                            # Si la confiance est en deça du seuil, ajoute le mot entre crochets
                            if word_confidence < confidence_threshold:
                                detected_text += f"[{word_text}]"
                            # Sinon, ajoute le mot tel quel
                            else:
                                detected_text += word_text
                            # Si le dernier symbole du mot a un detected_break de type LINE_BREAK, ajoute un saut de ligne
                            if word.symbols[-1].property.detected_break.type_ == vision_v1.TextAnnotation.DetectedBreak.BreakType.LINE_BREAK:
                                detected_text += "\n"
                            else:
                                # Ajoute un espace après chaque mot qui n'est pas à la fin d'une ligne
                                detected_text += " "

            st.session_state['detected_text'] = detected_text

    # print("avant affichage textarea detected_text");affiche_session_state()

# if st.session_state['detected_text'] !="":
    #on récupère la dernière version du texte détecté (éventuellement modifié par l'utilisateur)
    detected_text = st.session_state['detected_text']
    # Compte le nombre de lignes dans detected_text
    num_lines =detected_text.count('\n') + len(detected_text) // 80  
    # print("Nombre de lignes : ", num_lines)
    # Calcule la hauteur en pixels en multipliant le nombre de lignes par une valeur fixe
    height_in_px = num_lines * 15

    css = f'''
    <style>
        .stTextArea textarea[aria-label='texte lu par Google Vision Cloud'] {{
            height: {height_in_px}px;   
            width:60%;
            margin-left:20%;
            font-size: 0.8em;       
        }}
    </style>
    '''
    st.write(css, unsafe_allow_html=True) 
    st.text_area('texte lu par Google Vision Cloud', key='detected_text')

    ########################################################################################
    # choix du system_prompt (rôle) à utiliser pour l'appel à l'api OpenAI
    ########################################################################################

    # Exécuter la requête pour récupérer les données de la table qcm_prompts_openai
    #on ne récupère que les lignes qui ont été créées par l'utilisateur connecté ou les lignes qui n'ont pas de user
    query = "SELECT name, content, user, visibility,description  FROM OCR.prompt_gpt WHERE (user='"+ username +"' OR visibility='public') AND type='system_prompt' ORDER BY name"
    query_job = client.query(query)
    # Convertir le résultat de la requête en un DataFrame pandas
    df = query_job.to_dataframe()
    # Convertir le DataFrame en une liste de dictionnaires
    rows = df.to_dict('records')
    # Créer une liste des noms des system_prompts
    system_prompt_names = [system_prompt['name'] for system_prompt in rows]

    # Sélectionner un nom de system_prompt à partir de la liste déroulante

    selected_system_prompt_name = st.selectbox('choisir un prompt système (rôle)', system_prompt_names, key='select_system_prompt',label_visibility='visible')

    # Trouver le contenu et le créateur (user) du system_prompt correspondant dans les données récupérées de la base de données
    #selected_system_prompt est un tableau à deux éléments :le name et le content du system_prompt
    selected_system_prompt = next(system_prompt for system_prompt in rows if system_prompt['name'] == selected_system_prompt_name)

    selected_system_prompt_content = selected_system_prompt['content']
    selected_system_prompt_user = selected_system_prompt['user']
    selected_system_prompt_description = selected_system_prompt['description']
    selected_system_prompt_visibility = selected_system_prompt['visibility']

    
    # Remplacer les caractères < et > par leurs entités HTML correspondantes
    selected_system_prompt_content = selected_system_prompt_content.replace('<', '&lt;').replace('>', '&gt;')
    # Remplacer \n par <br/> dans selected_system_prompt_content
    selected_system_prompt_content = selected_system_prompt_content.replace('\n', '<br/>')

    # Afficher le contenu du system_prompt sélectionné dans une zone de texte    
    # st.markdown("prompt system sélectionné:")
    st.markdown(f'<div class="system_prompt">{selected_system_prompt_content}</div>', unsafe_allow_html=True)

        # Initialise l'état d'affichage si ce n'est pas déjà fait
    if 'show_system_prompt' not in st.session_state:
        st.session_state['show_system_prompt'] = False

    # Crée le bouton
    if st.button('Affiche/Masque les détails', key='edit_system_prompt'):
        # Inverse l'état d'affichage lorsque le bouton est cliqué
        st.session_state['show_system_prompt'] = not st.session_state['show_system_prompt']

    if st.session_state['show_system_prompt']:
        if selected_system_prompt_user != username:
            st.write("Ce system_prompt est en lecture seule, vous pouvez cliquer sur 'créer un nouveau system_prompt' pour en faire une copie éditable.")
        else:
            st.write("Créé par : ", selected_system_prompt_user)

        st.write("Visibilité : ", selected_system_prompt_visibility)

        if selected_system_prompt_description is not None:
            selected_system_prompt_description = html.escape(selected_system_prompt_description)
        st.markdown("Description du system_prompt sélectionné dans la liste:")
        st.markdown(f'<div class="system_prompt" style="white-space: pre-wrap; margin-bottom:20px">{selected_system_prompt_description}</div>', unsafe_allow_html=True)

        ########################################################################################
        # Ajouter un bouton "Modifier le system_prompt"
        if selected_system_prompt_user == username: #seul le créateur du system_prompt peut le modifier
            if st.button('Modifier ce system_prompt', key='edit_above_system_prompt'):
                #ce drapeau editing est utilisé pour qu'au rechargement de la page, le formulaire d'édition soit affiché
                st.session_state['system_prompt_editing'] = True

            if st.session_state.get('system_prompt_editing', False):  #false = valeur par défaut
                # print("ouverture du formulaire d'édition du system_prompt sélectionné")

                with st.form(key='edit_form_system_prompt'):

                    # Ajouter un bouton "Enregistrer"
                    system_prompt_save_button = st.form_submit_button('Enregistrer les modifications')

                    # Ajouter un bouton "Annuler"
                    system_prompt_cancel_button = st.form_submit_button('Fermer le formulaire sans enregistrer les modifications')

                    # Ajouter un nouveau nom de system_prompt
                    st.session_state['new_system_prompt_name'] = st.text_input('Modifier le nom du system_prompt', value=selected_system_prompt['name'], key='edit_system_prompt_name')

                    #ajouter un choix de visibilité (public ou privé)
                    st.session_state['new_system_prompt_visibility'] = st.radio("Visibilité du system_prompt", ("public", "private"), key='edit_modify_system_prompt_visibility',label_visibility='hidden', index=("public", "private").index(selected_system_prompt['visibility']))

                    #ajouter une description du system_prompt
                    st.session_state['new_system_prompt_description'] = st.text_area('Description du system_prompt', value=selected_system_prompt['description'], key='edit_system_prompt_description',height=500)
                    
                    # Ajouter un nouveau contenu de system_prompt
                    st.session_state['new_system_prompt_content'] = st.text_area('Modifier le system_prompt', value=selected_system_prompt['content'], key='edit_system_prompt_content', height=500)

                
                    ########################################################################################

                    if system_prompt_cancel_button:
                        # print("cancel edited system_prompt")
                        st.session_state['system_prompt_editing'] = False
                        st.experimental_rerun()

                    # Sauvegarder les modifications apportées au system_prompt sélectionné
                    if system_prompt_save_button:
                        # print("save edited system_prompt")
                        new_system_prompt_name = st.session_state.get('new_system_prompt_name')
                        new_system_prompt_content = st.session_state.get('new_system_prompt_content')
                        new_system_prompt_visibility = st.session_state.get('new_system_prompt_visibility')
                        new_system_prompt_description = st.session_state.get('new_system_prompt_description')
                        
                        # print(new_system_prompt_name)

                        if new_system_prompt_name.strip() and new_system_prompt_content.strip():
                                
                            # Mettre à jour la table
                            query = """
                                UPDATE `OCR.prompt_gpt`
                                SET type='system_prompt', name = @new_system_prompt_name, content = @new_system_prompt_content, visibility = @new_system_prompt_visibility, description = @new_system_prompt_description
                                WHERE name = @selected_system_prompt_name AND user = @username
                            """
                            params = [
                                bigquery.ScalarQueryParameter('new_system_prompt_name', 'STRING', new_system_prompt_name),
                                bigquery.ScalarQueryParameter('new_system_prompt_content', 'STRING', new_system_prompt_content),
                                bigquery.ScalarQueryParameter('new_system_prompt_visibility', 'STRING', new_system_prompt_visibility),
                                bigquery.ScalarQueryParameter('new_system_prompt_description', 'STRING', new_system_prompt_description),
                                bigquery.ScalarQueryParameter('selected_system_prompt_name', 'STRING', selected_system_prompt_name),
                                bigquery.ScalarQueryParameter('username', 'STRING', username),
                            ]
                            job_config = bigquery.QueryJobConfig()
                            job_config.query_parameters = params
                            client.query(query, job_config=job_config)
                            
                            # print("mise à jour de selected_system_prompt")
        
                            st.session_state['system_prompt_editing'] = False
                            with st.spinner('Mise à jour des données...'):
                                time.sleep(temps_d_attente)
                            st.experimental_rerun()


        ########################################################################################

        # Ajouter un bouton "Supprimer" seulement s'il y a au moins deux system_prompts et si on est le créateur du system_prompt
        if len(rows) > 1 and selected_system_prompt_user != "":
            if st.button('Supprimer ce system_prompt (n\'oubliez pas de cocher la confirmation)', key='delete_system_prompt'):
                st.session_state['system_prompt_confirm_delete'] = True  # Change this to True

        # Si le bouton "Supprimer" a été cliqué, afficher une case à cocher pour la confirmation
        if st.session_state.get('system_prompt_confirm_delete', False): # (false : valeur par défaut)
            confirm = st.checkbox('Confirmer la suppression', key='system_prompt_confirm_delete_checkbox')
            if confirm:

                # Supprimer le system_prompt sélectionné de la table
                query = """
                    DELETE FROM `OCR.prompt_gpt`
                    WHERE name = @selected_system_prompt_name AND user = @username AND type='system_prompt'
                """
                params = [
                    bigquery.ScalarQueryParameter('selected_system_prompt_name', 'STRING', selected_system_prompt_name),
                    bigquery.ScalarQueryParameter('username', 'STRING', username),
                ]
                job_config = bigquery.QueryJobConfig()
                job_config.query_parameters = params
                client.query(query, job_config=job_config)

                # se rappeler que la case à cocher de confirmation doit etre masquée
                st.session_state['system_prompt_confirm_delete'] = False
                with st.spinner('Mise à jour des données...'):
                    time.sleep(temps_d_attente)
                st.experimental_rerun() 
            

        ########################################################################################
        if st.button('Créer un nouveau system_prompt à partir de celui-là', key="add_new_system_prompt"):
            #ce drapeau editing est utilisé pour qu'au rechargement de la page, le formulaire d'édition soit affiché
            st.session_state['form_new_system_prompt'] = True

        if st.session_state.get('form_new_system_prompt', False):

            with st.form(key='system_prompt_new_form'):

                # Ajouter un bouton "Enregistrer"
                save_button_new_system_prompt = st.form_submit_button('Enregistrer ce nouveau system_prompt')

                # Ajouter un bouton "Annuler"
                cancel_button_new_system_prompt = st.form_submit_button('Annuler la création du nouveau system_prompt')

            # Ajouter un nouveau nom de system_prompt (par défaut celui du system_prompt sélectionné, pour simplifier la duplication)
                selected_system_prompt_name = selected_system_prompt_name + " [copie " + username + "]"
                # Ajouter un nouveau nom de system_prompt
                st.session_state['new_system_prompt_name'] = st.text_input('nom du system_prompt', value=selected_system_prompt['name'], key='edit_new_system_prompt_name')

                #ajouter un choix de visibilité (public ou privé)
                st.session_state['new_system_prompt_visibility'] = st.radio("Visibilité du system_prompt", ("public", "private"), key='edit_new_system_prompt_visibility',label_visibility='hidden', index=("public", "private").index(selected_system_prompt['visibility']))

                #ajouter une description du system_prompt
                st.session_state['new_system_prompt_description'] = st.text_area('Description du system_prompt', value=selected_system_prompt['description'], key='edit_system_prompt_description',height=500)
                
                # Ajouter un nouveau contenu de system_prompt
                st.session_state['new_system_prompt_content'] = st.text_area('Modifier le system_prompt', value=selected_system_prompt['content'], key='edit_system_prompt_content', height=500)

            
                ########################################################################################

                if cancel_button_new_system_prompt:
                    st.session_state['form_new_system_prompt'] = False
                    st.experimental_rerun()

                # Sauvegarder le nouveau system_prompt
                if save_button_new_system_prompt:
                    new_system_prompt_name = st.session_state.get('new_system_prompt_name')
                    new_system_prompt_content = st.session_state.get('new_system_prompt_content')
                    new_system_prompt_visibility = st.session_state.get('new_system_prompt_visibility')
                    new_system_prompt_description = st.session_state.get('new_system_prompt_description')
                    # print(new_system_prompt_name)

                    # Vérifier si une entrée avec le même name et user existe déjà
                    query = """
                        SELECT * FROM `OCR.prompt_gpt`
                        WHERE name = @new_system_prompt_name AND type='system_prompt'
                    """
                    params = [
                        bigquery.ScalarQueryParameter('new_system_prompt_name', 'STRING', new_system_prompt_name),                    
                    ]
                    job_config = bigquery.QueryJobConfig()
                    job_config.query_parameters = params
                    
                    results = client.query(query, job_config=job_config)
                    rows = list(results.result())
                    existing_entry = rows[0] if rows else None

                    if new_system_prompt_name.strip() and new_system_prompt_content.strip() and not existing_entry:
                    
                        query = """
                            INSERT INTO `test-big-query-janv-2019.OCR.prompt_gpt` (name, content, user, visibility, description,type)
                            VALUES (@new_system_prompt_name, @new_system_prompt_content, @username, @new_system_prompt_visibility, @new_system_prompt_description,'system_prompt')
                        """
                        params = [
                            bigquery.ScalarQueryParameter('new_system_prompt_name', 'STRING', new_system_prompt_name),
                            bigquery.ScalarQueryParameter('new_system_prompt_content', 'STRING', new_system_prompt_content),
                            bigquery.ScalarQueryParameter('username', 'STRING', username),
                            bigquery.ScalarQueryParameter('new_system_prompt_visibility', 'STRING', new_system_prompt_visibility),
                            bigquery.ScalarQueryParameter('new_system_prompt_description', 'STRING', new_system_prompt_description),
                        ]
                        job_config = bigquery.QueryJobConfig()
                        job_config.query_parameters = params
                        client.query(query, job_config=job_config)

                        st.session_state['form_new_system_prompt'] = False
                        with st.spinner('Mise à jour des données...'):
                            time.sleep(temps_d_attente)
                        st.experimental_rerun() #forcer le rechargement de la page pour masquer le formulaire de création de system_prompt



    #print("avant affichage éventuel du bouton GPT");affiche_session_state()

      ########################################################################################
    # choix du user_prompt (consigne utilisateur) à utiliser pour l'appel à l'api OpenAI
    ##########################################################################################

    # Exécuter la requête pour récupérer les données de la table qcm_prompts_openai
    #on ne récupère que les lignes qui ont été créées par l'utilisateur connecté ou les lignes qui n'ont pas de user
    query = "SELECT name, content, user, visibility,description  FROM OCR.prompt_gpt WHERE (user='"+ username +"' OR visibility='public') AND type='user_prompt' ORDER BY name"
    query_job = client.query(query)
    # Convertir le résultat de la requête en un DataFrame pandas
    df = query_job.to_dataframe()
    # Convertir le DataFrame en une liste de dictionnaires
    rows = df.to_dict('records')
    # Créer une liste des noms des user_prompts
    user_prompt_names = [user_prompt['name'] for user_prompt in rows]

    # Sélectionner un nom de user_prompt à partir de la liste déroulante
    selected_user_prompt_name = st.selectbox('choisir un prompt utilisateur', user_prompt_names, key='select_user_prompt',label_visibility='visible')

    # Trouver le contenu et le créateur (user) du user_prompt correspondant dans les données récupérées de la base de données
    #selected_user_prompt est un tableau à deux éléments :le name et le content du user_prompt
    selected_user_prompt = next(user_prompt for user_prompt in rows if user_prompt['name'] == selected_user_prompt_name)

    selected_user_prompt_content = selected_user_prompt['content']
    selected_user_prompt_user = selected_user_prompt['user']
    selected_user_prompt_description = selected_user_prompt['description']
    selected_user_prompt_visibility = selected_user_prompt['visibility']

        # Remplacer les caractères < et > par leurs entités HTML correspondantes
    selected_user_prompt_content = selected_user_prompt_content.replace('<', '&lt;').replace('>', '&gt;')
    # Remplacer \n par <br/> dans selected_user_prompt_content
    selected_user_prompt_content = selected_user_prompt_content.replace('\n', '<br/>')

    # Afficher le contenu du user_prompt sélectionné dans une zone de texte    
    st.markdown(f'<div class="user_prompt">{selected_user_prompt_content}</div>', unsafe_allow_html=True)


    if 'show_user_prompt' not in st.session_state:
        st.session_state['show_user_prompt'] = False

    if st.button('Affiche/Masque les détails', key='edit_user_prompt'):
        # Inverse l'état d'affichage lorsque le bouton est cliqué
        st.session_state['show_user_prompt'] = not st.session_state['show_user_prompt']

    if st.session_state['show_user_prompt']:
        if selected_user_prompt_user != username:
            st.write("Ce user_prompt est en lecture seule, vous pouvez cliquer sur 'créer un nouveau user_prompt' pour en faire une copie éditable.")
        else:
            st.write("Créé par : ", selected_user_prompt_user)

        st.write("Visibilité : ", selected_user_prompt_visibility)

        if selected_user_prompt_description is not None:
            selected_user_prompt_description = html.escape(selected_user_prompt_description)
        st.markdown("Description du user_prompt:")
        st.markdown(f'<div class="user_prompt" style="white-space: pre-wrap; margin-bottom:20px">{selected_user_prompt_description}</div>', unsafe_allow_html=True)




        ########################################################################################
        # Ajouter un bouton "Modifier le user_prompt"
        if selected_user_prompt_user == username: #seul le créateur du user_prompt peut le modifier
            if st.button('Modifier ce user_prompt', key='edit_above_user_prompt'):
                #ce drapeau editing est utilisé pour qu'au rechargement de la page, le formulaire d'édition soit affiché
                st.session_state['user_prompt_editing'] = True

            if st.session_state.get('user_prompt_editing', False):  #false = valeur par défaut
                # print("ouverture du formulaire d'édition du user_prompt sélectionné")

                with st.form(key='edit_form_user_prompt'):

                    # Ajouter un bouton "Enregistrer"
                    user_prompt_save_button = st.form_submit_button('Enregistrer les modifications')

                    # Ajouter un bouton "Annuler"
                    user_prompt_cancel_button = st.form_submit_button('Fermer le formulaire sans enregistrer les modifications')
                    # Ajouter un nouveau nom de user_prompt
                    st.session_state['new_user_prompt_name'] = st.text_input('Modifier le nom du user_prompt', value=selected_user_prompt['name'], key='edit_user_prompt_name')

                    #ajouter un choix de visibilité (public ou privé)
                    st.session_state['new_user_prompt_visibility'] = st.radio("Visibilité du user_prompt", ("public", "private"), key='edit_modify_user_prompt_visibility',label_visibility='hidden', index=("public", "private").index(selected_user_prompt['visibility']))

                    #ajouter une description du user_prompt
                    st.session_state['new_user_prompt_description'] = st.text_area('Description du user_prompt', value=selected_user_prompt['description'], key='edit_user_prompt_description',height=500)
                    
                    # Ajouter un nouveau contenu de user_prompt
                    st.session_state['new_user_prompt_content'] = st.text_area('Modifier le user_prompt', value=selected_user_prompt['content'], key='edit_user_prompt_content', height=500)

                
                    ########################################################################################

                    if user_prompt_cancel_button:
                        # print("cancel edited user_prompt")
                        st.session_state['user_prompt_editing'] = False
                        st.experimental_rerun()

                    # Sauvegarder les modifications apportées au user_prompt sélectionné
                    if user_prompt_save_button:
                        # print("save edited user_prompt")
                        new_user_prompt_name = st.session_state.get('new_user_prompt_name')
                        new_user_prompt_content = st.session_state.get('new_user_prompt_content')
                        new_user_prompt_visibility = st.session_state.get('new_user_prompt_visibility')
                        new_user_prompt_description = st.session_state.get('new_user_prompt_description')
                        
                        # print(new_user_prompt_name)

                        if new_user_prompt_name.strip() and new_user_prompt_content.strip():
                                
                            # Mettre à jour la table
                            query = """
                                UPDATE `OCR.prompt_gpt`
                                SET type='user_prompt', name = @new_user_prompt_name, content = @new_user_prompt_content, visibility = @new_user_prompt_visibility, description = @new_user_prompt_description
                                WHERE name = @selected_user_prompt_name AND user = @username
                            """
                            params = [
                                bigquery.ScalarQueryParameter('new_user_prompt_name', 'STRING', new_user_prompt_name),
                                bigquery.ScalarQueryParameter('new_user_prompt_content', 'STRING', new_user_prompt_content),
                                bigquery.ScalarQueryParameter('new_user_prompt_visibility', 'STRING', new_user_prompt_visibility),
                                bigquery.ScalarQueryParameter('new_user_prompt_description', 'STRING', new_user_prompt_description),
                                bigquery.ScalarQueryParameter('selected_user_prompt_name', 'STRING', selected_user_prompt_name),
                                bigquery.ScalarQueryParameter('username', 'STRING', username),
                            ]
                            job_config = bigquery.QueryJobConfig()
                            job_config.query_parameters = params
                            client.query(query, job_config=job_config)
                            
                            # print("mise à jour de selected_user_prompt")
        
                            st.session_state['user_prompt_editing'] = False
                            with st.spinner('Mise à jour des données...'):
                                time.sleep(temps_d_attente)
                            st.experimental_rerun()


        ########################################################################################

        # Ajouter un bouton "Supprimer" seulement s'il y a au moins deux user_prompts et si on est le créateur du user_prompt
        if len(rows) > 1 and selected_user_prompt_user != "":
            if st.button('Supprimer ce user_prompt (n\'oubliez pas de cocher la confirmation)', key='delete_user_prompt'):
                st.session_state['user_prompt_confirm_delete'] = True  # Change this to True

        # Si le bouton "Supprimer" a été cliqué, afficher une case à cocher pour la confirmation
        if st.session_state.get('user_prompt_confirm_delete', False): # (false : valeur par défaut)
            user_prompt_confirm = st.checkbox('Confirmer la suppression', key='user_prompt_confirm_delete_checkbox')
            if user_prompt_confirm:

                # Supprimer le user_prompt sélectionné de la table
                query = """
                    DELETE FROM `OCR.prompt_gpt`
                    WHERE name = @selected_user_prompt_name AND user = @username AND type='user_prompt'
                """
                params = [
                    bigquery.ScalarQueryParameter('selected_user_prompt_name', 'STRING', selected_user_prompt_name),
                    bigquery.ScalarQueryParameter('username', 'STRING', username),
                ]
                job_config = bigquery.QueryJobConfig()
                job_config.query_parameters = params
                client.query(query, job_config=job_config)

                # se rappeler que la case à cocher de confirmation doit etre masquée
                st.session_state['user_prompt_confirm_delete'] = False
                with st.spinner('Mise à jour des données...'):
                    time.sleep(temps_d_attente)
                st.experimental_rerun() 
            

        ########################################################################################
        if st.button('Créer un nouveau user_prompt à partir de celui-là', key="add_new_user_prompt"):
            #ce drapeau editing est utilisé pour qu'au rechargement de la page, le formulaire d'édition soit affiché
            st.session_state['form_new_user_prompt'] = True

        if st.session_state.get('form_new_user_prompt', False):

            with st.form(key='user_prompt_new_form'):

                # Ajouter un bouton "Enregistrer"
                save_button_new_user_prompt = st.form_submit_button('Enregistrer ce nouveau user_prompt')

                # Ajouter un bouton "Annuler"
                cancel_button_new_user_prompt = st.form_submit_button('Annuler la création du nouveau user_prompt')

            # Ajouter un nouveau nom de user_prompt (par défaut celui du user_prompt sélectionné, pour simplifier la duplication)
                selected_user_prompt_name = selected_user_prompt_name + " [copie " + username + "]"
                # Ajouter un nouveau nom de user_prompt
                st.session_state['new_user_prompt_name'] = st.text_input('nom du user_prompt', value=selected_user_prompt['name'], key='edit_new_user_prompt_name')


                #ajouter un choix de visibilité (public ou privé)
                st.session_state['new_user_prompt_visibility'] = st.radio("Visibilité du user_prompt", ("public", "private"), key='edit_new_user_prompt_visibility',label_visibility='hidden', index=("public", "private").index(selected_user_prompt['visibility']))

                #ajouter une description du user_prompt
                st.session_state['new_user_prompt_description'] = st.text_area('Description du user_prompt', value=selected_user_prompt['description'], key='edit_user_prompt_description',height=500)
                
                # Ajouter un nouveau contenu de user_prompt
                st.session_state['new_user_prompt_content'] = st.text_area('Modifier le user_prompt', value=selected_user_prompt['content'], key='edit_user_prompt_content', height=500)

            
                ########################################################################################

                if cancel_button_new_user_prompt:
                    st.session_state['form_new_user_prompt'] = False
                    st.experimental_rerun()

                # Sauvegarder le nouveau user_prompt
                if save_button_new_user_prompt:
                    new_user_prompt_name = st.session_state.get('new_user_prompt_name')
                    new_user_prompt_content = st.session_state.get('new_user_prompt_content')
                    new_user_prompt_visibility = st.session_state.get('new_user_prompt_visibility')
                    new_user_prompt_description = st.session_state.get('new_user_prompt_description')
                    # print(new_user_prompt_name)

                    # Vérifier si une entrée avec le même name et user existe déjà
                    query = """
                        SELECT * FROM `OCR.prompt_gpt`
                        WHERE name = @new_user_prompt_name AND type='user_prompt'
                    """
                    params = [
                        bigquery.ScalarQueryParameter('new_user_prompt_name', 'STRING', new_user_prompt_name),                    
                    ]
                    job_config = bigquery.QueryJobConfig()
                    job_config.query_parameters = params
                    
                    results = client.query(query, job_config=job_config)
                    rows = list(results.result())
                    existing_entry = rows[0] if rows else None

                    if new_user_prompt_name.strip() and new_user_prompt_content.strip() and not existing_entry:
                    
                        # # Ajouter le nouveau user_prompt à la liste des user_prompts
                        # data.append({'name': new_user_prompt_name, 'content': new_user_prompt_content})

                        # # Sauvegarder les données dans le fichier JSON
                        # with open('user_prompts.json', 'w') as f:
                        #     json.dump(data, f)

                        query = """
                            INSERT INTO `test-big-query-janv-2019.OCR.prompt_gpt` (name, content, user, visibility, description,type)
                            VALUES (@new_user_prompt_name, @new_user_prompt_content, @username, @new_user_prompt_visibility, @new_user_prompt_description,'user_prompt')
                        """
                        params = [
                            bigquery.ScalarQueryParameter('new_user_prompt_name', 'STRING', new_user_prompt_name),
                            bigquery.ScalarQueryParameter('new_user_prompt_content', 'STRING', new_user_prompt_content),
                            bigquery.ScalarQueryParameter('username', 'STRING', username),
                            bigquery.ScalarQueryParameter('new_user_prompt_visibility', 'STRING', new_user_prompt_visibility),
                            bigquery.ScalarQueryParameter('new_user_prompt_description', 'STRING', new_user_prompt_description),
                        ]
                        job_config = bigquery.QueryJobConfig()
                        job_config.query_parameters = params
                        client.query(query, job_config=job_config)

                        st.session_state['form_new_user_prompt'] = False
                        with st.spinner('Mise à jour des données...'):
                            time.sleep(temps_d_attente)
                        st.experimental_rerun() #forcer le rechargement de la page pour masquer le formulaire de création de user_prompt



    # user_content = st.text_area('Entrez le contenu du rôle utilisateur ici', value=consigne)

    if st.button('Lancer le traitement par GPT', type='primary'):
        #on vient juste d'appuyer sur le bouton : on corrige le texte avec GPT  
            # Utilise GPT-3 pour corriger le texte lu par google vision

        #print("avant affichage textarea corrected_text");affiche_session_state()

        #on utilise la dernière version du text_area "detected_text" pour corriger le texte, dans le cas où l'utilisateur aurait modifié le texte
        detected_text = st.session_state['detected_text']

        user_content = selected_user_prompt_content + ' Texte à corriger :' + detected_text

        completion = clientOpenAI.chat.completions.create(
            # model="gpt-3.5-turbo",
            model="gpt-3.5-turbo-0125",
            messages=[
                {"role": "system", "content": selected_system_prompt_content},
                {"role": "user", "content": user_content}
            ]
        )
        corrected_text = completion.choices[0].message.content
        #on mémorise le texte corrigé
        st.session_state['corrected_text'] = corrected_text

    #print("avant affichage éventuel du bouton synthèse vocale");affiche_session_state()


    if st.session_state['corrected_text'] !="":

        corrected_text = st.session_state['corrected_text']

        num_lines = len(corrected_text) // 50
        height_in_px = num_lines *16
        css = f'''
        <style>
            .stTextArea textarea[aria-label='texte corrigé par GPT'] {{
            height: {height_in_px}px;       
            font-size: 0.8em;         
            }}
        </style>
        '''
        st.write(css, unsafe_allow_html=True) 

        # Crée deux colonnes
        col1, col2 = st.columns(2)

        # Affiche le texte corrigé dans la première colonne
        col1.text_area('texte corrigé par GPT', key='corrected_text')

        # Affiche l'image dans la deuxième colonne
        if uploaded_file is not None:
            col2.image(uploaded_file, caption='Image téléchargée.')
        
        if st.button('Générer la synthèse vocale'):

            #on vient juste d'appuyer sur le bouton : on génère la synthèse vocale du texte corrigé, en utilisant la dernière version du texte corrigé

            # Synthèse vocale du texte corrigé
            voice = texttospeech.VoiceSelectionParams(
                language_code="fr-FR", ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            )
            clientTextToSpeech = texttospeech.TextToSpeechClient(credentials=credentials)
            synthesis_input = texttospeech.SynthesisInput(text=corrected_text)
            response = clientTextToSpeech.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )
            # Stocke l'audio dans st.session_state
            st.session_state['audio'] = response.audio_content

        # Affiche un lecteur audio dans la page web qui joue le fichier MP3
        if 'audio' in st.session_state:
            st.audio(st.session_state['audio'], format='audio/mp3')




