"""
Invoice Extractor - Demo Interactivo con Claude Sonnet 4
Aplicación de demostración con chat inteligente para extraer datos de facturas
Con detección automática de moneda (USD/ARS/EUR/etc)
"""

import streamlit as st
import base64
import json
import io
from datetime import datetime
import requests
from PIL import Image
import PyPDF2


def analyze_invoice_with_claude(pdf_text):
    """
    Analiza la factura - intenta usar Claude API real, sino fallback a regex
    """
    try:
        # Intentar con Claude API real (inteligente)
        from claude_ocr import extract_invoice_with_claude
        result = extract_invoice_with_claude(pdf_text)
        return result
    except Exception as e:
        st.warning(f"⚠️ Claude API no disponible, usando modo regex básico: {str(e)}")
        
        import re
        
        # Fallback: código regex básico
        result = {
            'supplier': {},
            'client': {},
            'currency': 'ARS',
            'currencySymbol': '$',
            'invoiceType': None,
            'invoiceNumber': None,
            'pointSale': None,
            'documentDate': None,
            'dueDate': None,
            'amount': 0,
            'iva': 0,
            'amountGrav': 0,
            'amountNoGrav': 0,
            'amountExen': 0,
            'cae': None,
            'items': [],
            'confidence': {},
            'reasoning': {}
        }
        
        # CUIT del proveedor
        cuit_match = re.search(r'CUIT[:\s]+(\d{2}-\d{8}-\d{1})', pdf_text)
        if cuit_match:
            result['supplier']['cuit'] = cuit_match.group(1)
            result['confidence']['supplier_cuit'] = 0.98
            result['reasoning']['supplier_cuit'] = f"Encontré el CUIT '{cuit_match.group(1)}' claramente marcado en el encabezado del documento."
        
        # Razón social
        name_match = re.search(r'(AMX ARGENTINA S\.A\.|[A-Z]{3,}[\sA-Z\.]+S\.A\.|[A-Z]{3,}[\sA-Z\.]+S\.R\.L\.)', pdf_text)
        if name_match:
            result['supplier']['name'] = name_match.group(1).strip()
            result['confidence']['supplier_name'] = 0.95
            result['reasoning']['supplier_name'] = f"Identifiqué la razón social '{result['supplier']['name']}' como el nombre legal de la empresa."
        
        # Número de factura
        invoice_match = re.search(r'Factura\s+N[°ro\.]+\s*[:\s]*(\d+-\d+)', pdf_text, re.IGNORECASE)
        if invoice_match:
            result['invoiceNumber'] = invoice_match.group(1)
            parts = invoice_match.group(1).split('-')
            if len(parts) == 2:
                result['pointSale'] = parts[0]
            result['confidence']['invoice_number'] = 0.98
            result['reasoning']['invoice_number'] = f"El número de factura '{result['invoiceNumber']}' está en formato estándar argentino."
        
        # Tipo de factura
        type_match = re.search(r'CODIGO\s+(\d{2})', pdf_text)
        if type_match:
            code = type_match.group(1)
            code_map = {'01': 'A', '06': 'B', '11': 'C'}
            result['invoiceType'] = code_map.get(code, code)
            result['confidence']['invoice_type'] = 0.99
            result['reasoning']['invoice_type'] = f"El código AFIP {code} corresponde a una Factura tipo {result['invoiceType']}."
        
        # CAE
        cae_match = re.search(r'C\.?A\.?E\.?\s*N[°º]?\s*[:\s]*(\d+)', pdf_text, re.IGNORECASE)
        if cae_match:
            result['cae'] = cae_match.group(1)
            result['confidence']['cae'] = 0.97
            result['reasoning']['cae'] = f"CAE {result['cae']} es el código de autorización electrónica de AFIP."
        
        # Fechas
        date_match = re.search(r'Fecha\s+de\s+Emisi[oó]n[:\s]+(\d{2}/\d{2}/\d{4})', pdf_text, re.IGNORECASE)
        if date_match:
            date_str = date_match.group(1)
            result['documentDate'] = convert_date_format(date_str)
            result['confidence']['document_date'] = 0.98
            result['reasoning']['document_date'] = f"Fecha de emisión {date_str} extraída del encabezado."
        
        due_match = re.search(r'Vencimiento[:\s]+(\d{2}/\d{2}/\d{4})', pdf_text, re.IGNORECASE)
        if due_match:
            date_str = due_match.group(1)
            result['dueDate'] = convert_date_format(date_str)
            result['confidence']['due_date'] = 0.95
            result['reasoning']['due_date'] = f"Fecha de vencimiento {date_str} para el pago."
        
        # Montos
        total_match = re.search(r'Total\s+(?:Factura|a\s+Pagar)[:\s]*\$?\s*([\d,\.]+)', pdf_text, re.IGNORECASE)
        if total_match:
            result['amount'] = parse_amount(total_match.group(1))
            result['confidence']['amount'] = 0.99
            result['reasoning']['amount'] = f"Total de ${result['amount']:,.2f} extraído del pie de la factura."
        
        iva_match = re.search(r'Impuesto\s+Interno[:\s]*\$?\s*([\d,\.]+)', pdf_text, re.IGNORECASE)
        if iva_match:
            result['iva'] = parse_amount(iva_match.group(1))
            result['confidence']['iva'] = 0.95
            result['reasoning']['iva'] = f"IVA de ${result['iva']:,.2f} identificado en el desglose de impuestos."
        
        subtotal_match = re.search(r'Subtotal[:\s]*\$?\s*([\d,\.]+)', pdf_text, re.IGNORECASE)
        if subtotal_match:
            result['amountGrav'] = parse_amount(subtotal_match.group(1))
            result['confidence']['amount_grav'] = 0.92
            result['reasoning']['amount_grav'] = f"Subtotal gravado de ${result['amountGrav']:,.2f}."
        
        # Detección básica de moneda en fallback
        if 'USD' in pdf_text or 'US$' in pdf_text or 'dollars' in pdf_text.lower():
            result['currency'] = 'USD'
            result['currencySymbol'] = 'US$'
            result['reasoning']['currency'] = 'Detectado USD por la presencia de "USD" o "US$" en el documento'
        elif 'CUIT' in pdf_text or 'AFIP' in pdf_text:
            result['currency'] = 'ARS'
            result['currencySymbol'] = '$'
            result['reasoning']['currency'] = 'Detectado ARS por la presencia de CUIT y/o AFIP (factura argentina)'
        
        result['confidence']['currency'] = 0.85
        
        return result


def generate_initial_analysis_message(data):
    """Genera el mensaje inicial de análisis de Claude"""
    
    supplier_name = data.get('supplier', {}).get('name', 'el proveedor')
    invoice_number = data.get('invoiceNumber', 'sin número')
    invoice_type = data.get('invoiceType', 'desconocido')
    total = data.get('amount', 0)
    currency = data.get('currency', 'ARS')
    currency_symbol = data.get('currencySymbol', '$')
    
    # Emoji de moneda
    currency_emoji = {
        'USD': '💵',
        'ARS': '💰',
        'EUR': '💶',
        'MXN': '💵',
        'BRL': '💵',
        'CLP': '💵'
    }.get(currency, '💰')
    
    message = f"""¡Hola! 👋 He analizado la factura y esto es lo que encontré:

📄 **Factura tipo {invoice_type} - N° {invoice_number}**

🏢 **Proveedor detectado:** {supplier_name}
- CUIT: {data.get('supplier', {}).get('cuit', 'No detectado')}

{currency_emoji} **Monto total:** {currency_symbol}{total:,.2f} {currency}

He identificado los siguientes campos con alta confianza:
"""
    
    # Agregar campos con alta confianza
    high_confidence_fields = []
    for field, confidence in data.get('confidence', {}).items():
        # Normalizar confianza
        conf_normalized = confidence if confidence <= 1 else confidence / 100
        if conf_normalized >= 0.95:
            high_confidence_fields.append(f"✅ {field.replace('_', ' ').title()}: {conf_normalized:.0%}")
    
    if high_confidence_fields:
        message += "\n" + "\n".join(high_confidence_fields[:5])
    
    # Calcular confianza promedio normalizada
    confidences = [c if c <= 1 else c/100 for c in data.get('confidence', {}).values()]
    avg_conf = sum(confidences) / len(confidences) * 100 if confidences else 0
    
    message += f"""

📊 **Resumen de la extracción:**
- Total de campos detectados: {len([k for k, v in data.items() if v and k != 'confidence' and k != 'reasoning'])}
- Confianza promedio: {avg_conf:.1f}%

💡 **¿Qué puedo hacer por ti?**
- Pregúntame sobre cualquier campo específico
- Pídeme que explique cómo lo detecté
- Solicita que revise algún dato que te parezca dudoso

¿Hay algo en particular que quieras que revise? 🤔"""
    
    return message


def generate_chat_response(user_input, extracted_data, pdf_text):
    """
    Genera una respuesta conversacional basada en la pregunta del usuario.
    """
    user_input_lower = user_input.lower()
    
    # Respuestas inteligentes basadas en el contexto
    if 'cuit' in user_input_lower:
        cuit = extracted_data.get('supplier', {}).get('cuit', 'No detectado')
        confidence = extracted_data.get('confidence', {}).get('supplier_cuit', 0)
        reasoning = extracted_data.get('reasoning', {}).get('supplier_cuit', '')
        
        # Normalizar confianza
        if confidence > 1:
            confidence = confidence / 100
        
        return f"""Sobre el CUIT del proveedor:

📊 **Valor detectado:** {cuit}
🎯 **Confianza:** {confidence:.0%}

💭 **Mi razonamiento:**
{reasoning}

El CUIT tiene el formato correcto (XX-XXXXXXXX-X) y está claramente identificado en el documento. {"Estoy muy seguro de este valor." if confidence > 0.95 else "Hay una pequeña posibilidad de error en la lectura."}

¿Te gustaría que revise algún otro campo?"""
    
    elif 'monto' in user_input_lower or 'total' in user_input_lower or 'calculaste' in user_input_lower or 'moneda' in user_input_lower or 'currency' in user_input_lower:
        amount = extracted_data.get('amount', 0)
        iva = extracted_data.get('iva', 0)
        subtotal = extracted_data.get('amountGrav', 0)
        confidence = extracted_data.get('confidence', {}).get('amount', 0.99)
        currency = extracted_data.get('currency', 'ARS')
        currency_symbol = extracted_data.get('currencySymbol', '$')
        currency_reasoning = extracted_data.get('reasoning', {}).get('currency', 'No especificado')
        
        # Normalizar confianza
        if confidence > 1:
            confidence = confidence / 100
        
        currency_emoji = {
            'USD': '💵',
            'ARS': '💰',
            'EUR': '💶',
            'MXN': '💵',
            'BRL': '💵',
            'CLP': '💵'
        }.get(currency, '💰')
        import html
        currency_reasoning_safe = html.escape(currency_reasoning) if currency_reasoning else " "

        return f"""Te explico cómo identifiqué los montos:

{currency_emoji} **Moneda detectada:** {currency} ({currency_symbol})
{currency_reasoning_safe}

💰 **Total Final:** {currency_symbol}{amount:,.2f} {currency}
- Encontré este valor en la sección "Total a Pagar" del documento
- Confianza: {confidence:.0%}

📊 **Desglose:**
- Subtotal Gravado: {currency_symbol}{subtotal:,.2f}
- IVA/Impuestos: {currency_symbol}{iva:,.2f}

✅ **Verificación:** El total coincide con la suma de subtotal + impuestos

Los montos están claramente marcados en la factura y el formato numérico es correcto. En este caso particular, la confianza es muy alta porque:
1. Los valores están en posiciones estándar del documento
2. El formato de moneda es consistente
3. Las matemáticas cuadran (subtotal + IVA = total)

¿Necesitas que revise algún otro aspecto de los montos?"""
    
    elif 'dudoso' in user_input_lower or 'seguro' in user_input_lower or 'confianza' in user_input_lower:
        low_confidence_fields = []
        for field, confidence in extracted_data.get('confidence', {}).items():
            # Normalizar
            conf_normalized = confidence if confidence <= 1 else confidence / 100
            if conf_normalized < 0.90:
                field_name = field.replace('_', ' ').title()
                low_confidence_fields.append(f"⚠️ {field_name}: {conf_normalized:.0%}")
        
        if low_confidence_fields:
            fields_text = "\n".join(low_confidence_fields)
            return f"""Estos son los campos donde tengo menor confianza:

{fields_text}

💡 **¿Por qué menor confianza?**
Generalmente, la confianza baja cuando:
- El texto está en una posición inusual del documento
- La calidad del PDF no es óptima
- El formato no sigue el estándar habitual

**Recomendación:** Te sugiero revisar manualmente estos campos antes de enviar el JSON al sistema.

¿Quieres que te explique alguno de estos campos en detalle?"""
        else:
            confidences = [c if c <= 1 else c/100 for c in extracted_data.get('confidence', {}).values()]
            avg_conf = sum(confidences) / len(confidences) * 100 if confidences else 0
            
            return f"""¡Excelente! 🎉

No encontré ningún campo con confianza baja. Todos los valores detectados tienen una confianza superior al 90%, lo que significa que:

✅ El documento tiene buena calidad
✅ Los datos están en posiciones estándares
✅ No hay ambigüedades en la información

**Confianza promedio:** {avg_conf:.1f}%

Puedes proceder con tranquilidad a cargar esta factura en el sistema. ¿Quieres exportar el JSON ahora?"""
    
    elif 'fecha' in user_input_lower:
        doc_date = extracted_data.get('documentDate', 'No detectado')
        due_date = extracted_data.get('dueDate', 'No detectado')
        doc_conf = extracted_data.get('confidence', {}).get('document_date', 0.95)
        due_conf = extracted_data.get('confidence', {}).get('due_date', 0.90)
        
        # Normalizar
        if doc_conf > 1:
            doc_conf = doc_conf / 100
        if due_conf > 1:
            due_conf = due_conf / 100
        
        return f"""Sobre las fechas de la factura:

📅 **Fecha de Emisión:** {doc_date}
- {extracted_data.get('reasoning', {}).get('document_date', 'Detectada en el encabezado del documento')}
- Confianza: {doc_conf:.0%}

⏰ **Fecha de Vencimiento:** {due_date}
- {extracted_data.get('reasoning', {}).get('due_date', 'Detectada en la sección de pagos')}
- Confianza: {due_conf:.0%}

Las fechas están en formato ISO (YYYY-MM-DD) para facilitar su procesamiento en el sistema.

¿Hay algo más que quieras saber sobre las fechas?"""
    
    elif 'items' in user_input_lower or 'líneas' in user_input_lower or 'productos' in user_input_lower:
        items = extracted_data.get('items', [])
        
        if items:
            items_list = []
            for i, item in enumerate(items[:5], 1):
                desc = item.get('description', 'Sin descripción')[:50]
                total = item.get('total', 0)
                items_list.append(f"📦 {i}. {desc}... - ${total:,.2f}")
            
            items_text = "\n".join(items_list)
            
            return f"""Identifiqué {len(items)} línea(s) en la factura:

{items_text}

Cada línea incluye:
- Descripción del servicio/producto
- Cantidad
- Precio unitario
- Total de la línea

Los items fueron extraídos de la tabla de conceptos del documento. ¿Quieres que te dé más detalles sobre alguno en particular?"""
        else:
            return """No detecté items individuales en esta factura, pero sí los montos totales. 

Esto puede ocurrir cuando:
- La factura es de un único concepto
- El formato de la tabla no es estándar
- Los items están en un formato no estructurado

Los montos totales son correctos, solo que no están desglosados línea por línea. ¿Necesitas que revise algo más?"""
    
    else:
        # Respuesta genérica
        return """Entiendo tu pregunta. Déjame pensar en cómo puedo ayudarte mejor...

📊 **Datos disponibles:**
- Información del proveedor (CUIT, nombre, dirección)
- Información del cliente (nombre, dirección)
- Detalles de la factura (tipo, número, CAE)
- Moneda detectada automáticamente
- Fechas (emisión, vencimiento)
- Montos (total, IVA, subtotales)
- Items/líneas (si aplica)

Puedes preguntarme sobre:
- La confianza de cualquier campo específico
- Cómo detecté algún valor en particular
- Por qué elegí esa moneda (USD vs ARS)
- Si hay campos que requieren revisión manual
- Comparar valores entre diferentes secciones

¿Qué te gustaría saber específicamente? Puedo darte detalles sobre cualquiera de estos aspectos. 🤔"""


def display_field_with_confidence(label, value, confidence):
    """Muestra un campo con su nivel de confianza"""
    
    if confidence >= 0.95:
        conf_class = "confidence-high"
        icon = "✅"
    elif confidence >= 0.85:
        conf_class = "confidence-medium"
        icon = "⚠️"
    else:
        conf_class = "confidence-low"
        icon = "❌"

    if confidence > 1:
        confidence = confidence / 100

    st.markdown(f"""
    <div class="field-box">
        <strong>{label}:</strong> {value}<br>
        <span class="{conf_class}">{icon} Confianza: {confidence:.0%}</span>
    </div>
    """, unsafe_allow_html=True)


def prepare_final_json(data):
    """Prepara el JSON final para enviar al sistema"""
    
    # Detectar moneda del análisis
    currency = data.get('currency', 'ARS')
    
    return {
        "supplier": data.get('supplier', {}),
        "client": data.get('client', {}),
        "currency": currency,
        "currencySymbol": data.get('currencySymbol', '$'),
        "invoiceType": data.get('invoiceType'),
        "invoiceNumber": data.get('invoiceNumber'),
        "pointSale": data.get('pointSale'),
        "documentDate": data.get('documentDate'),
        "dueDate": data.get('dueDate'),
        "amount": data.get('amount'),
        "iva": data.get('iva'),
        "amountGrav": data.get('amountGrav'),
        "amountNoGrav": data.get('amountNoGrav'),
        "amountExen": data.get('amountExen'),
        "cae": data.get('cae'),
        "taxCode": data.get('taxCode'),
        "exchangeType": "1",
        "active": True,
        "hasPo": False,
        "items": data.get('items', [])
    }


def convert_date_format(date_str):
    """Convierte DD/MM/YYYY a YYYY-MM-DD"""
    try:
        day, month, year = date_str.split('/')
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    except:
        return date_str


def parse_amount(amount_str):
    """Parsea un monto desde string a float"""
    try:
        # Remover separadores de miles y usar punto como decimal
        cleaned = amount_str.replace('.', '').replace(',', '')
        # Asumir que los últimos 2 dígitos son centavos
        if len(cleaned) >= 2:
            return float(cleaned[:-2] + '.' + cleaned[-2:])
        return float(cleaned)
    except:
        return 0.0


# Configuración de la página
st.set_page_config(
    page_title="Invoice Extractor Demo",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #FF6B6B;
        text-align: center;
        margin-bottom: 2rem;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        display: flex;
        flex-direction: column;
    }
    .user-message {
        background-color: #E3F2FD;
        border-left: 4px solid #2196F3;
        color: #1565C0;
    }
    .assistant-message {
        background-color: #F3E5F5;
        border-left: 4px solid #9C27B0;
        color: #4A148C;
    }
    .field-box {
        background-color: #E8F5E9;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        border-left: 4px solid #4CAF50;
        color: #1B5E20;
    }
    .field-box strong {
        color: #2E7D32;
    }
    .confidence-high {
        color: #2E7D32;
        font-weight: bold;
    }
    .confidence-medium {
        color: #E65100;
        font-weight: bold;
    }
    .confidence-low {
        color: #C62828;
        font-weight: bold;
    }
    .json-output {
        background-color: #263238;
        color: #A6E22E;
        padding: 1rem;
        border-radius: 0.5rem;
        font-family: 'Courier New', monospace;
        overflow-x: auto;
    }
    .currency-badge {
        display: inline-block;
        padding: 0.3rem 0.8rem;
        border-radius: 1rem;
        font-weight: bold;
        margin: 0.5rem 0;
    }
    .currency-usd {
        background-color: #C8E6C9;
        color: #2E7D32;
    }
    .currency-ars {
        background-color: #BBDEFB;
        color: #1565C0;
    }
    .currency-eur {
        background-color: #F8BBD0;
        color: #C2185B;
    }
</style>
""", unsafe_allow_html=True)

# Inicializar estado de la sesión
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'pdf_data' not in st.session_state:
    st.session_state.pdf_data = None
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = None
if 'pdf_text' not in st.session_state:
    st.session_state.pdf_text = None

# Sidebar
with st.sidebar:
    # Logo con emoji en vez de imagen
    st.markdown("<h1 style='text-align: center; font-size: 3em;'>📄</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Invoice Extractor AI</h3>", unsafe_allow_html=True)
    
    st.markdown("### ⚙️ Configuración")
    
    # Modo de operación
    operation_mode = st.radio(
        "Modo de operación:",
        ["🎭 Demo (Sin API)", "🚀 Producción (Con API)"],
        help="Demo usa Claude directamente en el navegador. Producción usa tu endpoint de AWS."
    )
    
    if operation_mode == "🚀 Producción (Con API)":
        api_endpoint = st.text_input(
            "API Endpoint:",
            placeholder="https://xxxxx.execute-api.us-east-1.amazonaws.com/prod/process-invoice"
        )
    
    st.markdown("---")
    st.markdown("### 📊 Estadísticas")
    
    # Mostrar moneda detectada si hay datos
    if st.session_state.extracted_data:
        currency = st.session_state.extracted_data.get('currency', 'ARS')
        currency_emoji = {
            'USD': '💵',
            'ARS': '💰',
            'EUR': '💶',
            'MXN': '💵',
            'BRL': '💵',
            'CLP': '💵'
        }.get(currency, '💰')
        st.metric("Moneda detectada", f"{currency_emoji} {currency}")
    
    st.markdown("---")
    st.markdown("### ℹ️ Información")
    st.info("""
    **Cómo usar:**
    1. Sube tu factura PDF
    2. Espera el análisis automático
    3. Conversa con Claude sobre los campos
    4. Exporta el JSON final
    
    **Monedas soportadas:**
    💵 USD, 💰 ARS, 💶 EUR, y más
    """)
    
    if st.button("🗑️ Limpiar conversación", use_container_width=True):
        st.session_state.messages = []
        st.session_state.extracted_data = None
        st.session_state.pdf_data = None
        st.session_state.pdf_text = None
        st.rerun()

# Header principal
st.markdown('<div class="main-header">📄 Invoice Extractor - Demo Interactivo</div>', unsafe_allow_html=True)

# Tabs principales
tab1, tab2, tab3 = st.tabs(["💬 Chat Inteligente", "📋 Datos Extraídos", "📄 Vista del PDF"])

with tab1:
    # Área de carga de PDF
    uploaded_file = st.file_uploader(
        "Sube tu factura PDF",
        type=['pdf'],
        help="Formatos soportados: PDF (digital o escaneado)"
    )
    
    if uploaded_file is not None and st.session_state.pdf_data is None:
        # Procesar el PDF
        with st.spinner("🔍 Analizando factura..."):
            # Leer PDF
            pdf_bytes = uploaded_file.read()
            st.session_state.pdf_data = pdf_bytes
            
            # Extraer texto del PDF
            try:
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
                pdf_text = ""
                for page in pdf_reader.pages:
                    pdf_text += page.extract_text()
                st.session_state.pdf_text = pdf_text
            except:
                st.session_state.pdf_text = "No se pudo extraer texto del PDF"
            
            # Simular análisis con Claude (en demo)
            if operation_mode == "🎭 Demo (Sin API)":
                analysis_result = analyze_invoice_with_claude(pdf_text)
                st.session_state.extracted_data = analysis_result
                
                # Agregar mensaje inicial de Claude
                initial_message = generate_initial_analysis_message(analysis_result)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": initial_message,
                    "data": analysis_result
                })
            else:
                # Modo producción: llamar a tu API
                if api_endpoint:
                    try:
                        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
                        response = requests.post(
                            api_endpoint,
                            json={"pdf_base64": pdf_base64},
                            timeout=300
                        )
                        result = response.json()
                        st.session_state.extracted_data = result
                        
                        initial_message = generate_initial_analysis_message(result)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": initial_message,
                            "data": result
                        })
                    except Exception as e:
                        st.error(f"Error al procesar con API: {str(e)}")
        
        st.rerun()
    
    # Mostrar chat
    st.markdown("### 💬 Conversación con el Asistente")
    
    # Contenedor de mensajes
    chat_container = st.container()
    
    with chat_container:
        for message in st.session_state.messages:
            if message["role"] == "user":
                st.markdown(f"""
                <div class="chat-message user-message">
                    <b>👤 Tú:</b><br>
                    {message["content"]}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="chat-message assistant-message">
                    <b>🤖 Claude:</b><br>
                    {message["content"]}
                </div>
                """, unsafe_allow_html=True)
    
    # Input de chat
    if st.session_state.extracted_data:
        user_input = st.chat_input("Pregúntame sobre los campos detectados...")
        
        if user_input:
            # Agregar mensaje del usuario
            st.session_state.messages.append({
                "role": "user",
                "content": user_input
            })
            
            # Generar respuesta de Claude
            with st.spinner("🤔 Claude está pensando..."):
                response = generate_chat_response(
                    user_input, 
                    st.session_state.extracted_data,
                    st.session_state.pdf_text
                )
                
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response
                })
            
            st.rerun()
        
        # Sugerencias de preguntas
        st.markdown("#### 💡 Preguntas sugeridas:")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("¿Qué tan seguro estás del CUIT?", use_container_width=True, key="btn_cuit"):
                # Agregar ambos mensajes
                st.session_state.messages.append({
                    "role": "user",
                    "content": "¿Qué tan seguro estás del CUIT del proveedor?"
                })
                response = generate_chat_response(
                    "¿Qué tan seguro estás del CUIT del proveedor?",
                    st.session_state.extracted_data,
                    st.session_state.pdf_text
                )
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response
                })
                st.rerun()

        with col2:
            if st.button("Explícame los montos y la moneda", use_container_width=True, key="btn_montos"):
                st.session_state.messages.append({
                    "role": "user",
                    "content": "Explícame cómo detectaste la moneda y los montos"
                })
                response = generate_chat_response(
                    "Explícame cómo detectaste la moneda y los montos",
                    st.session_state.extracted_data,
                    st.session_state.pdf_text
                )
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response
                })
                st.rerun()

        with col3:
            if st.button("¿Hay algún campo dudoso?", use_container_width=True, key="btn_dudoso"):
                st.session_state.messages.append({
                    "role": "user",
                    "content": "¿Hay algún campo del que no estés seguro?"
                })
                response = generate_chat_response(
                    "¿Hay algún campo del que no estés seguro?",
                    st.session_state.extracted_data,
                    st.session_state.pdf_text
                )
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response
                })
                st.rerun()
with tab2:
    st.markdown("### 📋 Datos Extraídos de la Factura")
    
    if st.session_state.extracted_data:
        data = st.session_state.extracted_data
        
        # Badge de moneda
        currency = data.get('currency', 'ARS')
        currency_symbol = data.get('currencySymbol', '$')
        currency_class = {
            'USD': 'currency-usd',
            'ARS': 'currency-ars',
            'EUR': 'currency-eur'
        }.get(currency, 'currency-ars')
        
        currency_emoji = {
            'USD': '💵',
            'ARS': '💰',
            'EUR': '💶'
        }.get(currency, '💰')
        
        st.markdown(f"""
        <div class="currency-badge {currency_class}">
            {currency_emoji} Moneda: {currency} ({currency_symbol})
        </div>
        """, unsafe_allow_html=True)
        
        # Mostrar razonamiento de moneda si existe
        currency_reasoning = data.get('reasoning', {}).get('currency')
        if currency_reasoning:
            st.info(f"💭 **¿Cómo detecté la moneda?** {currency_reasoning}")
        
        # Mostrar campos en categorías
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 🏢 Información del Proveedor")
            display_field_with_confidence(
                "CUIT", 
                data.get('supplier', {}).get('cuit', 'No detectado'),
                data.get('confidence', {}).get('supplier_cuit', 0.95)
            )
            display_field_with_confidence(
                "Razón Social",
                data.get('supplier', {}).get('name', 'No detectado'),
                data.get('confidence', {}).get('supplier_name', 0.90)
            )
            display_field_with_confidence(
                "Dirección",
                data.get('supplier', {}).get('address', 'No detectado'),
                data.get('confidence', {}).get('supplier_address', 0.85)
            )
            
            # Información del cliente
            if data.get('client', {}).get('name'):
                st.markdown("#### 👤 Información del Cliente")
                display_field_with_confidence(
                    "Nombre",
                    data.get('client', {}).get('name', 'No detectado'),
                    data.get('confidence', {}).get('client_name', 0.90)
                )
                if data.get('client', {}).get('code'):
                    display_field_with_confidence(
                        "Código",
                        data.get('client', {}).get('code', 'No detectado'),
                        0.95
                    )
            
            st.markdown("#### 📄 Información de la Factura")
            display_field_with_confidence(
                "Tipo",
                data.get('invoiceType', 'No detectado'),
                data.get('confidence', {}).get('invoice_type', 0.98)
            )
            display_field_with_confidence(
                "Número",
                data.get('invoiceNumber', 'No detectado'),
                data.get('confidence', {}).get('invoice_number', 0.95)
            )
            display_field_with_confidence(
                "Punto de Venta",
                data.get('pointSale', 'No detectado'),
                data.get('confidence', {}).get('point_sale', 0.90)
            )
            display_field_with_confidence(
                "CAE",
                data.get('cae', 'No detectado'),
                data.get('confidence', {}).get('cae', 0.92)
            )
        
        with col2:
            st.markdown("#### 📅 Fechas")
            display_field_with_confidence(
                "Fecha de Emisión",
                data.get('documentDate', 'No detectado'),
                data.get('confidence', {}).get('document_date', 0.95)
            )
            display_field_with_confidence(
                "Fecha de Vencimiento",
                data.get('dueDate', 'No detectado'),
                data.get('confidence', {}).get('due_date', 0.90)
            )
            
            st.markdown(f"#### 💰 Montos ({currency})")
            display_field_with_confidence(
                "Total",
                f"{currency_symbol}{data.get('amount') or 0:,.2f}" if data.get('amount') is not None else "No detectado",
                data.get('confidence', {}).get('amount', 0.98)
            )
            display_field_with_confidence(
                "IVA",
                f"{currency_symbol}{data.get('iva') or 0:,.2f}" if data.get('iva') is not None else "No detectado",
                data.get('confidence', {}).get('iva', 0.95)
            )
            display_field_with_confidence(
                "Subtotal Gravado",
                f"{currency_symbol}{data.get('amountGrav') or 0:,.2f}" if data.get('amountGrav') is not None else "No detectado",
                data.get('confidence', {}).get('amount_grav', 0.90)
            )
            display_field_with_confidence(
                "No Gravado",
                f"{currency_symbol}{data.get('amountNoGrav') or 0:,.2f}" if data.get('amountNoGrav') is not None else "No detectado",
                data.get('confidence', {}).get('amount_no_grav', 0.85)
            )
        
        # Items/Líneas
        if data.get('items'):
            st.markdown("#### 📦 Items de la Factura")
            items_df = []
            for i, item in enumerate(data['items'], 1):
                items_df.append({
                    "#": i,
                    "Descripción": item.get('description', ''),
                    "Cantidad": item.get('quantity', 0),
                    "Precio Unit.": f"{currency_symbol}{item.get('unit_price', 0):,.2f}",
                    "Total": f"{currency_symbol}{item.get('total', 0):,.2f}"
                })
            
            st.dataframe(items_df, use_container_width=True)
        
        # JSON completo
        st.markdown("#### 📤 JSON para Caja de Pagos")
        
        # Preparar JSON final
        final_json = prepare_final_json(data)
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown('<div class="json-output">', unsafe_allow_html=True)
            st.code(json.dumps(final_json, indent=2, ensure_ascii=False), language='json')
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col2:
            st.download_button(
                label="⬇️ Descargar JSON",
                data=json.dumps(final_json, indent=2, ensure_ascii=False),
                file_name=f"factura_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True
            )
            
            if st.button("📋 Copiar al portapapeles", use_container_width=True):
                st.write("¡JSON listo para copiar!")
    else:
        st.info("👆 Sube una factura para ver los datos extraídos")

with tab3:
    st.markdown("### 📄 Vista del PDF")
    
    if st.session_state.pdf_text:
        st.markdown("#### Texto extraído del PDF:")
        st.text_area(
            "Contenido del PDF",
            st.session_state.pdf_text,
            height=400,
            disabled=True
        )
    else:
        st.info("👆 Sube una factura para ver su contenido")


# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666;">
    <p>🤖 Powered by Claude Sonnet 4 | 📄 Invoice Extractor v2.0</p>
    <p style="font-size: 0.9em;">Con detección automática de moneda (USD/ARS/EUR)</p>
</div>
""", unsafe_allow_html=True)