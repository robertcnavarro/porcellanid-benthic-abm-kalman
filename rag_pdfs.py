# -*- coding: utf-8 -*-
import os
import sys
import getpass

try:
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_chroma import Chroma
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnablePassthrough
    from langchain_core.output_parsers import StrOutputParser
    import warnings
    warnings.filterwarnings('ignore')
except ImportError as e:
    print(f"Faltan dependencias ({e}). Ejecuta:")
    print("py -m pip install langchain langchain-community langchain-huggingface langchain-chroma chromadb pypdf sentence-transformers langchain-google-genai google-generativeai")
    sys.exit(1)

# Configuracion de rutas
DATA_DIR = r"c:\Users\roberto.navarro\Documents\paula\01_datos_raw"
DB_DIR = r"c:\Users\roberto.navarro\Documents\paula\03_codigo_python\chroma_db"

ARCHIVOS = [
    "ART_DENSIDAD__ESTRUCTURA CON COSAS PARA REPRODUCCION.pdf",
    "Cardoso_et_al_Manual_ABM.pdf",
    "libroPaulaQuiceno.pdf"
]

def inicializar_bd_vectorial():
    print("\n--- PASO 1: CARGANDO BASE DE DATOS ---")
    print("Cargando modelo de embeddings local (all-MiniLM-L6-v2)...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    if os.path.exists(DB_DIR) and os.listdir(DB_DIR):
        print(f"Base de datos encontrada en '{DB_DIR}'. Cargando datos existentes...")
        vectorstore = Chroma(persist_directory=DB_DIR, embedding_function=embeddings)
        return vectorstore

    print("Base de datos no encontrada. Iniciando el procesamiento de los PDFs (esto tomara unos minutos)...")
    docs = []
    for archivo in ARCHIVOS:
        ruta = os.path.join(DATA_DIR, archivo)
        if not os.path.exists(ruta):
            print(f"  [ERROR] No se encontro el archivo: {ruta}")
            continue
        
        print(f"  Leyendo {archivo}...")
        loader = PyPDFLoader(ruta)
        docs.extend(loader.load())
    
    if not docs:
        print("No se cargaron documentos. Verifica las rutas.")
        sys.exit(1)
        
    print(f"Se cargaron {len(docs)} paginas en total. Dividiendo el texto...")
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        add_start_index=True
    )
    splits = text_splitter.split_documents(docs)
    print(f"El texto se dividio en {len(splits)} fragmentos. Generando embeddings y guardando en ChromaDB...")
    
    vectorstore = Chroma.from_documents(documents=splits, embedding=embeddings, persist_directory=DB_DIR)
    print("Base de datos creada exitosamente!")
    
    return vectorstore

def iniciar_interfaz(vectorstore):
    print("\n--- PASO 2: CONFIGURANDO IA (GEMINI) ---")
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
        
    if "GOOGLE_API_KEY" not in os.environ:
        api_key = getpass.getpass("Por favor, ingresa tu GOOGLE_API_KEY (permanecera oculta): ")
        os.environ["GOOGLE_API_KEY"] = api_key.strip()
    
    # Inicializar el modelo Gemini
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.3)
    
    # Definir el prompt para la IA
    template = """Eres un asistente de investigacion experto en biologia marina, ecologia de poblaciones, modelos basados en agentes y analisis de datos.
Usa los siguientes fragmentos de contexto recuperado de la literatura proporcionada para responder la pregunta del investigador.
Si no sabes la respuesta o no esta en el contexto, di amablemente que no tienes informacion en los documentos sobre ese tema en especifico. No inventes informacion.
Se exhaustivo pero claro y mantn un tono academico profesional.

Contexto extraido:
{context}

Pregunta: {question}
"""
    prompt = ChatPromptTemplate.from_template(template)

    # Configurar el retriever
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)

    # Crear cadena con LCEL
    rag_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    print("\n--- SISTEMA RAG INICIADO CON EXITO ---\n")
    print("El asistente virtual esta listo para responder preguntas basandose en los PDFs.")
    
    while True:
        print("-" * 60)
        pregunta = input("Escribe tu pregunta (o 'salir' para terminar):\n> ").strip()
        
        if pregunta.lower() in ['salir', 'exit', 'quit']:
            print("Saliendo del asistente...")
            break
            
        if not pregunta:
            continue
            
        print("\nPensando y consultando documentos...\n")
        try:
            # Recuperar documentos por separado para poder mostrarlos
            documentos = retriever.invoke(pregunta)
            
            # Generar respuesta
            respuesta = rag_chain.invoke(pregunta)
            
            print("=== RESPUESTA GEMINI ===")
            print(respuesta)
            print("========================\n")
            
            print("Fuentes consultadas:")
            fuentes_vistas = set()
            for doc in documentos:
                fuente = os.path.basename(doc.metadata.get("source", "Desconocido"))
                pagina = doc.metadata.get("page", "Desconocida")
                origen = f"{fuente} (Pagina {pagina})"
                if origen not in fuentes_vistas:
                    print(f"- {origen}")
                    fuentes_vistas.add(origen)
            print()
            
        except Exception as e:
            print(f"\n[ERROR] Ocurrio un problema al comunicarse con Gemini o al recuperar datos: {e}")
            print("Verifica tu conexion a internet o tu API KEY.\n")

if __name__ == "__main__":
    vectorstore = inicializar_bd_vectorial()
    iniciar_interfaz(vectorstore)
