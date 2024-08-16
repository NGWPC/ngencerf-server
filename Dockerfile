## TODO: replace with base image created under NGWPC-3223 ##
## see: https://jira.nextgenwaterprediction.com/browse/NGWPC-3223
FROM rockylinux:9

## FIXME: Replace installation and build of FOSS dependencies wiith a base image. ##

# runtime dependencies
RUN set -eux; \
    dnf install -y yum-utils ; \
    dnf config-manager --set-enabled crb; \
    dnf install -y epel-release; \
    dnf install -y \
        file \
        findutils \
        libpq \
        git \
        openssl openssl-devel \
        python3.11 python3.11-libs python3.11-devel \
        python3.11-pip \
        python3.11-setuptools \
        which \ 
    ; \
    dnf clean all

COPY . /ngencerf/ngencerf-server/

ENV VIRTUAL_ENV=/ngencerf/ngencerf-python
RUN set -eux; \
	\
    python3.11 -m venv ${VIRTUAL_ENV}
ENV PATH=${VIRTUAL_ENV}/bin:${PATH}

WORKDIR /ngencerf/ngencerf-server/

RUN set -eux; \
	\
    pip3 install -r requirements.txt; \
# Lock numpy and netcdf4 versions so t-route doesn't break
    pip3 install "numpy==1.26.4" "pandas~=2.2.2" ; \
    pip3 cache purge

COPY ./cerfserver-docker.env /ngencerf/ngencerf-server/cerfserver.env
COPY ./cerfServer/__.env-docker /ngencerf/ngencerf-server/cerfServer/.env
COPY ./cerfServer/__local_settings.py /ngencerf/ngencerf-server/cerfServer/local_settings.py

## perform server init
RUN set -eux; \
	\
    python3 manage.py migrate; \
    ## TODO: use Docker secrets to create admin account with password
    python3 manage.py createsuperuser_docker --noinput --username admin --password admin --email admin@nextgenwaterprediction.com; \
    python3 manage.py init_sql; \
    python3 manage.py init_gages

WORKDIR /

ENTRYPOINT [ "/ngencerf/ngencerf-server/runCerf.sh" ] 

