"""
Gateway Utilities
================
Helpers para configurar AgentCore Gateway (basado en lab_helpers.utils)
"""
import os
import json
import boto3
from typing import Optional, Dict


def get_ssm_parameter(param_name: str, region: str = None) -> Optional[str]:
    """Obtiene un parámetro de SSM."""
    try:
        ssm = boto3.client("ssm", region_name=region)
        response = ssm.get_parameter(Name=param_name, WithDecryption=True)
        return response["Parameter"]["Value"]
    except Exception as e:
        print(f"⚠️ No se pudo obtener parámetro {param_name}: {e}")
        return None


def put_ssm_parameter(param_name: str, value: str, region: str = None) -> bool:
    """Guarda un parámetro en SSM."""
    try:
        ssm = boto3.client("ssm", region_name=region)
        ssm.put_parameter(
            Name=param_name,
            Value=value,
            Type="String",
            Overwrite=True
        )
        return True
    except Exception as e:
        print(f"❌ Error guardando parámetro {param_name}: {e}")
        return False


def load_api_spec(file_path: str) -> list:
    """Carga la especificación de API desde un archivo JSON."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_cognito_token(client_id: str, pool_id: str, region: str = None) -> Optional[str]:
    """
    Obtiene un token JWT de Cognito usando usuario de servicio.
    """
    try:
        cognito = boto3.client("cognito-idp", region_name=region)
        
        # Usuario de servicio para el Gateway
        username = "test-gateway-user"
        password = "Test123!@#"
        
        # Intentar autenticación
        auth_response = cognito.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": username,
                "PASSWORD": password,
            },
            ClientId=client_id,
        )
        
        return auth_response["AuthenticationResult"]["AccessToken"]
    except Exception as e:
        print(f"⚠️ Error obteniendo token de Cognito: {e}")
        return None


def get_or_create_cognito_pool(refresh_token: bool = False) -> Dict[str, str]:
    """
    Obtiene o crea configuración de Cognito.
    En producción, estos valores vendrían de SSM o CloudFormation.
    """
    # Obtener de SSM (si existen)
    region = boto3.session.Session().region_name
    
    client_id = get_ssm_parameter("/jamar/agentcore/cognito_client_id", region)
    discovery_url = get_ssm_parameter("/jamar/agentcore/cognito_discovery_url", region)
    pool_id = get_ssm_parameter("/jamar/agentcore/cognito_pool_id", region)
    
    if not all([client_id, discovery_url, pool_id]):
        raise ValueError(
            "Cognito no está configurado. "
            "Necesitas crear un Cognito User Pool y guardar los valores en SSM:\n"
            "- /jamar/agentcore/cognito_client_id\n"
            "- /jamar/agentcore/cognito_discovery_url\n"
            "- /jamar/agentcore/cognito_pool_id"
        )
    
    # Obtener token real de Cognito
    bearer_token = None
    if refresh_token:
        bearer_token = get_cognito_token(client_id, pool_id, region)
    
    return {
        "client_id": client_id,
        "discovery_url": discovery_url,
        "pool_id": pool_id,
        "bearer_token": bearer_token,
    }
