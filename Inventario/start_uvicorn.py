"""Arranque local del API de inventario; análisis se ejecuta por separado."""
import uvicorn
if __name__ == '__main__':
    uvicorn.run('main:app', host='127.0.0.1', port=5002, log_level='info')
