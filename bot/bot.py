#!/usr/bin/env python3
import os, time, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

print("=== CONTAINER STARTED ===", flush=True)
print(f"BOT_TOKEN set: {bool(os.getenv('BOT_TOKEN'))}", flush=True)
print(f"ADMIN_ID: {os.getenv('ADMIN_ID', 'NOT SET')}", flush=True)
print(f"All env keys: {list(os.environ.keys())}", flush=True)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *a): pass

def serve():
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

threading.Thread(target=serve, daemon=True).start()
print("Health server started on :8080", flush=True)

while True:
    time.sleep(30)
    print("still alive", flush=True)
