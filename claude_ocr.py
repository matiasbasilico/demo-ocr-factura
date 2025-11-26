"""
claude_ocr.py
Extracción inteligente de facturas usando Claude API con detección automática de moneda
Versión mejorada con soporte para OC, HES, HEM y desglose completo de IVAs
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
    Incluye nuevos campos: OC, HES, HEM y desglose completo de IVAs.
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

**IMPORTANTE - TIPO DE FACTURA ARGENTINA (CÓDIGOS AFIP):**
En Argentina existen estos tipos de factura:
- CÓDIGO AFIP 01 → Factura Tipo A (RI vende a RI)
- CÓDIGO AFIP 06 → Factura Tipo B (RI vende a No RI / Consumidor)
- CÓDIGO AFIP 11 → Factura Tipo C (Monotributista)

Busca el "Código" con números de dos dígitos (01, 06, 11, etc) y traduce al tipo de letra correspondiente.
Si ves "Factura A", "Factura B", "Factura C" directamente, usa ese valor.

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
- Subtotal / Importe Neto Gravado
- Otros Tributos
- IVA/Tax/Impuestos - DESGLOSE DETALLADO de TODOS los porcentajes encontrados:
  * IVA 0%: $ monto (si existe)
  * IVA 2.5%: $ monto (si existe)
  * IVA 5%: $ monto (si existe)
  * IVA 10.5%: $ monto (si existe)
  * IVA 21%: $ monto (si existe)
  * IVA 27%: $ monto (si existe)
- Monto gravado
- Monto no gravado
- Monto exento

**DOCUMENTOS ASOCIADOS (MUY IMPORTANTE):**
Busca cuidadosamente en el detalle de items y extrae si existen:
- **OC** (Orden de Compra) - busca patrones como:
  * "OC:" seguido de número (ej: OC: 4527976895)
  * "Orden de Compra:" seguido de número
  * "Purchase Order:" seguido de número
  * Cualquier referencia a número de orden
  
- **HES** (Hoja de Entrada de Servicio) - busca patrones como:
  * "HES:" seguido de número (ej: HES: 1024526137)
  * "Hoja de Entrada de Servicio:" seguido de número
  * "Service Entry Sheet:" seguido de número
  
- **HEM** (Hoja de Entrada de Materiales) - busca patrones como:
  * "HEM:" seguido de número (ej: HEM: 1024526137)
  * "Hoja de Entrada de Materiales:" seguido de número
  * "Material Entry Sheet:" seguido de número
  * "Goods Receipt:" seguido de número

**ITEMS/LÍNEAS (si los hay):**
Para cada item detecta:
- Descripción de cada item
- Cantidad
- Precio unitario
- Total por línea
- Descuentos/bonificaciones
- Alícuota de IVA aplicada
- Si contiene "OC:" → extrae como "orden_compra"
- Si contiene "HES:" → extrae como "hoja_entrada_servicio"
- Si contiene "HEM:" → extrae como "hoja_entrada_materiales"

FORMATO DE RESPUESTA:
Responde ÚNICAMENTE con un JSON válido (sin ```json, sin markdown, sin explicaciones adicionales) con esta estructura EXACTA:

{{
  "supplier": {{
    "cuit": "30-71017365-2 o Tax ID",
    "name": "Razón Social Exacta Como Aparece",
    "address": "Dirección completa o null",
    "country": "Argentina o null"
  }},
  "client": {{
    "name": "Nombre exacto del cliente",
    "cuit": "30707542329 o null",
    "address": "Dirección o null",
    "code": "Código de cliente o null"
  }},
  "currency": "ARS",
  "currencySymbol": "$",
  "invoiceType": "A",
  "invoiceNumber": "00005-00000121",
  "pointSale": "00005",
  "cae": "74108913004192",
  "documentDate": "2024-03-08",
  "dueDate": "2024-03-18",
  "billingPeriod": {{
    "from": "2024-03-01",
    "to": "2024-03-31"
  }},
  "amount": 360564.27,
  "amountGrav": 297987.00,
  "amountNoGrav": 0,
  "amountExen": 0,
  "otherTaxes": 0.00,
  "ivaBreakdown": {{
    "iva_0": 0.00,
    "iva_2_5": 0.00,
    "iva_5": 0.00,
    "iva_10_5": 0.00,
    "iva_21": 62577.27,
    "iva_27": 0.00
  }},
  "items": [
    {{
      "description": "Acceso Back Office Portal Proveedores",
      "quantity": 1,
      "unit_price": 297987.00,
      "total": 297987.00,
      "discount": 0,
      "iva_rate": "21%",
      "orden_compra": "4527976895",
      "hoja_entrada_servicio": "1024526137",
      "hoja_entrada_materiales": null
    }}
  ],
  "confidence": {{
    "supplier_cuit": 0.98,
    "supplier_name": 0.95,
    "client_name": 0.92,
    "invoice_number": 0.99,
    "invoice_type": 0.95,
    "amount": 0.99,
    "currency": 0.95,
    "iva_breakdown": 0.98,
    "orden_compra": 0.95,
    "hoja_entrada_servicio": 0.95,
    "hoja_entrada_materiales": 0.00
  }},
  "reasoning": {{
    "supplier_name": "Encontré 'FRENCHELI GUSTAVO LEANDRO' como proveedor en el encabezado",
    "invoice_type": "Encontré 'Código 01' que corresponde a Factura Tipo A según AFIP",
    "amount": "Total de $360,564.27 claramente marcado como 'Importe Total'",
    "currency": "Detecté ARS porque: (1) documento en español, (2) CUIT argentino 20232505088, (3) CAE 74108913004192 presente, (4) referencias a AFIP",
    "iva_breakdown": "Desglosé los IVAs: IVA 21%: $62,577.27 sobre base de $297,987.00",
    "orden_compra": "Encontré OC: 4527976895 en la columna de detalle del item",
    "hoja_entrada_servicio": "Encontré HES: 1024526137 en la misma línea del item",
    "hoja_entrada_materiales": "No encontré ninguna referencia a HEM en el documento"
  }}
}}

REGLAS IMPORTANTES:
- Fechas SIEMPRE en formato YYYY-MM-DD
- Montos como números float (ej: 297987.00), NO strings
- Si un campo no existe en el documento, usa null
- NO inventes información que no esté en el texto
- La confianza debe reflejar qué tan seguro estás (0.0 = nada seguro, 1.0 = completamente seguro)
- En reasoning, explica BREVEMENTE cómo encontraste los campos más importantes
- Para ivaBreakdown, extrae TODOS los porcentajes mencionados, usa 0.00 si no existe ese porcentaje
- Para OC, HES, HEM: incluye el número exacto si está presente, sino usa null
- Si encuentras OC/HES/HEM, también inclúyelos en el reasoning explicando dónde los encontraste
- La suma de todos los IVAs en ivaBreakdown debe ser igual al campo "iva"
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
        if 'client' not in result:
            result['client'] = {}
        if 'confidence' not in result:
            result['confidence'] = {}
        if 'reasoning' not in result:
            result['reasoning'] = {}
        if 'ivaBreakdown' not in result:
            result['ivaBreakdown'] = {}
        if 'items' not in result:
            result['items'] = []
        
        # Asegurar que tenga moneda (default ARS si no detecta)
        if 'currency' not in result:
            result['currency'] = 'ARS'
            result['currencySymbol'] = '$'
            result['reasoning']['currency'] = 'No se pudo determinar con certeza, asumiendo ARS por defecto'
        
        # Calcular IVA total sumando todos los IVAs del breakdown
        if result.get('ivaBreakdown'):
            total_iva = sum(result['ivaBreakdown'].values())
            if total_iva > 0 and not result.get('iva'):
                result['iva'] = total_iva
        
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
    """Función de prueba con ejemplo que incluye OC, HES"""
    sample_text = """
    FRENCHELI GUSTAVO LEANDRO
    CUIT: 20232505088
    Factura A Nº 00005-00000121
    Código 01
    Fecha: 08/03/2024
    
    Cliente: LAN ARGENTINA SOCIEDAD ANONIMA
    CUIT: 30707542329
    
    Detalle:
    Acceso Back Office Portal Proveedores
    OC: 4527976895
    HES: 1024526137
    Cantidad: 1
    Precio Unit.: $ 297987,00
    
    Importe Neto Gravado: $ 297987,00
    IVA 21%: $ 62577,27
    Importe Total: $ 360564,27
    
    CAE: 74108913004192
    """
    
    try:
        result = extract_invoice_with_claude(sample_text)
        print("✅ Extracción exitosa:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    test_extraction()