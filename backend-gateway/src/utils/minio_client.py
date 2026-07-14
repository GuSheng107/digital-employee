# -*- coding: utf-8 -*-
"""MinIO 统一对象存储工具。

封装 MinIO 官方 Python SDK，提供多模态媒体资源（图片、文件）的上传与下载功能。
"""

import os
from io import BytesIO
from dotenv import load_dotenv
from loguru import logger
from minio import Minio
from minio.error import S3Error

# 自动从项目根目录 .env 加载配置
load_dotenv()


class MinioClientWrapper:
    """MinIO 对象存储客户端包装器单例类。"""

    def __init__(self) -> None:
        """初始化 MinIO 包装客户端，基于环境变量读取凭证。"""
        self.endpoint: str = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
        secure_str = os.getenv("MINIO_SECURE", "false").lower()
        self.secure: bool = secure_str == "true"
        self.access_key: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self.bucket_name: str = os.getenv("MINIO_BUCKET_NAME", "file-buckets")

        self.client: Minio | None = None
        self._initialized: bool = False

    def init_client(self) -> None:
        """从环境变量懒加载初始化客户端连接并检查 Bucket 状态。"""
        if self._initialized:
            return

        try:
            logger.info("正在建立与 MinIO 对象存储的连接 (Endpoint: {})...", self.endpoint)
            self.client = Minio(
                endpoint=self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )

            # 检测并自动创建公共 Bucket 容器
            if not self.client.bucket_exists(self.bucket_name):
                logger.info("指定的存储桶 '{}' 不存在，正在自动创建...", self.bucket_name)
                self.client.make_bucket(self.bucket_name)

            self._initialized = True
            logger.info("MinIO 对象存储客户端初始化成功，已绑定存储桶: {}", self.bucket_name)
        except S3Error as exc:
            logger.error("连接 MinIO 存储发生 S3 协议错误: {}", exc)
        except Exception as exc:
            logger.error("连接 MinIO 异常，请检查配置或 MinIO 容器状态: {}", exc)

    def upload_file(
        self,
        *,
        object_name: str,
        data: BytesIO,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> str | None:
        """将二进制文件流上传到 MinIO。

        Args:
            object_name: 在存储桶中的唯一对象路径（如 feishu/20260702/uuid.png）。
            data: 文件的二进制内存流。
            length: 流的总长度（字节）。
            content_type: MIME 媒体类型。

        Returns:
            成功后返回内部可直接拉取的标准 URL。若失败返回 None。
        """
        self.init_client()
        if not self._initialized or self.client is None:
            logger.error("MinIO 客户端未初始化成功，放弃上传: {}", object_name)
            return None

        try:
            # 重设流指针到头部
            data.seek(0)
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=data,
                length=length,
                content_type=content_type,
            )

            # 组装内部标准网络 URL
            schema = "https" if self.secure else "http"
            file_url = f"{schema}://{self.endpoint}/{self.bucket_name}/{object_name}"
            logger.info("文件上传 MinIO 成功: {} -> {}", object_name, file_url)
            return file_url
        except Exception as exc:
            logger.error("上传文件到 MinIO 失败 ({}): {}", object_name, exc)
            return None

    def download_file(self, *, object_name: str) -> BytesIO | None:
        """从 MinIO 下载指定对象的二进制数据。

        Args:
            object_name: 存储桶中的对象唯一路径。

        Returns:
            文件数据的 BytesIO 流。若失败返回 None。
        """
        self.init_client()
        if not self._initialized or self.client is None:
            logger.error("MinIO 客户端未初始化成功，放弃下载: {}", object_name)
            return None

        try:
            response = self.client.get_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
            )
            # 将流读入内存，以便安全关闭 HTTP 响应连接
            try:
                data_bytes = response.read()
                return BytesIO(data_bytes)
            finally:
                response.close()
                response.release_conn()
        except Exception as exc:
            logger.error("从 MinIO 下载文件失败 ({}): {}", object_name, exc)
            return None


# 全局唯一的 MinIO 对象存储客户端包装单例
minio_client: MinioClientWrapper = MinioClientWrapper()
