# Using ngenCERF-server Dockerfile

## Requirements

To build and run the ngenCERF-server container, you will need the following software installed and running on your system:
- Docker Engine
- Docker Compose 

You will also need a file containing your NGWPC gitlab Personal Access Token (PAT) written at ~/.gitlab_token.

This will also create directories to persist data for the database and a directory to store initialization data for the ngencerf-server applicatoin. Your directory structure should look like this:
```
$ tree -L 1
.
├── data
└── ngencerf-server
```

## Running ngenCERF-server

It is recommended to use the [ngencerf-docker](https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/ngencerf-docker/) project to run the full ngenCERF application stack at once. However, if you would like to just run the back-end services in isolation, execute the following command:
```
docker compose up
```

This will start instances of the following:
- ngencerf-server, running at the address http://localhost:8000
- PostgreSQL, running at the address http://localhost:5432

## Troubleshooting

### Forcing static data loads

By default, the first time this container is run it will perform a load of all the necessary static data into the database. When complete it will write the file `../data/.ngencerf-init/.load_static`. You can delete this file to force the data to be reloaded the next time your start the application.

### Executing custom commands in a running container

If there is a need to connect to a container to issue commands from a terminal, perform the following steps:
1. Get a list of the running containers by executing the following command:
```
docker container ls
```
2. Attach a terminal to that container:
```
docker exec -it <container_id> bash
```
3. Execute any needed commands from that terminal.
4. Issue the following command to disconnect:
```
exit
```

## Future Improvements 

- Data mounts for ngen-cal-work directory
- Separate configuration to allow discrete production and development environments.

