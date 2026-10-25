# Laboratory conformity assessments and multiple specifications

Checked: 25 October 2026. Primary-source research supporting the [conformity assessment requirements](../specs/conformity-assessments.md). The specification defines product behaviour; this document records the supporting sources and their evidence limits.

## Finding

A product's assessment framework can explicitly combine several regulatory documents. QCVN 01-132:2013/BNNPTNT demonstrates this for fresh vegetables, fruit and fresh tea in production/preliminary processing: sections 2.3.1–2.3.2 refer metals and microbiology to QCVN 8-2:2011/BYT and QCVN 8-3:2012/BYT respectively; sections 3.2.3–3.2.4 refer their testing methods to those documents. [Government-hosted regulation](https://datafiles.chinhphu.vn/cpp/files/vbpq/2013/05/tt-07.pdf).

The software inference is that a physical sample identifier should not impose a universal one-regulation ceiling. The laboratory identifies applicable requirements and the requested service, then links each statement to its evidence. This does not mean every sample needs several QCVNs, or that analysts may select whichever limit produces a pass. A testing report for submitted material also does not establish conformity of an entire farm, production facility or lot.

## Laboratory principles

ILAC-G8:09/2019 explains ISO/IEC 17025:2017 conformity statements. Its section 2.3, reproducing clause 7.1.3, requires defined specifications and decision rules, with customer agreement where the rule is not inherent. Sections 2.6–2.7, addressing clauses 7.8.6.1–7.8.6.2, require documented assessment rules and identification of covered results and requirements. Section 6 gives legally prescribed rules priority; section 7 places agreement and documentation before the work. [Official ILAC PDF, viewer pages 7 and 14–15](https://ilac.org/?ddownload=122722).

BoA's decision-rule training describes laboratory-specific documented rules, agreement, risk and measurement uncertainty. It corroborates the relevance of these principles to Vietnamese laboratory practice; a training page is not itself a statutory rule. [BoA, Decision Rules section](https://www.boa.gov.vn/vi/tieu-chuan-isoiec-170252017-0).

Vietnamese law distinguishes voluntary standards from binding technical regulations. Article 3(2) of the consolidated law describes mandatory regulations. Article 10a(2)(b) also addresses standards incorporated into regulations or legal instruments; Article 10a(3)(b) prevents declared standards from contradicting regulations or law. These provisions incorporate Law 70/2025/QH15, effective 1 January 2026. A contractual service choice cannot remove an otherwise applicable legal obligation. [Official consolidated law, Article 3 and Article 10a](https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2025/8/45845/58228-1-20251091-109256-vbhn-vpqh.pdf), [Government amendment metadata](https://vanban.chinhphu.vn/?classid=1&docid=214672&pageid=27160&typegroupid=3).

## Concrete published QCVN examples

The vegetable example follows explicit cross-references in QCVN 01-132:2013/BNNPTNT. Section 2.3.1 refers metals limits to QCVN 8-2; section 2.3.2 refers microbiological limits to QCVN 8-3. Sections 3.2.3 and 3.2.4 refer the corresponding testing methods to those documents. These clauses were checked visually in the government scan, PDF viewer pages 10-11, printed pages 9-10. That regulation also concerns production and processing conditions: section IV describes a wider conformity-assessment framework. Testing submitted vegetables covers the relevant test evidence, not that entire framework. [Government PDF, sections 2.3, 3.2 and IV](https://datafiles.chinhphu.vn/cpp/files/vbpq/2013/05/tt-07.pdf).

Applying an example to a current engagement still needs a check of editions, amendments, transitions and product classification; government hosting alone does not establish current legal force.

| Case | Published source and exact location | Implication |
| --- | --- | --- |
| Raw-eaten leafy vegetables, such as lettuce where that product classification applies | QCVN 8-2:2011/BYT, section II.3, row 14: the lead limit for leafy vegetables excluding spinach is 0.3 mg/kg. [NIFC PDF, viewer page 8, printed page 6](https://nifc.gov.vn/ajax/research/getfile?filecode=8772c09c-e5f1-47b7-942f-0ce82fd590f5). | A metals assessment identifies this document and the applicable product row. |
| The same product dossier's microbiology | QCVN 8-3:2012/BYT, section II.6.2: raw-eaten vegetables have E. coli and Salmonella requirements, including sampling-plan values. [NIFC PDF, viewer page 8, printed page 10](https://nifc.gov.vn/ajax/research/getfile?filecode=d6aba005-7047-4cc1-bd1b-a62bc6351e9e). | A microbiological assessment identifies a different document and criteria; a single document selector would hide this relationship. |
| Bottled drinking or natural mineral water | QCVN 6-1:2010/BYT, section II.2.1–2.3, assigns chemistry to annexes I/II and microbiology to annex III. [NIFC PDF, viewer page 3](https://nifc.gov.vn/ajax/research/getfile?filecode=e12703ac-a3bb-4f6c-85d7-bffbe84e5f51). | One specialised regulation may already cover several test families. Several families do not automatically require several QCVNs. |

The microbiological example has an important boundary. Section I.3.3 defines `n` as samples taken from a lot, `c` as the permitted count between `m` and `M`, and the acceptance logic. Section II.6.2 gives Salmonella `n = 5`, `c = 0`, not detected in 25 g; E. coli uses `n = 5`, `c = 2`, `m = 100`, `M = 1000` CFU/g. Section I.3.2 makes the distinction between type A and type B criteria conditional on production controls. One tested portion cannot by itself demonstrate completion of the lot's sampling plan. [QCVN 8-3, viewer pages 1–2 and 8](https://nifc.gov.vn/ajax/research/getfile?filecode=d6aba005-7047-4cc1-bd1b-a62bc6351e9e).

## Application in MediLab

The [conformity assessment specification](../specs/conformity-assessments.md) applies the following design principles. These are product design choices informed by the sources, rather than additional rules stated verbatim by them:

1. Let the laboratory establish an applicable-requirements plan for the product and requested service. It can reference one or several documents, with the relevant clauses, product categories and editions.
2. Associate each assessment with its requirements, appropriate result or sampling group, limits, units and decision rule. Keep measurements separate from conformity assessments. Reusing a result requires technical suitability; sharing a parameter name is insufficient.
3. Approve reusable presets through laboratory technical review. Applying a preset unchanged needs no separate approval on each request; authored or changed criteria require technical approval before the affected work. Receipt checks and applicable customer agreement still apply. Legal applicability takes precedence over a preference for a more favourable limit.
4. Preserve the copied criteria, source preset version and inherited approval reference for routine reuse. Keep changes, reasons and direct approvals when criteria are edited. Do not impose a universal one-document ceiling because of a database field.
5. Report conclusions per identified criterion or assessment scope. Distinguish a tested portion, a complete sampling-plan assessment and a broader product-conformity claim.

A criterion with `n`, `c`, `m` and `M` is not adequately represented by a generic numeric minimum/maximum alone. The specification preserves such requirements and evidence for professional assessment; it does not require a universal automatic sampling-plan decision engine.

## Evidence limits

This research examined published primary documents, not records of a particular laboratory's practice. It does not certify product, lot or production-facility conformity or establish an exhaustive list of applicable regulations. Indexed official VSQI catalog metadata marks QCVN 8-2, QCVN 6-1 and QCVN 01-132 active; direct status-page retrieval was unreliable. The corresponding current status of QCVN 8-3 was not exhaustively confirmed. These observations do not replace a complete amendment, repeal and transition audit. [VSQI 8-2](https://tieuchuan.vsqi.gov.vn/quychuan/view?sohieu=QCVN+8-2%3A2011%2FBYT), [VSQI 6-1](https://tieuchuan.vsqi.gov.vn/quychuan/view?sohieu=QCVN+6-1%3A2010%2FBYT), [VSQI 01-132](https://tieuchuan.vsqi.gov.vn/quychuan/view?sohieu=QCVN+01-132%3A2013%2FBNNPTNT).

The ILAC document was obtained through its official guidance index; the BoA source used here is a training description. No runtime implementation or database was verified.

## Related documents

- [Conformity assessments](../specs/conformity-assessments.md)
- [Laboratory overview](../functional/laboratory_module/overview.md)
- [Administrator catalog](../functional/laboratory_module/features/admin.md)
- [Tester](../functional/laboratory_module/features/tester.md)
- [Test reports](../specs/test-reports.md)
