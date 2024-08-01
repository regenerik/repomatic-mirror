import logging
import sys

# Configuración básica del logger
logging.basicConfig(level=logging.INFO)

# Crear un logger global
logger = logging.getLogger(__name__)

# Crear un manejador de salida que redirige sys.stdout (prints)
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.INFO)
logger.addHandler(stdout_handler)

# Opcional: redirigir sys.stderr también si es necesario
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.ERROR)
logger.addHandler(stderr_handler)
