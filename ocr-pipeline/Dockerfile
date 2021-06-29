FROM python:3.7

ENV OMP_THREAD_LIMIT=1
ARG build_env=prod
ENV BUILD_ENVIRONMENT=$build_env

RUN apt-get update && apt-get install -y software-properties-common && add-apt-repository -y ppa:alex-p/tesseract-ocr
RUN apt-get install -y libsm6 libxext6 libxrender-dev wget imagemagick imagemagick-doc ghostscript tesseract-ocr libtesseract-dev libleptonica-dev pkg-config libenchant1c2a locales locales-all openjdk-11-jdk maven git

ENV LC_ALL=C
COPY policy.xml /etc/ImageMagick-6/policy.xml

WORKDIR /home/work

ADD FreeSans.ttf /home/work/ocr/

ADD SUTime /home/work/ocr/
RUN mvn -f /home/work/ocr/sutime_dependencies dependency:copy-dependencies -DoutputDirectory=./jars
ADD fetch_tess_traindata.sh ./

# git - fetch tesseract models
RUN bash fetch_tess_traindata.sh

RUN pip install --upgrade pip==20.2

ADD requirements_freeze/requirements_frozen.$build_env.txt .
RUN pip install --no-cache-dir -r requirements_frozen.$build_env.txt

# pyenchant language dictionaries
RUN apt-get install -y myspell-de-de myspell-de-at myspell-fr myspell-ru

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