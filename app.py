"""
Streamlit Chat - Agente de Ventas Jamar
=======================================
Versión simple y limpia del chat.
Usa AgentCore Gateway para todas las tools.
"""
import streamlit as st
import uuid
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar página
st.set_page_config(
    page_title="Jami - Muebles Jamar",
    page_icon="🛋️",
    layout="centered"
)

# CSS mínimo
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stChatMessage {
        padding: 1rem;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# IDENTIFICACIÓN DE USUARIO
# ============================================================================

def get_device_id() -> str:
    """
    Genera ID único basado en el dispositivo/IP del usuario.
    El mismo dispositivo tendrá el mismo ID en diferentes sesiones.
    
    Usa una combinación de:
    1. Session ID de Streamlit (persistente por sesión del navegador)
    2. User agent (identifica el navegador/dispositivo)
    3. IP si está disponible
    
    Esto crea un ID consistente que persiste mientras el usuario use el mismo navegador.
    """
    try:
        import hashlib
        
        # Obtener información del contexto de Streamlit
        ctx = st.runtime.scriptrunner.get_script_run_ctx()
        if not ctx:
            return f"st_{uuid.uuid4().hex[:8]}"
        
        # Usar session_id como base (es único por sesión del navegador)
        session_id = ctx.session_id
        if not session_id:
            return f"st_{uuid.uuid4().hex[:8]}"
        
        # Crear hash del session_id para tener un ID consistente
        # El session_id de Streamlit persiste mientras el navegador esté abierto
        # y se mantiene entre recargas de la página
        device_hash = hashlib.md5(session_id.encode()).hexdigest()[:12]
        
        return f"device_{device_hash}"
        
    except Exception as e:
        # Si falla, usar UUID normal
        print(f"⚠️ No se pudo obtener device ID: {e}")
        return f"st_{uuid.uuid4().hex[:8]}"


def get_actor_id() -> str:
    """
    Obtiene o genera un actor_id persistente para el usuario.
    
    El mismo dispositivo/navegador mantendrá el mismo actor_id entre:
    - Recargas de página ✅
    - Cerrar y reabrir navegador ✅ (usando query_params en URL)
    - Reinicios de Streamlit ✅
    
    Esto permite mantener el contexto y memoria de conversaciones.
    """
    # Primero intentar obtener de query_params (persiste en la URL)
    query_params = st.query_params
    if "actor_id" in query_params:
        actor_id = query_params["actor_id"]
        st.session_state.actor_id = actor_id
        return actor_id
    
    # Si no está en query_params, verificar session_state
    if "actor_id" in st.session_state:
        actor_id = st.session_state.actor_id
        # Guardar en query_params para persistencia
        st.query_params["actor_id"] = actor_id
        return actor_id
    
    # Si no existe, generar uno nuevo
    actor_id = f"device_{uuid.uuid4().hex[:12]}"
    st.session_state.actor_id = actor_id
    # Guardar en query_params para persistencia entre sesiones
    st.query_params["actor_id"] = actor_id
    print(f"👤 Nuevo Actor ID generado: {actor_id}")
    
    return actor_id


# ============================================================================
# INICIALIZACIÓN DEL AGENTE
# ============================================================================

@st.cache_resource
def init_memory():
    """Inicializa memoria (una sola vez)."""
    from src.memory.manager import create_memory
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    memory = create_memory(region_name=region)
    return memory, region


# NOTA: No necesitamos inicializar cliente Shopify aquí
# Las tools están en Lambda y se consumen vía AgentCore Gateway


class ResponseCapture:
    """Callback para capturar la respuesta completa del agente."""
    def __init__(self):
        self.captured_text = []
        self.tool_results = []
        self.tool_outputs = []
    
    def __call__(self, **kwargs):
        # Capturar texto del streaming (respuesta del agente)
        if kwargs.get("data"):
            self.captured_text.append(kwargs["data"])
        
        # Capturar resultado de tools
        if kwargs.get("tool_result"):
            tool_result = kwargs["tool_result"]
            if isinstance(tool_result, str):
                self.tool_results.append(tool_result)
                self.tool_outputs.append(tool_result)
            elif isinstance(tool_result, dict):
                # Buscar texto en diferentes campos
                if "content" in tool_result:
                    content = str(tool_result["content"])
                    self.tool_results.append(content)
                    self.tool_outputs.append(content)
                elif "text" in tool_result:
                    text = str(tool_result["text"])
                    self.tool_results.append(text)
                    self.tool_outputs.append(text)
                elif "result" in tool_result:
                    result = tool_result["result"]
                    if isinstance(result, str):
                        self.tool_results.append(result)
                        self.tool_outputs.append(result)
                    else:
                        self.tool_results.append(str(result))
                        self.tool_outputs.append(str(result))
                else:
                    self.tool_results.append(str(tool_result))
                    self.tool_outputs.append(str(tool_result))
        
        # Capturar output de tools directamente
        if kwargs.get("tool_output"):
            output = kwargs["tool_output"]
            if isinstance(output, str):
                self.tool_outputs.append(output)
            else:
                self.tool_outputs.append(str(output))
    
    def get_text(self) -> str:
        """Obtiene todo el texto capturado."""
        # Combinar texto del agente y resultados de tools
        all_text = "".join(self.captured_text)
        if self.tool_outputs:
            # Priorizar tool outputs (más recientes)
            all_text += "\n".join(self.tool_outputs)
        elif self.tool_results:
            # Si no hay outputs, usar results
            all_text += "\n".join(self.tool_results)
        return all_text.strip()


def get_mcp_client(region: str):
    """Obtiene o crea el MCPClient."""
    if "mcp_client" not in st.session_state:
        try:
            from strands.tools.mcp import MCPClient
            from mcp.client.streamable_http import streamablehttp_client
            import sys
            import os
            
            # Agregar gateway al path
            gateway_path = os.path.join(os.path.dirname(__file__), "gateway")
            if gateway_path not in sys.path:
                sys.path.insert(0, gateway_path)
            from gateway.utils import get_ssm_parameter, get_cognito_token
            
            gateway_url = get_ssm_parameter("/jamar/agentcore/gateway_url", region)
            if not gateway_url:
                raise ValueError("Gateway URL no encontrada en SSM")
            
            # Obtener configuración de Cognito
            client_id = get_ssm_parameter("/jamar/agentcore/cognito_client_id", region)
            pool_id = get_ssm_parameter("/jamar/agentcore/cognito_pool_id", region)
            
            if not client_id or not pool_id:
                raise ValueError("Cognito no configurado en SSM")
            
            # Obtener token real de Cognito
            bearer_token = get_cognito_token(client_id, pool_id, region)
            if not bearer_token:
                raise ValueError("No se pudo obtener token de Cognito")
            
            mcp_client = MCPClient(
                lambda: streamablehttp_client(
                    gateway_url,
                    headers={"Authorization": f"Bearer {bearer_token}"},
                )
            )
            
            # Guardar cliente para usar cuando se ejecute el agente
            st.session_state.mcp_client = mcp_client
            print(f"✅ MCPClient creado (se inicializará cuando se ejecute el agente)")
            
        except Exception as e:
            print(f"⚠️ Error creando MCPClient: {e}")
            import traceback
            traceback.print_exc()
            st.session_state.mcp_client = None
    
    return st.session_state.get("mcp_client")


def get_agent(actor_id: str):
    """Obtiene o crea el agente usando AgentCore Gateway."""
    # NOTA: No necesitamos cliente Shopify aquí - las tools están en Lambda/Gateway
    
    if "agent" not in st.session_state:
        from src.core.agent import create_agent
        memory, region = init_memory()
        
        # Obtener o crear MCPClient
        mcp_client = get_mcp_client(region)
        
        agent, session_id, _ = create_agent(
            memory_id=memory["id"],
            region=region,
            actor_id=actor_id,
            use_gateway=True,  # SIEMPRE usar Gateway (todas las tools vienen del Gateway)
            mcp_client=mcp_client
        )
        st.session_state.agent = agent
        st.session_state.session_id = session_id
    return st.session_state.agent


def get_response_text(response) -> str:
    """Extrae texto de la respuesta del agente."""
    try:
        # Si es string directo
        if isinstance(response, str):
            return response
        
        texts = []
        
        # 1. Intentar obtener del message.content
        if hasattr(response, 'message'):
            msg = response.message
            
            # Si message es un diccionario
            if isinstance(msg, dict):
                content = msg.get('content', [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and 'text' in item:
                            texts.append(item['text'])
                        elif isinstance(item, str):
                            texts.append(item)
                elif isinstance(content, str):
                    texts.append(content)
            
            # Si message tiene atributo content (objeto)
            elif hasattr(msg, 'content'):
                content = msg.content
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and 'text' in item:
                            texts.append(item['text'])
                        elif isinstance(item, str):
                            texts.append(item)
                elif isinstance(content, str):
                    texts.append(content)
            
            # Si message es string
            elif isinstance(msg, str):
                texts.append(msg)
        
        # 2. Buscar en tool_results (incluso si ya hay textos, pueden ser complementarios)
        if hasattr(response, 'tool_results'):
            tool_results = response.tool_results
            if tool_results:
                for tool_result in tool_results:
                    # Si tool_result es un diccionario
                    if isinstance(tool_result, dict):
                        if 'result' in tool_result:
                            result = tool_result['result']
                            if isinstance(result, str) and result.strip():
                                texts.append(result)
                            elif isinstance(result, dict):
                                if 'content' in result:
                                    texts.append(str(result['content']))
                                elif 'text' in result:
                                    texts.append(str(result['text']))
                                else:
                                    texts.append(str(result))
                        # Buscar directamente en el diccionario
                        elif 'content' in tool_result:
                            texts.append(str(tool_result['content']))
                        elif 'text' in tool_result:
                            texts.append(str(tool_result['text']))
                    # Si tool_result es un objeto
                    elif hasattr(tool_result, 'result'):
                        result = tool_result.result
                        if isinstance(result, str) and result.strip():
                            texts.append(result)
                        elif isinstance(result, dict):
                            if 'content' in result:
                                texts.append(str(result['content']))
                            elif 'text' in result:
                                texts.append(str(result['text']))
                            else:
                                texts.append(str(result))
                    # Si tool_result es string directo
                    elif isinstance(tool_result, str) and tool_result.strip():
                        texts.append(tool_result)
        
        # 3. Si aún no hay texto, buscar en structured_output
        if not texts and hasattr(response, 'structured_output'):
            so = response.structured_output
            if so:
                if isinstance(so, str):
                    texts.append(so)
                elif isinstance(so, dict):
                    texts.append(str(so))
        
        # 4. Si hay textos, unirlos
        if texts:
            return '\n'.join(texts)
        
        # 5. Último recurso - convertir todo a string y buscar texto útil
        response_str = str(response)
        if len(response_str) > 50:  # Si tiene contenido significativo
            return response_str
        
        return "Lo siento, no pude procesar la respuesta. Por favor intenta de nuevo."
        
    except Exception as e:
        import traceback
        return f"Error extrayendo respuesta: {e}"


def render_response_with_images(text: str):
    """Renderiza respuesta con detección de URLs e imágenes."""
    import re
    
    # Detectar URLs de productos
    url_pattern = r'🔗 Ver producto: (https?://[^\s]+)'
    image_pattern = r'🖼️ Imagen: (https?://[^\s]+)'
    
    # Extraer URLs e imágenes
    urls = re.findall(url_pattern, text)
    images = re.findall(image_pattern, text)
    
    # Reemplazar en el texto para markdown
    # Convertir URLs a links clickeables
    text = re.sub(url_pattern, r'🔗 [Ver producto](\1)', text)
    text = re.sub(image_pattern, '', text)  # Remover línea de imagen del texto
    
    # Mostrar texto con markdown
    st.markdown(text)
    
    # Mostrar imágenes si hay
    if images:
        cols = st.columns(min(len(images), 3))
        for i, img_url in enumerate(images[:3]):
            with cols[i]:
                try:
                    st.image(img_url, use_container_width=True, caption=f"Producto {i+1}")
                except:
                    pass  # Si falla cargar imagen, continuar


# ============================================================================
# INTERFAZ
# ============================================================================

def main():
    # Header simple
    st.title("🛋️ Jami - Muebles Jamar")
    st.caption("Tu asistente de ventas virtual 🇵🇦")
    
    # Obtener actor_id
    actor_id = get_actor_id()
    
    # Sidebar con info
    with st.sidebar:
        st.markdown("### 📊 Sesión")
        st.code(actor_id)
        
        if st.button("🔄 Nueva conversación"):
            st.session_state.messages = []
            if "agent" in st.session_state:
                del st.session_state.agent
            st.rerun()
        
        st.markdown("---")
        st.markdown("**Canales:**")
        st.markdown("- 🌐 PoC")
        
        st.markdown("---")
        st.success("✅ AgentCore Gateway activo")
    
    # Inicializar agente con Gateway
    try:
        # Mostrar info del Gateway antes de crear el agente
        with st.spinner("Conectando al AgentCore Gateway..."):
            import boto3
            from gateway.utils import get_ssm_parameter
            gateway_url = get_ssm_parameter("/jamar/agentcore/gateway_url", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))

        
        agent = get_agent(actor_id)
    except Exception as e:
        st.error(f"Error inicializando: {e}")
        st.info("Verifica tu archivo `.env` con las credenciales AWS y Shopify")
        import traceback
        with st.expander("Detalles del error"):
            st.code(traceback.format_exc())
        return
    
    # Inicializar mensajes (vacío - sin bienvenida automática)
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Mostrar historial de mensajes
    for message in st.session_state.messages:
        with st.chat_message(message["role"], avatar="🛋️" if message["role"] == "assistant" else "👤"):
            st.markdown(message["content"])
    
    # Input del usuario
    if prompt := st.chat_input("Escribe tu mensaje..."):
        # Mostrar mensaje del usuario
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)
        
        # Obtener respuesta del agente
        with st.chat_message("assistant", avatar="🛋️"):
            with st.spinner("Pensando..."):
                try:
                    # NOTA: No necesitamos cliente Shopify - las tools están en Lambda/Gateway
                    
                    # Capturar stdout para obtener la respuesta completa
                    import io
                    import sys
                    from contextlib import redirect_stdout
                    
                    captured_output = io.StringIO()
                    
                    # Crear callback para capturar respuesta
                    capture = ResponseCapture()
                    agent.callback_handler = capture
                    
                    # Capturar stdout mientras se ejecuta el agente
                    # IMPORTANTE: El MCPClient debe estar dentro del contexto cuando se ejecutan las tools
                    mcp_client = st.session_state.get("mcp_client")
                    with redirect_stdout(captured_output):
                        if mcp_client:
                            # Ejecutar dentro del contexto del MCPClient para que las tools funcionen
                            with mcp_client:
                                response = agent(prompt)
                        else:
                            # Si no hay cliente, ejecutar normalmente (no debería pasar)
                            response = agent(prompt)
                    
                    # Obtener el output capturado
                    stdout_text = captured_output.getvalue()
                    
                    # Intentar obtener texto de la respuesta
                    response_text = get_response_text(response)
                    
                    # Si está vacío, usar el texto capturado del stdout
                    if not response_text or response_text.strip() == "":
                        # Limpiar el texto del stdout (remover mensajes de tools)
                        lines = stdout_text.split('\n')
                        clean_lines = []
                        skip_next = False
                        for line in lines:
                            if 'Tool #' in line or '🔧 Usando:' in line or '=== TOOL RESULTS ===' in line:
                                skip_next = True
                                continue
                            if skip_next and line.strip() == '':
                                skip_next = False
                                continue
                            if not skip_next and line.strip() and not line.startswith('No tiene'):
                                clean_lines.append(line)
                        response_text = '\n'.join(clean_lines).strip()
                    
                    # Si aún está vacío, usar el callback
                    if not response_text or response_text.strip() == "":
                        response_text = capture.get_text()
                    
                    # Si aún está vacío, buscar en la respuesta completa del agente
                    if not response_text or response_text.strip() == "":
                        # Intentar obtener del response directamente
                        if hasattr(response, '__dict__'):
                            response_dict = response.__dict__
                            # Buscar en diferentes campos posibles
                            for key in ['content', 'text', 'message', 'output']:
                                if key in response_dict:
                                    value = response_dict[key]
                                    if isinstance(value, str) and value.strip():
                                        response_text = value
                                        break
                                    elif isinstance(value, (list, dict)):
                                        response_text = str(value)
                                        break
                    
                    # Si aún está vacío, mensaje de error con debug
                    if not response_text or response_text.strip() == "":
                        # Debug: mostrar qué hay en la respuesta
                        debug_info = f"Debug - Response type: {type(response)}\n"
                        if hasattr(response, '__dict__'):
                            debug_info += f"Response keys: {list(response.__dict__.keys())}\n"
                        debug_info += f"Stdout length: {len(stdout_text)}\n"
                        debug_info += f"Callback text: {capture.get_text()[:100]}\n"
                        
                        # Intentar usar el stdout completo como último recurso
                        if stdout_text and len(stdout_text.strip()) > 10:
                            response_text = stdout_text.strip()
                        else:
                            response_text = "Lo siento, hubo un problema procesando tu solicitud. Por favor intenta de nuevo."
                    
                    # Si no hay respuesta, mostrar mensaje de error
                    if not response_text or response_text.strip() == "":
                        response_text = "Lo siento, no pude generar una respuesta. Por favor intenta de nuevo."
                        st.warning("⚠️ La respuesta está vacía")
                    
                    # Renderizar con imágenes y URLs
                    render_response_with_images(response_text)
                    
                    # Guardar en historial
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                    
                except Exception as e:
                    import traceback
                    error_details = traceback.format_exc()
                    error_msg = f"❌ Error: {str(e)}"
                    st.error(error_msg)
                    
                    # Mostrar detalles del error en un expander
                    with st.expander("🔍 Ver detalles del error"):
                        st.code(error_details[:1000], language="python")
                    
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})


if __name__ == "__main__":
    main()
