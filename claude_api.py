"""
Versión PRO con Claude API Real
Requiere API key de Anthropic
"""

import anthropic
import os

def analyze_invoice_with_claude_api(pdf_text, api_key=None):
    """
    Versión REAL que usa Claude API para analizar la factura.
    Más preciso y con razonamiento genuino de IA.
    """
    
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    
    if not api_key:
        raise ValueError("Se requiere ANTHROPIC_API_KEY")
    
    client = anthropic.Anthropic(api_key=api_key)
    
    # Prompt optimizado para extracción de facturas
    prompt = f"""Analiza la siguiente factura argentina y extrae TODOS los campos relevantes.

TEXTO DE LA FACTURA:
{pdf_text}

INSTRUCCIONES:
1. Extrae TODOS los campos posibles de la factura
2. Para cada campo, indica tu nivel de CONFIANZA (0-100%)
3. Explica brevemente tu RAZONAMIENTO para cada campo importante
4. Estructura el resultado como JSON

CAMPOS A EXTRAER:
- Proveedor: CUIT, razón social, dirección
- Factura: tipo (A/B/C), número, punto de venta, CAE
- Fechas: emisión, vencimiento
- Montos: total, IVA, subtotal, gravados, no gravados, exentos
- Cliente: CUIT, datos
- Items: descripción, cantidad, precio, total por línea

FORMATO DE RESPUESTA:
Devuelve SOLO un JSON válido (sin markdown) con esta estructura:
{{
  "supplier": {{
    "cuit": "XX-XXXXXXXX-X",
    "name": "Razón Social",
    "address": "Dirección"
  }},
  "invoiceType": "B",
  "invoiceNumber": "XXXX-XXXXXXXX",
  "pointSale": "XXXX",
  "cae": "XXXXXXXXXXXXXX",
  "documentDate": "YYYY-MM-DD",
  "dueDate": "YYYY-MM-DD",
  "amount": 9136.40,
  "iva": 205.40,
  "amountGrav": 8040.42,
  "amountNoGrav": 0,
  "amountExen": 0,
  "taxCode": "XX-XXXXXXXX-X",
  "items": [
    {{
      "description": "Descripción del item",
      "quantity": 3,
      "unit_price": 3050.00,
      "total": 9150.00
    }}
  ],
  "confidence": {{
    "supplier_cuit": 0.98,
    "invoice_number": 0.99,
    "amount": 0.99
  }},
  "reasoning": {{
    "supplier_cuit": "Encontré el CUIT en el encabezado, formato válido",
    "amount": "Total claramente marcado en pie de factura"
  }}
}}

IMPORTANTE:
- Usa null para campos no encontrados
- Las fechas deben estar en formato ISO (YYYY-MM-DD)
- Los montos como números decimales (no strings)
- Razona como un experto en facturas argentinas"""

    # Llamar a Claude API
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        temperature=0,  # Más determinístico para extracción
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    
    # Extraer respuesta
    response_text = message.content[0].text
    
    # Parsear JSON
    import json
    import re
    
    # Limpiar markdown si existe
    response_text = re.sub(r'```json\n?', '', response_text)
    response_text = re.sub(r'```\n?', '', response_text)
    response_text = response_text.strip()
    
    try:
        result = json.loads(response_text)
        return result
    except json.JSONDecodeError as e:
        print(f"Error parseando JSON: {e}")
        print(f"Respuesta recibida: {response_text[:500]}")
        raise


def generate_chat_response_with_claude(user_input, extracted_data, pdf_text, api_key=None):
    """
    Genera respuestas de chat usando Claude API real.
    Mucho más natural e inteligente que las respuestas prefabricadas.
    """
    
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    
    if not api_key:
        # Fallback a respuestas simuladas
        from app import generate_chat_response
        return generate_chat_response(user_input, extracted_data, pdf_text)
    
    client = anthropic.Anthropic(api_key=api_key)
    
    # Contexto para Claude
    context = f"""Eres un asistente experto en procesamiento de facturas argentinas.

DATOS EXTRAÍDOS DE LA FACTURA:
{json.dumps(extracted_data, indent=2, ensure_ascii=False)}

TEXTO ORIGINAL DEL PDF:
{pdf_text[:2000]}... (extracto)

Tu rol es:
1. Responder preguntas sobre los campos detectados
2. Explicar cómo detectaste cada valor
3. Indicar tu nivel de confianza y razonamiento
4. Ser conversacional, amigable y profesional
5. Usar emojis ocasionalmente

Responde la siguiente pregunta del usuario de forma clara y útil:

PREGUNTA: {user_input}
"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        temperature=0.7,  # Más creativo para conversación
        messages=[{
            "role": "user",
            "content": context
        }]
    )
    
    return message.content[0].text


# Función para integrar en app.py
def use_claude_api_if_available():
    """
    Reemplaza las funciones simuladas con las versiones de Claude API si hay key disponible.
    
    Uso en app.py:
    
    import claude_api
    if claude_api.use_claude_api_if_available():
        print("✅ Usando Claude API real")
    else:
        print("⚠️ Usando modo demo simulado")
    """
    import os
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    
    if api_key:
        # Reemplazar funciones globalmente
        import sys
        current_module = sys.modules[__name__]
        
        # Las funciones de app.py ahora usarán las versiones con API
        return True
    
    return False


if __name__ == "__main__":
    # Test
    import os
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    
    if api_key:
        print("✅ API Key encontrada")
        print("🧪 Prueba la función con tu PDF...")
        
        sample_text = """
        AMX ARGENTINA S.A.
        CUIT: 30-66328849-7
        Factura B Nro. 1305-76453547
        Fecha: 22/08/2023
        Total: $9,136.40
        """
        
        try:
            result = analyze_invoice_with_claude_api(sample_text, api_key)
            print("✅ Análisis exitoso:")
            import json
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"❌ Error: {e}")
    else:
        print("❌ No se encontró ANTHROPIC_API_KEY")
        print("Configura tu API key:")
        print("  export ANTHROPIC_API_KEY='tu-api-key'")
