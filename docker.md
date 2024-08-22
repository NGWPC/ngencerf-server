# Using ngenCERF-server Dockerfile

## Requirements

To build and run the ngenCERF-server container, you will need the following software installed and running on your system:
- Docker
- PostgreSQL (recommend version 16), listening on port 5432

## Building ngenCERF-server Container

To build the ngenCERF-server container, execute the following command:
```
docker build --add-host host.docker.internal:host-gateway --tag=ngencerf-server .
```
This will load all necessary static data in the database and create a Django superuser account admin with the password admin.

## Running ngenCERF-server Container

To run the ngenCERF-server container, execute the following command:
```
docker run -it  --add-host host.docker.internal:host-gateway -p 8000:8000 ngencerf-server
```
This will give you an instance of the ngenCERF-server application running on your system listening on local port 8000.

## Future Improvements 

- Install necessary packages from ngen-cal repo.
- Data mounts for ngen-cal-work directory
- Docker compose project that launces all necessary containers simultaneously.

