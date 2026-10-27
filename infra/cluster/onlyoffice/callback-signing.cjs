"use strict";

const Module = require("node:module");

const DOCS_CO_SERVER = "/snapshot/server/DocService/sources/DocsCoServer.js";
const COMMON = "/snapshot/server/Common/sources/";

function install() {
  const load = Module._load;
  let installed = false;

  Module._load = function (request, parent, isMain) {
    const exported = load.call(this, request, parent, isMain);
    if (
      /(?:^|\/)DocsCoServer(?:\.js)?$/.test(request) &&
      Module._resolveFilename(request, parent) === DOCS_CO_SERVER &&
      typeof exported.sendServerRequest === "function"
    ) {
      const sender = exported.sendServerRequest;
      const utils = load.call(this, COMMON + "utils.js", parent, false);
      const tenants = load.call(this, COMMON + "tenantManager.js", parent, false);
      const definitions = load.call(this, COMMON + "commondefines.js", parent, false);
      if (sender.length !== 4 || utils.fillJwtForRequest.length !== 4) {
        throw new Error("Unexpected ONLYOFFICE callback signing contract");
      }

      exported.sendServerRequest = async function (ctx, uri, data, checkLength) {
        if (checkLength && utils.canIncludeOutboxAuthorization(ctx, uri)) {
          const secret = await tenants.getTenantSecret(ctx, definitions.c_oAscSecretType.Outbox);
          const authorization = utils.fillJwtForRequest(ctx, data, secret, false);
          // Upstream trims history after signing the body token. Finalize its payload before either token is signed.
          checkLength(authorization, data);
          return sender.call(this, ctx, uri, data);
        }
        return sender.call(this, ctx, uri, data, checkLength);
      };
      installed = true;
      Module._load = load;
    }
    return exported;
  };

  return function assertInstalled() {
    if (!installed) {
      throw new Error("ONLYOFFICE callback signing correction was not installed");
    }
  };
}

module.exports = {install};
