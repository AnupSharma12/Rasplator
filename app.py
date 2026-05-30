from contextlib import asynccontextmanager
import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Load .env from project root if present.
load_dotenv()

# Custom AI provider settings (read from environment only).
# Primary variables are AI_PROVIDER_* (provider-agnostic).
AI_PROVIDER_MODEL = os.getenv("AI_PROVIDER_MODEL", "google/gemini-2.5-flash-lite")
AI_PROVIDER_API_URL = os.getenv("AI_PROVIDER_API_URL", "")
AI_PROVIDER_HTTP_REFERER = os.getenv("AI_PROVIDER_HTTP_REFERER")
AI_PROVIDER_APP_TITLE = os.getenv("AI_PROVIDER_APP_TITLE")
AI_PROVIDER_TYPE = os.getenv("AI_PROVIDER_TYPE", "chat")  # 'chat' or 'text'


class HealthResponse(BaseModel):
	status: str
	started: bool


class VersionResponse(BaseModel):
	service: str
	api_version: str


class TranslateRequest(BaseModel):
	text: str = Field(...)
	target_language: str = Field(...)


class TranslateResponse(BaseModel):
	original_text: str
	target_language: str
	translated_text: str
	model: str


@asynccontextmanager
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


@app.post("/translate", response_model=TranslateResponse)
async def translate(payload: TranslateRequest) -> TranslateResponse:
	provider_api_key = os.getenv("AI_PROVIDER_API_KEY")
	if not provider_api_key:
		raise HTTPException(
			status_code=500,
			detail="Missing AI_PROVIDER_API_KEY environment variable",
		)

	if not AI_PROVIDER_API_URL:
		raise HTTPException(
			status_code=500,
			detail="Missing AI_PROVIDER_API_URL environment variable",
		)

	prompt = (
		f"Detect the source language automatically and translate the text "
		f"to {payload.target_language}. Return only the translated text.\n\n"
		f"Text: {payload.text}"
	)
	# Build request body according to provider type
	if AI_PROVIDER_TYPE == "text":
		# Simple prompt-based providers
		body = {"model": AI_PROVIDER_MODEL, "prompt": prompt}
	else:
		# Default to chat-style messages
		body = {
			"model": AI_PROVIDER_MODEL,
			"messages": [
				{"role": "system", "content": "You are a translation engine. Output translation only."},
				{"role": "user", "content": prompt},
			],
		}
	headers = {
		"Authorization": f"Bearer {provider_api_key}",
		"Content-Type": "application/json",
	}
	if AI_PROVIDER_HTTP_REFERER:
		headers["HTTP-Referer"] = AI_PROVIDER_HTTP_REFERER
	if AI_PROVIDER_APP_TITLE:
		headers["X-Title"] = AI_PROVIDER_APP_TITLE

	try:
		async with httpx.AsyncClient(timeout=20.0) as client:
			response = await client.post(
				AI_PROVIDER_API_URL,
				headers=headers,
				json=body,
			)
			response.raise_for_status()
			data = response.json()
	except httpx.TimeoutException as exc:
		raise HTTPException(status_code=504, detail="AI provider request timed out") from exc
	except httpx.HTTPStatusError as exc:
		if exc.response.status_code == 429:
			retry_after = exc.response.headers.get("Retry-After")
			message = "AI provider rate limit reached. Please retry in a moment."
			if retry_after:
				message = f"AI provider rate limit reached. Retry after {retry_after} seconds."
			raise HTTPException(status_code=429, detail=message) from exc
		if exc.response.status_code == 402:
			# Common provider response for insufficient credits
			try:
				provider_body = exc.response.text
			except Exception:
				provider_body = ""
			snippet = (provider_body[:500] + "...") if provider_body and len(provider_body) > 500 else provider_body
			raise HTTPException(
				status_code=402,
				detail=(f"AI provider returned 402 (insufficient credits). {snippet}"),
			) from exc
		# non-429: include a short snippet of the provider response to aid debugging
		try:
			provider_body = exc.response.text
		except Exception:
			provider_body = ""
		snippet = (provider_body[:500] + "...") if provider_body and len(provider_body) > 500 else provider_body
		raise HTTPException(
			status_code=502,
			detail=f"AI provider error: {exc.response.status_code} - {snippet}",
		) from exc
	except httpx.HTTPError as exc:
		raise HTTPException(status_code=502, detail="AI provider request failed") from exc

	try:
		translated_text = data["choices"][0]["message"]["content"]
		if isinstance(translated_text, list):
			translated_text = "".join(
				part.get("text", "") if isinstance(part, dict) else str(part)
				for part in translated_text
			)
		translated_text = str(translated_text).strip()
		if not translated_text:
			raise ValueError("empty translation")
	except (KeyError, IndexError, TypeError, ValueError) as exc:
		raise HTTPException(status_code=502, detail="Invalid AI provider response") from exc

	return {
		"original_text": payload.text,
		"target_language": payload.target_language,
		"translated_text": translated_text,
		"model": AI_PROVIDER_MODEL,
	}


if __name__ == "__main__":
	import uvicorn

	uvicorn.run(app, host="0.0.0.0", port=8000)
