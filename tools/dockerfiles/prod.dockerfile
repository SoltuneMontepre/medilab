FROM docker.io/library/odoo:19.0 AS builder

USER root

COPY ./src/core/requirements.txt /tmp/requirements.txt

RUN pip3 install --no-cache-dir --break-system-packages \
    --ignore-installed --only-binary :all: \
    --target /opt/python-packages \
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
