
from fastapi import FastAPI

app = FastAPI(
    title="Bulk Certificate Generator",
    description="Generate and retrieve certificates for bulk recipient jobs.",
    version="0.1.0",
)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Return the API health status."""
    return {"status": "ok"}
