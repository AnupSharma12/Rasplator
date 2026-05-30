from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
	# Lightweight startup state for early-stage diagnostics.
	app.state.started = True
	yield
	# Keep shutdown explicit so future cleanup hooks can be added safely.
	app.state.started = False


app = FastAPI(title="Rasplator API", version="0.1.0", lifespan=lifespan)


if __name__ == "__main__":
	import uvicorn

	uvicorn.run(app, host="0.0.0.0", port=8000)
