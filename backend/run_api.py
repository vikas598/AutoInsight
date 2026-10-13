"""
AutoInsight — API entry point

Run from backend/:
    python run_api.py

The API will be available at http://localhost:8000
    * Swagger UI:    http://localhost:8000/docs
    * ReDoc:         http://localhost:8000/redoc
    * Health check:  http://localhost:8000/api/health
"""

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app"],
        log_level="info",
    )
