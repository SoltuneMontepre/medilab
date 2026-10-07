FROM docker.io/library/odoo:19.0

USER root

COPY ./src/requirements.txt /etc/odoo/requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends locales \
    && sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' \
              -e 's/# vi_VN.UTF-8 UTF-8/vi_VN.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8

RUN pip3 install --no-cache-dir --break-system-packages \
    --ignore-installed --only-binary :all: \
    -r /etc/odoo/requirements.txt

COPY ./tools/patches/fix_mail_manifest_rst.py /tmp/fix_mail_manifest_rst.py
RUN python3 /tmp/fix_mail_manifest_rst.py && rm /tmp/fix_mail_manifest_rst.py

COPY ./src/modules /mnt/extra-addons
COPY ./src/config /etc/odoo
COPY ./src/templates /mnt/templates

USER odoo
