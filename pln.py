import re
import ast
import json
import torch
from transformers import MT5Tokenizer, MT5ForConditionalGeneration
from diccionario import productos_base, marcas_conocidas, verbos_accion, MARCAS_EXTRACCION, STOPWORDS_MODELO

# ---------------------- CONFIGURACIÓN ----------------------
MODEL_PATH = "./pln_model"
device = "cuda" if torch.cuda.is_available() else "cpu"

# Cargar tokenizer y modelo entrenado
tokenizer = MT5Tokenizer.from_pretrained(MODEL_PATH)
model = MT5ForConditionalGeneration.from_pretrained(MODEL_PATH).to(device)


# ---------------------- ANÁLISIS MEJORADO DE PALABRAS ----------------------
def dividir_palabras_orden(texto: str):
    """
    Divide una orden de inventario en componentes semánticos para facilitar su análisis.
    Maneja plurales, sinónimos y detecta estructura de la oración.
    """
    # Limpiar y normalizar el texto
    texto_limpio = texto.lower().strip()

    # Dividir texto en palabras
    palabras = re.findall(r'\b\w+\b', texto_limpio)

    # Extraer números
    numeros = re.findall(r'\d+', texto_limpio)

    resultado = {
        'texto_original': texto,
        'texto_normalizado': texto_limpio,
        'palabras': palabras,
        'numeros': numeros,
        'accion_detectada': None,
        'producto_detectado': None,
        'marca_detectada': None,
        'cantidad_detectada': None,
        'palabras_clave': [],
        'estructura_detectada': None,
        'confianza': 0.0
    }

    # Detectar acción principal
    for i, palabra in enumerate(palabras):
        for accion_tipo, verbos in verbos_accion.items():
            if palabra in verbos:
                resultado['accion_detectada'] = accion_tipo
                resultado['palabras_clave'].append(f"verbo:{palabra}")
                resultado['confianza'] += 0.3
                break
        if resultado['accion_detectada']:
            break

    # Detectar producto (incluye manejo de plurales)
    for palabra in palabras:
        for producto_base, variantes in productos_base.items():
            if palabra in variantes:
                resultado['producto_detectado'] = producto_base
                resultado['palabras_clave'].append(f"producto:{palabra}")
                resultado['confianza'] += 0.3
                break
        if resultado['producto_detectado']:
            break

    # Detectar marca
    for palabra in palabras:
        if palabra in marcas_conocidas:
            resultado['marca_detectada'] = palabra
            resultado['palabras_clave'].append(f"marca:{palabra}")
            resultado['confianza'] += 0.2
            break

    # Detectar cantidad
    if numeros:
        try:
            resultado['cantidad_detectada'] = int(numeros[0])
            resultado['palabras_clave'].append(f"cantidad:{numeros[0]}")
            resultado['confianza'] += 0.2
        except ValueError:
            pass

    return resultado

# ---------------------- FUNCIONES HELPER PARA MODELO ----------------------
def _detectar_indices_producto_marca(palabras):
    idx_prod, prod_base = -1, None
    for i, p in enumerate(palabras):
        for base, vars in productos_base.items():  # usa global
            if p in vars:
                idx_prod, prod_base = i, base
                break
        if idx_prod != -1:
            break
    idx_marca, marca = -1, None
    for i, p in enumerate(palabras):
        if p in marcas_conocidas:  # usa global
            idx_marca, marca = i, p
            break
    return prod_base, idx_prod, marca, idx_marca

def _extraer_modelo_desde_tokens(palabras, idx_producto, idx_marca):
    start = idx_marca + 1 if idx_marca != -1 else (idx_producto + 1 if idx_producto != -1 else -1)
    if start == -1:
        return None
    modelo_tokens = []
    for i in range(start, len(palabras)):
        t = palabras[i]
        if t.isdigit():
            break
        if t in STOPWORDS_MODELO:
            if modelo_tokens:
                break
            else:
                continue
        if t in MARCAS_EXTRACCION:
            if modelo_tokens:
                break
            else:
                continue
        modelo_tokens.append(t)
    return " ".join(modelo_tokens) if modelo_tokens else None

def _detectar_cantidad_mejorada(texto_limpio: str, accion_detectada: str):
    nums = re.findall(r'\d+', texto_limpio)  # CORREGIDO
    if not nums:
        return None
    if accion_detectada == 'ajustar':
        return int(nums[-1])
    return int(nums[0])

# ---------------------- REGLAS BÁSICAS MEJORADAS ----------------------
def reglas_basicas_mejoradas(texto: str):
    analisis = dividir_palabras_orden(texto)

    # Mejorar cantidad si es ajuste
    analisis['cantidad_detectada'] = _detectar_cantidad_mejorada(
        analisis['texto_normalizado'], 
        analisis.get('accion_detectada')
    )

    # Extraer modelo desde tokens y posiciones de producto/marca
    prod, idx_prod, marca, idx_marca = _detectar_indices_producto_marca(analisis['palabras'])
    modelo = _extraer_modelo_desde_tokens(analisis['palabras'], idx_prod, idx_marca)

    analisis['producto_detectado'] = prod or analisis.get('producto_detectado')
    analisis['marca_detectada'] = marca or analisis.get('marca_detectada')
    analisis['modelo_detectado'] = modelo

    if analisis['confianza'] >= 0.5:
        mapeo_acciones = {
            'agregar': 'agregar_inventario',
            'quitar': 'quitar_inventario', 
            'consultar': 'consultar_stock',
            'generar': 'generar_reporte',
            'ajustar': 'ajustar_stock'
        }
        return {
            'accion': mapeo_acciones.get(analisis['accion_detectada'], analisis['accion_detectada']),
            'producto': analisis['producto_detectado'],
            'marca': analisis['marca_detectada'],
            'modelo': analisis['modelo_detectado'],
            'cantidad': analisis['cantidad_detectada'],
            'metodo': 'analisis_palabras_mejorado',
            'confianza': analisis['confianza'],
            'palabras_clave': analisis['palabras_clave']
        }
    return None

# ---------------------- FUNCIONES ORIGINALES MANTENIDAS ----------------------
def parse_resultado(resultado):
    """Convierte la salida del modelo a diccionario de Python seguro."""
    if "raw_output" in resultado:
        try:
            return ast.literal_eval(resultado["raw_output"])
        except:
            return {}
    return resultado

def parse_json_sucio(raw_output: str):
    """Extrae un JSON aunque el texto tenga comillas simples o texto extra."""
    cleaned = raw_output.replace("'", '"')
    match = re.search(r"\{.*\}", cleaned)
    if match:
        try:
            return json.loads(match.group())
        except:
            return {}
    return {}

def modelo_mt5(texto: str):
    """Usa mT5 para estructurar texto en JSON si las reglas no cubren el caso."""
    prompt = f'Convierte este comando de inventario en JSON con los campos: accion, producto, marca, modelo, cantidad. Texto: "{texto}"'

    inputs = tokenizer(prompt, return_tensors="pt", padding=True, truncation=True).to(device)
    outputs = model.generate(**inputs, max_new_tokens=128)
    generated = tokenizer.decode(outputs[0], skip_special_tokens=True)

    try:
        return json.loads(generated)
    except:
        return {"raw_output": generated}

# ---------------------- FUNCIÓN PRINCIPAL MEJORADA ----------------------
def analizar_texto_mt5_mejorado(texto: str):
    """
    Convierte un comando de inventario en JSON estructurado usando:
    1) Análisis mejorado de palabras (nuevo)
    2) Reglas básicas mejoradas 
    3) Modelo entrenado local mT5 como último recurso
    """

    # 1) Intentar análisis mejorado de palabras con reglas
    reglas_mejoradas = reglas_basicas_mejoradas(texto)
    if reglas_mejoradas and reglas_mejoradas.get('confianza', 0) >= 0.5:
        return reglas_mejoradas

    # 2) Usar modelo MT5 como fallback
    resultado = modelo_mt5(texto)
    if "raw_output" in resultado:
        parsed = parse_json_sucio(resultado["raw_output"])
        parsed['metodo'] = 'modelo_mt5'
        parsed['confianza'] = 0.3
        return parsed

    resultado['metodo'] = 'modelo_mt5'
    resultado['confianza'] = 0.4
    return resultado

# ---------------------- FUNCIÓN DIVIDIR ORDEN MEJORADA ----------------------
def dividir_orden_mejorada(resultado_json):
    if resultado_json is None:
        return {
            "tipo_movimiento": "desconocido",
            "producto": None,
            "marca": None,
            "modelo": None,
            "cantidad": None,
            "metodo": "ninguno",
            "confianza": 0.0
        }

    accion = (resultado_json.get("accion") or "").lower()
    producto = resultado_json.get("producto")
    marca = resultado_json.get("marca")
    modelo = resultado_json.get("modelo")
    cantidad = resultado_json.get("cantidad")
    metodo = resultado_json.get("metodo", "desconocido")
    confianza = resultado_json.get("confianza", 0.0)

    if accion in ["agregar", "insertar", "entrada", "agregar_inventario", "añadir"]:
        tipo_movimiento = "entrada"
    elif accion in ["salida", "retirar", "quitar_inventario", "eliminar", "sacar"]:
        tipo_movimiento = "salida"
    elif accion in ["ajuste", "modificar", "ajustar_stock", "actualizar", "corregir"]:
        tipo_movimiento = "ajuste"
    elif accion in ["reporte", "mostrar reporte", "generar_reporte", "informe"]:
        tipo_movimiento = "reporte"
    elif accion in ["consultar_stock", "consulta", "stock"]:
        tipo_movimiento = "consulta"
    else:
        tipo_movimiento = "desconocido"

    return {
        "tipo_movimiento": tipo_movimiento,
        "producto": producto,
        "marca": marca,
        "modelo": modelo,
        "cantidad": cantidad,
        "metodo_usado": metodo,
        "nivel_confianza": confianza
    }

# ---------------------- FUNCIÓN PRINCIPAL PARA USAR ----------------------
def procesar_orden_inventario(texto: str):
    """
    Función principal que procesa una orden completa de inventario.
    Retorna el resultado estructurado listo para usar en CRUD.
    """

    # Analizar el texto
    json_resultado = analizar_texto_mt5_mejorado(texto)

    # Dividir la orden en formato CRUD
    orden_dividida = dividir_orden_mejorada(json_resultado)

    return {
        'input_original': texto,
        'json_intermedio': json_resultado,
        'resultado_final': orden_dividida
    }

# ---------------------- EJEMPLOS DE USO ----------------------
if __name__ == "__main__":
    # Ejemplos de órdenes de inventario
    ordenes_prueba = [
        "agrega 50 mouse logitech",
        "quita 10 teclados HP", 
        "consulta stock de impresoras Epson",
        "generar reporte de monitores Samsung",
        "ajustar stock mouse Apple a 30",
        "añadí 25 laptops Dell",
        "saca 5 tablets Samsung",
        "cuánto stock hay de auriculares Sony"
    ]

    print("=== PROCESAMIENTO DE ÓRDENES DE INVENTARIO ===\n")

    for orden in ordenes_prueba:
        resultado = procesar_orden_inventario(orden)

        print(f"Orden: '{orden}'")
        print(f"Método usado: {resultado['json_intermedio'].get('metodo', 'desconocido')}")
        print(f"Confianza: {resultado['json_intermedio'].get('confianza', 0):.1f}")
        print(f"Resultado final: {resultado['resultado_final']}")
        print("-" * 60)