FROM docker.io/library/python:3.13.16-slim-trixie

ENV VIRTUAL_ENV=/opt/ansible \
    PATH=/opt/ansible/bin:$PATH \
    ANSIBLE_CONFIG=/work/infra/ansible/ansible.cfg \
    ANSIBLE_LOCAL_TEMP=/tmp/ansible \
    ANSIBLE_FORCE_COLOR=1

COPY ./infra/ansible/requirements.yml /tmp/requirements.yml

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 ansible \
    && python -m venv "$VIRTUAL_ENV" \
    && pip install --no-cache-dir --only-binary :all: \
        ansible-core==2.21.5 \
        ansible-lint==26.10.1 \
    && ansible-galaxy collection install -r /tmp/requirements.yml -p /usr/share/ansible/collections \
    && chown -R ansible:ansible "$VIRTUAL_ENV" \
    && rm -rf /tmp/ansible /tmp/requirements.yml

USER ansible

WORKDIR /work/infra/ansible
