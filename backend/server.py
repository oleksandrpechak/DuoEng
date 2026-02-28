from app.main import app

__all__ = ["app"]


if __name__ == "__main__":
    import os
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
