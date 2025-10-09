# constantes.py

# Productos y sus variantes
productos_base = {
    'mouse': ['mouse', 'ratón', 'ratones', 'mouses'],
    'teclado': ['teclado', 'teclados'],
    'monitor': ['monitor', 'monitores', 'pantalla', 'pantallas'],
    'impresora': ['impresora', 'impresoras'],
    'laptop': ['laptop', 'laptops', 'computadora', 'computadoras', 'notebook', 'notebooks'],
    'tablet': ['tablet', 'tablets'],
    'celular': ['celular', 'celulares', 'telefono', 'teléfono', 'teléfonos', 'smartphone', 'smartphones'],
    'auriculares': ['auriculares', 'audífonos', 'audífono', 'headset', 'headsets'],
    'cámara': ['cámara', 'cámaras', 'webcam', 'webcams'],
    'altavoz': ['altavoz', 'altavoces', 'parlante', 'parlantes', 'speaker', 'speakers']
}

# Marcas conocidas
marcas_conocidas = [
    'logitech','hp','dell','samsung','apple','microsoft','epson','brother','canon','xerox','acer',
    'asus','lenovo','lg','genius','corsair','razer','sony','toshiba','viewsonic','oki','ricoh', 
    'redragon','vsg', 'antryx','wooting','playstation'
]

# Verbos de acción
verbos_accion = {
    'agregar': ['agrega', 'añade', 'añadir', 'inserta', 'insertar', 'mete', 'meter', 'pon', 'poner', 'suma', 'sumar', 
                'ingresa', 'ingresar', 'incorpora', 'incorporar', 'adiciona', 'adicionar', 'registra', 'registrar', 
                'coloca', 'colocar', 'agregá', 'añadí', 'metí'],
    'quitar': ['quita', 'quitar', 'elimina', 'eliminar', 'extrae', 'extraer', 'retira', 'retirar', 'saca', 'sacar', 
               'suprime', 'suprimir', 'descarta', 'descartar', 'remueve', 'remover', 'baja', 'bajar', 'dele', 'delete', 
               'quitá', 'eliminá', 'retiré'],
    'consultar': ['consulta', 'consultar', 'cuanto', 'cuánto', 'disponible', 'existencias', 'estado', 'tengo', 
                  'hay', 'queda', 'quedan', 'consultá', 'estado'],
    'generar': ['genera', 'generar', 'haz', 'hacer', 'reporte', 'informe', 'muestra', 'mostrar', 'generá', 'hacé'],
    'ajustar': ['ajusta', 'ajustar', 'modifica', 'modificar', 'corrige', 'corregir', 'actualiza', 'actualizar', 
                'cambia', 'cambiar', 'ajustá', 'modificá', 'actualizá']
}

# Marcas para extracción en modelo
MARCAS_EXTRACCION = set(marcas_conocidas)

# Stopwords para modelo
STOPWORDS_MODELO = set([
    'de','del','la','el','los','las','a','al','para','en','con','base','datos','inventario','total','cantidad'
])
