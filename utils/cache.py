"""
ORC Research Dashboard - Cache Module
Caches OpenAlex API responses to reduce redundant calls
"""

import time
import json
import hashlib
import os
import logging
from typing import Any, Optional
from datetime import datetime, timedelta


class Cache:
    """
    Simple file-based cache for API responses
    
    Usage:
        cache = Cache(ttl_seconds=3600)  # 1 hour default TTL
        
        # Get cached data
        data = cache.get("openalex", "works_123")
        
        # Set cached data
        cache.set("openalex", "works_123", some_data)
        
        # Check if exists
        if cache.exists("openalex", "works_123"):
            ...
    """
    
    def __init__(self, cache_dir: str = ".cache", default_ttl: int = 3600):
        """
        Initialize cache
        
        Args:
            cache_dir: Directory to store cache files
            default_ttl: Default time-to-live in seconds (1 hour)
        """
        self.cache_dir = cache_dir
        self.default_ttl = default_ttl
        
        # Create cache directory
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_key(self, namespace: str, key: str) -> str:
        """Generate cache file key"""
        # Create hash for the key
        hash_obj = hashlib.sha256(f"{namespace}:{key}".encode())
        return f"{namespace}_{hash_obj.hexdigest()}.json"
    
    def _get_cache_path(self, namespace: str, key: str) -> str:
        """Get full path to cache file"""
        filename = self._get_cache_key(namespace, key)
        return os.path.join(self.cache_dir, filename)
    
    def get(self, namespace: str, key: str) -> Optional[Any]:
        """
        Get cached data
        
        Args:
            namespace: Cache namespace (e.g., 'openalex', 'ai')
            key: Cache key
            
        Returns:
            Cached data or None if not found/expired
        """
        cache_path = self._get_cache_path(namespace, key)
        
        if not os.path.exists(cache_path):
            return None
        
        try:
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)
            
            # Check expiration
            expiry = cache_data.get("expiry", 0)
            if time.time() > expiry:
                # Expired - remove it
                os.remove(cache_path)
                return None
            
            return cache_data.get("data")
            
        except (json.JSONDecodeError, IOError):
            return None
    
    def set(self, namespace: str, key: str, data: Any, ttl: Optional[int] = None) -> None:
        """
        Set cached data
        
        Args:
            namespace: Cache namespace
            key: Cache key
            data: Data to cache
            ttl: Time-to-live in seconds (optional, uses default)
        """
        ttl = ttl or self.default_ttl
        expiry = time.time() + ttl
        
        cache_data = {
            "data": data,
            "expiry": expiry,
            "created": datetime.now().isoformat(),
            "namespace": namespace,
            "key": key
        }
        
        cache_path = self._get_cache_path(namespace, key)
        
        try:
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except IOError as e:
            logging.getLogger(__name__).warning('Cache write failed for %s/%s: %s', namespace, key, e)
    
    def exists(self, namespace: str, key: str) -> bool:
        """Check if key exists and is not expired"""
        return self.get(namespace, key) is not None
    
    def delete(self, namespace: str, key: str) -> None:
        """Delete cached data"""
        cache_path = self._get_cache_path(namespace, key)
        if os.path.exists(cache_path):
            os.remove(cache_path)
    
    def clear(self, namespace: Optional[str] = None) -> None:
        """
        Clear all cached data
        
        Args:
            namespace: Optional namespace to clear (None = clear all)
        """
        if not os.path.exists(self.cache_dir):
            return
        
        for filename in os.listdir(self.cache_dir):
            if namespace and not filename.startswith(namespace):
                continue
            
            filepath = os.path.join(self.cache_dir, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
    
    def cleanup(self) -> None:
        """Remove expired cache entries"""
        if not os.path.exists(self.cache_dir):
            return
        
        now = time.time()
        for filename in os.listdir(self.cache_dir):
            filepath = os.path.join(self.cache_dir, filename)
            
            if not os.path.isfile(filepath):
                continue
            
            try:
                with open(filepath, 'r') as f:
                    cache_data = json.load(f)
                
                expiry = cache_data.get("expiry", 0)
                if now > expiry:
                    os.remove(filepath)
            except (json.JSONDecodeError, IOError, KeyError):
                # Remove corrupted files
                os.remove(filepath)


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

# Global cache instance
cache = Cache(default_ttl=3600)  # 1 hour default


def get_cached_works(orcid: str) -> Optional[list[dict]]:
    """Get cached works for an ORCID"""
    return cache.get("openalex", f"works_{orcid}")


def set_cached_works(orcid: str, works: list[dict], ttl: int = 3600) -> None:
    """Cache works for an ORCID"""
    cache.set("openalex", f"works_{orcid}", works, ttl)


def get_cached_author(orcid: str) -> Optional[dict]:
    """Get cached author data"""
    return cache.get("openalex", f"author_{orcid}")


def set_cached_author(orcid: str, author_data: dict, ttl: int = 86400) -> None:
    """Cache author data (24 hour TTL)"""
    cache.set("openalex", f"author_{orcid}", author_data, ttl)


# Clean up old cache on import
cache.cleanup()
