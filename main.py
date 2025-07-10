#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jul  7 23:12:07 2025

@author: panasabena
"""

import os
from fastapi import FastAPI, UploadFile, File, Form, Request, Depends, HTTPException, Path
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import PyPDF2
import pdfplumber
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import requests
from fastapi import Body
import base64
import json
from transformers import AutoTokenizer
from datetime import datetime, timedelta

# Importar módulos de base de datos y autenticación
from database import get_db, User, Conversation, Message, create_tables
from auth import authenticate_user, create_access_token, get_current_user, create_user
from sqlalchemy.orm import Session

app = FastAPI()

# Permitir CORS para desarrollo local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelos Pydantic para las requests
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

UPLOAD_DIR = "pdfs"
INDEX_DIR = "indices"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
OLLAMA_URL = "http://localhost:11434/api/generate"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(INDEX_DIR, exist_ok=True)

model = SentenceTransformer(EMBEDDING_MODEL)

def get_tokenizer():
    # Usar un tokenizer abierto y público compatible
    return AutoTokenizer.from_pretrained("hf-internal-testing/llama-tokenizer", use_fast=True)

tokenizer = get_tokenizer()

def count_tokens(text):
    return len(tokenizer.encode(text))

# Utilidad: extraer texto de PDF
def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                if not page_text.strip():
                    with open(pdf_path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        if i < len(reader.pages):
                            page_text = reader.pages[i].extract_text() or ""
                text += page_text + "\n"
    except Exception as e:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() or ""
    return text

def chunk_text(text, chunk_size=500, overlap=50):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i+chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks

def chunk_text_with_pages(texts_by_page, chunk_size=500, overlap=50):
    chunks = []
    chunk_pages = []
    for page_num, text in enumerate(texts_by_page):
        words = text.split()
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i+chunk_size])
            if chunk:
                chunks.append(chunk)
                chunk_pages.append(page_num + 1)
    return chunks, chunk_pages

# Endpoints de autenticación
@app.post("/register", response_model=Token)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    """Registrar un nuevo usuario"""
    try:
        db_user = create_user(db, user.username, user.email, user.password)
        access_token_expires = timedelta(minutes=30)
        access_token = create_access_token(
            data={"sub": db_user.username}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@app.post("/login", response_model=Token)
async def login(user_credentials: UserLogin, db: Session = Depends(get_db)):
    """Iniciar sesión"""
    user = authenticate_user(db, user_credentials.username, user_credentials.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# Endpoint para subir PDF y crear índice
@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    pdf_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(pdf_path, "wb") as f:
        f.write(await file.read())
    
    texts_by_page = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                texts_by_page.append(page.extract_text() or "")
    except Exception:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                texts_by_page.append(page.extract_text() or "")
    
    chunks, chunk_pages = chunk_text_with_pages(texts_by_page)
    embeddings = model.encode(chunks)
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(np.array(embeddings).astype('float32'))
    faiss.write_index(index, os.path.join(INDEX_DIR, file.filename + ".index"))
    
    with open(os.path.join(INDEX_DIR, file.filename + ".chunks.txt"), "w") as f:
        for chunk in chunks:
            f.write(chunk + "\n---CHUNK---\n")
    with open(os.path.join(INDEX_DIR, file.filename + ".pages.txt"), "w") as f:
        for page in chunk_pages:
            f.write(str(page) + "\n")
    return {"message": "PDF procesado y embebido", "pdf": file.filename}

# Endpoints para gestión de conversaciones
@app.get("/conversations/")
async def get_conversations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Obtener todas las conversaciones del usuario"""
    conversations = db.query(Conversation).filter(Conversation.user_id == current_user.id).all()
    return conversations

@app.post("/conversations/")
async def create_conversation(
    pdf_name: str = Form(None),
    title: str = Form("Nueva conversación"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crear una nueva conversación"""
    conversation = Conversation(
        user_id=current_user.id,
        pdf_name=pdf_name,
        title=title
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation

@app.get("/conversations/{conversation_id}/messages/")
async def get_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener mensajes de una conversación"""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return conversation.messages

@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int = Path(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Borrar una conversación y sus mensajes"""
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    # Borrar mensajes primero
    db.query(Message).filter(Message.conversation_id == conversation_id).delete()
    db.delete(conversation)
    db.commit()
    return {"message": "Conversación borrada"}

# Endpoint de chat actualizado
@app.post("/chat/")
async def chat(
    conversation_id: int = Form(...),
    question: str = Form(...),
    language: str = Form("español"),
    ollama_model: str = Form("mistral"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Chat con memoria usando base de datos"""
    # Verificar que la conversación pertenece al usuario
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    
    # Obtener historial de mensajes
    messages = db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.created_at).all()
    
    # Construir historial en texto
    history_text = ""
    for msg in messages[-10:]:  # Últimos 10 mensajes
        history_text += f"Usuario: {msg.question}\nIA: {msg.answer}\n"
    
    # Límite de tokens
    MAX_TOKENS = 3900
    
    if not conversation.pdf_name:
        # Chat IA convencional
        prompt_base = (
            f"Eres un asistente conversacional. Responde únicamente en {language}.\n"
            f"Sigue el hilo de la conversación.\n"
        )
        prompt_final = f"{prompt_base}{history_text}Usuario: {question}\nIA:"
        
        # Recortar historial si excede el límite
        while count_tokens(prompt_final) > MAX_TOKENS and len(messages) > 0:
            messages = messages[1:]  # Quita el más antiguo
            history_text = ""
            for msg in messages[-10:]:
                history_text += f"Usuario: {msg.question}\nIA: {msg.answer}\n"
            prompt_final = f"{prompt_base}{history_text}Usuario: {question}\nIA:"
        
        n_tokens = count_tokens(prompt_final)
        response = requests.post(OLLAMA_URL, json={"model": ollama_model, "prompt": prompt_final, "stream": False})
        if response.status_code == 200:
            answer = response.json().get("response", "Sin respuesta")
        else:
            answer = "Error al consultar el modelo Ollama"
        
        # Guardar mensaje en la base de datos
        message = Message(
            conversation_id=conversation_id,
            question=question,
            answer=answer,
            tokens_used=n_tokens
        )
        db.add(message)
        db.commit()
        
        return {"answer": answer, "pages": [], "n_tokens": n_tokens}
    
    # Modo PDF
    index_path = os.path.join(INDEX_DIR, conversation.pdf_name + ".index")
    chunks_path = os.path.join(INDEX_DIR, conversation.pdf_name + ".chunks.txt")
    pages_path = os.path.join(INDEX_DIR, conversation.pdf_name + ".pages.txt")
    
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
    
    prompt_base = (
        f"Responde la siguiente pregunta usando solo el contexto proporcionado. Si la respuesta no está en el contexto, responde: 'No hay información suficiente en el PDF para responder esa pregunta.' Responde únicamente en {language}.\n"
        f"Contexto:\n{context}\n\n"
        f"Historial de la conversación:\n"
    )
    prompt_final = f"{prompt_base}{history_text}Usuario: {question}\nIA:"
    
    # Recortar historial si excede el límite
    while count_tokens(prompt_final) > MAX_TOKENS and len(messages) > 0:
        messages = messages[1:]
        history_text = ""
        for msg in messages[-10:]:
            history_text += f"Usuario: {msg.question}\nIA: {msg.answer}\n"
        prompt_final = f"{prompt_base}{history_text}Usuario: {question}\nIA:"
    
    n_tokens = count_tokens(prompt_final)
    response = requests.post(OLLAMA_URL, json={"model": ollama_model, "prompt": prompt_final, "stream": False})
    if response.status_code == 200:
        answer = response.json().get("response", "Sin respuesta")
    else:
        answer = "Error al consultar el modelo Ollama"
    
    # Guardar mensaje en la base de datos
    message = Message(
        conversation_id=conversation_id,
        question=question,
        answer=answer,
        tokens_used=n_tokens,
        pages_referenced=pages
    )
    db.add(message)
    db.commit()
    
    return {"answer": answer, "pages": pages, "n_tokens": n_tokens}

@app.post("/delete_pdf/")
async def delete_pdf(pdf_name: str = Form(...), current_user: User = Depends(get_current_user)):
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

# Crear tablas al iniciar
@app.on_event("startup")
async def startup_event():
    create_tables()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)