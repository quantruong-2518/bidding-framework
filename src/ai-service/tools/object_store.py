"""S0.5 Wave 1 — S3-compatible object-store wrapper (Python sibling of TS).

Mirrors :class:`ObjectStoreService` (api-gateway) one-for-one so server-side
parse + materialise share an identical contract:

    * ``put_object(bucket, key, body, mime=None)``
    * ``get_object(bucket, key) -> bytes | None``
    * ``presigned_get_url(bucket, key, ttl_sec)``
    * ``rename_prefix(bucket, old_prefix, new_prefix) -> int``
    * ``delete_prefix(bucket, prefix) -> int``
    * ``ensure_bucket(bucket)``

Backend selection (env-driven, one-shot at construction):
    * ``OBJECT_STORE_BACKEND=minio`` → standard MinIO (path-style by default).
    * ``OBJECT_STORE_BACKEND=s3``    → AWS S3 (SDK auto-region, virtual-host
                                       hostnames). Endpoint optional.
    * ``OBJECT_STORE_BACKEND``       unset → **stub mode** (warning + no-ops).

Constructed via :func:`get_object_store` for module-level reuse. Stub-mode is
the default in tests because ``OBJECT_STORE_BACKEND`` is not exported by
``conftest.py`` — every Wave 2A activity that uses the wrapper therefore
exercises the deterministic path automatically.

Async-safety: the underlying ``minio.Minio`` client is sync, so every method
shells out via :func:`anyio.to_thread.run_sync`. Each method awaits a fresh
thread; no blocking call leaks back into the event loop.
"""

from __future__ import annotations

import io
import logging
import os
from datetime import timedelta
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import anyio

logger = logging.getLogger(__name__)

__all__ = [
    "ObjectStoreError",
    "ObjectStore",
    "get_object_store",
]


class ObjectStoreError(RuntimeError):
    """Raised on unrecoverable wrapper-level failures (NOT stubbed methods)."""


def _split_endpoint(endpoint: str | None) -> tuple[str, bool]:
    """Strip scheme from endpoint; return (host:port, secure).

    MinIO's Python SDK takes ``host:port`` separately from a ``secure`` bool
    (the @aws-sdk JS client takes one URL). We accept either form so callers
    can mirror the TS env vars without fork.
    """
    if not endpoint:
        return ("", False)
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    secure = parsed.scheme == "https"
    netloc = parsed.netloc or parsed.path
    return (netloc, secure)


class _DuckCopySource:
    """Fallback CopySource shim used when the real ``minio`` SDK is absent.

    Exposes both attribute styles the SDK / our test fake recognise.
    """

    __slots__ = ("bucket_name", "object_name", "bucket", "object")

    def __init__(self, bucket: str, key: str) -> None:
        self.bucket_name = bucket
        self.object_name = key
        # Real SDK uses bucket_name/object_name; some forks expose bucket/object.
        self.bucket = bucket
        self.object = key


class _DuckDeleteObject:
    """Fallback DeleteObject shim used when the real ``minio`` SDK is absent."""

    __slots__ = ("name", "object_name")

    def __init__(self, key: str) -> None:
        self.name = key
        self.object_name = key


def _make_copy_source() -> Any:
    """Return ``minio.commonconfig.CopySource`` if importable, else a duck-typed shim."""
    try:
        from minio.commonconfig import CopySource  # type: ignore[import-untyped]

        return CopySource
    except ImportError:
        return _DuckCopySource


def _make_delete_object() -> Any:
    """Return ``minio.deleteobjects.DeleteObject`` if importable, else a duck shim."""
    try:
        from minio.deleteobjects import DeleteObject  # type: ignore[import-untyped]

        return DeleteObject
    except ImportError:
        return _DuckDeleteObject


class ObjectStore:
    """Thin async facade over the (sync) MinIO Python SDK.

    Stub-fallback rules:
      * ``OBJECT_STORE_BACKEND`` unset/unknown → :attr:`is_stub` is True;
        every method logs a debug line and returns the no-op shape.
      * SDK import failure (e.g. minio not installed) → log warning, fall
        back to stub.
      * Any exception during client construction → fall back to stub.
    """

    def __init__(
        self,
        *,
        backend: str | None = None,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._backend = (backend or os.environ.get("OBJECT_STORE_BACKEND", "")).lower()
        self._endpoint = endpoint or os.environ.get("OBJECT_STORE_ENDPOINT")
        self._access_key = access_key or os.environ.get("OBJECT_STORE_ACCESS_KEY", "")
        self._secret_key = secret_key or os.environ.get("OBJECT_STORE_SECRET_KEY", "")
        self._region = region or os.environ.get("OBJECT_STORE_REGION", "us-east-1")
        self._client: Any | None = client
        self._stub: bool

        if self._client is not None:
            # Test-injected client — assume real.
            self._stub = False
            return

        if self._backend not in ("minio", "s3"):
            logger.warning(
                "object_store.stub_mode reason=backend_unset_or_unknown "
                "(set OBJECT_STORE_BACKEND=minio|s3 to enable)"
            )
            self._stub = True
            return

        try:
            from minio import Minio  # type: ignore[import-untyped]
        except ImportError as exc:
            logger.warning("object_store.stub_mode reason=minio_sdk_missing err=%s", exc)
            self._stub = True
            return

        try:
            host, secure = _split_endpoint(self._endpoint)
            if not host:
                # MinIO SDK requires an endpoint host. Stub if missing.
                logger.warning(
                    "object_store.stub_mode reason=endpoint_missing "
                    "(set OBJECT_STORE_ENDPOINT=host:port)"
                )
                self._stub = True
                return
            self._client = Minio(
                host,
                access_key=self._access_key or None,
                secret_key=self._secret_key or None,
                secure=secure,
                region=self._region,
            )
            self._stub = False
            logger.info(
                "object_store.ready backend=%s endpoint=%s secure=%s region=%s",
                self._backend,
                host,
                secure,
                self._region,
            )
        except Exception as exc:  # noqa: BLE001 — never crash on init
            logger.warning("object_store.stub_mode reason=client_init_failed err=%s", exc)
            self._stub = True

    @property
    def is_stub(self) -> bool:
        """``True`` when no real backend is wired up; useful for health endpoints."""
        return self._stub

    async def put_object(
        self,
        bucket: str,
        key: str,
        body: bytes | bytearray | memoryview | str,
        mime: str | None = None,
    ) -> None:
        """Upload a single object. ``body`` may be bytes-like or str (UTF-8 encoded)."""
        if self._stub or self._client is None:
            logger.debug(
                "object_store.stub.put_object bucket=%s key=%s bytes=%d mime=%s",
                bucket,
                key,
                len(body) if hasattr(body, "__len__") else -1,
                mime,
            )
            return
        if isinstance(body, str):
            body_bytes = body.encode("utf-8")
        else:
            body_bytes = bytes(body)
        await anyio.to_thread.run_sync(
            self._put_sync, bucket, key, body_bytes, mime
        )

    def _put_sync(
        self, bucket: str, key: str, body_bytes: bytes, mime: str | None
    ) -> None:
        assert self._client is not None
        self._client.put_object(
            bucket,
            key,
            io.BytesIO(body_bytes),
            length=len(body_bytes),
            content_type=mime or "application/octet-stream",
        )

    async def get_object(self, bucket: str, key: str) -> bytes | None:
        """Fetch an object. Returns ``None`` in stub mode."""
        if self._stub or self._client is None:
            logger.debug("object_store.stub.get_object bucket=%s key=%s", bucket, key)
            return None
        return await anyio.to_thread.run_sync(self._get_sync, bucket, key)

    def _get_sync(self, bucket: str, key: str) -> bytes:
        assert self._client is not None
        response = self._client.get_object(bucket, key)
        try:
            return response.read()
        finally:
            try:
                response.close()
                response.release_conn()
            except Exception:  # noqa: BLE001
                pass

    async def presigned_get_url(self, bucket: str, key: str, ttl_sec: int) -> str:
        """Generate a TTL-bounded presigned GET URL.

        Returns a stable ``stub://`` placeholder when in stub mode so callers
        can still produce a payload that the frontend won't choke on.
        """
        if self._stub or self._client is None:
            logger.debug(
                "object_store.stub.presigned_get_url bucket=%s key=%s ttl=%d",
                bucket,
                key,
                ttl_sec,
            )
            return f"stub://object-store/{bucket}/{key}?ttl={ttl_sec}"
        return await anyio.to_thread.run_sync(
            self._presign_sync, bucket, key, ttl_sec
        )

    def _presign_sync(self, bucket: str, key: str, ttl_sec: int) -> str:
        assert self._client is not None
        return self._client.presigned_get_object(
            bucket, key, expires=timedelta(seconds=ttl_sec)
        )

    async def rename_prefix(
        self, bucket: str, old_prefix: str, new_prefix: str
    ) -> int:
        """List + copy + delete every key under ``old_prefix``. Returns moved count."""
        if self._stub or self._client is None:
            logger.debug(
                "object_store.stub.rename_prefix bucket=%s %s -> %s",
                bucket,
                old_prefix,
                new_prefix,
            )
            return 0
        return await anyio.to_thread.run_sync(
            self._rename_sync, bucket, old_prefix, new_prefix
        )

    def _rename_sync(self, bucket: str, old_prefix: str, new_prefix: str) -> int:
        assert self._client is not None
        copy_source = _make_copy_source()

        moved = 0
        keys = self._list_sync(bucket, old_prefix)
        for key in keys:
            new_key = new_prefix + key[len(old_prefix) :]
            self._client.copy_object(
                bucket,
                new_key,
                copy_source(bucket, key),
            )
            self._client.remove_object(bucket, key)
            moved += 1
        return moved

    async def delete_prefix(self, bucket: str, prefix: str) -> int:
        """Delete every key under ``prefix``. Returns count deleted."""
        if self._stub or self._client is None:
            logger.debug(
                "object_store.stub.delete_prefix bucket=%s prefix=%s", bucket, prefix
            )
            return 0
        return await anyio.to_thread.run_sync(self._delete_prefix_sync, bucket, prefix)

    def _delete_prefix_sync(self, bucket: str, prefix: str) -> int:
        assert self._client is not None
        delete_object = _make_delete_object()

        keys = self._list_sync(bucket, prefix)
        if not keys:
            return 0
        objs = [delete_object(k) for k in keys]
        # Drain the generator so partial failures still register as deleted.
        for _ in self._client.remove_objects(bucket, objs):
            pass
        return len(keys)

    async def ensure_bucket(self, bucket: str) -> None:
        """Idempotent bucket creation."""
        if self._stub or self._client is None:
            logger.debug("object_store.stub.ensure_bucket bucket=%s", bucket)
            return
        await anyio.to_thread.run_sync(self._ensure_sync, bucket)

    def _ensure_sync(self, bucket: str) -> None:
        assert self._client is not None
        if self._client.bucket_exists(bucket):
            return
        self._client.make_bucket(bucket)

    def _list_sync(self, bucket: str, prefix: str) -> list[str]:
        """List every key under ``prefix`` (recursive)."""
        assert self._client is not None
        out: list[str] = []
        for obj in self._client.list_objects(bucket, prefix=prefix, recursive=True):
            name = getattr(obj, "object_name", None)
            if name:
                out.append(name)
        return out


@lru_cache(maxsize=1)
def get_object_store() -> ObjectStore:
    """Return the singleton :class:`ObjectStore` (cached per process)."""
    return ObjectStore()
