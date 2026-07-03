# -*- coding: utf-8 -*-
"""RabbitMQ 异步客户端与拓扑自动构建模块。

基于 aio-pika 实现异步连接管理，在网关启动时自动声明 Exchange 和 Queue
并完成路由绑定，为三期双模路由调度提供 MQ 基础设施。
"""

import os

import aio_pika
from loguru import logger


class RabbitMQClient:
    """RabbitMQ 异步客户端单例类。

    负责连接管理、拓扑声明与消息发布。
    """

    def __init__(self) -> None:
        self.connection: aio_pika.abc.AbstractRobustConnection | None = None
        self.channel: aio_pika.abc.AbstractChannel | None = None
        self.exchange: aio_pika.abc.AbstractExchange | None = None

    async def connect_and_setup(self) -> aio_pika.abc.AbstractQueue:
        """建立长连接并声明单节点下的固定拓扑结构。

        从环境变量 RABBITMQ_URL 读取连接地址，自动声明 Topic 交换机
        和入站/出站双队列并完成路由键绑定。

        Returns:
            出站队列对象，供调用方注册消费者回调。
        """
        mq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
        self.connection = await aio_pika.connect_robust(mq_url)
        self.channel = await self.connection.channel()

        # 1. 声明 TOPIC 交换机 (durable=True 保证重启不丢失)
        self.exchange = await self.channel.declare_exchange(
            "bot.topic.exchange", aio_pika.ExchangeType.TOPIC, durable=True
        )

        # 2. 声明固定的入站和出站队列（单节点架构，禁用点号命名）
        inbound_queue = await self.channel.declare_queue(
            "q_inbound_to_agent", durable=True
        )
        await inbound_queue.bind(self.exchange, routing_key="msg.inbound.#")

        outbound_queue = await self.channel.declare_queue(
            "q_outbound_to_gateway", durable=True
        )
        await outbound_queue.bind(self.exchange, routing_key="msg.outbound.#")

        logger.info("[MQ] 单节点拓扑结构自动化构建与绑定成功")
        return outbound_queue

    async def publish(self, routing_key: str, payload_json: str) -> None:
        """安全发布消息至交换机（含状态哨兵机制）。

        Args:
            routing_key: 消息路由键，如 msg.inbound.feishu.bot_001。
            payload_json: 序列化后的 JSON 消息体字符串。

        Raises:
            RuntimeError: 客户端尚未初始化时抛出。
        """
        if not self.exchange:
            raise RuntimeError("[MQ] 客户端尚未初始化，无法发布消息")

        message = aio_pika.Message(
            body=payload_json.encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self.exchange.publish(message, routing_key=routing_key)

    async def close(self) -> None:
        """安全关闭 RabbitMQ 连接。"""
        if self.connection is not None:
            await self.connection.close()
            logger.info("[MQ] RabbitMQ 连接已安全关闭")


# 全局唯一的 RabbitMQ 客户端单例
mq_client: RabbitMQClient = RabbitMQClient()
