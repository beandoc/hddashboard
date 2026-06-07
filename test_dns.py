import socket
import urllib.request

hosts = ["google.com", "supabase.com", "aws-1-ap-south-1.pooler.supabase.com", "postgres.skuuvwjsotlqpyobjbsw.supabase.co"]

for host in hosts:
    try:
        ip = socket.gethostbyname(host)
        print(f"Resolved {host} to {ip}")
    except Exception as e:
        print(f"Failed to resolve {host}: {e}")

try:
    response = urllib.request.urlopen("https://www.google.com", timeout=5)
    print("HTTPS GET google.com: success, status code:", response.getcode())
except Exception as e:
    print("HTTPS GET google.com failed:", e)
