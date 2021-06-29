FROM python:3.7-slim

ARG build_env=prod
ENV BUILD_ENVIRONMENT=$build_env

RUN apt-get update --fix-missing && \
    apt-get install -y build-essential python3-dev default-libmysqlclient-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY generic-ner-ui/setup.py generic-ner-ui/manage.py ./

RUN if [ $build_env = "prod" ]; \
    then \
        pip install -e . ; \
    else \
        pip install -e .[${build_env}] ; \
    fi

CMD pip freeze --exclude-editable > requirements_freeze/requirements_frozen.${BUILD_ENVIRONMENT}.txt