# Onboarding questions

- **Sector sources.** Which sources list the testing methods, parameters and sample types of pharmaceuticals and of environment? (blocks US-AD33)
- **Regulations.** Are regulations with their limits per parameter also staged, and from which source? (US-AD07, US-AD33)
- **Other modules.** Does Onboarding also stage master data of E-commerce or Inventory, such as chemicals and their CAS numbers, or only Laboratory's?
- **Outbound access.** Production lets web traffic in only through Cloudflare Tunnel. May Odoo's pods reach the hosts of the turned-on sources over HTTPS, and is that limited to a list of hosts in the cluster? (blocks US-AD32, US-AD33)
- **Release.** Is Onboarding published on the Odoo marketplace with the other modules, or installed only on the laboratory's own servers?
- **Organisations listed.** BoA's search lists certification bodies, inspection bodies and other schemes (VICAS, VIAS, VIPAS, VIRAS, GLP) beside laboratories (VILAS, VILAS MED). Does picking an organisation offer only laboratories, and which schemes count as one?
- **Scope lines.** BoA's list of accredited tests names, for each row, the material tested, the specific test, its limit of quantitation and its methods. Does a run also stage sample types, test parameters and ways of testing from it, and does accepting a certificate add its scope lines? If so: is the test name, such as "Determination of Octan number, Engine method", the parameter, or does the administrator name it; which main group and which parent sample type do new ones get; and is the limit of quantitation staged as the LOQ of the way of testing? (US-AD28, US-AD34)
- **Keeping the scope current.** Is the laboratory's own organisation collected again on a schedule, and who is told when its scope changes or its certificate nears its end of validity? That needs the laboratory's own organisation recorded once, for example on the company.
- **Vietnamese terms.** What are the Vietnamese terms of Organisation, Sector and Snapshot? The code proposes *Tổ Chức*, *Ngành* and *Bản Lưu Trang*, because *Lĩnh vực* is already the term of a testing field.

## Related documents

- [Onboarding overview](../docs/functional/onboarding_module/overview.md)
