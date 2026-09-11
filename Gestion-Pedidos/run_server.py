"""
run_server.py - Arranque estable para servicio Windows/WinSW.
"""

import uvicorn
from config import get_settings

settings = get_settings()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=False,
        log_level="info",
    )
