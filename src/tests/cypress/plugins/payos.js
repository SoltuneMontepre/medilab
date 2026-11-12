// PayOS notifications sent from the test runner, signed with the checksum key Odoo runs with.

const { createHmac } = require("node:crypto");

// PayOS signs the data fields in code point order, as Odoo sorts them, joined as key=value, skipping empty ones.
function signature(data, key) {
  const raw = Object.keys(data)
    .sort((a, b) => (a < b ? -1 : Number(a > b)))
    .filter((name) => data[name] !== null && data[name] !== undefined)
    .map((name) => `${name}=${data[name]}`)
    .join("&");
  return createHmac("sha256", key).update(raw).digest("hex");
}

function payosTasks(baseUrl) {
  // Posts one transfer to the webhook and yields the HTTP status.
  async function payosNotify(data) {
    const key = process.env.PAYOS_CHECKSUM_KEY;
    if (!key) {
      throw new Error("Set PAYOS_CHECKSUM_KEY to the checksum key Odoo runs with.");
    }
    const response = await fetch(new URL("/payment/payos/webhook", baseUrl), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: "00", data, signature: signature(data, key) }),
    });
    return response.status;
  }

  return { payosNotify };
}

module.exports = { payosTasks };
