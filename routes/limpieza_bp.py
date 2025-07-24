import gc
import psutil
import os
from flask import Blueprint, jsonify
from logging_config import logger
limpieza_bp = Blueprint('limpieza_bp', __name__)


@limpieza_bp.route('/limpiar_memoria', methods=['POST'])
def limpiar_memoria():

    # Liberar la basura del recolector
    logger.info("Iniciando limpieza de memoria...")
    collected = gc.collect()
    logger.info(f"Garbage Collector recolectó {collected} objetos.")

    # Intentar liberar caché de procesos (funciona mejor en Linux)
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    logger.info(f"Uso de memoria antes: {mem_info.rss / (1024 ** 2):.2f} MB")

    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
        logger.info("malloc_trim ejecutado.")
    except Exception as e:
        logger.warning(f"No se pudo ejecutar malloc_trim: {e}")

    mem_info_after = process.memory_info()
    logger.info(f"Uso de memoria después: {mem_info_after.rss / (1024 ** 2):.2f} MB")

    return jsonify({
        "status": "ok",
        "memoria_antes": f"{mem_info.rss / (1024 ** 2):.2f} MB",
        "memoria_despues": f"{mem_info_after.rss / (1024 ** 2):.2f} MB",
        "objetos_recolectados": collected
    })
