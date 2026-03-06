import logging
import time
from typing import TypedDict

import boto3
import requests
from botocore.exceptions import ClientError
from flask import current_app
from jose import JWTError, jwk, jwt

logger = logging.getLogger(__name__)

# Cache JWKS keys per user pool to avoid repeated fetches
_jwks_cache: dict[str, dict] = {}
_jwks_cache_time: dict[str, float] = {}
_JWKS_CACHE_TTL = 3600  # 1 hour


class CognitoTokens(TypedDict):
    id_token: str
    access_token: str
    refresh_token: str


class CognitoError(Exception):
    """Custom exception for Cognito operations."""

    def __init__(self, message: str, code: str = "CognitoError") -> None:
        super().__init__(message)
        self.code = code


def _get_cognito_client():
    """Get a boto3 cognito-idp client."""
    region = current_app.config["COGNITO_REGION"]
    return boto3.client("cognito-idp", region_name=region)


def _get_user_pool_id() -> str:
    pool_id = current_app.config.get("COGNITO_USER_POOL_ID")
    if not pool_id:
        raise CognitoError("COGNITO_USER_POOL_ID not configured", "ConfigError")
    return pool_id


def _get_client_id() -> str:
    client_id = current_app.config.get("COGNITO_CLIENT_ID")
    if not client_id:
        raise CognitoError("COGNITO_CLIENT_ID not configured", "ConfigError")
    return client_id


def sign_up(email: str, password: str, display_name: str) -> str:
    """Register a user in Cognito.

    Returns the Cognito user sub (unique identifier).
    Raises CognitoError on failure.
    """
    client = _get_cognito_client()
    client_id = _get_client_id()

    try:
        response = client.sign_up(
            ClientId=client_id,
            Username=email,
            Password=password,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "name", "Value": display_name},
            ],
        )
        return response["UserSub"]
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        if error_code == "UsernameExistsException":
            raise CognitoError("An account with this email already exists", error_code)
        if error_code == "InvalidPasswordException":
            raise CognitoError(error_msg, error_code)
        if error_code == "InvalidParameterException":
            raise CognitoError(error_msg, error_code)
        logger.error("Cognito sign_up error: %s - %s", error_code, error_msg)
        raise CognitoError(f"Registration failed: {error_msg}", error_code)


def confirm_sign_up(email: str, confirmation_code: str) -> bool:
    """Confirm email verification for a Cognito user.

    Returns True on success.
    Raises CognitoError on failure.
    """
    client = _get_cognito_client()
    client_id = _get_client_id()

    try:
        client.confirm_sign_up(
            ClientId=client_id,
            Username=email,
            ConfirmationCode=confirmation_code,
        )
        return True
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        if error_code == "CodeMismatchException":
            raise CognitoError("Invalid verification code", error_code)
        if error_code == "ExpiredCodeException":
            raise CognitoError(
                "Verification code has expired. Please request a new one.", error_code
            )
        if error_code == "NotAuthorizedException":
            raise CognitoError("User is already confirmed", error_code)
        logger.error("Cognito confirm_sign_up error: %s - %s", error_code, error_msg)
        raise CognitoError(f"Confirmation failed: {error_msg}", error_code)


def sign_in(email: str, password: str) -> CognitoTokens:
    """Authenticate a user and return Cognito tokens.

    Returns dict with id_token, access_token, refresh_token.
    Raises CognitoError on failure.
    """
    client = _get_cognito_client()
    client_id = _get_client_id()

    try:
        response = client.initiate_auth(
            ClientId=client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": email,
                "PASSWORD": password,
            },
        )
        result = response["AuthenticationResult"]
        return CognitoTokens(
            id_token=result["IdToken"],
            access_token=result["AccessToken"],
            refresh_token=result["RefreshToken"],
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        if error_code == "NotAuthorizedException":
            raise CognitoError("Incorrect email or password", error_code)
        if error_code == "UserNotConfirmedException":
            raise CognitoError(
                "Email not verified. Please check your email for a verification code.",
                error_code,
            )
        if error_code == "UserNotFoundException":
            raise CognitoError("Incorrect email or password", error_code)
        logger.error("Cognito sign_in error: %s - %s", error_code, error_msg)
        raise CognitoError(f"Login failed: {error_msg}", error_code)


def resend_confirmation_code(email: str) -> bool:
    """Resend the email verification code.

    Returns True on success.
    Raises CognitoError on failure.
    """
    client = _get_cognito_client()
    client_id = _get_client_id()

    try:
        client.resend_confirmation_code(
            ClientId=client_id,
            Username=email,
        )
        return True
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        if error_code == "LimitExceededException":
            raise CognitoError(
                "Too many attempts. Please wait before requesting a new code.",
                error_code,
            )
        logger.error(
            "Cognito resend_confirmation_code error: %s - %s", error_code, error_msg
        )
        raise CognitoError(f"Failed to resend code: {error_msg}", error_code)


def _get_jwks(user_pool_id: str, region: str) -> dict:
    """Fetch and cache JWKS (JSON Web Key Set) from Cognito."""
    now = time.time()
    cached_time = _jwks_cache_time.get(user_pool_id, 0)

    if user_pool_id in _jwks_cache and (now - cached_time) < _JWKS_CACHE_TTL:
        return _jwks_cache[user_pool_id]

    jwks_url = (
        f"https://cognito-idp.{region}.amazonaws.com"
        f"/{user_pool_id}/.well-known/jwks.json"
    )
    response = requests.get(jwks_url, timeout=10)
    response.raise_for_status()
    jwks_data = response.json()

    _jwks_cache[user_pool_id] = jwks_data
    _jwks_cache_time[user_pool_id] = now
    return jwks_data


def verify_token(access_token: str) -> dict:
    """Verify a Cognito JWT access token.

    Returns the decoded token claims on success.
    Raises CognitoError if the token is invalid or expired.
    """
    user_pool_id = _get_user_pool_id()
    region = current_app.config["COGNITO_REGION"]

    try:
        # Get the kid from the token header
        unverified_header = jwt.get_unverified_header(access_token)
        kid = unverified_header.get("kid")
        if not kid:
            raise CognitoError("Token missing kid header", "InvalidToken")

        # Fetch JWKS and find matching key
        jwks_data = _get_jwks(user_pool_id, region)
        key_data = None
        for key in jwks_data.get("keys", []):
            if key["kid"] == kid:
                key_data = key
                break

        if not key_data:
            raise CognitoError("Token signing key not found", "InvalidToken")

        # Construct the public key
        public_key = jwk.construct(key_data)

        # Verify and decode the token
        issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        claims = jwt.decode(
            access_token,
            public_key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},  # access tokens don't have aud claim
        )

        # Verify token_use is "access"
        if claims.get("token_use") != "access":
            raise CognitoError("Token is not an access token", "InvalidToken")

        return claims

    except JWTError as e:
        raise CognitoError(f"Invalid or expired token: {e}", "InvalidToken")
