import os
import requests
from flask import Flask, render_template, request, session
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pypdf import PdfReader
from google import genai
from google.genai import types

# Cargar las credenciales del archivo .env
load_dotenv()

app = Flask(__name__)
# Llave secreta necesaria para poder usar el historial de sesión (session) en Flask
app.secret_key = "byte_wave_secret_key_for_session_management"

def extraer_texto_pdf(file_storage):
    """Extrae el texto de un objeto de archivo PDF en memoria."""
    try:
        lector = PdfReader(file_storage)
        texto_completo = ""
        for pagina in lector.pages:
            texto_completo += pagina.extract_text() + "\n"
        return texto_completo
    except Exception as e:
        return None

def extraer_texto_url(url):
    """Descarga una página web o foro y extrae el texto de los párrafos principales."""
    try:
        # Simulamos un navegador para que los foros o blogs no nos bloqueen el acceso
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        respuesta = requests.get(url, headers=headers, timeout=10)
        
        if respuesta.status_code != 200:
            return f"Error: No se pudo acceder al enlace (Código de estado: {respuesta.status_code})"
            
        soup = BeautifulSoup(respuesta.text, 'html.parser')
        
        # Eliminamos elementos innecesarios del HTML para no saturar a la IA con basura
        for elemento in soup(["script", "style", "nav", "footer", "header", "aside"]):
            elemento.decompose()
            
        # Extraemos el texto de todos los párrafos (<p>)
        parrafos = soup.find_all('p')
        texto_limpio = "\n".join([p.get_text() for p in parrafos])
        
        if not texto_limpio.strip():
            return "Error: No se encontró texto legible en los párrafos de esta página web."
            
        return texto_limpio
    except Exception as e:
        return f"Error al conectar con la URL: {e}"

def generar_resumen(texto_documento, enfoque):
    """Envía el texto limpio a Gemini con instrucciones de rol avanzado."""
    client = genai.Client()
    
    prompts_enfoque = {
        "legal": "Eres un experto asesor legal. Analiza el siguiente texto jurídico en español y genera un dictamen ejecutivo estructurado estrictamente con los siguientes subtítulos en negritas: 1. SÍNTESIS EJECUTIVA, 2. OBLIGACIONES Y DERECHOS IMPLICADOS, 3. PLAZOS Y FECHAS CRUCIALES, 4. RIESGOS O CONTINGENCIAS DETECTADAS. Usa un tono formal.",
        "gobierno": "Eres un analista senior de políticas públicas. Analiza este documento oficial, decreto o minuta gubernamental en español y estructúralo con: 1. OBJETIVO Y ALCANCE DE LA NORMA, 2. DEPENDENCIAS E INSTITUCIONES AFECTADAS, 3. IMPACTO SOCIAL O PRESUPUESTAL, 4. VIGENCIA Y TRANSITORIOS.",
        "medios": "Eres un editor de noticias senior. Analiza esta nota informativa, artículo o foro de discusión en español y genera: 1. TITULAR RECOMENDADO, 2. RESUMEN CRONOLÓGICO DE LOS HECHOS, 3. DECLARACIONES O POSTURAS CLAVE, 4. CONTEXTO GENERAL.",
        "general": "Genera un informe analítico de nivel profesional en español sobre el siguiente texto. Organízalo con subtítulos claros y viñetas elegantes destacando las ideas principales."
    }
    
    instruccion_sistema = prompts_enfoque.get(enfoque, prompts_enfoque["general"])
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=texto_documento,
            config=types.GenerateContentConfig(
                system_instruction=instruccion_sistema,
                temperature=0.2  # Temperatura baja para garantizar precisión técnica
            )
        )
        return response.text
    except Exception as e:
        return f"Error de comunicación con el motor de IA: {e}"

@app.route("/", methods=["GET", "POST"])
def index():
    # Inicializar la lista del historial en la sesión si no existe
    if 'historial' not in session:
        session['historial'] = []
        
    resumen_generado = None
    tipo_entrada = "pdf"  # Estado por defecto
    error_msg = None
    
    if request.method == "POST":
        enfoque = request.form.get("enfoque", "general")
        tipo_entrada = request.form.get("tipo_entrada", "pdf")
        nombre_elemento = ""
        
        if tipo_entrada == "pdf":
            archivo = request.files.get("archivo")
            if archivo and archivo.filename.endswith('.pdf'):
                nombre_elemento = archivo.filename
                texto = extraer_texto_pdf(archivo)
                if texto and texto.strip():
                    resumen_generado = generar_resumen(texto, enfoque)
                else:
                    error_msg = "El archivo PDF subido no contiene texto extraíble o está protegido."
            else:
                error_msg = "Por favor, cargue un archivo con extensión .pdf válido."
                
        elif tipo_entrada == "url":
            enlace = request.form.get("enlace_url")
            if enlace and (enlace.startswith("http://") or enlace.startswith("https://")):
                # Acortamos el nombre para que se vea estético en el historial lateral
                nombre_elemento = enlace.replace("https://", "").replace("http://", "").split('/')[0]
                texto = extraer_texto_url(enlace)
                
                if texto and not texto.startswith("Error"):
                    resumen_generado = generar_resumen(texto, enfoque)
                else:
                    error_msg = texto if texto else "No se pudo recuperar información del enlace."
            else:
                error_msg = "Inserte una dirección URL válida que comience con http:// o https://"
        
        # Si el proceso fue exitoso, guardamos el elemento en el historial de la sesión
        if resumen_generado and not error_msg:
            # Evitamos duplicados en la lista visual
            nuevo_registro = {"nombre": nombre_elemento, "tipo": tipo_entrada.upper(), "enfoque": enfoque.upper()}
            if nuevo_registro not in session['historial']:
                # Clonamos la lista para asegurar que Flask detecte la mutación de la sesión
                lista_actual = list(session['historial'])
                lista_actual.insert(0, nuevo_registro)  # Insertar al inicio
                session['historial'] = lista_actual[:5]  # Mantener solo los últimos 5 para optimizar espacio
                session.modified = True

    return render_template("index.html", resumen=resumen_generado, tipo_entrada=tipo_entrada, error=error_msg, historial=session['historial'])

@app.route("/limpiar-historial")
def limpiar_historial(): 
    """Ruta rápida para vaciar el historial lateral."""
    session['historial'] = []
    session.modified = True
    return render_template("index.html", resumen=None, tipo_entrada="pdf", error=None, historial=[])

if __name__ == "__main__":
    app.run(debug=True)