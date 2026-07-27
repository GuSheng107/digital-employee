from app.core.redis_client import get_redis_client


class CacheService:
    """Redis 缓存业务编排层。

    封装健康检查用测试键的写入与读取逻辑。
    """

    test_key = "digital_employee:data_platform:test"
    test_value = "redis-ok"

    def write_test_key(self) -> dict:
        """写入测试键，TTL 1 小时。

        Returns:
            写入的键名与对应值。
        """
        client = get_redis_client()
        client.set(self.test_key, self.test_value, ttl_seconds=3600)
        return {"key": self.test_key, "value": self.test_value}

    def read_test_key(self) -> dict:
        """读取测试键当前值。

        Returns:
            键名与读取到的值（键不存在时为 None）。
        """
        client = get_redis_client()
        value = client.get(self.test_key)
        return {"key": self.test_key, "value": value}
