#!/usr/bin/env python3
"""
TCP Load Balancer / Connection Switcher for Cowrie Honeypots

Routes incoming SSH connections to multiple Cowrie instances using round-robin.
"""

import socket
import threading
import itertools
import sys

# Configuration
LISTEN_HOST = '0.0.0.0'
LISTEN_PORT = 2222  # The port attackers connect to (EXTERNAL)

# The two cowrie instances (INTERNAL)
BACKENDS = [
    ('127.0.0.1', 2223),
    ('127.0.0.1', 2224)
]

# Round-robin cycle
backend_cycle = itertools.cycle(BACKENDS)
cycle_lock = threading.Lock()


def get_next_backend():
    """Thread-safe backend selection."""
    with cycle_lock:
        return next(backend_cycle)


def handle_client(client_socket, client_addr):
    """Handle a single client connection by forwarding to a backend."""
    # Select next backend
    backend_host, backend_port = get_next_backend()
    print(f"[*] Forwarding connection from {client_addr[0]} to {backend_host}:{backend_port}")

    try:
        backend_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        backend_socket.connect((backend_host, backend_port))
    except Exception as e:
        print(f"[!] Failed to connect to backend {backend_host}:{backend_port}: {e}")
        client_socket.close()
        return

    # Start bidirectional forwarding
    client_to_backend = threading.Thread(
        target=forward,
        args=(client_socket, backend_socket, f"{client_addr[0]} -> backend")
    )
    backend_to_client = threading.Thread(
        target=forward,
        args=(backend_socket, client_socket, f"backend -> {client_addr[0]}")
    )

    client_to_backend.start()
    backend_to_client.start()


def forward(source, destination, direction=""):
    """Forward data from source to destination socket."""
    try:
        while True:
            data = source.recv(4096)
            if len(data) == 0:
                break
            destination.send(data)
    except Exception:
        pass
    finally:
        try:
            source.close()
        except Exception:
            pass
        try:
            destination.close()
        except Exception:
            pass


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((LISTEN_HOST, LISTEN_PORT))
    except Exception as e:
        print(f"[!] Error binding to {LISTEN_HOST}:{LISTEN_PORT}: {e}")
        sys.exit(1)

    server.listen(100)
    print(f"[*] Load Balancer listening on {LISTEN_HOST}:{LISTEN_PORT}")
    print(f"[*] Forwarding traffic to backends: {BACKENDS}")

    while True:
        try:
            client_socket, addr = server.accept()
            # Start a thread for the connection so the loop can accept next one immediately
            client_handler = threading.Thread(target=handle_client, args=(client_socket, addr))
            client_handler.daemon = True
            client_handler.start()
        except KeyboardInterrupt:
            print("\n[*] Stopping...")
            break
        except Exception as e:
            print(f"[!] Socket error: {e}")

    server.close()


if __name__ == '__main__':
    main()
