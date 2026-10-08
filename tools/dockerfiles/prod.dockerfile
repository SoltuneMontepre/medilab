FROM docker.io/library/odoo:19.0 AS builder

USER root

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv
COPY ./src/core/pyproject.toml ./src/core/uv.lock /tmp/core/

RUN uv export --directory /tmp/core --frozen --no-dev \
        --output-file /tmp/requirements.txt \
    && uv pip install --python /usr/bin/python3 --no-cache --require-hashes \
        --only-binary :all: --target /opt/python-packages \
        -r /tmp/requirements.txt


FROM docker.io/library/odoo:19.0

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends locales \
    && sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' \
              -e 's/# vi_VN.UTF-8 UTF-8/vi_VN.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8 \
    PYTHONPATH=/opt/python-packages

COPY --from=builder /opt/python-packages /opt/python-packages

COPY ./src/core/modules /mnt/extra-addons
COPY ./src/core/config /etc/odoo

USER odoo
