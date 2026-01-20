"""
Memory Manager
==============
Gestión de memoria AgentCore para el agente.
"""
import contextlib
from io import StringIO
from bedrock_agentcore_starter_toolkit.operations.memory.manager import MemoryManager as BaseMemoryManager
from bedrock_agentcore.memory.constants import StrategyType


def create_memory(region_name: str, memory_name: str = "ShopifySalesAgentMemory"):
    """
    Crea o obtiene una memoria existente.
    
    Args:
        region_name: Región de AWS
        memory_name: Nombre de la memoria
    
    Returns:
        dict: Información de la memoria con 'id'
    """
    # Redirigir stderr temporalmente para ocultar mensajes de inicialización
    with contextlib.redirect_stderr(StringIO()):
        memory_manager = BaseMemoryManager(region_name=region_name)
        memory = memory_manager.get_or_create_memory(
            name=memory_name,
            strategies=[
                {
                    StrategyType.USER_PREFERENCE.value: {
                        "name": "CustomerPreferences",
                        "description": "Preferencias del cliente: estilo, colores, presupuesto, tamaño de espacios",
                        "namespaces": ["shopify/customer/{actorId}/preferences"],
                    }
                },
                {
                    StrategyType.SEMANTIC.value: {
                        "name": "CustomerInteractions",
                        "description": "Historial de productos vistos, consultas y compras anteriores",
                        "namespaces": ["shopify/customer/{actorId}/interactions"],
                    }
                },
            ]
        )
    
    return memory
