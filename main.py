#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jul  7 23:12:07 2025

@author: panasabena
"""

import os
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import PyPDF2
import pdfplumber
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import requests
from fastapi import Body
import base64

app = FastAPI()

# Permitir CORS para desarrollo local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "pdfs"
INDEX_DIR = "indices"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
OLLAMA_URL = "http://localhost:11434/api/generate"  # Cambia si tu Ollama corre en otro puerto

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(INDEX_DIR, exist_ok=True)

model = SentenceTransformer(EMBEDDING_MODEL)

# Utilidad: extraer texto de PDF
def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                # Si pdfplumber no extrae nada, intenta con PyPDF2
                if not page_text.strip():
                    with open(pdf_path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        if i < len(reader.pages):
                            page_text = reader.pages[i].extract_text() or ""
                text += page_text + "\n"
    except Exception as e:
        # Si pdfplumber falla, usa solo PyPDF2
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() or ""
    return text

# Utilidad: dividir texto en fragmentos/chunks
def chunk_text(text, chunk_size=500, overlap=50):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i+chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks

# Utilidad: dividir texto en fragmentos/chunks y guardar la página de origen
def chunk_text_with_pages(texts_by_page, chunk_size=500, overlap=50):
    chunks = []
    chunk_pages = []
    for page_num, text in enumerate(texts_by_page):
        words = text.split()
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i+chunk_size])
            if chunk:
                chunks.append(chunk)
                chunk_pages.append(page_num + 1)  # Páginas empiezan en 1
    return chunks, chunk_pages

# Endpoint para subir PDF y crear índice
@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    pdf_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(pdf_path, "wb") as f:
        f.write(await file.read())
    # Extraer texto por página
    texts_by_page = []
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                texts_by_page.append(page.extract_text() or "")
    except Exception:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                texts_by_page.append(page.extract_text() or "")
    # Dividir en chunks y guardar páginas
    chunks, chunk_pages = chunk_text_with_pages(texts_by_page)
    embeddings = model.encode(chunks)
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(np.array(embeddings).astype('float32'))
    faiss.write_index(index, os.path.join(INDEX_DIR, file.filename + ".index"))
    # Guardar los chunks y las páginas para referencia
    with open(os.path.join(INDEX_DIR, file.filename + ".chunks.txt"), "w") as f:
        for chunk in chunks:
            f.write(chunk + "\n---CHUNK---\n")
    with open(os.path.join(INDEX_DIR, file.filename + ".pages.txt"), "w") as f:
        for page in chunk_pages:
            f.write(str(page) + "\n")
    return {"message": "PDF procesado y embebido", "pdf": file.filename}

# Endpoint de chat
@app.post("/chat/")
async def chat(pdf_name: str = Form(...), question: str = Form(...), language: str = Form("español"), ollama_model: str = Form("llama2")):
    index_path = os.path.join(INDEX_DIR, pdf_name + ".index")
    chunks_path = os.path.join(INDEX_DIR, pdf_name + ".chunks.txt")
    pages_path = os.path.join(INDEX_DIR, pdf_name + ".pages.txt")
    if not os.path.exists(index_path) or not os.path.exists(chunks_path) or not os.path.exists(pages_path):
        return JSONResponse(status_code=404, content={"error": "PDF no encontrado o no procesado"})
    index = faiss.read_index(index_path)
    with open(chunks_path, "r") as f:
        chunks = f.read().split("\n---CHUNK---\n")
    with open(pages_path, "r") as f:
        chunk_pages = [int(line.strip()) for line in f if line.strip()]
    q_emb = model.encode([question])
    D, I = index.search(np.array(q_emb).astype('float32'), k=3)
    context = "\n".join([chunks[i] for i in I[0] if i < len(chunks)])
    pages = [chunk_pages[i] for i in I[0] if i < len(chunk_pages)]
    prompt = (
        f"Responde la siguiente pregunta usando solo el contexto proporcionado. Si la respuesta no está en el contexto, responde: 'No hay información suficiente en el PDF para responder esa pregunta.' Responde únicamente en {language}.\n\n"
        f"Contexto:\n{context}\n\nPregunta: {question}\nRespuesta:"
    )
    response = requests.post(OLLAMA_URL, json={"model": ollama_model, "prompt": prompt, "stream": False})
    if response.status_code == 200:
        answer = response.json().get("response", "Sin respuesta")
    else:
        answer = "Error al consultar el modelo Ollama"
    return {"answer": answer, "pages": pages}

@app.post("/delete_pdf/")
async def delete_pdf(pdf_name: str = Form(...)):
    pdf_path = os.path.join(UPLOAD_DIR, pdf_name)
    index_path = os.path.join(INDEX_DIR, pdf_name + ".index")
    chunks_path = os.path.join(INDEX_DIR, pdf_name + ".chunks.txt")
    historial_path = f"historial_{pdf_name}.json"
    errores = []
    for path in [pdf_path, index_path, chunks_path, historial_path]:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            errores.append(f"No se pudo eliminar {path}: {e}")
    if errores:
        return JSONResponse(status_code=500, content={"error": " ".join(errores)})
    return {"message": f"PDF '{pdf_name}' y archivos asociados eliminados."}

import streamlit as st

def mostrar_pdf(pdf_path, page=None):
    with open(pdf_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    # Puedes agregar #page= para ir a una página específica si el navegador lo soporta
    page_str = f"#page={page}" if page else ""
    pdf_display = f'''
        <iframe
            src="data:application/pdf;base64,{base64_pdf}{page_str}"
            width="100%" height="600"
            type="application/pdf">
        </iframe>
    '''
    st.markdown(pdf_display, unsafe_allow_html=True)