FROM rockylinux:8

# Install runtime dependencies
RUN set -eux && \
    dnf install -y yum-utils epel-release && \
    dnf install -y \
        file \
        findutils \
        jq \
        libpq \
        git \
        openssl openssl-devel \
        python3.11 python3.11-libs python3.11-devel \
        python3.11-pip \
        python3.11-setuptools && \
    dnf clean all

# Configure Git with the GitLab token using BuildKit secret mount
RUN --mount=type=secret,id=gitlab_token \
    set -eux && \
    git config --global url."https://oauth2:$(cat /run/secrets/gitlab_token)@gitlab.sh.nextgenwaterprediction.com/".insteadOf "https://gitlab.sh.nextgenwaterprediction.com/"

# Install Python virtual environment
ENV VIRTUAL_ENV=/ngencerf/ngencerf-python
ENV PATH=${VIRTUAL_ENV}/bin:${PATH}

RUN --mount=type=cache,target=/root/.cache/pip,id=pip-cache \
    set -eux && \
    python3.11 -m venv ${VIRTUAL_ENV} && \
    # Lock numpy and netcdf4 versions so t-route doesn't break
    pip3 install --upgrade pip "numpy==1.26.4" "pandas~=2.2.2"

WORKDIR /ngencerf/ngencerf-server/

# Pre-copy requirements for better caching
COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip,id=pip-cache \
    set -eux && \
    pip3 install -r requirements.txt && \
    rm -f requirements.txt

ARG CREATE_INPUT_TAG
ARG RUN_SWE_TAG
ARG CACHE_BUST=1
# Configure Git with the GitLab token using BuildKit secret mount
RUN --mount=type=secret,id=gitlab_token \
    set -eux && \
    echo $CACHE_BUST && pip3 install "git+https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/ngen-cal.git@${CREATE_INPUT_TAG}#egg=createInput&subdirectory=python/createInput" && \
    echo $CACHE_BUST && pip3 install "git+https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/ngen-forcing.git@${RUN_SWE_TAG}#egg=swe_processing&subdirectory=swe_processing" && \
    rm -f /root/.gitconfig && \
    pip3 cache purge

COPY cli /ngencerf/ngencerf-server/cli

# Build CLI executable in cli/dist
RUN cli/build_cli.sh

# Should parallel similar functionality in the run_cerf.sh
COPY .git .git

RUN set -eux && \
    # Get the remote URL from Git configuration
    repo_url=$(git config --get remote.origin.url) && \
    # Extract the repo name (everything after the last slash) and remove any trailing .git
    key=${repo_url##*/} && \
    key=${key%.git} && \
    # Construct the file path using the derived key
    GIT_INFO_PATH="${key}_git_info.json" && \
    jq -n \
      --arg commit_hash "$(git rev-parse HEAD)" \
      --arg branch "$(git rev-parse --abbrev-ref HEAD)" \
      --arg tags "$(git tag --points-at HEAD | tr '\n' ' ')" \
      --arg author "$(git log -1 --pretty=format:'%an')" \
      --arg commit_date "$(date -u -d @$(git log -1 --pretty=format:'%ct') +'%Y-%m-%d %H:%M:%S UTC')" \
      --arg message "$(git log -1 --pretty=format:'%s' | tr '\n' ';')" \
      --arg build_date "$(date -u +'%Y-%m-%d %H:%M:%S UTC')" \
      "{\"$key\": {commit_hash: \$commit_hash, branch: \$branch, tags: \$tags, author: \$author, commit_date: \$commit_date, message: \$message, build_date: \$build_date}}" \
      > $GIT_INFO_PATH

# Copy application code
COPY . /ngencerf/ngencerf-server/

# Remove .git directory
RUN rm -rf .git

# Copy additional configuration files
COPY ./cerfserver-docker.env /ngencerf/ngencerf-server/cerfserver.env
COPY ./cerfServer/__.env-docker-dev /ngencerf/ngencerf-server/cerfServer/.env
COPY ./cerfServer/__local_settings.py /ngencerf/ngencerf-server/cerfServer/local_settings.py

# Set the entry point and expose the application port
ENTRYPOINT [ "/ngencerf/ngencerf-server/runCerf.sh" ]
EXPOSE 8000
