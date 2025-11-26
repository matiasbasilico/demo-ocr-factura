"""
claude_ocr.py
Extracción inteligente de facturas usando Claude API con detección automática de moneda
"""

import anthropic
import os
import json
import re


def extract_invoice_with_claude(pdf_text, api_key=None):
    """
    Usa Claude API real para extraer datos de forma inteligente.
    Claude analiza el texto completo y extrae campos automáticamente.
    Detecta automáticamente la moneda (USD vs ARS) según el idioma y contexto.
    """
    
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    
    if not api_key:
        raise ValueError("Se requiere ANTHROPIC_API_KEY en las variables de entorno")
    
    client = anthropic.Anthropic(api_key=api_key)
    
    prompt = f"""Eres un experto en análisis de facturas internacionales. Analiza el siguiente texto extraído de una factura y extrae TODA la información relevante.

TEXTO DE LA FACTURA:
{pdf_text}

INSTRUCCIONES CRÍTICAS:
1. Extrae TODOS los campos que encuentres
2. NO inventes datos - solo extrae lo que realmente está en el texto
3. Sé MUY PRECISO con números y fechas
4. Para cada campo importante, indica tu nivel de confianza (0.0 a 1.0)
5. Explica brevemente cómo encontraste cada campo importante

**DETECCIÓN AUTOMÁTICA DE MONEDA (MUY IMPORTANTE):**
Analiza el idioma y contexto del documento para determinar la moneda:

REGLAS PARA USD (Dólares estadounidenses):
- Documento EN INGLÉS (palabras: "invoice", "total", "amount", "tax")
- Contiene explícitamente: "USD", "US$", "dollars", "US dollars"
- Tiene Tax ID (en vez de CUIT) o EIN number
- País: USA, United States, o sin país pero en inglés

REGLAS PARA ARS (Pesos argentinos):
- Documento EN ESPAÑOL (palabras: "factura", "total", "monto", "impuesto")
- Contiene: "CUIT", "AFIP", "Argentina", "Ingresos Brutos"
- Tiene CAE (Código de Autorización Electrónico)
- Referencias geográficas argentinas (provincias, ciudades)

REGLAS PARA OTRAS MONEDAS:
- EUR: Europa, "€", "euros", idioma español/francés/alemán con referencias europeas
- MXN: México, "MXN", "RFC" (en vez de CUIT)
- CLP: Chile, "CLP", "RUT"
- BRL: Brasil, "R$", "CNPJ"

Si el símbolo "$" aparece sin aclaración explícita:
- Documento en inglés → USD
- Documento en español con CUIT/AFIP/Argentina → ARS
- Documento en español sin referencias argentinas → revisar país

IMPORTANTE: 
- Incluye "currency" con el código ISO (USD, ARS, EUR, etc)
- Incluye "currencySymbol" con el símbolo visual ($, US$, €, etc)
- En "reasoning.currency" explica DETALLADAMENTE por qué elegiste esa moneda

CAMPOS A BUSCAR (extrae todos los que encuentres):

**PROVEEDOR (quien emite la factura):**
- CUIT/Tax ID/RFC del proveedor
- Razón social completa
- Dirección
- País

**CLIENTE (a quien se le factura):**
- Nombre/razón social del cliente
- CUIT/Tax ID del cliente
- Dirección del cliente
- Código de cliente

**FACTURA:**
- Tipo (A, B, C, Invoice, etc)
- Número completo
- Punto de venta (si aplica)
- CAE (si es factura argentina)
- Fecha de emisión
- Fecha de vencimiento
- Período facturado (desde-hasta)

**MONEDA Y MONTOS:**
- Moneda detectada (USD, ARS, EUR, etc)
- Símbolo usado ($, US$, €, etc)
- Total a pagar (el monto final)
- Subtotal
- IVA/Tax/Impuestos (desglosa si hay varios)
- Monto gravado
- Monto no gravado
- Monto exento
- Otros impuestos o percepciones

**ITEMS/LÍNEAS (si los hay):**
- Descripción de cada item
- Cantidad
- Precio unitario
- Total por línea
- Descuentos/bonificaciones

FORMATO DE RESPUESTA:
Responde ÚNICAMENTE con un JSON válido (sin ```json, sin markdown, sin explicaciones adicionales) con esta estructura EXACTA:

{{
  "supplier": {{
    "cuit": "XX-XXXXXXXX-X o Tax ID",
    "name": "Razón Social Exacta Como Aparece",
    "address": "Dirección completa o null",
    "country": "Argentina|USA|Mexico|etc o null"
  }},
  "client": {{
    "name": "Nombre exacto del cliente",
    "cuit": "XX-XXXXXXXX-X o null",
    "address": "Dirección o null",
    "code": "Código de cliente o null"
  }},
  "currency": "ARS",
  "currencySymbol": "$",
  "invoiceType": "B",
  "invoiceNumber": "1305-76453547",
  "pointSale": "1305",
  "cae": "73347774383997",
  "documentDate": "2023-08-22",
  "dueDate": "2023-09-14",
  "billingPeriod": {{
    "from": "2023-07-23",
    "to": "2023-08-22"
  }},
  "amount": 9136.40,
  "iva": 205.40,
  "amountGrav": 8040.42,
  "amountNoGrav": 0,
  "amountExen": 0,
  "otherTaxes": [
    {{"name": "Perc. IIBB Salta", "amount": 890.55}}
  ],
  "items": [
    {{
      "description": "Plan Control 1GB PC90R",
      "quantity": 3,
      "unit_price": 3050.00,
      "total": 11071.50,
      "discount": -5535.78
    }}
  ],
  "confidence": {{
    "supplier_cuit": 0.98,
    "supplier_name": 0.95,
    "client_name": 0.92,
    "invoice_number": 0.99,
    "amount": 0.99,
    "currency": 0.95
  }},
  "reasoning": {{
    "supplier_name": "Encontré 'AMX ARGENTINA S.A.' en el encabezado como emisor de la factura",
    "client_name": "Identificado 'ASOCIACION CULTURAL Y DEPORTI' como el destinatario/cliente",
    "amount": "Total de $9,136.40 claramente marcado como 'Total a Pagar' al final del documento",
    "currency": "Detecté ARS (pesos argentinos) porque: (1) documento completamente en español, (2) contiene CUIT argentino 30-66328849-7, (3) referencia a AFIP y CAE, (4) ubicación en Argentina. Si fuera USD, el documento estaría en inglés o tendría 'USD' explícito."
  }}
}}

REGLAS IMPORTANTES:
- Fechas SIEMPRE en formato YYYY-MM-DD
- Montos como números float (ej: 9136.40), NO strings
- Si un campo no existe en el documento, usa null
- NO inventes información que no esté en el texto
- La confianza debe reflejar qué tan seguro estás (0.0 = nada seguro, 1.0 = completamente seguro)
- En reasoning, explica BREVEMENTE cómo encontraste los campos más importantes
- Para currency, explica DETALLADAMENTE las pistas que usaste (idioma, referencias geográficas, códigos fiscales)
"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            temperature=0,  # Determinístico para extracción de datos
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        response_text = message.content[0].text
        
        # Limpiar respuesta (quitar markdown si Claude lo agregó)
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*', '', response_text)
        response_text = response_text.strip()
        
        # Parsear JSON
        result = json.loads(response_text)
        
        # Validar estructura básica
        if not isinstance(result, dict):
            raise ValueError("La respuesta no es un diccionario válido")
        
        # Asegurar que tenga las claves mínimas
        if 'supplier' not in result:
            result['supplier'] = {}
        if 'confidence' not in result:
            result['confidence'] = {}
        if 'reasoning' not in result:
            result['reasoning'] = {}
        
        # Asegurar que tenga moneda (default ARS si no detecta)
        if 'currency' not in result:
            result['currency'] = 'ARS'
            result['currencySymbol'] = '$'
            result['reasoning']['currency'] = 'No se pudo determinar con certeza, asumiendo ARS por defecto'
        
        return result
        
    except json.JSONDecodeError as e:
        print(f"❌ Error parseando JSON de Claude: {e}")
        print(f"📄 Respuesta recibida (primeros 500 chars): {response_text[:500]}")
        raise Exception(f"Claude no retornó JSON válido: {str(e)}")
        
    except anthropic.APIError as e:
        print(f"❌ Error en API de Anthropic: {e}")
        raise Exception(f"Error de API: {str(e)}")
        
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        raise


def test_extraction():
    """Función de prueba"""
    sample_text = """
    AMX ARGENTINA S.A.
    CUIT: 30-66328849-7
    Factura B Nro. 1305-76453547
    Fecha: 22/08/2023
    
    Cliente: ASOCIACION CULTURAL Y DEPORTI
    Total: $9,136.40
    """
    
    try:
        result = extract_invoice_with_claude(sample_text)
        print("✅ Extracción exitosa:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    test_extraction()