from app.core.redis_client import get_redis_client


class CacheService:
    test_key = "digital_employee:data_platform:test"
    test_value = "redis-ok"

    def write_test_key(self) -> dict:
        client = get_redis_client()
        client.set(self.test_key, self.test_value, ttl_seconds=3600)
        return {"key": self.test_key, "value": self.test_value}

    def read_test_key(self) -> dict:
        client = get_redis_client()
        value = client.get(self.test_key)
        return {"key": self.test_key, "value": value}
