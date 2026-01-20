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


def get_tool_name(tool):
    """Extrae el nombre real de una tool, intentando diferentes métodos."""
    if hasattr(tool, 'name'):
        name = getattr(tool, 'name', None)
        if name:
            return name
    if hasattr(tool, 'function') and hasattr(tool.function, 'name'):
        return tool.function.name
    if hasattr(tool, '__name__'):
        return tool.__name__
    # Intentar acceder a atributos internos de MCPAgentTool
    if hasattr(tool, '_tool_name'):
        return tool._tool_name
    if hasattr(tool, 'tool_name'):
        return tool.tool_name
    return None


def create_agent_in_context(memory_id: str, region: str, actor_id: str, mcp_client):
    """
    Crea el agente DENTRO de un contexto MCPClient activo.
    IMPORTANTE: Esta función DEBE llamarse dentro de un bloque 'with mcp_client:'
    
    Args:
        memory_id: ID de la memoria AgentCore
        region: Región de AWS
        actor_id: ID del actor/cliente
        mcp_client: MCPClient que ya está dentro de un contexto activo
    
    Returns:
        tuple: (agente, session_id)
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
    
    # Obtener tools del Gateway (ya estamos dentro del contexto)
    print(f"🔧 Obteniendo tools del Gateway...")
    gateway_tools = mcp_client.list_tools_sync()
    print(f"✅ Tools obtenidas: {len(gateway_tools)}")
    
    # Mostrar nombres de tools
    tool_names = []
    for t in gateway_tools[:10]:
        name = get_tool_name(t) or "Unknown"
        tool_names.append(name)
    print(f"   Primeras 10 tools: {tool_names}")
    
    # Verificar buscar_productos
    buscar_productos_found = False
    for t in gateway_tools:
        name = get_tool_name(t)
        if name and name.lower() == 'buscar_productos':
            buscar_productos_found = True
            break
    if buscar_productos_found:
        print(f"   ✅ Tool 'buscar_productos' encontrada")
    else:
        print(f"   ⚠️ Tool 'buscar_productos' NO encontrada")
    
    # Crear agente con las tools del Gateway
    print(f"🔧 Creando agente con {len(gateway_tools)} tools...")
    agente = Agent(
        model=model,
        session_manager=session_manager,
        tools=gateway_tools,
        system_prompt=SYSTEM_PROMPT,
    )
    print(f"✅ Agente creado exitosamente")
    
    return agente, session_id


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
                # Obtener las tools dentro del contexto (el cliente se inicializará automáticamente)
                # NOTA: El cliente se cerrará después, pero se volverá a abrir cuando se ejecute el agente
                # IMPORTANTE: El MCPClient DEBE estar dentro de un contexto 'with' para usar list_tools_sync()
                print(f"🔧 Obteniendo tools del Gateway (cliente proporcionado)...")
                try:
                    # Intentar usar el cliente dentro de un contexto
                    with mcp_client:
                        gateway_tools = mcp_client.list_tools_sync()
                        tools_list.extend(gateway_tools)
                        print(f"✅ Gateway conectado exitosamente!")
                        print(f"   Tools disponibles: {len(gateway_tools)}")
                        # Debug: Mostrar nombres de algunas tools
                        if gateway_tools:
                            # Obtener nombres reales de las tools
                            tool_names = []
                            for t in gateway_tools[:10]:
                                tool_name = "Unknown"
                                if hasattr(t, 'name'):
                                    tool_name = getattr(t, 'name', 'Unknown')
                                elif hasattr(t, 'function') and hasattr(t.function, 'name'):
                                    tool_name = t.function.name
                                elif hasattr(t, '__name__'):
                                    tool_name = t.__name__
                                tool_names.append(tool_name[:50])
                            print(f"   Primeras 10 tools: {tool_names}")
                            
                            # Verificar específicamente buscar_productos
                            buscar_productos_found = False
                            for t in gateway_tools:
                                tool_name = None
                                if hasattr(t, 'name'):
                                    tool_name = getattr(t, 'name', '').lower()
                                elif hasattr(t, 'function') and hasattr(t.function, 'name'):
                                    tool_name = t.function.name.lower()
                                if tool_name == 'buscar_productos':
                                    buscar_productos_found = True
                                    break
                            if buscar_productos_found:
                                print(f"   ✅ Tool 'buscar_productos' encontrada en Gateway")
                            else:
                                print(f"   ⚠️ Tool 'buscar_productos' NO encontrada en Gateway")
                except Exception as ctx_error:
                    error_msg = str(ctx_error)
                    if "not running" in error_msg.lower() or "session" in error_msg.lower():
                        print(f"⚠️ MCPClient necesita estar en contexto. Creando nuevo cliente temporal...")
                        # Crear un cliente temporal solo para obtener las tools
                        from strands.tools.mcp import MCPClient
                        from mcp.client.streamable_http import streamablehttp_client
                        import sys
                        import os
                        gateway_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "gateway")
                        if gateway_path not in sys.path:
                            sys.path.insert(0, gateway_path)
                        from utils import get_ssm_parameter, get_cognito_token
                        
                        gateway_url = get_ssm_parameter("/jamar/agentcore/gateway_url", region)
                        client_id = get_ssm_parameter("/jamar/agentcore/cognito_client_id", region)
                        pool_id = get_ssm_parameter("/jamar/agentcore/cognito_pool_id", region)
                        bearer_token = get_cognito_token(client_id, pool_id, region)
                        
                        temp_client = MCPClient(
                            lambda: streamablehttp_client(
                                gateway_url,
                                headers={"Authorization": f"Bearer {bearer_token}"},
                            )
                        )
                        with temp_client:
                            gateway_tools = temp_client.list_tools_sync()
                            tools_list.extend(gateway_tools)
                            print(f"✅ Gateway conectado exitosamente (cliente temporal)!")
                            print(f"   Tools disponibles: {len(gateway_tools)}")
                # NOTA: El cliente original se usará cuando se ejecute el agente dentro del contexto
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
                
                # Obtener tools dentro del contexto (el cliente se inicializará automáticamente)
                # NOTA: El cliente se cerrará después, pero se volverá a abrir cuando se ejecute el agente
                with created_mcp_client:
                    gateway_tools = created_mcp_client.list_tools_sync()
                    tools_list.extend(gateway_tools)
                    print(f"✅ Gateway conectado exitosamente!")
                    print(f"   URL: {gateway_url}")
                    print(f"   Tools disponibles: {len(gateway_tools)}")
                    # Debug: Mostrar nombres de algunas tools
                    if gateway_tools:
                        tool_names = []
                        for t in gateway_tools[:10]:
                            name = get_tool_name(t) or "Unknown"
                            tool_names.append(name[:50])
                        print(f"   Primeras 10 tools: {tool_names}")
                        
                        # Verificar específicamente buscar_productos
                        buscar_productos_found = False
                        for t in gateway_tools:
                            name = get_tool_name(t)
                            if name and name.lower() == 'buscar_productos':
                                buscar_productos_found = True
                                break
                        if buscar_productos_found:
                            print(f"   ✅ Tool 'buscar_productos' encontrada en Gateway")
                        else:
                            print(f"   ⚠️ Tool 'buscar_productos' NO encontrada en Gateway")
                # NOTA: El cliente se cerrará aquí, pero se volverá a abrir cuando se ejecute el agente dentro del contexto
        
        except Exception as e:
            print(f"⚠️ Error integrando Gateway: {e}")
            import traceback
            traceback.print_exc()
            raise RuntimeError("No se pudo conectar al Gateway. Verifica la configuración.")
    
    if not tools_list:
        raise RuntimeError("No hay tools disponibles. El Gateway debe estar configurado correctamente.")
    
    # Debug: Verificar tools antes de crear agente
    print(f"📦 Total de tools que se pasarán al agente: {len(tools_list)}")
    if tools_list:
        tool_names_preview = []
        for t in tools_list[:10]:
            name = get_tool_name(t) or "Unknown"
            tool_names_preview.append(name[:40])
        print(f"   Preview de tools: {tool_names_preview}")
        
        # Verificar que hay tools importantes
        tool_names_lower = []
        for t in tools_list:
            name = get_tool_name(t)
            if name:
                tool_names_lower.append(name.lower())
        if 'buscar_productos' in tool_names_lower:
            print(f"   ✅ Tool 'buscar_productos' encontrada")
        else:
            print(f"   ⚠️ Tool 'buscar_productos' NO encontrada en la lista")
            print(f"   Tools disponibles: {tool_names_lower[:20]}")
    else:
        print(f"   ❌ ERROR: No hay tools disponibles!")
    
    # Crear agente con tools del Gateway
    print(f"🔧 Creando agente con {len(tools_list)} tools...")
    try:
        agente_ventas = Agent(
            model=model,
            session_manager=session_manager,
            tools=tools_list,
            system_prompt=SYSTEM_PROMPT,
        )
        print(f"✅ Agente creado exitosamente")
    except Exception as e:
        print(f"❌ Error creando agente: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    # Verificar que el agente tiene las tools
    # Strands Agent puede almacenar tools de diferentes maneras
    tools_in_agent = None
    if hasattr(agente_ventas, 'tools'):
        tools_in_agent = agente_ventas.tools
    elif hasattr(agente_ventas, '_tools'):
        tools_in_agent = agente_ventas._tools
    elif hasattr(agente_ventas, 'agent') and hasattr(agente_ventas.agent, 'tools'):
        tools_in_agent = agente_ventas.agent.tools
    
    if tools_in_agent:
        try:
            tool_count = len(tools_in_agent) if hasattr(tools_in_agent, '__len__') else 'N/A'
            print(f"✅ Agente tiene {tool_count} tools registradas")
            # Verificar nuevamente que buscar_productos está disponible
            try:
                agent_tool_names = []
                for t in tools_in_agent[:50]:  # Limitar a 50 para no saturar logs
                    tool_name = get_tool_name(t)
                    if tool_name:
                        agent_tool_names.append(tool_name.lower())
                
                if 'buscar_productos' in agent_tool_names:
                    print(f"   ✅ Tool 'buscar_productos' está disponible en el agente")
                else:
                    print(f"   ⚠️ Tool 'buscar_productos' NO encontrada en las primeras 50 tools")
                    print(f"   Primeras tools encontradas: {agent_tool_names[:10]}")
            except Exception as e:
                print(f"   ⚠️ Error verificando nombres de tools: {e}")
        except Exception as e:
            print(f"   ⚠️ Error contando tools: {e}")
    else:
        print("⚠️ Advertencia: No se pudo encontrar tools en el agente")
        print(f"   Atributos del agente: {[attr for attr in dir(agente_ventas) if not attr.startswith('_')][:20]}")
    
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
