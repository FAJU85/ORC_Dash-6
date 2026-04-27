"""
ORC Research Dashboard - Tests for Cache module
"""

import pytest
import sys
import os
import time
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.cache import Cache


@pytest.fixture
def tmp_cache(tmp_path):
    """Cache instance using a temporary directory"""
    c = Cache(cache_dir=str(tmp_path / "cache"), default_ttl=60)
    return c


class TestCacheSetGet:

    def test_set_and_get_string(self, tmp_cache):
        tmp_cache.set("ns", "key1", "hello")
        assert tmp_cache.get("ns", "key1") == "hello"

    def test_set_and_get_dict(self, tmp_cache):
        data = {"title": "Test Paper", "year": 2024}
        tmp_cache.set("ns", "key2", data)
        assert tmp_cache.get("ns", "key2") == data

    def test_set_and_get_list(self, tmp_cache):
        data = [1, 2, 3, {"a": "b"}]
        tmp_cache.set("ns", "key3", data)
        assert tmp_cache.get("ns", "key3") == data

    def test_missing_key_returns_none(self, tmp_cache):
        assert tmp_cache.get("ns", "nonexistent") is None

    def test_exists_true(self, tmp_cache):
        tmp_cache.set("ns", "k", "v")
        assert tmp_cache.exists("ns", "k") is True

    def test_exists_false(self, tmp_cache):
        assert tmp_cache.exists("ns", "missing") is False


class TestCacheTTL:

    def test_expired_entry_returns_none(self, tmp_cache):
        tmp_cache.set("ns", "ttl_key", "data", ttl=1)
        time.sleep(1.1)
        assert tmp_cache.get("ns", "ttl_key") is None

    def test_not_expired_entry_returns_data(self, tmp_cache):
        tmp_cache.set("ns", "ttl_ok", "data", ttl=60)
        assert tmp_cache.get("ns", "ttl_ok") == "data"


class TestCacheDelete:

    def test_delete_removes_entry(self, tmp_cache):
        tmp_cache.set("ns", "del_key", "data")
        tmp_cache.delete("ns", "del_key")
        assert tmp_cache.get("ns", "del_key") is None

    def test_delete_nonexistent_is_safe(self, tmp_cache):
        tmp_cache.delete("ns", "ghost")  # should not raise

    def test_clear_all(self, tmp_cache):
        tmp_cache.set("ns", "a", 1)
        tmp_cache.set("ns", "b", 2)
        tmp_cache.clear()
        assert tmp_cache.get("ns", "a") is None
        assert tmp_cache.get("ns", "b") is None

    def test_clear_namespace_only(self, tmp_cache):
        tmp_cache.set("ns1", "a", 1)
        tmp_cache.set("ns2", "b", 2)
        tmp_cache.clear(namespace="ns1")
        assert tmp_cache.get("ns1", "a") is None
        assert tmp_cache.get("ns2", "b") == 2


class TestCacheCleanup:

    def test_cleanup_removes_expired(self, tmp_cache):
        tmp_cache.set("ns", "old", "data", ttl=1)
        time.sleep(1.1)
        tmp_cache.cleanup()
        cache_files = list(os.scandir(tmp_cache.cache_dir))
        assert len(cache_files) == 0

    def test_cleanup_keeps_valid(self, tmp_cache):
        tmp_cache.set("ns", "fresh", "data", ttl=60)
        tmp_cache.cleanup()
        assert tmp_cache.get("ns", "fresh") == "data"
