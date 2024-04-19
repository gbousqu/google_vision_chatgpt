import streamlit as st

import sys

import subprocess
import sys


from google.cloud import vision_v1

from google.oauth2 import service_account
import io
import os
from openai import OpenAI
from google.cloud import texttospeech
import json

#à faire 
# mettre le contenu du json dans un fichier toml (comme dans le projet pdf_to_quiz)
#tester la version sur share.streamit.io

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

# # Chemin vers votre fichier de clés de service JSON
# key_path = "test-big-query-janv-2019-27bb26c617ae.json"

# # Crée des informations d'identification à partir du fichier de clés de service JSON
# credentials = service_account.Credentials.from_service_account_file(key_path)

gcp_service_account = st.secrets["gcp_service_account"]
service_account_info = json.loads(gcp_service_account)
# Créer des identifiants à partir des informations du compte de service
credentials = service_account.Credentials.from_service_account_info(service_account_info)

# Initialise le client Vision avec les informations d'identification
clientGoogleVision = vision_v1.ImageAnnotatorClient(credentials=credentials)

uploaded_file = st.file_uploader("Choisissez une image avec du texte à transcrire", type=["jpg", "jpeg","png"])

if uploaded_file is not None:
    st.image(uploaded_file, caption='Image téléchargée.',key='uploaded_image')

    if 'confidence_threshold' not in st.session_state:
        st.session_state.confidence_threshold = 0.8

    confidence_threshold = st.slider("Choisissez le seuil de confiance", 0.0, 1.0, st.session_state.confidence_threshold)

    st.session_state.confidence_threshold = confidence_threshold

    # Prépare l'image pour l'API Google Vision
    image = vision_v1.Image(content=uploaded_file.getvalue())
    
    # Crée un contexte d'image avec la langue "fr" (français)
    image_context = vision_v1.ImageContext(language_hints=["fr"])

    if st.button('Lancer la détection de texte'):
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

    if 'detected_text' in st.session_state:
        detected_text = st.session_state['detected_text']
        # Compte le nombre de lignes dans detected_text
        num_lines =detected_text.count('\n') + len(detected_text) // 80  
        # print("Nombre de lignes : ", num_lines)
        # Calcule la hauteur en pixels en multipliant le nombre de lignes par une valeur fixe
        # (par exemple, 20 pixels par ligne)
        height_in_px = num_lines * 24
        css = f'''
        <style>
            .stTextArea textarea[aria-label='texte lu par Google Vision Cloud'] {{
                height: {height_in_px}px;   
                width:60%;
                margin-left:20%           
            }}
        </style>
        '''
        st.write(css, unsafe_allow_html=True) 
        st.text_area('texte lu par Google Vision Cloud', value=detected_text)

        system_content = st.text_area('Entrez le contenu du rôle système ici', value="Tu es un correcteur professionnel, qui corrige des textes provenant d'OCR.")
        user_content = st.text_area('Entrez le contenu du rôle utilisateur ici', value=f"corrige  l'orthographe du texte. Respecte les mots et la syntaxe caractéristiques d'un texte de 1920.  Assure-toi que chaque mot et chaque phrase ait un sens.  Conserve les 'deux points' (:) quand tu en trouves. Aère le texte en paragraphes. Renvoie uniquement le texte corrigé, sans explication")
        user_content = user_content + ' Texte à corriger :' + st.session_state['detected_text']

        if st.button('Lancer le traitement par GPT'):
            #on vient juste d'appuyer sur le bouton : on corrige le texte avec GPT  
                # Utilise GPT-3 pour corriger le texte lu par google vision
            completion = clientOpenAI.chat.completions.create(
                # model="gpt-3.5-turbo",
                model="gpt-3.5-turbo-0125",
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}
                ]
            )
            corrected_text = completion.choices[0].message.content
            #on mémorise le texte corrigé
            st.session_state['corrected_text'] = corrected_text


        if 'corrected_text' in st.session_state:
            corrected_text = st.session_state['corrected_text']

            
            if st.button('Lancer la synthèse vocale'):
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
                # Affiche un lecteur audio dans la page web qui joue le fichier MP3
                st.audio(response.audio_content, format='audio/mp3')

            num_lines = len(corrected_text) // 50
            height_in_px = num_lines * 24
            css = f'''
            <style>
                .stTextArea textarea[aria-label='texte corrigé par GPT'] {{
                height: {height_in_px}px;                
                }}
            </style>
            '''
            st.write(css, unsafe_allow_html=True) 

             # Crée deux colonnes
            col1, col2 = st.columns(2)

            # Affiche le texte corrigé dans la première colonne
            col1.text_area('texte corrigé par GPT', value=corrected_text,key='texte corrigé par GPT')

            # Affiche l'image dans la deuxième colonne
            if uploaded_file is not None:
                col2.image(uploaded_file, caption='Image téléchargée.')


