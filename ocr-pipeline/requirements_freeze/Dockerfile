FROM python:3.7

ARG build_env=prod
ENV BUILD_ENVIRONMENT=$build_env

RUN apt-get update && apt-get install -y software-properties-common && add-apt-repository -y ppa:alex-p/tesseract-ocr
RUN apt-get install -y libsm6 libxext6 libxrender-dev wget imagemagick imagemagick-doc ghostscript tesseract-ocr libtesseract-dev libleptonica-dev pkg-config libenchant1c2a locales locales-all openjdk-11-jdk maven git

ENV LC_ALL=C
COPY policy.xml /etc/ImageMagick-6/policy.xml

WORKDIR /home/work

RUN pip install --upgrade pip==20.2

# Set the working directory to /app
WORKDIR /app

COPY setup.py ./

RUN if [ $build_env = "prod" ]; \
    then \
        pip install -e . ; \
    else \
        pip install -e .[${build_env}] ; \
    fi

CMD pip freeze --exclude-editable > requirements_freeze/requirements_frozen.${BUILD_ENVIRONMENT}.txt

# usage: docker-compose -f requirements_freeze/docker-compose.yml up --build