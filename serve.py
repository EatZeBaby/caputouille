"""
Datatouille dev server — serves over HTTPS so the PWA/Service Worker works on iPad.

Usage:
    python3 serve.py          # HTTPS on port 8443 (PWA-compatible)
    python3 serve.py --http   # HTTP on port 8080 (desktop dev only)
"""
import http.server
import ssl
import os
import subprocess
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

CERT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.certs')
CERT_FILE = os.path.join(CERT_DIR, 'cert.pem')
KEY_FILE = os.path.join(CERT_DIR, 'key.pem')


def generate_self_signed_cert():
    """Generate a self-signed certificate for local HTTPS."""
    os.makedirs(CERT_DIR, exist_ok=True)
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        return

    # Get local IP for the certificate SAN
    import socket
    local_ip = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = '127.0.0.1'

    print(f"Generating self-signed certificate for {local_ip}...")

    subprocess.run([
        'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
        '-keyout', KEY_FILE, '-out', CERT_FILE,
        '-days', '365', '-nodes',
        '-subj', f'/CN={local_ip}',
        '-addext', f'subjectAltName=IP:{local_ip},IP:127.0.0.1,DNS:localhost',
    ], check=True, capture_output=True)
    print("Certificate generated.\n")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler with correct MIME types and less noise."""
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        '.js': 'text/javascript',
        '.css': 'text/css',
        '.json': 'application/json',
        '.svg': 'image/svg+xml',
        '.webmanifest': 'application/manifest+json',
    }

    def log_message(self, format, *args):
        # Only log errors, not every request
        if args and isinstance(args[0], str) and args[0].startswith('GET'):
            return
        super().log_message(format, *args)


def get_local_ips():
    """Get all local IPs (WiFi, Ethernet, VPN)."""
    import socket
    ips = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith('127.'):
                ips.append(ip)
    except Exception:
        pass
    # Fallback: route-based detection
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            pass
    return ips or ['localhost']


def main():
    use_https = '--http' not in sys.argv
    port = 8443 if use_https else 8080
    local_ips = get_local_ips()

    if use_https:
        generate_self_signed_cert()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(CERT_FILE, KEY_FILE)

    server = http.server.HTTPServer(('0.0.0.0', port), QuietHandler)

    if use_https:
        server.socket = context.wrap_socket(server.socket, server_side=True)

    protocol = 'https' if use_https else 'http'
    print(f"  Datatouille running at:")
    print(f"    Local:   {protocol}://localhost:{port}/app/")
    for ip in local_ips:
        print(f"    Network: {protocol}://{ip}:{port}/app/")
    if use_https:
        print(f"\n  On iPad (same WiFi): open a Network URL in Safari,")
        print(f"  accept the certificate warning, then 'Add to Home Screen'.\n")
    else:
        print(f"\n  Note: Service Worker requires HTTPS. Run without --http for iPad.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == '__main__':
    main()
