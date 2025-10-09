import uvicorn
import sys
import os
import platform
from config import settings

def main():
    """Inicia el servidor con configuración optimizada"""

    is_windows = platform.system() == "Windows"

    if settings.DEBUG:
        print("🚀 Iniciando servidor en modo DESARROLLO")
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level=settings.LOG_LEVEL.lower(),
            access_log=True
        )
    else:
        print("🚀 Iniciando servidor en modo PRODUCCIÓN")
        kwargs = dict(
            host="0.0.0.0",
            port=8000,
            workers=4,
            log_level=settings.LOG_LEVEL.lower(),
            access_log=True
        )
        if not is_windows:
            kwargs["loop"] = "uvloop"  # Solo en Linux/macOS

        uvicorn.run("main:app", **kwargs)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Servidor detenido por el usuario")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error iniciando servidor: {str(e)}")
        sys.exit(1)
