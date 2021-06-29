import os

from everett.component import ConfigOptions, RequiredConfigMixin
from everett.ext.yamlfile import ConfigYamlEnv
from everett.manager import ConfigManager, ConfigOSEnv, ListOf

from ocr_pipeline.pipeline.pipeline_config import PipelineConfig


class AmqpConfig(RequiredConfigMixin):
    """Contains all AMQP information"""
    required_config = ConfigOptions()

    required_config.add_option(
        'url',
        parser=str,
        doc='AMQP connection str used to connect to broker.'
    )

    required_config.add_option(
        'inqueue',
        parser=str,
        doc='Name of the worker input queue.'
    )

    required_config.add_option(
        'invalidqueue',
        parser=str,
        default="adp_invalid",
        doc='Name of the worker invalid queue.'
    )

    required_config.add_option(
        'dlx',
        parser=str,
        default="dlx",
        doc='Dead letter exchange destination for queues'
    )

    def __init__(self, config):
        self.config = config.with_options(self)
        self.url = self.config('url')
        self.inqueue = self.config('inqueue')
        self.invalidqueue = self.config('invalidqueue')
        self.dlx = self.config('dlx')

    def __call__(self, *args, **kwargs):
        return self.config(*args, **kwargs)


class MinioConfig(RequiredConfigMixin):
    """Contains all MINIO information"""
    required_config = ConfigOptions()

    required_config.add_option(
        'host',
        parser=str,
        default="localhost",
        doc='Host of the minio installation'
    )

    required_config.add_option(
        'port',
        parser=int,
        default="9000",
        doc='Port of the minio installation'
    )

    required_config.add_option(
        'key',
        parser=str,
        default="abcdACCESS",
        doc='Key used to connect to minio'
    )

    required_config.add_option(
        'secret',
        parser=str,
        default="abcdSECRET",
        doc='Secret used to connect to minio'
    )

    def __init__(self, config):
        self.config = config.with_options(self)
        self.host = self.config('host')
        self.port = self.config('port')
        self.key = self.config('key')
        self.secret = self.config('secret')

    def __call__(self, *args, **kwargs):
        return self.config(*args, **kwargs)


class Config(object):
    def __init__(self):
        self.manager = ConfigManager(
            environments=[
                ConfigOSEnv(),
                ConfigYamlEnv([
                    os.environ.get('CONFIG_YAML'),
                    './config.yaml',
                    './config.yml',
                    '/etc/config.yaml'
                    '/etc/config.yml'
                ]),
            ],
        ).with_namespace('config')
        self.amqp = AmqpConfig(self.manager.with_namespace('amqp'))
        self.minio = MinioConfig(self.manager.with_namespace('minio'))
        self.pipeline = PipelineConfig(self.manager.with_namespace('pipeline'))

