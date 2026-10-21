from __future__ import annotations

import time
import tomllib
import uuid
from urllib.parse import quote

import httpx

from .config import CopilotError, Settings


class DatabaseError(CopilotError):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(
            f"Database returned HTTP {status_code}. "
            "Check connection permissions and supported operations; response body omitted."
        )


class Database:
    """Small application-specific HTTP adapter; no copied SDK implementation."""

    def __init__(self, settings: Settings, transport=None):
        headers = {"Authorization": f"Bearer {settings.bearer}"}
        if settings.db_user:
            headers.update({"X-OC-DB-User": settings.db_user, "X-OC-DB-Key": settings.db_key})
        self.client = httpx.Client(
            base_url=settings.base_url.rstrip("/"),
            headers=headers,
            timeout=60,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )
        self.prefix = f"/v1/tenants/{settings.tenant}"

    def close(self):
        self.client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        response_json: bool = True,
        response_text: bool = False,
        **kwargs,
    ):
        headers = dict(kwargs.pop("headers", {}))
        if method in {"POST", "PUT", "DELETE"}:
            headers["Idempotency-Key"] = uuid.uuid4().hex
        for attempt in range(3):
            try:
                response = self.client.request(
                    method, self.prefix + path, headers=headers, **kwargs
                )
            except httpx.HTTPError:
                raise CopilotError(
                    "Database connection failed. Check the endpoint and database wake-up state."
                ) from None
            if response.status_code == 429 and attempt < 2:
                try:
                    wait = max(0, float(response.headers.get("Retry-After", "1")))
                except ValueError:
                    wait = 1
                if wait > 10:
                    raise CopilotError("Database rate limit reached. Wait before trying again.")
                time.sleep(wait)
                continue
            if not response.is_success:
                raise DatabaseError(response.status_code)
            if response_text:
                return response.text
            if not response_json:
                return None
            try:
                return response.json()
            except ValueError:
                raise CopilotError("Database returned a non-JSON response.") from None
        raise CopilotError("Database rate limit reached.")

    def register(self, namespace: str, table: str, columns: dict[str, str]):
        definition = [
            f'namespace = "{namespace}"',
            f'table = "{table}"',
            'primary_key = ["id"]',
        ]
        for name, kind in columns.items():
            definition += ["[[columns]]", f'name = "{name}"', f'ty = "{kind}"', "required = true"]
        try:
            return self.request(
                "POST",
                "/schemas",
                content="\n".join(definition),
                headers={"Content-Type": "text/plain"},
            )
        except DatabaseError as error:
            if error.status_code != 409:
                raise
        existing = self.request("GET", f"/schemas/{namespace}.{table}", response_text=True)
        try:
            parsed = tomllib.loads(existing)
            expected = tomllib.loads("\n".join(definition))
            same = (
                parsed.get("namespace") == namespace
                and parsed.get("table") == table
                and parsed.get("primary_key") == ["id"]
                and {c["name"]: (c["ty"], c.get("required", False)) for c in parsed["columns"]}
                == {c["name"]: (c["ty"], c["required"]) for c in expected["columns"]}
            )
        except (ValueError, KeyError, TypeError):
            same = False
        if not same:
            raise CopilotError(
                "Existing schema differs from this starter. Choose a new COPILOT_NAMESPACE."
            )
        return {"existing_schema_verified": True}

    def put(self, table: str, row: dict):
        return self.request("POST", f"/rows/{table}", json=row)

    def get(self, table: str, row_id: str):
        return self.request("GET", f"/rows/{table}/{quote(row_id, safe='')}")

    def sql(self, statement: str) -> list[dict]:
        # Only application-owned statements use this method. Never accept user SQL.
        response = self.request("POST", "/sql", json={"sql": statement})
        if not isinstance(response, dict) or not isinstance(response.get("rows"), list):
            raise CopilotError("Unexpected SQL response; expected a rows array.")
        return response["rows"]

    def index_text(self, table: str, row_id: str, text: str):
        return self.request(
            "POST",
            f"/fts/{table}/body",
            json={"doc_id": row_id, "text": text},
            response_json=False,
        )

    def index_vector(self, table: str, row_id: str, vector: list[float]):
        return self.request(
            "POST",
            f"/vector/{table}/put",
            json={"id": row_id, "embedding": vector, "dim": len(vector)},
            response_json=False,
        )

    def search_text(self, table: str, question: str, k: int = 8) -> list[dict]:
        response = self.request(
            "GET", f"/fts/{table}/body", params={"q": question, "mode": "bm25", "k": k}
        )
        hits = response.get("hits", []) if isinstance(response, dict) else response
        if not isinstance(hits, list):
            raise CopilotError("Unexpected full-text response.")
        return [{"id": str(hit["doc_id"]), "score": hit.get("score", 0)} for hit in hits]

    def search_vector(self, table: str, vector: list[float], k: int = 8) -> list[dict]:
        response = self.request(
            "POST",
            f"/vector/{table}/topk",
            json={"query": vector, "dim": len(vector), "k": k, "metric": "cosine"},
        )
        if not isinstance(response, list):
            raise CopilotError("Unexpected vector response.")
        return response
