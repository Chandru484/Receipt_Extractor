"""Helper script to launch an ngrok tunnel to the local FastAPI server.

Usage:
    python run_ngrok.py [port]

Default port: 8000
"""

import sys
from pyngrok import ngrok


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Connecting ngrok tunnel to http://localhost:{port}...")
    try:
        tunnel = ngrok.connect(port, "http")
        print("=" * 64)
        print(f"🚀 PUBLIC NGROK URL: {tunnel.public_url}")
        print(f"📖 Swagger Docs:    {tunnel.public_url}/docs")
        print(f"📥 Extract API:     {tunnel.public_url}/extract")
        print("=" * 64)
        print("Tunnel is active! Press Ctrl+C in this terminal to stop.\n")

        ngrok_process = ngrok.get_ngrok_process()
        ngrok_process.proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down ngrok tunnel...")
        ngrok.kill()
    except Exception as e:
        print(f"\n❌ Could not start ngrok: {e}")
        print("\nIf you haven't set your auth token yet, run:")
        print("  .\\venv\\Scripts\\ngrok config add-authtoken <YOUR_AUTHTOKEN>")
        print("or:")
        print("  python -c \"from pyngrok import ngrok; ngrok.set_auth_token('<YOUR_AUTHTOKEN>')\"")


if __name__ == "__main__":
    main()
