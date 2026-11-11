# VILAS accreditation scopes

The accredited tests of four VILAS laboratories, read on 21-10-2026 from the scope documents the [BoA organisation search](https://www.boa.gov.vn/vi/timkiem/tochuc) publishes. They ground the Laboratory catalog: testing fields, the sample type tree, parameter groups, parameters, testing methods and what an accreditation certificate covers. The demo catalog comes from VILAS 677 only.

## Files

- [vilas-677-tests.csv](vilas-677-tests.csv): the 153 accredited tests of Chấn Nam, a contract testing laboratory for food, water, cosmetics, animal feed and food-contact packaging
- [vilas-252-tests.csv](vilas-252-tests.csv): the 171 accredited tests of a veterinary drug control centre, all on veterinary drugs
- [vilas-238-tests.csv](vilas-238-tests.csv): the 145 tests of Eurofins Sắc Ký Hải Đăng's February 2026 expansion, from broad food groups to single products such as yogurt and soy sauce
- [vilas-238-analytes.csv](vilas-238-analytes.csv): the 150 analytes, with CAS number and LOQ, of the seven appendices that the multi-residue tests of VILAS 238 refer to
- [vilas-092-tests.csv](vilas-092-tests.csv): one dioxin test accredited on 11 different materials
- [vilas-092-analytes.csv](vilas-092-analytes.csv): the dioxin and furan congeners of each VILAS 092 test, with their LOQ

## Scopes

| Scope     | Laboratory                                                                                                     | Fields    | Decision                       | Valid                    | Source                                                                                                                                                              |
| --------- | -------------------------------------------------------------------------------------------------------------- | --------- | ------------------------------ | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| VILAS 677 | Công ty Cổ phần Dịch vụ Khoa học Công nghệ Chấn Nam                                                            | Sinh, Hóa | 3085/QĐ-VPCNCLQG of 03-11-2025 | 03-11-2025 to 03-11-2030 | [page](https://www.boa.gov.vn/vi/cong-ty-co-phan-dich-vu-khoa-hoc-cong-nghe-chan-nam), [scope](https://www.boa.gov.vn/sites/default/files/2025-11/677lmr092025.pdf) |
| VILAS 252 | Trung tâm Kiểm nghiệm Thuốc Thú y Trung ương II                                                                | Dược      | 1252/QĐ-VPCNCLQG of 15-05-2026 | 15-05-2026 to 05-03-2027 | [page](https://www.boa.gov.vn/vi/trung-tam-kiem-nghiem-thuoc-thu-y-trung-uong-ii), [scope](https://www.boa.gov.vn/sites/default/files/2026-05/252tt0526.pdf)        |
| VILAS 238 | Công ty TNHH Eurofins Sắc Ký Hải Đăng, Ho Chi Minh City                                                        | Sinh, Hóa | 383/QĐ-VPCNCLQG of 23-02-2026  | 23-02-2026 to 15-11-2029 | [page](https://www.boa.gov.vn/vi/cong-ty-tnhh-eurofins-sac-ky-hai-dang), [scope](https://www.boa.gov.vn/sites/default/files/2026-02/vilas-238mr0226hcm.pdf)         |
| VILAS 092 | Phòng Hóa Dược, Trung tâm Dịch vụ Phân tích thí nghiệm và Tiêu chuẩn Đo lường Chất lượng thành phố Hồ Chí Minh | Hóa       | 745/QĐ-VPCNCLQG of 26-03-2026  | 26-03-2026 to 23-03-2031 | [page](https://www.boa.gov.vn/vi/phong-hoa-duoc), [scope](https://www.boa.gov.vn/sites/default/files/2026-03/3.-092.l.-hoa-duoc.pdf)                                |

VILAS 238 is the expansion only. Its main scope and the other scope file on the same page were not read.

## Columns

Tests files, one row per accredited test:

| Column         | Holds                                                                                                              |
| -------------- | ------------------------------------------------------------------------------------------------------------------ |
| `scope`        | The VILAS number.                                                                                                  |
| `field`        | The field of testing the test is listed under: Sinh, Hóa or Dược.                                                  |
| `row`          | The test's number in its field.                                                                                    |
| `materials_vi` | The products or materials tested, in Vietnamese, as one label that often lists several.                            |
| `materials_en` | The same in English.                                                                                               |
| `test_vi`      | The test in Vietnamese: the analytes and the technique.                                                            |
| `test_en`      | The same in English.                                                                                               |
| `limit`        | The limit of quantitation or range of measurement as printed, per analyte and sometimes per form, such as liquid.  |
| `method`       | The test method as printed: its code, the equivalent standard in brackets or the reference of a laboratory method. |

Analytes files, one row per analyte:

| Column                       | Holds                                                                      |
| ---------------------------- | -------------------------------------------------------------------------- |
| `scope`                      | The VILAS number.                                                          |
| `field`, `test_row`          | The test the analyte is listed under, for analytes listed inside a test.   |
| `appendix_vi`, `appendix_en` | The appendix the analyte is listed in, for analytes listed in an appendix. |
| `row`                        | The analyte's number in its test or appendix.                              |
| `analyte`                    | The analyte's name.                                                        |
| `cas`                        | Its CAS number, where the appendix gives one.                              |
| `technique`                  | The analytical technique, where the appendix gives one.                    |
| `loq`                        | The limit of quantitation as printed.                                      |
| `loq_unit`                   | The unit of `loq` when the appendix header gives it.                       |

Values keep the scope's notation: decimal commas, `eLOD50` for the estimated detection limit of microbiological tests, and the `(a)` and `(b)` marks of VILAS 238 for updated and extended tests.

## What the scopes show

- **Fields.** Each scope is split by field of testing: Sinh (Biological), Hóa (Chemical), Dược (Pharmaceutical). BoA also accredits Cơ, Điện – Điện tử, Vật liệu xây dựng and Không phá hủy.
- **Materials.** The material is a flat label of any breadth, from "Thực phẩm" to "Nước mắm" or "Sữa chua". Broader groups show only in names such as "Thủy sản và sản phẩm thủy sản". Materials named next to "Thực phẩm", such as health supplements, food additives, animal feed and water, have their own rows and methods.
- **Analytes.** One test often covers several analytes with one method, and names their class, such as "nhóm b-lactam (Amoxicilline, Ampicilline, …)" or "thuốc bảo vệ thực vật gốc clo".
- **Accreditation.** A method is accredited for the materials and analytes of its row only. Pb and Cd by GF-AAS use SMEWW 3113B for water, AOAC 999.11 for food, ACM THA 005:2006 for cosmetics and QCVN 12-1:2011/BYT for plastic packaging in VILAS 677. One method code can appear on several rows, such as AOAC 999.11 for Pb and Cd and for Fe, Cu and Zn.
- **Methods.** Codes include national and international standards, such as TCVN 6848:2007 (ISO 4832:2007), SMEWW 3112B:2023 and USP-NF 2023 <2021>, and laboratory methods with their reference, such as H159:2025 (Ref. TCVN 8122:2009) and TCCS 003:2017/TTKNII. Scopes give no method titles.
- **Limits.** The LOQ is given per analyte and can differ by form, such as liquid and other, and by material for the same analyte.

## Extraction

The scope PDFs have a text layer. Their tables were read cell by cell with pdfplumber:

- the scope's space characters were ignored and words split by the gaps between them;
- a merged material or method cell was carried down to the rows it spans;
- a bilingual cell was split where its English lines begin;
- two words that ran together were separated by hand.

Contact details and people's names in the scope headers were left out, and the PDFs are not stored.

## BoA site

- `robots.txt` allows the organisation search, the organisation pages and the scope files under `/sites/default/files/`.
- The search is a GET form on `/vi/timkiem/tochuc`. Its filters are:
  - accreditation programme: `field_tochuc_phanloai_target_id`, with 238 for testing and calibration laboratories;
  - VILAS number: `field_tochuc_idphanloai_value`;
  - parent organisation: `field_tochuc_donvichuquan_value`;
  - field of testing: `field_tochuc_linhvuc_target_id`;
  - province: `field_tochuc_tinhthanh_target_id[]`;
  - status: `field_tochuc_tinhtrang_target_id`, with 270 for valid.
- An organisation page gives the laboratory, its VILAS number, fields, the last valid day, its location and one or more scope PDFs. One VILAS number can have several pages, one per site or department, and a page can hold the main scope and its expansions.
- Every page carries the notice "Cấm sao chép dưới mọi hình thức nếu không có sự chấp thuận bằng văn bản" (copying in any form needs written approval).

## Related documents

- [Administrator features: catalog](../../functional/laboratory_module/features/admin.md#1-catalog-us-ad01-to-us-ad08-us-ad26-to-us-ad28)
- [Glossaries](../../glossaries.md)
