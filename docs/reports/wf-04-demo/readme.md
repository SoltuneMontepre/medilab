# WF-04 demo

The script for presenting [WF-04 Result entry and approval](../../functional/business-flows.md#wf-04-result-entry-and-approval) through scenarios DS-04a to DS-04g of the Review 2 design brief, the result files the tester saves during it, and the edge cases to show when reviewers ask.

## Before the demo

1. Seed the samples, against the server and database of the demo:

   ```powershell
   python docs/reports/wf-04-demo/seed.py --url http://127.0.0.1:8069 --db medilab
   ```

   It prints one line per scenario with its lab code and, for the file scenarios, the ids of its `-raw` and `-result` folders. Each run adds new samples, so run it again to repeat the demo. A lead measurement whose end has passed keeps its machine busy until its result is sent, so the seed first marks such measurements finished and prints each one.

2. Open two browser windows, one signed in as the tester and one as the head of department. Every demo user's password is `demo`, or `MEDILAB_DEMO_PASSWORD` when the server sets it.

   | Login                      | Person         | Plays                                       |
   | -------------------------- | -------------- | ------------------------------------------- |
   | `demo.tester`              | Dang Thi Lan   | Tester of Chemistry, assigned every test    |
   | `demo.head_of_department`  | Hoang Van Minh | Head of Chemistry, owner of sample folders  |
   | `demo.chemistry_tester`    | Ly Van Hung    | The colleague of DS-04e, through `seed.py`  |

3. Start Medilab Sync with `task sync:dev`, sign in as `demo.tester` and, on the Folders tab, choose an empty `C:\MediLab` as the folder for your samples. The folders of every seeded sample appear inside it, as `C:\MediLab\<lab code>\Raw Data` and `C:\MediLab\<lab code>\Results`; the steps below copy files into the Results folder of DS-04a, DS-04e, DS-04f and DS-04g.
4. Keep [files](files) open in the file explorer. Each file is copied into a bound folder under the name it has here, so its later versions replace it under the same name.
5. For DS-04g, the online editor must be down: present on a server where ONLYOFFICE is stopped or not set up.

## Files

| File                                                                         | Scenario | Content                                                                           | Value entered |
| ---------------------------------------------------------------------------- | -------- | --------------------------------------------------------------------------------- | ------------- |
| [DS-04a/ket-qua-pb.csv](files/DS-04a/ket-qua-pb.csv)                         | DS-04a   | AAS-01 run of lead: calibration, QC check 0.010 mg/L, three replicates            | 0.006 mg/L    |
| [DS-04e/ket-qua-pb.csv](files/DS-04e/ket-qua-pb.csv)                         | DS-04e   | The version both testers start from                                               | 0.005 mg/L    |
| [DS-04e/colleague/ket-qua-pb.csv](files/DS-04e/colleague/ket-qua-pb.csv)     | DS-04e   | Ly Van Hung's change: a reviewer and a note                                       |               |
| [DS-04e/mine/ket-qua-pb.csv](files/DS-04e/mine/ket-qua-pb.csv)               | DS-04e   | Dang Thi Lan's change of the same version: a spiked recovery note                 |               |
| [DS-04f/ket-qua-pb.csv](files/DS-04f/ket-qua-pb.csv)                         | DS-04f   | A wrong export: replicates in µg/L, mean labelled mg/L, no QC check               |               |
| [DS-04f/corrected/ket-qua-pb.csv](files/DS-04f/corrected/ket-qua-pb.csv)     | DS-04f   | The corrected export in mg/L with its QC check                                    | 0.004 mg/L    |
| [DS-04g/so-ket-qua-pb.xlsx](files/DS-04g/so-ket-qua-pb.xlsx)                 | DS-04g   | The tester's lead workbook: three replicates and their mean                       | 0.007 mg/L    |
| [DS-04g/edited/so-ket-qua-pb.xlsx](files/DS-04g/edited/so-ket-qua-pb.xlsx)   | DS-04g   | The workbook after a fourth replicate, saved in Excel                             |               |

Every sample is bottled water compared with QCVN 6-1:2010/BYT, which limits lead to at most 0.01 mg/L. Lead by TCVN 7602:2007 on bottled water reports in mg/L with 3 decimals, an LOD of 0.005 and an LOQ of 0.015, so a result below 0.015 is entered as the text `<0.015 mg/L (below LOQ)`; keep the number.

The back-office paths below are in the Laboratory app. A sample test opens from Samples › Sample Tests or from the tester's Tasks › My Tasks.

## DS-04a Main path

The sample: `DS-04a main`, lead assigned to the tester with a scheduled booking on an AAS.

| #   | Who    | Do                                                                                             | Show                                                                                                                                          |
| --- | ------ | ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Tester | Open the lead sample test; on Bookings, click Start                                            | The test is In Testing and its machine busy                                                                                                   |
| 2   | Tester | Copy `DS-04a/ket-qua-pb.csv` into the bound Results folder                                     | Medilab Sync shows Completed; Documents › File Versions has version 1, Synced, with the tester, the computer, the size and the SHA-256        |
| 3   | Tester | Enter Result, type 0.006 and save                                                              | The unit, LOD and LOQ are copied from the way of testing, and the limit of at most 0.01 mg/L from the regulation                              |
| 4   | Tester | Assess Pass, then Send for Approval                                                            | The result is Requested and signed by the tester; the test is Result Entered, the testing task done and the machine free; the head is notified |
| 5   | Head   | Results › Test Results, open the result, Approve                                               | The result and test are approved and the sample is completed; Results › Test Reports holds the draft report for WF-06                        |
| 6   | Head   | Documents › File Versions, open version 1 of `ket-qua-pb.csv`, Sign and confirm                | The version is Approved; the signature belongs to that version and its SHA-256                                                                |

Save the file before the result is approved: once the sample completes, its folders take no new version.

## DS-04b Rejected result and retest

The sample: `DS-04b reject and retest`, whose result of 0.008 mg/L the tester has sent.

| #   | Who    | Do                                                                                                                   | Show                                                                                                                               |
| --- | ------ | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Head   | Open the result, Reject, give the reason `Mẫu QC 0,010 mg/L đọc 0,0115 (cao 15%); hiệu chuẩn lại AAS-01 và đo lại.` | The result is Rejected and stays on record; the test is back In Testing, with a new testing task for the same tester holding the reason |
| 2   | Tester | Open the new task in My Tasks, then the sample test; Enter Result 0.007, assess Pass, Send for Approval              | A second result, the one reported                                                                                                  |
| 3   | Head   | Approve the new result                                                                                               | The new result is approved; the sample test lists both results, the rejected one not reported                                      |

## DS-04c Unusual result

The sample: `DS-04c unusual result`.

| #   | Who    | Do                                                                | Show                                                                                                                                                                                                 |
| --- | ------ | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Tester | Start the booking, Enter Result 0.010, assess Pass, save          | The Warning box: `0.010 mg/L is within 10% of the regulation limit 0.010 mg/L.`, and, with enough history, `0.010 mg/L is more than 3 standard deviations from <mean> mg/L, the mean of the <n> approved results of this way of testing on this sample type.` No customer or sample is named |
| 2   | Tester | Send for Approval anyway                                          | The warning is kept on the result                                                                                                                                                                    |
| 3   | Head   | Open the result                                                   | Sent With Warning shows the same text; Approve                                                                                                                                                       |

The spread warning needs at least 10 approved results of lead by TCVN 7602:2007 on bottled water; the minimum, the 3 standard deviations and the 10% margin are settings. Without that history only the limit warning shows.

## DS-04d Cancelled test

The sample: `DS-04d cancel`, with pH approved and lead assigned with a booking.

| #   | Who  | Do                                                                                                 | Show                                                                                                           |
| --- | ---- | -------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| 1   | Head | Open the lead sample test, Cancel Test, give the reason `Mẫu không đủ thể tích để phân tích chì.` | The test is Cancelled with its reason; its testing task and booking are cancelled; the sample is completed      |
| 2   | Head | Results › Test Reports, open the request's draft report                                            | It holds only the pH result                                                                                    |
| 3   | Head | Open the pH sample test                                                                            | No Cancel Test: a test with an approved result cannot be cancelled                                             |

## DS-04e Conflict

The sample: `DS-04e conflict`, whose folders have Ly Van Hung as a member too. `seed.py colleague` stands for his computer: it signs in as `demo.chemistry_tester` and saves through the API Medilab Sync uses.

| #   | Who       | Do                                                                                                                    | Show                                                                                                                       |
| --- | --------- | --------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| 1   | Tester    | Copy `DS-04e/ket-qua-pb.csv` into the bound Results folder                                                            | Version 1                                                                                                                  |
| 2   | Colleague | `python docs/reports/wf-04-demo/seed.py colleague <results folder id> docs/reports/wf-04-demo/files/DS-04e/colleague/ket-qua-pb.csv` | It prints `completed, version 2`: version 2 by Ly Van Hung from computer PC-HOA-02                       |
| 3   | Tester    | Replace the local `ket-qua-pb.csv` with `DS-04e/mine/ket-qua-pb.csv`                                                  | Medilab Sync shows Conflict: the change was made from version 1; the server keeps it as version 3, Conflict, not current    |
| 4   | Tester    | In Medilab Sync's status, choose Dùng phiên bản máy chủ                                                               | The local file is backed up and version 2 downloaded                                                                       |
| 5   | Head      | Documents › File Versions, filter on the folder                                                                       | Versions 1 and 2 synced and version 3 conflict, all kept; version 3 has no Sign                                            |

## DS-04f Rejected file version

The sample: `DS-04f file rejected`.

| #   | Who    | Do                                                                                                                                                  | Show                                                                                       |
| --- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| 1   | Tester | Copy `DS-04f/ket-qua-pb.csv` into the bound Results folder                                                                                          | Version 1                                                                                  |
| 2   | Head   | Open version 1, Reject, give the reason `Đơn vị ghi ug/L nhưng dòng trung bình ghi mg/L, thiếu mẫu QC 0,010 mg/L; xuất lại từ AAS-01.`               | Version 1 is Rejected with the reason                                                      |
| 3   | Tester | Replace the local file with `DS-04f/corrected/ket-qua-pb.csv`                                                                                       | Version 2                                                                                  |
| 4   | Head   | Sign version 2                                                                                                                                      | Version 2 is Approved; version 1 stays rejected and can no longer be signed                |
| 5   | Tester | Optionally, start the booking, Enter Result 0.004, assess Pass and send; the head approves                                                          | The sample completes                                                                       |

## DS-04g Online editor down

The sample: `DS-04g editor down`.

| #   | Who    | Do                                                                                             | Show                                                                                                      |
| --- | ------ | ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| 1   | Tester | Copy `DS-04g/so-ket-qua-pb.xlsx` into the bound Results folder                                 | Version 1                                                                                                 |
| 2   | Tester | Documents › Files, click `so-ket-qua-pb.xlsx`                                                  | The editor page shows the editing service's error and a retry button                                      |
| 3   | Tester | Open the workbook from the local folder in Excel and save it, or replace it with `DS-04g/edited/so-ket-qua-pb.xlsx` | Medilab Sync uploads version 2                                                                            |
| 4   | Tester | In Medilab Sync's version history, restore version 1                                           | Version 3, Restored, with the SHA-256 of version 1; versions 1 and 2 stay                                 |
| 5   | Tester | Optionally, start the booking, Enter Result 0.007, assess Pass and send; the head approves     | The sample completes                                                                                      |

## Edge cases

The `EDGE` samples of the seed are there for these; the messages are the ones the system shows.

| #   | Case                                              | Where                          | Do                                                                                       | Expected                                                                                                                                       |
| --- | ------------------------------------------------- | ------------------------------ | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| E1  | Sending a regulated result without an assessment  | Any sample with QCVN 6-1       | Enter a value, Send for Approval                                                         | `Assess the result against the regulation as pass, fail or insufficient basis before sending it.`                                             |
| E2  | A negative value                                  | `EDGE entry checks`            | Enter -0.001                                                                             | `… cannot be negative; enter a measurement below the LOD as a text, such as "< LOD".`                                                          |
| E3  | A value below the LOD                             | `EDGE entry checks`            | Enter 0.003 and the text `<0.005 mg/L (below LOD)`                                       | The text is the result; the measured number is kept, never zero                                                                               |
| E4  | Only the latest result is sent                    | `EDGE entry checks`            | Enter 0.003, then a second result 0.004; open the first                                  | No Send for Approval on it; sending it is refused with `Only the reported result of a sample test is sent for approval.`                       |
| E5  | A signed result is locked                         | `EDGE withdraw`                | As the tester, change the sent value                                                     | `The document has signatures; withdraw them before changing it.`                                                                              |
| E6  | The entrant cannot approve                        | `EDGE withdraw`                | As the tester, open the sent result                                                      | No Approve; approving is refused with `Only people with the role Head of department, or the role of a later level, can act at this level.`     |
| E7  | Withdrawing before the head acts                  | `EDGE withdraw`                | As the tester, Withdraw Signature                                                        | The result is editable again and the testing task is back with the tester                                                                      |
| E8  | No limit for the sample's exact type              | `EDGE no limit` (lettuce, QCVN 8-2:2011/BYT) | Enter 0.12, assess Pass                                                    | `The regulation sets no limit for … on the sample's type, so it can only be assessed as insufficient basis.`; Insufficient Basis is accepted  |
| E9  | No regulation and a text result                   | `EDGE no regulation`           | Enter the text `Không phát hiện` and send                                                | No assessment is asked; the result shows `Không phát hiện`                                                                                     |
| E10 | Rejecting without a reason                        | DS-04b result, DS-04f version  | Reject with a blank reason                                                               | `A rejection needs a reason.`                                                                                                                  |
| E11 | Cancelling without a reason                       | DS-04d lead test               | Cancel Test with a blank reason                                                          | `Give a reason for cancelling the test.`                                                                                                       |
| E12 | A tester changing a method's steps                | Any testing method             | As the tester, edit a step                                                               | The steps are read-only; a change is refused with `You are not allowed to Edit these records: …`                                               |
| E13 | Signing one's own file version                    | DS-04a version 1               | As the tester, open the version                                                          | No Sign: the person who saved a version cannot sign it                                                                                         |
| E14 | Signing an older version                          | DS-04f version 1               | Sign it after version 2 is saved                                                         | `Only the current version of a file is signed; this one has a newer version.`                                                                 |
| E15 | Changing a version                                | Any version                    | Open its form                                                                            | Read-only for everyone; a write is refused with `A version's number, content and origin never change; save the file again instead.`            |
| E16 | Saving into a completed sample's folder           | DS-04a after step 5            | Save `ket-qua-pb.csv` again                                                              | The upload is refused with `folder_sample_closed`: `A completed or cancelled sample's folders are read-only.`                                  |
| E17 | A sample's folders come with its tests            | `EDGE entry checks`            | As the head, open the sample and its Folders                                             | Raw Data and Results once, created when its test was assigned to the tester, owned by the head with the tester as a member; Create Folders is not offered |
| E18 | A person outside the folder                       | DS-04a Results folder          | Sign in to Medilab Sync as `demo.microbiology_tester`                                    | The server answers not found for the folder's files, so nothing of it syncs                                                                    |
| E19 | The tester never sees the customer                | Any sample                     | As the tester, open the sample                                                           | Only the lab code; searching by the customer's sample name is refused for lack of `test.request.read.all`                                      |
| E20 | A measurement past its end holds its machine      | Any started booking            | Leave a started booking past its end without sending its result                          | The machine takes no new booking: Approve Booking answers `No machine can finish Lead (Pb) before its due date.` until the result is sent or the booking marked Done |

## Related documents

- [Business flows](../../functional/business-flows.md#wf-04-result-entry-and-approval)
- [Laboratory files](../../specs/laboratory-files.md)
- [Medilab Sync technician guide](../../../src/applications/medilab-sync/docs/technician.md)
- [Reports](../readme.md)
