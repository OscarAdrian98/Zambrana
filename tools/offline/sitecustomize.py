"""Guard de red activado exclusivamente por tools/run_tests.py."""
import os
if os.environ.get('PORTFOLIO_OFFLINE_TESTS') == '1':
    import socket
    def blocked(*args, **kwargs):
        raise RuntimeError('Network access is disabled in portfolio tests.')
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    socket.socket.bind = blocked
    socket.create_connection = blocked
    socket.getaddrinfo = blocked
