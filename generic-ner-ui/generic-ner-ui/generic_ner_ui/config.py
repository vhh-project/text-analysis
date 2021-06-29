import os

from everett.component import ConfigOptions, RequiredConfigMixin
from everett.ext.yamlfile import ConfigYamlEnv
from everett.manager import ConfigManager, ConfigOSEnv, ListOf


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

    required_config.add_option(
        'upload_bucket',
        parser=str,
        default='upload',
        doc='The bucket documents are uploaded to per default'
    )

    def __init__(self, config):
        self.config = config.with_options(self)
        self.host = self.config('host')
        self.port = self.config('port')
        self.key = self.config('key')
        self.secret = self.config('secret')
        self.upload_bucket = self.config('upload_bucket')

    def __call__(self, *args, **kwargs):
        return self.config(*args, **kwargs)


class DatabaseConfig(RequiredConfigMixin):
    required_config = ConfigOptions()

    required_config.add_option(
        'host',
        parser=str,
        default='localhost',
        doc='The host url of the database'
    )

    required_config.add_option(
        'port',
        parser=str,
        default="3308",
        doc='The database port'
    )

    required_config.add_option(
        'user',
        parser=str,
        default='root',
        doc='The database user'
    )

    required_config.add_option(
        'password',
        parser=str,
        default="root",
        doc='The database password'
    )

    required_config.add_option(
        'schema',
        parser=str,
        default="GEN_NER_UI",
        doc='The database schema'
    )

    def __init__(self, config):
        self.config = config.with_options(self)

        self.host = self.config("host")
        self.port = self.config("port")
        self.user = self.config("user")
        self.password = self.config("password")
        self.schema = self.config("schema")

    def __call__(self, *args, **kwargs):
        return self.config(*args, **kwargs)


class KeycloakConfig(RequiredConfigMixin):
    """Contains all KEYCLOAK information"""
    required_config = ConfigOptions()

    required_config.add_option(
        'key',
        parser=str,
        default="gen-ner-ui",
        doc='The key of the client'
    )

    required_config.add_option(
        'secret',
        parser=str,
        default="0755b389-cbb6-4d41-8d03-cc79470daf7b",
        doc='The secret verification of the client'
    )

    required_config.add_option(
        'public_key',
        parser=str,
        default="MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA7KrptJVTVYAv7iKqnGCi13W0U3yKhLkGuLqtbF71jaWqJR+MTPt5JbEXrlFup84TMDbC4vPr9Hl+18LxvL4QXLN1uItpi2vh0WGWRwmgJ9thNUob9liMc2G1Kdnn86JG8uEDn2/mhEpsmFxWOJf51q3cH7KGvSasrfV+jYhT6jf9snajoPDQyiYnLDdyyHtjpVRMu3x/tp0ynUMVrJlfouaI65yZiiJgAxVpeJRwghDTQHDqAgL7A7hUu8OAkSIRg77AKkPiGAjEkvEb0gYfWq54uMVvsCLteNttmFXdkd9AzG2Rwqy/FVFKKzvGjhJj3qMVI4r72IrAceapjmEzKQIDAQAB",  # noqa: E501
        doc='The public key of the client'
    )

    required_config.add_option(
        'id_key',
        parser=str,
        default="username",
        doc='The key used to identify the user'
    )

    required_config.add_option(
        'realm',
        parser=str,
        default="gen-ner-ui",
        doc='The realm of the keycloak'
    )

    required_config.add_option(
        'host',
        parser=str,
        default='localhost:8080',
        doc='The host url of the keycloak'
    )

    required_config.add_option(
        'access_host',
        parser=str,
        default='',
        doc='The access url via network-setup (e.g. docker network)'
    )

    required_config.add_option(
        'protocol',
        parser=str,
        default="http",
        doc='The message protocol of the keycloak'
    )

    def __init__(self, config):
        self.config = config.with_options(self)
        self.key = self.config('key')
        self.secret = self.config('secret')
        self.public_key = self.config('public_key')
        self.id_key = self.config('id_key')
        self.host = self.config('host')
        self.access_host = self.config('access_host')
        self.realm = self.config('realm')
        self.protocol = self.config('protocol')

    def __call__(self, *args, **kwargs):
        return self.config(*args, **kwargs)


class AmqpConfig(RequiredConfigMixin):
    """Contains all AMQP information"""
    required_config = ConfigOptions()

    required_config.add_option(
        'url',
        parser=str,
        doc='AMQP connection str used to connect to broker.',
        default='amqp://amqp_user:amqp_pass@localhost:5672/nerui?heartbeat=30'
    )

    def __init__(self, config):
        self.config = config.with_options(self)
        self.url = self.config('url')

    def __call__(self, *args, **kwargs):
        return self.config(*args, **kwargs)


class ImageConfig(RequiredConfigMixin):
    """Contains all AMQP information"""
    required_config = ConfigOptions()

    required_config.add_option(
        'width',
        parser=int,
        doc='width the images in the view get resized to',
        default='1200'
    )

    required_config.add_option(
        'height',
        parser=int,
        doc='height the images in the view get resized to',
        default='1200'
    )

    def __init__(self, config):
        self.config = config.with_options(self)
        self.width = self.config('width')
        self.height = self.config('height')

    def __call__(self, *args, **kwargs):
        return self.config(*args, **kwargs)


class PipelineConfig(RequiredConfigMixin):
    required_config = ConfigOptions()

    required_config.add_option(
        'queue_name',
        parser=str,
        default="ocr_pipeline",
        doc='The name of the rabbitmq queue'
    )

    required_config.add_option(
        'name',
        parser=str,
        default="ocr_pipeline",
        doc="The display name of the pipeline"
    )

    required_config.add_option(
        'depends_on',
        parser=ListOf(str),
        default="",
        doc="Describe what inputs are required from other pipelines"
    )

    required_config.add_option(
        'return_pages',
        parser=bool,
        default="True",
        doc="Determines whether the pipeline splits a document into pages"
    )

    def __init__(self, config):
        self.config = config.with_options(self)
        self.queue_name = self.config('queue_name')
        self.name = self.config('name')
        self.depends_on = self.config('depends_on')
        self.return_pages = self.config('return_pages')

    def __call__(self, *args, **kwargs):
        return self.config(*args, **kwargs)


class PipelinesConfig(RequiredConfigMixin):
    required_config = ConfigOptions()

    required_config.add_option(
        'count',
        parser=int,
        doc='The count of pipelines to be used',
        default="1"
    )

    required_config.add_option(
        'return_last',
        parser=bool,
        doc='determines weather only the last pipeline result should be used',
        default="True"
    )

    def __init__(self, config):
        self.config = config.with_options(self)
        self.count = self.config('count')
        self.return_last = self.config('return_last')
        self.pipelines = [PipelineConfig(self.config.with_namespace(f"P{i}"))
                          for i in range(self.count)]

    def __call__(self, *args, **kwargs):
        return self.config(*args, **kwargs)


class EntityGroupConfig(RequiredConfigMixin):
    required_config = ConfigOptions()

    required_config.add_option(
        'name',
        parser=str,
        default="Organisations and other",
        doc="The display name of the entity group"
    )

    required_config.add_option(
        'entities',
        parser=ListOf(str),
        default="ORG,MISC",
        doc="Describe what inputs are required from other pipelines"
    )

    def __init__(self, config):
        self.config = config.with_options(self)
        self.name = self.config('name')
        self.entities = self.config('entities')

    def __call__(self, *args, **kwargs):
        return self.config(*args, **kwargs)


class EntityGroupsConfig(RequiredConfigMixin):
    required_config = ConfigOptions()

    required_config.add_option(
        'count',
        parser=int,
        doc='The count of entity-groups to be used',
        default="1"
    )

    def __init__(self, config):
        self.config = config.with_options(self)
        self.count = self.config('count')
        self.groups = [EntityGroupConfig(self.config.with_namespace(f"E{i}"))
                       for i in range(self.count)]

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
            ]).with_namespace('config')
        self.minio = MinioConfig(self.manager.with_namespace('minio'))
        self.amqp = AmqpConfig(self.manager.with_namespace('amqp'))
        self.keycloak = KeycloakConfig(self.manager.with_namespace('keycloak'))
        self.database = DatabaseConfig(self.manager.with_namespace('database'))
        self.pipelines = PipelinesConfig(self.manager
                                         .with_namespace('pipelines'))
        self.entitygroups = EntityGroupsConfig(self.manager
                                               .with_namespace('entitygroups'))
        self.image = ImageConfig(self.manager.with_namespace('image'))
