"""NDAP Cognito access token provider with refresh support."""

from __future__ import annotations

import os

import boto3
from dotenv import load_dotenv

COGNITO_REGION = "ap-south-1"
COGNITO_CLIENT_ID = "1u8rqvgjm598uua954co358vfi"

_ACCESS_TOKEN: str | None = None
_REFRESH_TOKEN: str | None = None


def _load_tokens() -> tuple[str | None, str | None]:
    load_dotenv()
    access_token = os.getenv("NDAP_ACCESS_TOKEN")
    refresh_token = os.getenv("NDAP_REFRESH_TOKEN")
    return access_token, refresh_token


def refresh() -> str:
    """Refresh and cache Cognito access token using REFRESH_TOKEN_AUTH."""

    global _ACCESS_TOKEN, _REFRESH_TOKEN

    if _REFRESH_TOKEN is None:
        _, env_refresh_token = _load_tokens()
        _REFRESH_TOKEN = env_refresh_token

    if not _REFRESH_TOKEN:
        raise RuntimeError("NDAP_REFRESH_TOKEN is missing from environment")

    client = boto3.client("cognito-idp", region_name=COGNITO_REGION)
    response = client.initiate_auth(
        AuthFlow="REFRESH_TOKEN_AUTH",
        ClientId=COGNITO_CLIENT_ID,
        AuthParameters={"REFRESH_TOKEN": _REFRESH_TOKEN},
    )
    token = response.get("AuthenticationResult", {}).get("AccessToken")
    if not token:
        raise RuntimeError("Cognito refresh did not return AccessToken")

    _ACCESS_TOKEN = token
    os.environ["NDAP_ACCESS_TOKEN"] = token
    return token


def get_access_token() -> str:
    """Return cached access token; refresh only when missing."""

    global _ACCESS_TOKEN, _REFRESH_TOKEN

    if _ACCESS_TOKEN:
        return _ACCESS_TOKEN

    access_token, refresh_token = _load_tokens()
    _ACCESS_TOKEN = access_token
    _REFRESH_TOKEN = refresh_token

    if _ACCESS_TOKEN:
        return _ACCESS_TOKEN

    return refresh()
