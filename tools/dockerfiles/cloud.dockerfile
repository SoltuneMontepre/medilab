# Odoo image of a Claude Code cloud session, built by task ai:image when the session's proxy refuses the pull of the
# published image. It holds the Python packages of uv.lock; the modules and config come from the checkout's mounts.
# The proxy only passes HTTPS and signs it with its own certificate, given as the proxy_ca build secret.
ARG ODOO_IMAGE

FROM ${ODOO_IMAGE}

USER root

ARG HTTPS_PROXY
ARG HTTP_PROXY

COPY uv /bin/uv
COPY pyproject.toml uv.lock /tmp/core/

RUN --mount=type=secret,id=proxy_ca,required=true,mode=0444 \
    sed -i 's|http://|https://|g' /etc/apt/sources.list.d/*.sources \
    && apt-get -o Acquire::https::CaInfo=/run/secrets/proxy_ca update -qq \
    && apt-get -o Acquire::https::CaInfo=/run/secrets/proxy_ca install -y -qq --no-install-recommends locales \
    && sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' \
              -e 's/# vi_VN.UTF-8 UTF-8/vi_VN.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && uv export --directory /tmp/core --frozen --no-dev --output-file /tmp/requirements.txt \
    && SSL_CERT_FILE=/run/secrets/proxy_ca uv pip install --python /usr/bin/python3 --no-cache --require-hashes \
        --only-binary :all: --target /opt/python-packages -r /tmp/requirements.txt \
    && rm -rf /var/lib/apt/lists/* /tmp/core /tmp/requirements.txt /bin/uv

ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8 \
    PYTHONPATH=/opt/python-packages

USER odoo
