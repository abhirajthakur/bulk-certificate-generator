from fastapi import FastAPI

from .api.routes import router

app = FastAPI(
    title="Bulk Certificate Generator",
    description="Generate and retrieve certificates for bulk recipient jobs.",
    version="0.1.0",
)

app.include_router(router)
