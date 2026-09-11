"""Vertex AI client built from the service account key named in .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set - see .env.example")
    return value


def make_client():
    from google import genai
    from google.oauth2 import service_account

    key_path = Path(_required("GOOGLE_APPLICATION_CREDENTIALS")).expanduser()
    if not key_path.is_file():
        raise RuntimeError(f"Service account key not found: {key_path}")
    credentials = service_account.Credentials.from_service_account_file(str(key_path), scopes=SCOPES)
    return genai.Client(
        vertexai=True,
        project=_required("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        credentials=credentials,
    )
