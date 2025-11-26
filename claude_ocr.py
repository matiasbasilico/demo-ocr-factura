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
    
    prompt = f"""Eres un experto en análisis de documentos comerciales (facturas y proformas). Analiza el siguiente texto y extrae TODA la información relevante.

TEXTO DEL DOCUMENTO:
{pdf_text}

INSTRUCCIONES CRÍTICAS:
1. **DETECTA EL TIPO DE DOCUMENTO PRIMERO:**
   - Si contiene: "Factura", "CUIT", "CAE", "AFIP" → es una FACTURA
   - Si contiene: "Remito nº", "Fecha de Remito", "Sucursal Nº", columnas tabulares → es una PROFORMA
   - Si no estás seguro, analiza el contenido y estructura

2. Extrae TODOS los campos que encuentres según el tipo de documento
3. NO inventes datos - solo extrae lo que realmente está en el texto
4. Sé MUY PRECISO con números y fechas
5. Para cada campo importante, indica tu nivel de confianza (0.0 a 1.0)

═══════════════════════════════════════════════════════════════════════
TIPO 1: FACTURAS (mantener toda la lógica anterior)
═══════════════════════════════════════════════════════════════════════

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

═══════════════════════════════════════════════════════════════════════
TIPO 2: PROFORMAS (nuevo tipo de documento)
═══════════════════════════════════════════════════════════════════════

Si el documento es una PROFORMA (listado de remitos/trabajos), extrae:

**IDENTIFICACIÓN DE PROFORMA:**
Busca estos indicadores:
- Columnas: "Remito nº", "Fecha de Remito", "Sucursal Nº", "Nombre Sucursal", "Provincia", "Item nº", "Cantidad"
- Palabras clave: "TOTAL $", "Descripción Item", "Importe Unitario", "Importe total"
- Estructura tabular con múltiples remitos
- Puede tener secciones: "PLANILLA_RTOS", "SUCURSALES", "PRECIARIO"

**CAMPOS PRINCIPALES:**
- documentType: "PROFORMA"
- title: Extraer del nombre del archivo o primera línea (ej: "MACRO Trabajos en sucursales por obra")
- totalAmount: Buscar "TOTAL $" seguido del monto (ej: "TOTAL $ 9,666,318.56")
- currency: "ARS" (símbolo $, formato argentino)
- dateGenerated: Buscar fecha en formato DD-MM-YYYY o en nombre de archivo
- clientName: Buscar en el título o primera sección (ej: "MACRO")

**PLANILLAS/SECCIONES DETECTADAS:**
- sheetNames: Identificar secciones como:
  * "PLANILLA_RTOS" o "PLANILLA RTOS" → listado de remitos con items
  * "SUCURSALES" → listado de códigos y nombres de sucursales
  * "PRECIARIO" → listado de items con precios unitarios
  * Cualquier otra sección visible en el documento

**ITEMS DE PROFORMA - SECCIÓN "PLANILLA_RTOS":**

CRÍTICO: Extrae TODAS las filas de la tabla de remitos. Cada fila es un item.

Estructura típica de cada línea:
```
106257    8/22/2025    930    AV SANTA FE BMA    AMBA    19    1
```

Mapeo de columnas:
- Columna 1: remito_number (ej: "106257")
- Columna 2: remito_date (ej: "8/22/2025" → convertir a "2025-08-22")
- Columna 3: branch_number (ej: "930")
- Columna 4: branch_name (ej: "AV SANTA FE BMA")
- Columna 5: province (ej: "AMBA", "GRAN BS AS")
- Columna 6: item_number (ej: "19", "32", "48")
- Columna 7: quantity (ej: 1, 26, 152)

**IMPORTANTE - RELACIONAR CON PRECIOS:**
Los precios están en la sección "PRECIARIO" con formato:
```
19 - Normalización gral., incluye todas las tareas necesarias $ 39,557.58 $ 39,557.58
```

Mapeo:
- Primera parte: item_number y description (ej: "19 - Normalización gral...")
- Segunda parte: unit_price (ej: "$ 39,557.58")
- Tercera parte: total_price (ej: "$ 39,557.58")

Para cada item en PLANILLA_RTOS:
1. Buscar el item_number en PRECIARIO
2. Extraer description, unit_price del PRECIARIO
3. Calcular total_price = unit_price × quantity
4. Si el total_price ya está en PRECIARIO, usar ese valor

**FORMATO DE CADA ITEM:**
```json
{
  "remito_number": "106257",
  "remito_date": "2025-08-22",
  "branch_number": "930",
  "branch_name": "AV SANTA FE BMA",
  "province": "AMBA",
  "item_number": "19",
  "quantity": 1,
  "description": "Normalización gral., incluye todas las tareas necesarias",
  "unit_price": 39557.58,
  "total_price": 39557.58
}
```

**NOTAS:**
- Si un remito tiene múltiples items, crear un objeto separado para cada línea
- Convertir fechas de M/D/YYYY a YYYY-MM-DD
- Remover símbolos "$" y "," de los montos antes de convertir a float
- Si no encuentras el precio en PRECIARIO, dejar unit_price y total_price en 0

═══════════════════════════════════════════════════════════════════════
FORMATO DE RESPUESTA
═══════════════════════════════════════════════════════════════════════

**SI ES FACTURA**, responde con la estructura anterior de factura.

**SI ES PROFORMA**, responde ÚNICAMENTE con un JSON válido (sin ```json, sin markdown) con esta estructura:

{{
  "documentType": "PROFORMA",
  "title": "MACRO Trabajos en sucursales por obra 02-09-2025",
  "totalAmount": 9666318.56,
  "currency": "ARS",
  "currencySymbol": "$",
  "dateGenerated": "2025-09-02",
  "clientName": "MACRO",
  "sheetNames": ["PLANILLA_RTOS", "SUCURSALES", "PRECIARIO"],
  "items": [
    {{
      "remito_number": "106257",
      "remito_date": "2025-08-22",
      "branch_number": "930",
      "branch_name": "AV SANTA FE BMA",
      "province": "AMBA",
      "item_number": "19",
      "quantity": 1,
      "description": "Normalización gral., incluye todas las tareas necesarias",
      "unit_price": 39557.58,
      "total_price": 39557.58
    }},
    {{
      "remito_number": "106257",
      "remito_date": "2025-08-22",
      "branch_number": "930",
      "branch_name": "AV SANTA FE BMA",
      "province": "AMBA",
      "item_number": "32",
      "quantity": 1,
      "description": "Viaticos Zona 1 C.A.B.A y Conurbano hasta 50km",
      "unit_price": 25633.31,
      "total_price": 25633.31
    }},
    {{
      "remito_number": "106036",
      "remito_date": "2025-08-25",
      "branch_number": "480",
      "branch_name": "AVELLANEDA BMA",
      "province": "GRAN BS AS",
      "item_number": "21",
      "quantity": 2,
      "description": "Intervención en cámara (incluye cambio de lente)",
      "unit_price": 14384.57,
      "total_price": 28769.14
    }}
  ],
  "summary": {{
    "total_remitos": 15,
    "total_items": 85,
    "total_amount": 9666318.56,
    "unique_branches": 12,
    "date_range": "2025-08-13 to 2025-08-29"
  }},
  "confidence": {{
    "document_type": 0.99,
    "total_amount": 0.98,
    "items_extraction": 0.95,
    "price_matching": 0.92
  }},
  "reasoning": {{
    "document_type": "Detecté PROFORMA porque tiene: (1) columnas 'Remito nº', 'Fecha de Remito', 'Sucursal Nº', etc., (2) secciones PLANILLA_RTOS, SUCURSALES, PRECIARIO, (3) formato tabular con múltiples remitos",
    "total_amount": "Encontré 'TOTAL $ 9,666,318.56' en página 17 del documento",
    "currency": "Detecté ARS porque: (1) símbolo $, (2) formato argentino (ej: 9,666,318.56), (3) referencias a provincias argentinas (AMBA, GRAN BS AS), (4) nombres de sucursales argentinas",
    "items": "Extraje 85 líneas de PLANILLA_RTOS (páginas 1-3) y relacioné con precios del PRECIARIO (páginas 17-19). Cada línea tiene remito, sucursal, item y cantidad.",
    "price_matching": "Relacioné items con PRECIARIO: Item 19 → $39,557.58, Item 32 → $25,633.31, Item 48 → $6,534.28, etc."
  }}
}}

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
- IVA/Tax/Impuestos - CRÍTICO SOBRE DESGLOSE:
  * SOLO incluye en ivaBreakdown las alícuotas que estén EXPLÍCITAMENTE mencionadas con formato:
    - "IVA 0%: $X" o "IVA 0%: X"
    - "IVA 2.5%: $X" o "IVA 2,5%: X"
    - "IVA 5%: $X"
    - "IVA 10.5%: $X" o "IVA 10,5%: X"
    - "IVA 21%: $X"
    - "IVA 27%: $X"
  * Si el documento solo dice "I.V.A. INSC. %" o "IVA:" sin especificar alícuota → NO inventes el desglose
  * Si el documento solo dice "IVA" con un monto total → pon ese monto en el campo "iva" pero deja ivaBreakdown en ceros
  * NO ASUMAS que es IVA 21% si no está explícito
  * Si no hay desglose explícito, todos los valores de ivaBreakdown deben ser 0.00
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
    "iva_breakdown": "Desglosé los IVAs explícitos: IVA 21%: $62,577.27 sobre base de $297,987.00. Los demás están en 0 porque no aparecen en el documento.",
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
- **CRÍTICO - DESGLOSE DE IVA:**
  * Solo incluye valores en ivaBreakdown si el documento dice EXPLÍCITAMENTE "IVA X%: $monto"
  * Si solo dice "I.V.A. INSC. %" o "IVA: $monto" sin alícuota → todos los ivaBreakdown en 0.00
  * Ejemplo 1: Documento dice "IVA 21%: $62,577.27" → iva_21: 62577.27
  * Ejemplo 2: Documento dice "I.V.A. INSC. %: 6546.96" → TODOS los ivaBreakdown en 0.00, iva: 6546.96
  * Ejemplo 3: No menciona IVA → iva: 0.00 y todos los ivaBreakdown en 0.00
  * NO asumas la alícuota basándote en el país o tipo de factura
- Para OC, HES, HEM: incluye el número exacto si está presente, sino usa null
- Si encuentras OC/HES/HEM, también inclúyelos en el reasoning explicando dónde los encontraste
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
        
        # Detectar tipo de documento
        doc_type = result.get('documentType', 'FACTURA')
        
        if doc_type == 'PROFORMA':
            # Validar estructura de proforma
            if 'items' not in result:
                result['items'] = []
            if 'confidence' not in result:
                result['confidence'] = {}
            if 'reasoning' not in result:
                result['reasoning'] = {}
            if 'summary' not in result:
                result['summary'] = {}
            
            # Asegurar moneda
            if 'currency' not in result:
                result['currency'] = 'ARS'
                result['currencySymbol'] = '$'
        else:
            # Es una factura - validar estructura de factura
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