FROM mcr.microsoft.com/playwright:v1.56.1-noble

WORKDIR /opt/browser
RUN --mount=type=secret,id=proxy_ca,required=true \
    NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca \
    npm install --ignore-scripts --no-audit --no-fund playwright@1.56.1
COPY tools/onlyoffice_integration/browser.cjs ./browser.cjs
USER pwuser
CMD ["node", "browser.cjs"]
