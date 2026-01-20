"""
Agent Core - Versión simplificada para despliegue
==================================================
Solo usa AgentCore Gateway, no tools locales.
"""
import uuid
from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

from ..config import SYSTEM_PROMPT, DEFAULT_MODEL_ID, DEFAULT_TEMPERATURE


class StreamingCallback:
    """Callback para streaming sin duplicados."""
    
    def __init__(self):
        self.printed_tool = False
        self.tool_name = None
    
    def __call__(self, **kwargs):
        # Mostrar cuando se usa una herramienta
        if kwargs.get("current_tool_use") and not self.printed_tool:
            self.tool_name = kwargs["current_tool_use"].get("name", "tool")
            print(f"\n🔧 Usando: {self.tool_name}")
            self.printed_tool = True
        
        # Mostrar datos del streaming (respuestas del agente)
        if kwargs.get("data"):
            print(kwargs["data"], end="", flush=True)
        
        # Resetear cuando termina el resultado de la herramienta
        if kwargs.get("tool_result"):
            self.printed_tool = False
            self.tool_name = None


def create_agent(memory_id: str, region: str, actor_id: str = "customer_001", use_gateway: bool = True, mcp_client=None):
    """
    Crea el agente de ventas con memoria.
    SOLO usa AgentCore Gateway para las tools.
    
    Args:
        memory_id: ID de la memoria AgentCore
        region: Región de AWS
        actor_id: ID del actor/cliente
        use_gateway: Si True, integra tools del AgentCore Gateway (SIEMPRE True en esta versión)
        mcp_client: MCPClient opcional ya inicializado (si None, se crea uno nuevo)
    
    Returns:
        tuple: (agente, session_id, mcp_client) - mcp_client puede ser None si no se usa Gateway
    """
    session_id = str(uuid.uuid4())
    
    memory_config = AgentCoreMemoryConfig(
        memory_id=memory_id,
        session_id=session_id,
        actor_id=actor_id,
        retrieval_config={
            "shopify/customer/{actorId}/preferences": RetrievalConfig(top_k=5, relevance_score=0.2),
            "shopify/customer/{actorId}/interactions": RetrievalConfig(top_k=10, relevance_score=0.2)
        }
    )
    
    model = BedrockModel(
        model_id=DEFAULT_MODEL_ID,
        temperature=DEFAULT_TEMPERATURE,
        region_name=region,
    )
    
    session_manager = AgentCoreMemorySessionManager(memory_config, region)
    
    # Lista de herramientas - SOLO del Gateway
    tools_list = []
    
    # SIEMPRE usar Gateway en esta versión
    created_mcp_client = None
    if use_gateway:
        try:
            # Si ya se proporcionó un cliente, usarlo
            if mcp_client is not None:
                # El cliente ya está inicializado, solo obtener las tools
                gateway_tools = mcp_client.list_tools_sync()
                tools_list.extend(gateway_tools)
                print(f"✅ Gateway conectado exitosamente!")
                print(f"   Tools disponibles: {len(gateway_tools)}")
            else:
                # Crear nuevo cliente
                from strands.tools.mcp import MCPClient
                from mcp.client.streamable_http import streamablehttp_client
                import sys
                import os
                # Agregar gateway al path
                gateway_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "gateway")
                if gateway_path not in sys.path:
                    sys.path.insert(0, gateway_path)
                from utils import get_ssm_parameter, get_cognito_token
                
                gateway_url = get_ssm_parameter("/jamar/agentcore/gateway_url", region)
                if not gateway_url:
                    raise ValueError("Gateway URL no encontrada en SSM")
                
                print(f"🌐 Conectando al Gateway: {gateway_url}")
                
                # Obtener configuración de Cognito
                client_id = get_ssm_parameter("/jamar/agentcore/cognito_client_id", region)
                pool_id = get_ssm_parameter("/jamar/agentcore/cognito_pool_id", region)
                
                if not client_id or not pool_id:
                    raise ValueError("Cognito no configurado en SSM")
                
                # Obtener token real de Cognito
                bearer_token = get_cognito_token(client_id, pool_id, region)
                if not bearer_token:
                    raise ValueError("No se pudo obtener token de Cognito")
                
                created_mcp_client = MCPClient(
                    lambda: streamablehttp_client(
                        gateway_url,
                        headers={"Authorization": f"Bearer {bearer_token}"},
                    )
                )
                
                # Obtener tools dentro del contexto temporal
                # El cliente se usará dentro del contexto cuando se ejecute el agente
                with created_mcp_client:
                    gateway_tools = created_mcp_client.list_tools_sync()
                    tools_list.extend(gateway_tools)
                    print(f"✅ Gateway conectado exitosamente!")
                    print(f"   URL: {gateway_url}")
                    print(f"   Tools disponibles: {len(gateway_tools)}")
                # NOTA: El cliente se cerrará aquí, pero se volverá a abrir cuando se ejecute el agente dentro del contexto
        
        except Exception as e:
            print(f"⚠️ Error integrando Gateway: {e}")
            import traceback
            traceback.print_exc()
            raise RuntimeError("No se pudo conectar al Gateway. Verifica la configuración.")
    
    if not tools_list:
        raise RuntimeError("No hay tools disponibles. El Gateway debe estar configurado correctamente.")
    
    # Crear agente con tools del Gateway
    agente_ventas = Agent(
        model=model,
        session_manager=session_manager,
        tools=tools_list,
        system_prompt=SYSTEM_PROMPT,
    )
    
    # Retornar el cliente usado (el proporcionado o el creado)
    return_mcp_client = mcp_client if mcp_client is not None else created_mcp_client
    
    return agente_ventas, session_id, return_mcp_client


def chat(agente, mensaje: str):
    """
    Envía mensaje al agente con memoria.
    
    Args:
        agente: Instancia del agente
        mensaje: Mensaje del usuario para el agente
    """
    import sys
    callback = StreamingCallback()
    agente.callback_handler = callback
    try:
        response = agente(mensaje)
        # Asegurar que stdout se vacíe completamente
        sys.stdout.flush()
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrumpido por el usuario")
        sys.stdout.flush()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.stdout.flush()
    finally:
        print("\n")
        sys.stdout.flush()
