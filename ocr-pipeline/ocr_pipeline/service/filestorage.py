import mimetypes

from loguru import logger
import s3fs


class FileStorage(s3fs.S3FileSystem):

    def __init__(self, host, port, key, secret):
        endpoint = f'http://{host}:{port}'
        self.storage_options = {
            "key": key,
            "secret": secret,
            "client_kwargs": {"endpoint_url": endpoint}
        }
        super().__init__(**self.storage_options)
        logger.info("Setup {}", self)

    def put(self, filename, path, **kwargs):
        """Override super function, auto setting content type"""
        content_type, _encoding = mimetypes.guess_type(filename)
        super().put(filename, path, ContentType=content_type, **kwargs)

    def __repr__(self):
        key = self.storage_options.get("key")
        secret = f"{self.storage_options.get('secret')[:3]}***"
        ep = self.storage_options.get("client_kwargs").get("endpoint_url")
        return (
            f"<FileStorage key='{key}' secret='{secret}' endpoint='{ep}'>"
        )

    @classmethod
    def from_config(cls, config):
        return cls(
            config.minio.host,
            config.minio.port,
            config.minio.key,
            config.minio.secret
        )
