import logging

from fastapi import FastAPI

from app.routers.debug import router as debug_router
from app.routers.demo import router as demo_router
from app.routers.health import router as health_router
from app.routers.webhook import router as webhook_router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


app = FastAPI(
    title="Abitat WhatsApp Demo Mock",
    version="1.0.0",
    description="Mock funcional de flujo conversacional WhatsApp API para venta de toner y recogida de vacios.",
)

app.include_router(health_router)
app.include_router(demo_router)
app.include_router(webhook_router)
app.include_router(debug_router)

