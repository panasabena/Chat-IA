# Chat-IA: Chatea con tus PDFs

## Requisitos
- Python 3.8+
- pip
- [Ollama](https://ollama.com/) instalado y modelos descargados (opcional, para chat con IA)

## Instalación

1. Clona este repositorio o descarga los archivos en tu computadora.

2. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```

3. (Opcional) Descarga los modelos de Ollama que quieras usar:
   ```bash
   ollama pull llama2
   ollama pull mistral
   ollama pull llama2-13b-chat
   ollama pull gemma
   ollama pull phi3
   ollama pull llama3
   ```

## Cómo iniciar la aplicación

1. Abre una terminal y navega a la carpeta del proyecto:
   ```bash
   cd ruta/a/tu/proyecto
   ```

2. Inicia el backend (FastAPI):
   ```bash
   uvicorn main:app --reload
   ```
   El backend estará disponible en `http://localhost:8000`.

3. En otra terminal, inicia la app de Streamlit:
   ```bash
   streamlit run chatpdf_app.py
   ```
   Esto abrirá la interfaz web en tu navegador (`http://localhost:8501`).

4. (Opcional) Asegúrate de que Ollama esté corriendo:
   ```bash
   ollama serve
   ```

## Uso
- Sube un PDF usando el panel lateral izquierdo.
- Selecciona el PDF para chatear.
- Escribe tu pregunta, elige el idioma y el modelo de Ollama.
- Haz clic en "Preguntar" y explora las páginas relevantes del PDF.
- Puedes eliminar PDFs y limpiar el historial desde la barra lateral.

---

¡Listo! Ya puedes chatear con tus PDFs y explorar sus respuestas de manera interactiva. 