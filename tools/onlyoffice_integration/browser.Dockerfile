FROM mcr.microsoft.com/playwright:v1.56.1-noble

WORKDIR /opt/browser
RUN --mount=type=secret,id=proxy_ca,required=true \
    install -m 0644 /run/secrets/proxy_ca /tmp/medilab-build-ca.crt && \
    apt-get -o Acquire::https::CaInfo=/tmp/medilab-build-ca.crt update && \
    apt-get -o Acquire::https::CaInfo=/tmp/medilab-build-ca.crt install -y --no-install-recommends libnss3-tools && \
    rm -rf /var/lib/apt/lists/* /tmp/medilab-build-ca.crt
RUN --mount=type=secret,id=proxy_ca,required=true \
    NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca \
    npm install --ignore-scripts --no-audit --no-fund playwright@1.56.1
COPY tools/onlyoffice_integration/browser.cjs ./browser.cjs
COPY tools/onlyoffice_integration/editor_lifecycle.cjs ./editor_lifecycle.cjs
COPY tools/onlyoffice_integration/fixture_tls.cjs tools/onlyoffice_integration/garage_tls.cjs tools/onlyoffice_integration/start_browser.sh ./
ENTRYPOINT ["/bin/bash", "/opt/browser/start_browser.sh"]
CMD ["node", "browser.cjs"]
