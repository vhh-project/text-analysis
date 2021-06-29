FROM python:3.7-slim

ARG build_env=prod
ARG SCRIPT_NAME=/
ENV BUILD_ENVIRONMENT=$build_env
ENV SCRIPT_NAME=$SCRIPT_NAME

RUN apt-get update --fix-missing && \
    apt-get install -y build-essential python3-dev default-libmysqlclient-dev && \
    rm -rf /var/lib/apt/lists/*

EXPOSE 8000

ADD requirements_freeze/requirements_frozen.$build_env.txt .
RUN pip install --no-cache-dir -r requirements_frozen.$build_env.txt
ENV DEBUG=False

COPY generic-ner-ui /app/generic-ner-ui/
WORKDIR /app/generic-ner-ui

RUN if [ $build_env = "prod" ]; \
    then \
        pip install . -U --no-deps; \
    else \
        pip install .[${build_env}] -U --no-deps; \
    fi
RUN python manage.py collectstatic --noinput
RUN mkdir /app/generic-ner-ui/generic_ner_ui/staticfiles && chmod -R 0777 /app/generic-ner-ui/generic_ner_ui/staticfiles
RUN mkdir /app/generic-ner-ui/generic_ner_ui/migrations && chmod -R 0777 /app/generic-ner-ui/generic_ner_ui/migrations

CMD python manage.py makemigrations generic_ner_ui && python manage.py migrate && gunicorn generic_ner_ui.wsgi -b 0.0.0.0:8000 --keep-alive 20

# docker run -it --rm -p 8000:8000 generic-ner-ui