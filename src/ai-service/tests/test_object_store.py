"""S0.5 Wave 1 — ObjectStore wrapper unit specs.

Pure-Python module. The host environment may or may not have the ``minio``
SDK installed; we mock the SDK surface explicitly so the deterministic stub
path AND the "real" path (with mocked client) both run on bare pytest.

Mirrors the matrix covered by ``object-store.service.spec.ts`` in api-gateway.
"""

from __future__ import annotations

from typing import Any

import pytest

from tools.object_store import ObjectStore, _split_endpoint


@pytest.fixture(autouse=True)
def _compress_gate_timeouts():  # noqa: D401 — override conftest fixture
    """No-op override: object-store tests don't touch the workflow module."""

    yield


@pytest.fixture(autouse=True)
def _stub_redis_publish():
    """No-op override: object-store tests never publish."""

    yield None


@pytest.fixture(autouse=True)
def _sandbox_kb_vault(tmp_path):
    """No-op override: object-store tests never write to the vault."""

    yield tmp_path


@pytest.fixture(autouse=True)
def _scrub_object_store_env(monkeypatch):
    """Default state: no env vars → stub mode unless the test sets them."""
    for key in (
        "OBJECT_STORE_BACKEND",
        "OBJECT_STORE_ENDPOINT",
        "OBJECT_STORE_ACCESS_KEY",
        "OBJECT_STORE_SECRET_KEY",
        "OBJECT_STORE_REGION",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


class _FakeMinioObj:
    def __init__(self, name: str) -> None:
        self.object_name = name


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        return self._body

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class _FakeMinioClient:
    """Minimal in-memory stand-in for ``minio.Minio`` used by the wrapper."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.objects: dict[tuple[str, str], bytes] = {}
        self.buckets: set[str] = set()

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))

    # --- bucket lifecycle ------------------------------------------------
    def bucket_exists(self, bucket: str) -> bool:
        self._record("bucket_exists", bucket)
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self._record("make_bucket", bucket)
        self.buckets.add(bucket)

    # --- object IO -------------------------------------------------------
    def put_object(
        self,
        bucket: str,
        key: str,
        data: Any,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> None:
        self._record(
            "put_object", bucket, key, length=length, content_type=content_type
        )
        body = data.read() if hasattr(data, "read") else bytes(data)
        self.objects[(bucket, key)] = body

    def get_object(self, bucket: str, key: str) -> _FakeResponse:
        self._record("get_object", bucket, key)
        body = self.objects.get((bucket, key), b"")
        return _FakeResponse(body)

    def list_objects(self, bucket: str, prefix: str = "", recursive: bool = False):
        self._record("list_objects", bucket, prefix=prefix, recursive=recursive)
        return [
            _FakeMinioObj(name)
            for (b, name) in self.objects.keys()
            if b == bucket and name.startswith(prefix)
        ]

    def copy_object(self, bucket: str, new_key: str, source: Any) -> None:
        self._record("copy_object", bucket, new_key, source)
        # Source signature: CopySource(bucket, key) — duck-typed fields.
        src_bucket = getattr(source, "bucket_name", None) or getattr(
            source, "bucket", None
        )
        src_key = getattr(source, "object_name", None) or getattr(
            source, "object", None
        )
        if (src_bucket, src_key) in self.objects:
            self.objects[(bucket, new_key)] = self.objects[(src_bucket, src_key)]

    def remove_object(self, bucket: str, key: str) -> None:
        self._record("remove_object", bucket, key)
        self.objects.pop((bucket, key), None)

    def remove_objects(self, bucket: str, objs):
        self._record("remove_objects", bucket)
        for o in objs:
            key = getattr(o, "name", None) or getattr(o, "object_name", None)
            self.objects.pop((bucket, key), None)
            yield None  # generator surface mirrors the real SDK

    def presigned_get_object(self, bucket: str, key: str, expires=None) -> str:
        self._record("presigned_get_object", bucket, key, expires=expires)
        ttl = int(expires.total_seconds()) if expires is not None else 0
        return f"https://fake-presign/{bucket}/{key}?ttl={ttl}"


# ---------------------------------------------------------------------------
# Stub-mode specs
# ---------------------------------------------------------------------------


def test_default_construction_is_stub_when_env_unset() -> None:
    store = ObjectStore()
    assert store.is_stub is True


def test_unknown_backend_falls_back_to_stub() -> None:
    store = ObjectStore(backend="rados")
    assert store.is_stub is True


@pytest.mark.asyncio
async def test_stub_mode_methods_no_op_and_emit_placeholder_url() -> None:
    store = ObjectStore()
    await store.put_object("bid-originals", "k", b"x", "text/plain")
    assert await store.get_object("bid-originals", "k") is None
    assert await store.rename_prefix("bid-originals", "old/", "new/") == 0
    assert await store.delete_prefix("bid-originals", "old/") == 0
    await store.ensure_bucket("bid-originals")
    url = await store.presigned_get_url("bid-originals", "k", 300)
    assert url.startswith("stub://")


# ---------------------------------------------------------------------------
# Real-path specs (mocked SDK)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_object_round_trips_through_fake_client() -> None:
    fake = _FakeMinioClient()
    store = ObjectStore(backend="minio", endpoint="http://minio:9000", client=fake)
    assert store.is_stub is False
    await store.put_object("bid-originals", "sess/01.pdf", b"hello", "application/pdf")
    assert fake.objects[("bid-originals", "sess/01.pdf")] == b"hello"
    # Confirm content_type propagated
    name, _args, kwargs = fake.calls[-1]
    assert name == "put_object"
    assert kwargs["content_type"] == "application/pdf"


@pytest.mark.asyncio
async def test_get_object_returns_bytes() -> None:
    fake = _FakeMinioClient()
    fake.objects[("bid-originals", "k")] = b"payload"
    store = ObjectStore(backend="minio", endpoint="http://minio:9000", client=fake)
    body = await store.get_object("bid-originals", "k")
    assert body == b"payload"


@pytest.mark.asyncio
async def test_rename_prefix_lists_then_copies_then_deletes() -> None:
    fake = _FakeMinioClient()
    fake.objects[("bid-originals", "old/a.txt")] = b"a"
    fake.objects[("bid-originals", "old/sub/b.txt")] = b"b"
    store = ObjectStore(backend="minio", endpoint="http://minio:9000", client=fake)
    moved = await store.rename_prefix("bid-originals", "old/", "new/")
    assert moved == 2
    assert ("bid-originals", "old/a.txt") not in fake.objects
    assert ("bid-originals", "new/a.txt") in fake.objects
    assert fake.objects[("bid-originals", "new/a.txt")] == b"a"
    assert fake.objects[("bid-originals", "new/sub/b.txt")] == b"b"


@pytest.mark.asyncio
async def test_delete_prefix_removes_listed_keys() -> None:
    fake = _FakeMinioClient()
    fake.objects[("bid-originals", "sess/a")] = b"1"
    fake.objects[("bid-originals", "sess/b")] = b"2"
    fake.objects[("bid-originals", "other/x")] = b"keep"
    store = ObjectStore(backend="minio", endpoint="http://minio:9000", client=fake)
    n = await store.delete_prefix("bid-originals", "sess/")
    assert n == 2
    assert ("bid-originals", "sess/a") not in fake.objects
    assert ("bid-originals", "sess/b") not in fake.objects
    # Untouched keys outside the prefix
    assert fake.objects[("bid-originals", "other/x")] == b"keep"


@pytest.mark.asyncio
async def test_ensure_bucket_is_idempotent_when_exists() -> None:
    fake = _FakeMinioClient()
    fake.buckets.add("bid-originals")
    store = ObjectStore(backend="minio", endpoint="http://minio:9000", client=fake)
    await store.ensure_bucket("bid-originals")
    assert "bid-originals" in fake.buckets
    # No make_bucket call recorded
    assert not any(c[0] == "make_bucket" for c in fake.calls)


@pytest.mark.asyncio
async def test_ensure_bucket_creates_when_missing() -> None:
    fake = _FakeMinioClient()
    store = ObjectStore(backend="minio", endpoint="http://minio:9000", client=fake)
    await store.ensure_bucket("bid-originals")
    assert "bid-originals" in fake.buckets


@pytest.mark.asyncio
async def test_presigned_get_url_passes_ttl_through_to_sdk() -> None:
    fake = _FakeMinioClient()
    store = ObjectStore(backend="minio", endpoint="http://minio:9000", client=fake)
    url = await store.presigned_get_url("bid-originals", "sess/x.pdf", 600)
    assert "ttl=600" in url
    assert "/bid-originals/sess/x.pdf" in url


def test_split_endpoint_handles_scheme_variants() -> None:
    assert _split_endpoint("http://minio:9000") == ("minio:9000", False)
    assert _split_endpoint("https://s3.amazonaws.com") == ("s3.amazonaws.com", True)
    assert _split_endpoint("minio:9000") == ("minio:9000", False)
    assert _split_endpoint(None) == ("", False)
    assert _split_endpoint("") == ("", False)
