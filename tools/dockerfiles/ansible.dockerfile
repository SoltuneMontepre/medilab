FROM docker.io/library/python:3.13.16-slim-trixie

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --only-binary :all: \
        ansible-core==2.21.5 \
        ansible-lint==26.10.1

COPY ./infra/ansible/requirements.yml /tmp/requirements.yml
RUN ansible-galaxy collection install -r /tmp/requirements.yml -p /usr/share/ansible/collections

ENV ANSIBLE_CONFIG=/work/infra/ansible/ansible.cfg \
    ANSIBLE_LOCAL_TEMP=/tmp/ansible \
    ANSIBLE_FORCE_COLOR=1

WORKDIR /work/infra/ansible
