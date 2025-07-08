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

st.title("Chat-IA")

UPLOAD_URL = "http://localhost:8000/upload_pdf/"
CHAT_URL = "http://localhost:8000/chat/"
INDICES_DIR = "indices"

IDIOMAS = {
    "Español": "español",
    "Inglés": "inglés",
    "Italiano": "italiano",
    "Portugués": "portugués",
    "Alemán": "alemán",
    "Chino": "chino"
}

MODELOS_OLLAMA = {
    "llama2": "Llama 2: General, bueno para tareas en inglés y español, rápido y eficiente.",
    "llama2-13b-chat": "Llama 2 13B Chat: Mejor comprensión de instrucciones, más preciso, multilingüe.",
    "mistral": "Mistral: Muy bueno para español y otros idiomas, sigue bien instrucciones.",
    "phi3": "Phi-3: Compacto, rápido, útil para respuestas cortas y tareas simples.",
    "gemma": "Gemma: Bueno para tareas generales y multilingües, sigue bien el contexto.",
    "llama3": "Llama 3: Última generación, mejor comprensión y contexto, multilingüe avanzado."
}

# Función para cargar historial desde archivo
def cargar_historial(pdf_name):
    nombre_archivo = f"historial_{pdf_name}.json"
    if os.path.exists(nombre_archivo):
        with open(nombre_archivo, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def guardar_historial(pdf_name, historial):
    nombre_archivo = f"historial_{pdf_name}.json"
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        json.dump(historial, f, ensure_ascii=False, indent=2)

def listar_pdfs_procesados():
    if not os.path.exists(INDICES_DIR):
        return []
    archivos = os.listdir(INDICES_DIR)
    pdfs = set()
    for f in archivos:
        if f.endswith(".index"):
            base = f[:-6]
            if os.path.exists(os.path.join(INDICES_DIR, base + ".chunks.txt")):
                pdfs.add(base)
    return sorted(list(pdfs))

def paginas_como_links(paginas):
    links = []
    for p in sorted(set(paginas)):
        # El link llama a una función de Streamlit para cambiar la página actual
        links.append(f'<a href="#" onclick="window.parent.postMessage({{type: \'streamlit:setComponentValue\', key: \'pagina_actual\', value: {p}}}, \'*\'); return false;">Página {p}</a>')
    return " | ".join(links)

# Drag and drop para subir PDF
txt = st.sidebar.text("Arrastra y suelta un PDF para procesarlo:")
archivo_pdf = st.sidebar.file_uploader("Subir PDF", type=["pdf"], key="uploader")
if archivo_pdf is not None:
    with st.spinner("Procesando PDF..."):
        files = {"file": (archivo_pdf.name, archivo_pdf, "application/pdf")}
        response = requests.post(UPLOAD_URL, files=files)
        if response.status_code == 200:
            st.sidebar.success(f"PDF '{archivo_pdf.name}' procesado correctamente.")
        else:
            st.sidebar.error(f"Error al procesar PDF: {response.text}")

pdfs_disponibles = listar_pdfs_procesados()
pdf_name = st.sidebar.selectbox("Selecciona el PDF para chatear:", pdfs_disponibles, key="pdf_selector")

# Botón para eliminar PDF seleccionado
delete_pdf_url = "http://localhost:8000/delete_pdf/"
if st.sidebar.button("Eliminar PDF seleccionado"):
    if pdf_name:
        with st.spinner(f"Eliminando '{pdf_name}'..."):
            response = requests.post(delete_pdf_url, data={"pdf_name": pdf_name})
            if response.status_code == 200:
                st.sidebar.success(f"'{pdf_name}' eliminado correctamente.")
                st.session_state['historial'] = []
                pdfs_disponibles = listar_pdfs_procesados()
                st.rerun()
            else:
                st.sidebar.error(f"Error al eliminar: {response.text}")

if 'pdf_actual' not in st.session_state or st.session_state['pdf_actual'] != pdf_name:
    st.session_state['historial'] = cargar_historial(pdf_name)
    st.session_state['pdf_actual'] = pdf_name

st.sidebar.header("Historial de chat")
if st.sidebar.button("Limpiar historial"):
    st.session_state['historial'] = []
    guardar_historial(pdf_name, [])

for i, item in enumerate(st.session_state['historial']):
    st.sidebar.markdown(f"**Tú:** {item['pregunta']}")
    if '$' in item['respuesta'] or '\\(' in item['respuesta'] or '\\[' in item['respuesta']:
        st.sidebar.markdown(f"$$\\displaystyle {item['respuesta']}$$", unsafe_allow_html=True)
    else:
        st.sidebar.markdown(f"**Bot:** {item['respuesta']}")

# Layout: PDF a la izquierda, chat a la derecha
col1, col2 = st.columns([7, 5])  # O prueba [8, 4], [9, 5], etc.

st.markdown(
    """
    <style>
    .main .block-container {
        padding-left: 0.5rem;
        padding-right: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)

def mostrar_pdf(pdf_path, page=None):
    with open(pdf_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    page_str = f"#page={page}" if page else ""
    pdf_display = f'''
        <iframe
            src="data:application/pdf;base64,{base64_pdf}{page_str}"
            width="100%" height="1200"
            type="application/pdf">
        </iframe>
    '''
    st.markdown(pdf_display, unsafe_allow_html=True)

with col1:
    st.subheader(f"Visualizador de PDF: {pdf_name}")
    pdf_path = os.path.join("pdfs", pdf_name)
    if os.path.exists(pdf_path):
        # Control de página
        if 'pagina_actual' not in st.session_state:
            st.session_state['pagina_actual'] = 1
        # Obtener número de páginas
        try:
            import PyPDF2
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                num_pages = len(reader.pages)
        except Exception:
            num_pages = 1
        mostrar_pdf(pdf_path, page=st.session_state['pagina_actual'])
    else:
        st.info("No se encontró el PDF seleccionado.")

with col2:
    st.subheader(f"Chateando con: {pdf_name}")
    idioma_seleccionado = st.selectbox("Selecciona el idioma de la respuesta:", list(IDIOMAS.keys()), index=0)
    modelo_seleccionado = st.selectbox("Selecciona el modelo de Ollama:", list(MODELOS_OLLAMA.keys()), index=0)
    st.info(MODELOS_OLLAMA[modelo_seleccionado])
    question = st.text_area("Escribe tu pregunta:")
    if st.button("Preguntar"):
        if not pdf_name or not question:
            st.warning("Por favor, selecciona un PDF y escribe una pregunta.")
        else:
            with st.spinner("Consultando..."):
                data = {
                    "pdf_name": pdf_name,
                    "question": question,
                    "language": IDIOMAS[idioma_seleccionado],
                    "ollama_model": modelo_seleccionado
                }
                try:
                    response = requests.post(CHAT_URL, data=data)
                    if response.status_code == 200:
                        result = response.json()
                        answer = result.get("answer", "Sin respuesta")
                        pages = result.get("pages", [])
                        st.session_state['ultima_respuesta'] = answer
                        st.session_state['ultima_paginas'] = pages
                        st.session_state['ultima_pregunta'] = question
                        st.session_state['historial'].append({"pregunta": question, "respuesta": answer})
                        guardar_historial(pdf_name, st.session_state['historial'])
                        if '$' in answer or '\\(' in answer or '\\[' in answer:
                            st.markdown("**Respuesta:**")
                            st.markdown(f"$$\\displaystyle {answer}$$", unsafe_allow_html=True)
                        else:
                            st.success(f"Respuesta: {answer}")
                        # Si hay páginas relevantes, mostrar info y navegar
                        if pages:
                            st.write("La respuesta hace referencia a la(s) página(s):")
                            for p in sorted(set(pages)):
                                if st.button(f"Ir a página {p}", key=f"goto_{p}_{question}"):
                                    st.session_state['pagina_actual'] = p
                    else:
                        st.error(f"Error: {response.text}")
                except Exception as e:
                    st.error(f"No se pudo conectar al backend: {e}")

# Siempre muestra la última respuesta si existe
if 'ultima_respuesta' in st.session_state:
    answer = st.session_state['ultima_respuesta']
    pages = st.session_state.get('ultima_paginas', [])
    if '$' in answer or '\\(' in answer or '\\[' in answer:
        st.markdown("**Respuesta:**")
        st.markdown(f"$$\\displaystyle {answer}$$", unsafe_allow_html=True)
    else:
        st.success(f"Respuesta: {answer}")
    if pages:
        st.write("La respuesta hace referencia a la(s) página(s):")
        for p in sorted(set(pages)):
            if st.button(f"Ir a página {p}", key=f"goto_{p}_{st.session_state.get('ultima_pregunta', '')}"):
                st.session_state['pagina_actual'] = p