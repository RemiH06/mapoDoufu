from fastapi import FastAPI

app = FastAPI(title="mapo_core")


@app.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok"}