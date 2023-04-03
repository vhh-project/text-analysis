# BOW - Batch OCR Webservice


### quick launch
1. start all containers
```bash
BOW_ARCH=$(arch)
docker-compose -f docker-compose.$BOW_ARCH.yml up --build
# or run:
docker-compose -f docker-compose.$BOW_ARCH.yml up --build rabbitmq postgres database minio keycloak generic-ner-ui ocr-pipeline
```
2. http://localhost:8080/auth/
   1. create a test user
   2. copy/paste public key & into *CONFIG_KEYCLOAK_PUBLIC_KEY* in *docker-compose.yml* 
3. restart containers
4. http://localhost:8000/bow/main/
5. Welcome to BOW 👋


### platform support
set system architecture variable to chose arch related yaml file:
```bash
BOW_ARCH=$(arch)
# x86_64 / arm64
```


### sub services
| service                 | description                                                                      |
| ----------------------- | -------------------------------------------------------------------------------- |
| generic-ner-ui          | BOW user interface for data upload and retrieval, push tasks into rabbitmq queue |
| keycloak                | user management for generic-ner-ui                                               |
| minio                   | object storage, retrieve data from ocr_pipeline, provide data to generic-ner-ui  |
| rabbitmq                | manage tasks from generic-ner-ui                                                 |
| ocr_pipeline            | process tasks from rabbitmq queue; read/write data from minio; OCR images        |
| mysql                   | stores generic-ner-ui task metadata                                              |
| postgres                | stores keycloak users                                                            |


<div style="page-break-before:always"></div>


# Server Configuration

### update & run BOW on Server via ssh
```bash
### BOW – DBS (5 containers)
tmux a -t cli-session
cd /home/project/generic-ner-ui-umbrella
git pull
docker-compose -f docker-compose.x86_64.yml up rabbitmq postgres database minio keycloak

### BOW – UI (1 container)
tmux a -t ui-session
cd /home/project/generic-ner-ui-umbrella/generic-ner-ui/
git pull
docker-compose -f docker-compose.x86_64.yml up generic-ner-ui

### BOW – OCR (1 container)
tmux a -t ocr-session
cd /home/project/generic-ner-ui-umbrella/ocr-pipeline
git pull
docker-compose -f docker-compose.x86_64.yml up ocr-pipeline
```


### git authenticate on server
```bash
git pull
# _name_ & _token_
# login enter token git: settings > developer > token classic > (re)generate > paste
```


### three tmux sessions are running BOW
```bash
## create new session
tmux new -s cli-session
tmux new -s ui-session
tmux new -s ocr-session

## start sample-server on session
cd /data/project/service_example
python3 -m http.server --bind localhost 8080

## attach
tmux a -t cli-session
tmux a -t ui-session
tmux a -t ocr-session

## list
tmux ls

## exit tmux
Ctrl+b d or Ctrl+b :detach
```

***
