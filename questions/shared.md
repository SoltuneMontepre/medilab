# Shared questions

- **Certificate holder.** Whose certificate signs the printed documents: one laboratory certificate for all documents, or a certificate per signer or role (for example the Head of Sales for quotations)? This decides how many certificates Viettel Sign must hold. (blocks SH-04)
- **SMS.** The customer notification preferences include SMS. Brevo can be used for it, or another provider. (blocks US-C07)
- **Lock timeout.** The inactivity period after which an editing lock is released. (blocks SH-06)
- **Archived kinds.** Besides audit entries, which records does the cleanup job archive before removing them: job runs and items, notifications, locks, devices? (blocks SH-09)
- **Failed items before notifications.** When an item fails its last attempt, the job logs it and the Jobs screen lists it until the notifications feature sends administrators a notification. Is that enough meanwhile, or should the job also e-mail someone? (blocks SH-09)
- **Platform terms.** The glossary proposes Vietnamese terms for the platform records: Tác Vụ Định Kỳ (scheduled job), Mục Tác Vụ (job item), Lượt Chạy Tác Vụ (job run), Tham Số Hệ Thống (system parameter). Are they the terms the laboratory uses? (blocks SH-03, SH-09)

## Related documents

- [Shared technical features](../docs/functional/shared.md)
