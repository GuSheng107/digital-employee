"""RabbitMQ 共享原生 AMQP 客户端模块。"""

from rabbitmq_client.client import ConsumerResult, RabbitMQClient, get_rabbitmq_client

__all__ = [
    "ConsumerResult",
    "RabbitMQClient",
    "get_rabbitmq_client",
]
