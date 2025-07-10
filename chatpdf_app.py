#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jul  8 00:25:42 2025

@author: panasabena
"""

import streamlit as st
import requests
import json
import os
import base64
import glob

API_URL = "http://localhost:8000"

st.title("Chat-IA (con autenticación y multiusuario)")

# --- Autenticación ---
def login(username, password):
    response = requests.post(f"{API_URL}/login", json={"username": username, "password": password})
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        return None

def register(username, email, password):
    response = requests.post(f"{API_URL}/register", json={"username": username, "email": email, "password": password})
    if response.status_code == 200:
        return response.json()["access_token"], None  # Siempre dos valores
    else:
        try:
            return None, response.json().get("detail", response.text)
        except Exception:
            return None, response.text

# --- Estado de sesión ---
if "jwt" not in st.session_state:
    st.session_state.jwt = None
if "username" not in st.session_state:
    st.session_state.username = None
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "conversations" not in st.session_state:
    st.session_state.conversations = []
if "historial" not in st.session_state:
    st.session_state.historial = []
if "pdf_uploaded" not in st.session_state:
    st.session_state.pdf_uploaded = False

# --- Login/Registro UI ---
def auth_ui():
    st.subheader("Iniciar sesión o registrarse")
    tab1, tab2 = st.tabs(["Iniciar sesión", "Registrarse"])
    with tab1:
        username = st.text_input("Usuario", key="login_user")
        password = st.text_input("Contraseña", type="password", key="login_pass")
        if st.button("Iniciar sesión"):
            token = login(username, password)
            if token:
                st.session_state.jwt = token
                st.session_state.username = username
                st.success("¡Sesión iniciada!")
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")
    with tab2:
        username = st.text_input("Usuario", key="reg_user")
        email = st.text_input("Email", key="reg_email")
        password = st.text_input("Contraseña", type="password", key="reg_pass")
        if st.button("Registrarse"):
            token, error_msg = register(username, email, password)
            if token:
                st.session_state.jwt = token
                st.session_state.username = username
                st.success("¡Registro exitoso!")
                st.rerun()
            else:
                st.error(error_msg or "No se pudo registrar el usuario")

if not st.session_state.jwt:
    auth_ui()
    st.stop()

headers = {"Authorization": f"Bearer {st.session_state.jwt}"}

# --- Gestión de conversaciones ---
def cargar_conversaciones():
    response = requests.get(f"{API_URL}/conversations/", headers=headers)
    if response.status_code == 200:
        st.session_state.conversations = response.json()
    else:
        st.session_state.conversations = []

def crear_conversacion(pdf_name=None, title="Nueva conversación"):
    data = {"pdf_name": pdf_name or "", "title": title}
    response = requests.post(f"{API_URL}/conversations/", data=data, headers=headers)
    if response.status_code == 200:
        cargar_conversaciones()
        return response.json()["id"]
    else:
        st.error("No se pudo crear la conversación")
        return None

def cargar_historial(conversation_id):
    response = requests.get(f"{API_URL}/conversations/{conversation_id}/messages/", headers=headers)
    if response.status_code == 200:
        st.session_state.historial = response.json()
    else:
        st.session_state.historial = []

# --- Sidebar: gestión de conversaciones ---
st.sidebar.header(f"Usuario: {st.session_state.username}")
if st.sidebar.button("Cerrar sesión"):
    st.session_state.jwt = None
    st.session_state.username = None
    st.session_state.conversation_id = None
    st.rerun()

if st.sidebar.button("Actualizar conversaciones") or not st.session_state.conversations:
    cargar_conversaciones()

# Listar conversaciones
conv_options = {str(conv["id"]): f"{conv['title']} ({conv['pdf_name'] or 'IA'})" for conv in st.session_state.conversations}
conv_keys = list(conv_options.keys())
if conv_keys:
    selected = st.sidebar.selectbox("Conversaciones", conv_keys, format_func=lambda k: conv_options[k])
    st.session_state.conversation_id = int(selected)
    cargar_historial(st.session_state.conversation_id)
else:
    st.sidebar.info("No hay conversaciones. Crea una nueva.")

# Crear nueva conversación
st.sidebar.markdown("---")
new_title = st.sidebar.text_input("Título de la conversación")
if st.sidebar.button("Nueva conversación IA"):
    # Asegura título único
    base_title = new_title or "Chat IA"
    titles = [conv["title"] for conv in st.session_state.conversations]
    unique_title = base_title
    count = 1
    while unique_title in titles:
        count += 1
        unique_title = f"{base_title} {count}"
    conv_id = crear_conversacion(title=unique_title)
    if conv_id:
        st.session_state.conversation_id = conv_id
        cargar_historial(conv_id)
        st.rerun()

# Subir PDF y crear conversación con PDF
st.sidebar.markdown("---")
archivo_pdf = st.sidebar.file_uploader("Subir PDF", type=["pdf"], key="uploader")
if archivo_pdf is not None and not st.session_state.pdf_uploaded:
    with st.spinner("Procesando PDF..."):
        files = {"file": (archivo_pdf.name, archivo_pdf, "application/pdf")}
        response = requests.post(f"{API_URL}/upload_pdf/", files=files, headers=headers)
        if response.status_code == 200:
            st.sidebar.success(f"PDF '{archivo_pdf.name}' procesado correctamente.")
            # Asegura título único para PDF
            base_title = new_title or archivo_pdf.name
            titles = [conv["title"] for conv in st.session_state.conversations]
            unique_title = base_title
            count = 1
            while unique_title in titles:
                count += 1
                unique_title = f"{base_title} {count}"
            conv_id = crear_conversacion(pdf_name=archivo_pdf.name, title=unique_title)
            if conv_id:
                st.session_state.conversation_id = conv_id
                cargar_historial(conv_id)
                st.session_state.pdf_uploaded = True
                st.rerun()
        else:
            st.sidebar.error(f"Error al procesar PDF: {response.text}")
# Reset pdf_uploaded si no hay archivo
if archivo_pdf is None and st.session_state.pdf_uploaded:
    st.session_state.pdf_uploaded = False

# --- Chat principal ---
if st.session_state.conversation_id:
    cargar_historial(st.session_state.conversation_id)
    # Buscar la conversación seleccionada
    conv = next((c for c in st.session_state.conversations if c["id"] == st.session_state.conversation_id), None)
    if conv and conv.get("pdf_name"):
        pdf_path = os.path.join("pdfs", conv["pdf_name"])
        if os.path.exists(pdf_path):
            import streamlit.components.v1 as components
            st.markdown(f"**PDF asociado:** {conv['pdf_name']}")
            with open(pdf_path, "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode("utf-8")
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)
    # Botón para borrar conversación
    if st.button("🗑️ Borrar conversación"):
        response = requests.delete(f"{API_URL}/conversations/{st.session_state.conversation_id}", headers=headers)
        if response.status_code == 200:
            st.success("Conversación borrada")
            cargar_conversaciones()
            st.session_state.conversation_id = None
            st.session_state.historial = []
            st.rerun()
        else:
            st.error("No se pudo borrar la conversación")
    st.subheader(f"Conversación: {conv_options.get(str(st.session_state.conversation_id), 'Sin título')}")
    for item in st.session_state.historial:
        st.markdown("---")
        st.markdown(f"**Tú:** {item['question']}")
        st.markdown(f"**Bot:** {item['answer']}")
        if item.get("tokens_used") is not None:
            st.info(f"Tokens usados en el prompt: {item['tokens_used']}")
        if item.get("pages_referenced"):
            st.info(f"Páginas referenciadas: {item['pages_referenced']}")
    st.markdown("---")
    question = st.text_area("Escribe tu pregunta:")
    if st.button("Preguntar"):
        if not question:
            st.warning("Escribe una pregunta.")
        else:
            with st.spinner("Consultando..."):
                data = {"conversation_id": st.session_state.conversation_id, "question": question}
                response = requests.post(f"{API_URL}/chat/", data=data, headers=headers)
                if response.status_code == 200:
                    result = response.json()
                    st.session_state.historial.append({
                        "question": question,
                        "answer": result.get("answer", "Sin respuesta"),
                        "tokens_used": result.get("n_tokens"),
                        "pages_referenced": result.get("pages", [])
                    })
                    st.rerun()
                else:
                    st.error(f"Error: {response.text}")
else:
    st.info("Selecciona o crea una conversación para comenzar a chatear.")