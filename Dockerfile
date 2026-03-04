ARG BASE_IMAGE=rockylinux:8
FROM ${BASE_IMAGE}

# OCI Metadata Arguments
ARG BASE_IMAGE
ARG BASE_IMAGE_DIGEST="unknown"
ARG BASE_IMAGE_REVISION="unknown"
ARG IMAGE_SOURCE="unknown"
ARG IMAGE_VENDOR="unknown"
ARG IMAGE_VERSION="unknown"
ARG IMAGE_REVISION="unknown"
ARG IMAGE_CREATED="unknown"

# OCI Standard Labels
LABEL org.opencontainers.image.base.name="${BASE_IMAGE}" \
    org.opencontainers.image.base.digest="${BASE_IMAGE_DIGEST}" \
    io.ngwpc.image.base.revision="${BASE_IMAGE_REVISION}" \
    org.opencontainers.image.source="${IMAGE_SOURCE}" \
    org.opencontainers.image.vendor="${IMAGE_VENDOR}" \
    org.opencontainers.image.version="${IMAGE_VERSION}" \
    org.opencontainers.image.revision="${IMAGE_REVISION}" \
    org.opencontainers.image.created="${IMAGE_CREATED}" \
    org.opencontainers.image.title="NGENCERF Server" \
    org.opencontainers.image.description="Docker image for the NGENCERF server application"

# Install build and runtime dependencies
RUN set -eux && \
    dnf install -y yum-utils epel-release && \
    dnf install -y \
        redis \
        findutils \
        file \
        jq \
        libpq \
        git \
        openssl openssl-devel \
        # Python 3.11 stack
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
ARG MSWM_REF=development

ARG DATA_ASSIMILATION_ORG=NGWPC
ARG DATA_ASSIMILATION_REF=development

ARG NGEN_FORCING_ORG=NGWPC
ARG NGEN_FORCING_REF=development

ARG CACHE_BUST=1
RUN set -eux && \
    echo $CACHE_BUST && pip3 install "git+https://github.com/${MSWM_ORG}/nwm-msw-mgr.git@${MSWM_REF}" && \
    echo $CACHE_BUST && pip3 install "git+https://github.com/${DATA_ASSIMILATION_ORG}/nwm-data-assimilation.git@${DATA_ASSIMILATION_REF}" && \
    pip3 cache purge

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
    tmpdir=$(mktemp -d) && \
    if [ "$MSWM_REF" = "development" ]; then \
        git clone --depth 1 --branch development https://github.com/${MSWM_ORG}/nwm-msw-mgr.git "$tmpdir" && \
        cd "$tmpdir" && \
        branch="development" && \
        tags=""; \
    else \
        git clone --depth 1 --branch "$MSWM_REF" --single-branch https://github.com/${MSWM_ORG}/nwm-msw-mgr.git "$tmpdir" && \
        cd "$tmpdir" && \
        branch="" && \
        tags="$MSWM_REF"; \
    fi && \
    jq -n \
      --arg commit_hash "$(git rev-parse HEAD)" \
      --arg branch "$branch" \
      --arg tags "$tags" \
      --arg author "$(git log -1 --pretty=format:'%an')" \
      --arg commit_date "$(date -u -d @$(git log -1 --pretty=format:'%ct') +'%Y-%m-%d %H:%M:%S UTC')" \
      --arg message "$(git log -1 --pretty=format:'%s' | tr '\n' ';')" \
      --arg build_date "$(date -u +'%Y-%m-%d %H:%M:%S UTC')" \
      '{"nwm-msw-mgr": {commit_hash: $commit_hash, branch: $branch, tags: $tags, author: $author, commit_date: $commit_date, message: $message, build_date: $build_date}}' \
      > $GIT_INFO_PATH && \
    cd / && rm -rf "$tmpdir"

# Remove .git directory
RUN rm -rf .git

# Copy application code
COPY . /ngencerf/ngencerf-server/

# Fetch bmi_forcing_templates into an internal, non-mounted path to be copied at runtime by runCerf.sh
RUN set -eux && \
    PREBUILT_DIR="/ngencerf/prebuilt/bmi_forcing_templates" && \
    NGEN_FORCING_URL="https://github.com/${NGEN_FORCING_ORG}/ngen-forcing.git" && \
    \
    echo "Preparing bmi_forcing_templates from ${NGEN_FORCING_URL}, ref (branch/tag/commit): ${NGEN_FORCING_REF}" && \
    \
    # Ensure prebuilt directory exists and is empty
    rm -rf "$PREBUILT_DIR" && \
    mkdir -p "$PREBUILT_DIR" && \
    \
    # Clone sparse repo; allow branch, tag, or commit refs
    git clone --filter=blob:none --no-checkout --sparse \
        "$NGEN_FORCING_URL" tmp-ngen-forcing && \
    cd tmp-ngen-forcing && \
    (git fetch --depth 1 origin "${NGEN_FORCING_REF}" \
     || git fetch --depth 1 origin "refs/tags/${NGEN_FORCING_REF}:refs/tags/${NGEN_FORCING_REF}" \
     || git fetch origin "${NGEN_FORCING_REF}" \
     || git fetch origin "refs/tags/${NGEN_FORCING_REF}:refs/tags/${NGEN_FORCING_REF}") && \
    git checkout FETCH_HEAD && \
    \
    git sparse-checkout set \
        NextGen_Forcings_Engine_BMI/BMI_NextGen_Configs/config_templates && \
    \
    # Copy *contents* of config_templates into PREBUILT_DIR
    cp -a NextGen_Forcings_Engine_BMI/BMI_NextGen_Configs/config_templates/. \
        "$PREBUILT_DIR"/ && \
    \
    cd /ngencerf/ngencerf-server && \
    rm -rf tmp-ngen-forcing || true

# Build CLI executable in cli/dist
RUN cli/build_cli.sh

# Copy additional configuration files
COPY ./cerfserver-docker.env /ngencerf/ngencerf-server/cerfserver.env
COPY ./cerfServer/__local_settings.py /ngencerf/ngencerf-server/cerfServer/local_settings.py

# Set the entry point and expose the application port
ENTRYPOINT [ "/ngencerf/ngencerf-server/runCerf.sh" ]
EXPOSE 8000
