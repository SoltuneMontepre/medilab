# Onboarding questions

- **BoA pages.** Which BoA pages does the adapter read: the organisation search only, or also each organisation's page and its accreditation scope? Is the scope published as HTML, as a text PDF or as a scanned PDF, and do scanned PDFs need text recognition? (blocks US-AD32)
- **BoA terms.** Do BoA's terms of use allow collecting its pages automatically, and does BoA offer an export or an API to use instead? (blocks US-AD32, US-AD33)
- **Sector sources.** Which sources list the testing methods, parameters and sample types of a sector, such as food: the scopes of other accredited laboratories on BoA, national regulations (QCVN) and standards (TCVN), or other sites? Are the scopes of other laboratories acceptable to suggest from? (blocks US-AD33)
- **Regulations.** Are regulations with their limits per parameter also staged, and from which source? (US-AD07, US-AD33)
- **Other modules.** Does Onboarding also stage master data of E-commerce or Inventory, such as chemicals and their CAS numbers, or only Laboratory's?
- **Outbound access.** Production lets web traffic in only through Cloudflare Tunnel. May Odoo's pods reach the hosts of the turned-on sources over HTTPS, and is that limited to a list of hosts in the cluster? (blocks US-AD32, US-AD33)
- **Release.** Is Onboarding published on the Odoo marketplace with the other modules, or installed only on the laboratory's own servers?

## Related documents

- [Onboarding overview](../docs/functional/onboarding_module/overview.md)
