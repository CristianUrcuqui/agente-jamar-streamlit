# 🚀 Streamlit Deploy - Versión Simplificada

Esta carpeta contiene **solo lo necesario** para desplegar la app Streamlit que consume el AgentCore Gateway.

## 📋 ¿Qué contiene?

### Archivos principales:
- `app.py` - Aplicación Streamlit
- `src/core/agent.py` - Agente que **SOLO** usa Gateway (sin tools locales)
- `src/config/settings.py` - SYSTEM_PROMPT del agente
- `src/memory/manager.py` - Gestión de memoria AgentCore
- `gateway/utils.py` - Utilidades para conectarse al Gateway (SSM, Cognito)

**✅ NO incluye:**
- ❌ Código de Shopify (está en Lambda)
- ❌ Tools individuales (están en Lambda)
- ❌ Cliente Shopify (está en Lambda)

### Archivos de despliegue:
- `Dockerfile` - Para construir la imagen Docker
- `.dockerignore` - Archivos a excluir del build
- `.streamlit/config.toml` - Configuración de Streamlit
- `requirements.txt` - Dependencias Python

## 🏗️ Arquitectura

```
Usuario → Streamlit App → Agente Strands → AgentCore Gateway → Lambda (28 Tools)
                              ↓
                         SYSTEM_PROMPT
                              ↓
                         AgentCore Memory
```

**Importante:** Las tools están en Lambda, NO en este código. Este código solo:
1. Crea el agente Strands
2. Se conecta al Gateway para obtener las tools (que están en Lambda)
3. Ejecuta el agente con el SYSTEM_PROMPT

**Las tools de Shopify también están en Lambda**, por lo que NO necesitamos código de Shopify aquí.

## 🚀 Despliegue Rápido

### Opción 1: Streamlit Cloud (5 minutos)

1. Sube esta carpeta a GitHub
2. Ve a [streamlit.io/cloud](https://streamlit.io/cloud)
3. Conecta tu repo
4. Configura variables de entorno:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_DEFAULT_REGION` (ej: `us-east-1`)
   
   **NOTA:** No necesitas variables de Shopify aquí - están en Lambda

### Opción 2: AWS App Runner

```bash
cd streamlit-deploy
chmod +x ../deploy-apprunner.sh
../deploy-apprunner.sh
```

### Opción 3: Docker local

```bash
cd streamlit-deploy
docker build -t jamar-streamlit .
docker run -p 8080:8080 \
  -e AWS_ACCESS_KEY_ID=tu_key \
  -e AWS_SECRET_ACCESS_KEY=tu_secret \
  -e AWS_DEFAULT_REGION=us-east-1 \
  jamar-streamlit
```

## ⚙️ Variables de Entorno Requeridas

**Variables de entorno requeridas:**
- `AWS_ACCESS_KEY_ID` - Para acceder a SSM y Cognito
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION` - Región donde está el Gateway

**NOTA:** No necesitas variables de Shopify aquí - las tools de Shopify están en Lambda y se consumen vía Gateway.

## 📝 Notas

1. **El Gateway debe estar desplegado primero** en AWS
2. **Las tools están en Lambda**, no en este código
3. **El SYSTEM_PROMPT está en `src/config/settings.py`**
4. **Esta versión NO incluye tools locales** - solo usa Gateway

## 🔍 Verificación

Para verificar que todo funciona:

1. El Gateway debe estar desplegado y tener el target Lambda configurado
2. Los parámetros SSM deben existir:
   - `/jamar/agentcore/gateway_url`
   - `/jamar/agentcore/cognito_client_id`
   - `/jamar/agentcore/cognito_pool_id`
3. Las credenciales AWS deben tener permisos para:
   - SSM Parameter Store (lectura)
   - Cognito (obtener token)

## 🐛 Troubleshooting

### Error: "Gateway URL no encontrada en SSM"
- Verifica que el Gateway esté desplegado
- Verifica que el parámetro `/jamar/agentcore/gateway_url` exista en SSM

### Error: "Cognito no configurado"
- Verifica que los parámetros `/jamar/agentcore/cognito_client_id` y `/jamar/agentcore/cognito_pool_id` existan

### Error: "No hay tools disponibles"
- Verifica que el Gateway tenga el target Lambda configurado
- Revisa los logs de Lambda para ver si hay errores
