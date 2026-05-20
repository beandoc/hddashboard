import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        # Test 1: Hit /login with JSON
        r1 = await client.post("http://127.0.0.1:8080/login", json={"username": "admin", "password": "password"})
        print("Test 1 (JSON to /login):", r1.status_code, r1.text)

if __name__ == "__main__":
    asyncio.run(test())
