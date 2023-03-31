FROM arm64v8/python:3.7-slim

ENV OMP_THREAD_LIMIT=4
ARG build_env=prod
ENV BUILD_ENVIRONMENT=$build_env

RUN apt-get update && apt-get install -y software-properties-common && add-apt-repository -y ppa:alex-p/tesseract-ocr
RUN apt-get install -y libjpeg-dev libsm6 libxext6 libgl1 libxrender-dev wget imagemagick imagemagick-doc ghostscript tesseract-ocr libtesseract-dev libleptonica-dev pkg-config libgtk2.0-dev libenchant-2-2 locales locales-all git poppler-utils
RUN apt-get install python-dev -y

ENV LC_ALL=C
COPY policy.xml /etc/ImageMagick-6/policy.xml

WORKDIR /home/work

ADD FreeSans.ttf /home/work/ocr/

# fetch tesseract models from git
ADD fetch_tess_traindata.sh ./
RUN bash fetch_tess_traindata.sh

#==20.2
RUN pip install --upgrade pip 
RUN pip install --upgrade pip setuptools wheel

ADD requirements_freeze/requirements_frozen.$build_env.txt .
# --no-cache-dir
RUN pip install -r requirements_frozen.$build_env.txt 

# pyenchant language dictionaries
RUN apt-get install -y hunspell-de-de hunspell-de-at myspell-fr myspell-ru

WORKDIR /app

COPY symspell_dictionaries ./symspell_dictionaries
COPY setup.py config.yaml ./
COPY ocr_pipeline ./ocr_pipeline

RUN if [ $build_env = "prod" ]; \
    then \
        pip install -e . --no-deps; \
    else \
        pip install -e .[${build_env}] --no-deps; \
    fi

CMD pipeline