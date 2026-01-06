from watermark_studio import create_app

app = create_app()

if __name__ == "__main__":
    import os
    import socket

    host = os.environ.get("HOST", "127.0.0.1").strip() or "127.0.0.1"
    try:
        # macOS often has system services bound on 5000; default to 5050 to avoid surprises.
        start_port = int(os.environ.get("PORT", "5050"))
    except ValueError:
        start_port = 5050

    def find_available_port(bind_host: str, port: int, *, tries: int = 50) -> int:
        for p in range(port, port + tries):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind((bind_host, p))
                return p
            except OSError:
                continue
        return port

    port = find_available_port(host, start_port)
    if port != start_port:
        print(f"Port {start_port} is in use; using {port} instead.")
    print(f"Starting server: http://{host}:{port}")
    app.run(host=host, port=port)
