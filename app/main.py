import os

from fastapi import FastAPI

app = FastAPI(title="Docker Cloud App")


@app.get("/")
def root():
    return {"message": "Hello from Google Cloud Run!", "status": "running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
