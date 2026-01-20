# Dockerfile para AWS App Runner
# 
# Versión simplificada - Solo Streamlit + Agente que consume Gateway
# Las tools están en Lambda y se consumen vía AgentCore Gateway.
#
# Arquitectura:
#   Streamlit App → Agente Strands → AgentCore Gateway → Lambda (28 Tools)
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
# Esta carpeta solo contiene lo necesario para Streamlit
COPY . .

# Exponer puerto de Streamlit
EXPOSE 8080

# Configurar variables de entorno para Streamlit
ENV STREAMLIT_SERVER_PORT=8080
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Comando para ejecutar Streamlit
CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]
