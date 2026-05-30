from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
	status: str
	started: bool


class VersionResponse(BaseModel):
	service: str
	api_version: str


@asynccontextmante
async def lifespan(app: FastAPI):
	# Lightweight startup state for early-stage diagnostics.
	app.state.started = True
	yield
	# Keep shutdown explicit so future cleanup hooks can be added safely.
	app.state.started = False


app = FastAPI(title="Rasplator API", version="0.1.0", lifespan=lifespan)



@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
	return {
		"status": "ok",
		"started": bool(getattr(app.state, "started", False)),
	}


@app.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
	return {
		"service": app.title,
		"api_version": app.version,
	}


if __name__ == "__main__":
	import uvicorn

	uvicorn.run(app, host="0.0.0.0", port=8000)
