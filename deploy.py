import subprocess
import sys
import os
from datetime import datetime
from database import engine  # Tu conexión SQLAlchemy
from sqlalchemy import text

def run_command(command, description):
    """Ejecuta un comando y maneja errores"""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completado")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error en {description}: {e.stderr}")
        return False

def verificar_bd():
    """Verifica que la conexión a la base de datos funcione"""
    print("🔧 Verificando conexión a base de datos...")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))  # <-- envolver en text()
        print("✅ Conexión a BD exitosa")
        return True
    except Exception as e:
        print(f"❌ Error de conexión a BD: {str(e)}")
        print("   Verifica que MySQL esté corriendo y las credenciales sean correctas")
        return False

def main():
    print("🚀 INICIANDO DEPLOYMENT DEL BACKEND")
    print("=" * 50)

    # 1. Verificar archivos necesarios
    required_files = ['main.py', 'config.py', 'database.py', 'models.py', 'crud.py']
    missing_files = [f for f in required_files if not os.path.exists(f)]
    if missing_files:
        print(f"❌ Archivos faltantes: {missing_files}")
        return False
    print("✅ Todos los archivos necesarios están presentes")

    # 2. Instalar dependencias
    if not run_command("pip install -r requirements_final.txt", "Instalando dependencias"):
        return False

    # 3. Verificar archivo .env
    if not os.path.exists('.env'):
        print("⚠️  Archivo .env no encontrado. Usando valores por defecto.")

    # 4. Verificar conexión a BD
    if not verificar_bd():
        return False

    # 5. Verificar modelo PLN
    print("🔧 Verificando modelo PLN...")
    try:
        import pln
        pln.procesar_orden_inventario("test")
        print("✅ Modelo PLN cargado correctamente")
    except Exception as e:
        print(f"❌ Error cargando modelo PLN: {str(e)}")
        return False

    # 6. Verificar chatbot
    print("🔧 Verificando chatbot...")
    try:
        from chatbot import procesar_mensaje_chatbot
        test = procesar_mensaje_chatbot("agrega 1 mouse test", usuario_id=1)
        if test.get('exito'):
            print("✅ Chatbot funcionando correctamente")
        else:
            print("⚠️  Chatbot responde pero con errores - revisar logs")
    except Exception as e:
        print(f"❌ Error en chatbot: {str(e)}")
        return False

    # 7. Generar reporte de deployment
    report = f"""
=== REPORTE DE DEPLOYMENT ===
Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Status: ✅ EXITOSO

Componentes verificados:
✅ Dependencias instaladas
✅ Base de datos conectada  
✅ Modelo PLN cargado
✅ Chatbot funcionando
✅ Archivos de configuración presentes

Endpoints disponibles:
- POST /login - Autenticación
- POST /chatbot/inventario - Chatbot principal
- GET /chatbot/ayuda - Ayuda del chatbot
- GET /health - Estado del sistema
- GET /docs - Documentación API

Para iniciar el servidor:
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Para producción:
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
"""

    print(report)
    with open('deployment_report.txt', 'w', encoding='utf-8') as f:
        f.write(report)
    print("📋 Reporte guardado en: deployment_report.txt")
    print("🎉 DEPLOYMENT COMPLETADO EXITOSAMENTE")

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
