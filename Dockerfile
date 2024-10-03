FROM registry.sh.nextgenwaterprediction.com/infrastructure/rockylinux/rockylinux:latest


# runtime dependencies
RUN set -eux; \
    dnf install -y yum-utils ; \
    dnf config-manager --set-enabled crb; \
    dnf install -y epel-release; \
    dnf install -y \
        file \
        findutils \
        jq \
        libpq \
        git \
        openssl openssl-devel \
        python3.11 python3.11-libs python3.11-devel \
        python3.11-pip \
        python3.11-setuptools \
        which \
    ; \
    dnf clean all

RUN --mount=type=secret,id=gitlab_token \
    set -eux; \
    \
    git config --global url."https://oauth2:$(cat /run/secrets/gitlab_token)@gitlab.sh.nextgenwaterprediction.com/".insteadOf "https://gitlab.sh.nextgenwaterprediction.com/"

ENV VIRTUAL_ENV=/ngencerf/ngencerf-python
RUN set -eux; \
	\
    python3.11 -m venv ${VIRTUAL_ENV}
ENV PATH=${VIRTUAL_ENV}/bin:${PATH}

WORKDIR /ngencerf/ngencerf-server/
COPY requirements.txt /ngencerf/ngencerf-server/
RUN set -eux; \
    pip3 install -r requirements.txt; \
# Lock numpy and netcdf4 versions so t-route doesn't break
    pip3 install "numpy==1.26.4" "pandas~=2.2.2" ; \
    pip3 cache purge ; \
    rm --force /root/.gitconfig

COPY . /ngencerf/ngencerf-server/
COPY ./cerfserver-docker.env /ngencerf/ngencerf-server/cerfserver.env
COPY ./cerfServer/__.env-docker /ngencerf/ngencerf-server/cerfServer/.env
COPY ./cerfServer/__local_settings.py /ngencerf/ngencerf-server/cerfServer/local_settings.py

RUN --mount=type=secret,id=aws_token \
    set -eux; \
    \
    mkdir --parents ~/.aws/ ; \
    cp /run/secrets/aws_token ~/.aws/credentials 

ENTRYPOINT [ "/ngencerf/ngencerf-server/runCerf.sh" ] 
EXPOSE 8000
