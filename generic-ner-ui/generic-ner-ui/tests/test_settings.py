from generic_ner_ui.settings import *  # noqa: F401, F403

DATABASES = {
    'default': {
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
        'TEST': {}
    }
}
