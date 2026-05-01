from main import app
from fastapi.routing import APIRoute

for route in app.routes:
    if isinstance(route, APIRoute):
        print(f"{route.path} [{route.methods}]")
    else:
        print(f"{route.path} [Mount/Other]")
