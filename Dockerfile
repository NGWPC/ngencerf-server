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

# Install Python virtual environment
ENV VIRTUAL_ENV=/ngencerf/ngencerf-python
ENV PATH=${VIRTUAL_ENV}/bin:${PATH}

RUN --mount=type=cache,target=/root/.cache/pip,id=pip-cache \
    set -eux && \
    python3.11 -m venv ${VIRTUAL_ENV}

WORKDIR /ngencerf/ngencerf-server/

# Pre-copy requirements for better caching
COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip,id=pip-cache \
    set -eux && \
    pip3 install --upgrade pip && \
    pip3 install -r requirements.txt && \
    rm -f requirements.txt

ARG MSWM_ORG=NGWPC
ARG MSWM_TAG=development

ARG NGEN_FORCING_ORG=NGWPC
ARG NGEN_FORCING_TAG=development

ARG CACHE_BUST=1
RUN set -eux && \
    echo $CACHE_BUST && pip3 install "git+https://github.com/${MSWM_ORG}/nwm-msw-mgr.git@${MSWM_TAG}#egg=mswm" && \
    echo $CACHE_BUST && pip3 install "git+https://github.com/${NGEN_FORCING_ORG}/ngen-forcing.git@${NGEN_FORCING_TAG}#egg=swe_processing&subdirectory=swe_processing" && \
    pip3 cache purge

COPY cli /ngencerf/ngencerf-server/cli

# Build CLI executable in cli/dist
RUN cli/build_cli.sh

# Should parallel similar functionality in the run_cerf.sh
COPY .git .git

# Create git_info files for server and nwm-msw-mgr
RUN set -eux && \
    # ----- Server git_info -----
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
      > $GIT_INFO_PATH && \
    \
    # ----- nwm-msw-mgr git_info -----
    GIT_INFO_PATH="/ngencerf/ngencerf-server/nwm-msw-mgr_git_info.json" && \
    if [ "$MSWM_TAG" = "development" ]; then \
        tmpdir=$(mktemp -d) && \
        git clone --depth 1 --branch development https://github.com/${MSWM_ORG}/nwm-msw-mgr.git "$tmpdir" && \
        cd "$tmpdir" && \
        jq -n \
          --arg commit_hash "$(git rev-parse HEAD)" \
          --arg branch "development" \
          --arg tags "" \
          --arg author "$(git log -1 --pretty=format:'%an')" \
          --arg commit_date "$(date -u -d @$(git log -1 --pretty=format:'%ct') +'%Y-%m-%d %H:%M:%S UTC')" \
          --arg message "$(git log -1 --pretty=format:'%s' | tr '\n' ';')" \
          --arg build_date "$(date -u +'%Y-%m-%d %H:%M:%S UTC')" \
          '{"nwm-msw-mgr": {commit_hash: $commit_hash, branch: $branch, tags: $tags, author: $author, commit_date: $commit_date, message: $message, build_date: $build_date}}' \
          > "$GIT_INFO_PATH" && \
        cd / && rm -rf "$tmpdir"; \
    else \
        jq -n \
          --arg commit_hash "" \
          --arg branch "" \
          --arg tags "$MSWM_TAG" \
          --arg author "" \
          --arg commit_date "" \
          --arg message "" \
          --arg build_date "$(date -u +'%Y-%m-%d %H:%M:%S UTC')" \
          '{"nwm-msw-mgr": {commit_hash: $commit_hash, branch: $branch, tags: $tags, author: $author, commit_date: $commit_date, message: $message, build_date: $build_date}}' \
          > "$GIT_INFO_PATH"; \
    fi

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
