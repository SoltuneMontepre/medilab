import { call, callAs, callRefused } from "../../../support/odoo";
import { search } from "../../../support/form";
import { api, ok, refused, signOutDevices } from "./device";
import { downloaded, fileAt, fixture, upload } from "./files";
import {
  ADMINISTRATOR,
  HEAD,
  TESTER,
  addMember,
  confirmDialog,
  devices,
  foldersOfSample,
  ownFolder,
  person,
  runTag,
  sampleWithoutFolders,
} from "./setup";

// Medilab Sync's folder watching, local folders and history screens, and the saves of real people in the online editor,
// are outside these tests: they show what the server does with the calls a computer makes, with real bytes.
const LOCK_MINUTES = 30;

function twoWay(folder) {
  return callAs(ADMINISTRATOR, "medilab.laboratory.folder", "write", [[folder.id], { sync_mode: "two_way" }]);
}

function versionsOf(file, fields = ["number", "source", "size", "sha256", "user_id", "device_id", "restored_from_id", "approval_state"]) {
  return callAs(ADMINISTRATOR, "medilab.laboratory.file.version", "search_read", [[["file_id", "=", file.id]]], { fields, order: "number" });
}

// Moves the expiry of a lock, as time passing would. A server action does it, as running one needs only the right to change
// the records of its model; it is deleted at once.
function setLockExpiry(lockId, minutes) {
  const code = `env["medilab.laboratory.file.lock"].browse(${lockId}).sudo().write({"expires_at": datetime.datetime.utcnow() + datetime.timedelta(minutes=${minutes})})`;
  cy.signInAs("administrator");
  call("ir.model", "search", [[["model", "=", "ir.actions.server"]]]).then(([modelId]) =>
    call("ir.actions.server", "create", [{ name: `Move the expiry of lock ${lockId}`, model_id: modelId, state: "code", code }]).then((actionId) => {
      call("ir.actions.server", "run", [[actionId]]);
      call("ir.actions.server", "unlink", [[actionId]]);
    }),
  );
}

function minutesFromNow(isoOrOdoo) {
  return (new Date(isoOrOdoo.replace(" ", "T").replace(/(?<!\+\d\d:\d\d|Z)$/, "Z")).getTime() - Date.now()) / 60000;
}

describe("WF-07 laboratory file versions", () => {
  afterEach(signOutDevices);

  // Writing the downloaded version into the second computer's local folder is Medilab Sync's.
  it("TC-WF04-A6 a version saved on one computer reaches another through the changes feed with the same bytes", () => {
    const tag = runTag();
    person(TESTER).then((tester) =>
      devices(tag, HEAD, TESTER, TESTER).then(([owner, first, second]) =>
        ownFolder(owner, `A6 ${tag}`).then((folder) => {
          twoWay(folder);
          addMember(owner, folder, tester);
          fixture("result-a.xlsx").then((content) =>
            upload(first, folder, "result.xlsx", "result-a.xlsx").then(({ upload: saved }) => {
              expect(saved.status).to.eq("completed");
              expect(saved.version).to.include({ size: content.size, sha256: content.sha256 });

              api(second, "GET", `/folders/${folder.id}/changes`).then((response) => {
                const change = ok(response, "changes").changes.find(({ file }) => file.path === "result.xlsx");
                expect(change.version.id).to.eq(saved.version.id);
                downloaded(second, folder, change.file, change.version.id).then((bytes) =>
                  expect(bytes).to.deep.eq({ size: content.size, sha256: content.sha256 }),
                );
              });
              callAs(ADMINISTRATOR, "medilab.laboratory.file.version", "read", [
                [saved.version.id],
                ["user_id", "device_id", "size", "sha256", "number"],
              ]).then(([version]) => {
                expect(version).to.deep.include({
                  user_id: [tester.id, tester.name],
                  device_id: [first.id, first.name],
                  size: content.size,
                  sha256: content.sha256,
                  number: 1,
                });
              });
            }),
          );
        }),
      ),
    );
  });

  // Restoring from Medilab Sync's history screen is Medilab Sync's.
  it("TC-WF04-A7 restoring an earlier version saves a new one with its bytes and keeps the others", () => {
    const tag = runTag();
    devices(tag, HEAD).then(([owner]) =>
      ownFolder(owner, `A7 ${tag}`).then((folder) => {
        const saved = [];
        ["result-a.xlsx", "result-b.xlsx", "result-c.xlsx"].reduce(
          (chain, name) =>
            chain.then(() =>
              upload(owner, folder, "result.xlsx", name, { baseVersionId: saved.at(-1)?.id }).then(({ upload: done }) => {
                expect(done.status, name).to.eq("completed");
                saved.push(done.version);
              }),
            ),
          cy.wrap(null),
        );
        cy.then(() => fileAt(owner, folder, "result.xlsx")).then((file) => {
          const [first] = saved;
          api(owner, "POST", `/folders/${folder.id}/files/${file.id}/versions/${first.id}/restore`, {
            headers: { "Idempotency-Key": `${tag}-restore` },
          }).then((response) => {
            const restored = ok(response, "restore").version;
            expect(restored).to.include({ number: 4, source: "restored", sha256: first.sha256, size: first.size });
            downloaded(owner, folder, file, restored.id).then((bytes) => expect(bytes).to.deep.eq({ size: first.size, sha256: first.sha256 }));
            fileAt(owner, folder, "result.xlsx").then((current) => expect(current.current_version.id).to.eq(restored.id));
            versionsOf(file).then((versions) => {
              expect(versions.map(({ number }) => number)).to.deep.eq([1, 2, 3, 4]);
              expect(versions.slice(0, 3).map(({ sha256 }) => sha256)).to.deep.eq(saved.map(({ sha256 }) => sha256));
              expect(versions[3].restored_from_id[0]).to.eq(first.id);
            });
            cy.signInAs("administrator");
            cy.visit(`/odoo/laboratory-files/${file.id}`);
            cy.get(".o_field_widget[name=version_ids] .o_data_row").should("have.length", 4);
            cy.get(".o_field_widget[name=version_ids] .o_data_row")
              .invoke("text")
              .should("match", /Restored/i);
          });
        });
      }),
    );
  });

  // Editing in the desktop program is Medilab Sync's; the lock is what the server holds for it.
  it("TC-WF04-A9 a lock makes a file the holder's alone until it is released", () => {
    const tag = runTag();
    const path = `notes-${tag}.txt`;
    person(TESTER).then((tester) =>
      devices(tag, HEAD, TESTER).then(([owner, holder]) =>
        ownFolder(owner, `A9 ${tag}`).then((folder) => {
          addMember(owner, folder, tester);
          upload(owner, folder, path, "notes-1.txt").then(({ upload: first }) => {
            fileAt(owner, folder, path).then((file) => {
              api(holder, "POST", `/folders/${folder.id}/files/${file.id}/lock`).then((response) =>
                expect(ok(response, "lock").lock.user.id).to.eq(tester.id),
              );
              fileAt(owner, folder, path).then((locked) => expect(locked.lock.user.id, "lock seen by the other member").to.eq(tester.id));

              upload(owner, folder, path, "notes-2.txt", { baseVersionId: first.version.id }).then(({ refused: response }) => {
                refused(response, 409, "locked", "another member saves");
              });
              upload(holder, folder, path, "notes-2.txt", { baseVersionId: first.version.id }).then(({ upload: saved }) =>
                expect(saved.status, "holder saves").to.eq("completed"),
              );

              cy.signInAs("administrator");
              cy.visit("/odoo/laboratory-file-locks");
              search(path);
              cy.contains(".o_data_row", path).should("contain", tester.name);

              api(holder, "DELETE", `/folders/${folder.id}/files/${file.id}/lock`).then((response) => expect(response.status).to.eq(204));
              fileAt(owner, folder, path).then((released) => {
                expect(released.lock).to.be.null;
                upload(owner, folder, path, "notes-3.txt", { baseVersionId: released.current_version.id }).then(({ upload: saved }) =>
                  expect(saved.status, "saves after release").to.eq("completed"),
                );
              });
            });
          });
        }),
      ),
    );
  });

  // The conflict screen of Medilab Sync, and which version counts as the file's, are not asserted.
  it("TC-WF04-E4 an upload from an out-of-date version becomes a conflict version and the current one stays", () => {
    const tag = runTag();
    person(TESTER).then((tester) =>
      devices(tag, HEAD, TESTER).then(([owner, other]) =>
        ownFolder(owner, `E4 ${tag}`).then((folder) => {
          addMember(owner, folder, tester);
          upload(owner, folder, "result.xlsx", "result-a.xlsx").then(({ upload: first }) => {
            upload(other, folder, "result.xlsx", "result-b.xlsx", { baseVersionId: first.version.id }).then(({ upload: second }) => {
              expect(second.status).to.eq("completed");
              upload(owner, folder, "result.xlsx", "result-c.xlsx", { baseVersionId: first.version.id }).then(({ upload: late }) => {
                expect(late.status).to.eq("conflict");
                fileAt(owner, folder, "result.xlsx").then((file) => {
                  expect(file.current_version.id, "the current version stays").to.eq(second.version.id);
                  versionsOf(file).then((versions) => {
                    expect(versions.map(({ source }) => source)).to.include("conflict");
                    const conflict = versions.find(({ source }) => source === "conflict");
                    fixture("result-c.xlsx").then((content) => expect(conflict).to.include({ sha256: content.sha256, size: content.size }));
                    fixture("result-b.xlsx").then((content) =>
                      expect(versions.find(({ id }) => id === second.version.id).sha256).to.eq(content.sha256),
                    );
                    expect(versions).to.have.length(3);
                  });
                  cy.signInAs("administrator");
                  cy.visit(`/odoo/laboratory-files/${file.id}`);
                  cy.get(".o_field_widget[name=version_ids] .o_data_row")
                    .should("have.length", 3)
                    .invoke("text")
                    .should("match", /Conflict/i);
                });
              });
            });
          });
        }),
      ),
    );
  });

  // Signing with another level, the saver's own signing and the department rule are open decisions and not asserted.
  it("TC-WF04-E5 a rejection needs a reason, tells the saver, and a corrected version is signed by the head", () => {
    const tag = runTag();
    person(TESTER).then((tester) =>
      sampleWithoutFolders().then((sample) => {
        callAs(HEAD, "medilab.sample", "action_create_laboratory_folders", [[sample.id]]);
        foldersOfSample(sample).then((folders) =>
          devices(tag, HEAD, TESTER).then(([head, saver]) => {
            const results = folders.find(({ category }) => category === "result");
            addMember(head, results, tester);
            upload(saver, results, `result-${tag}.xlsx`, "result-a.xlsx").then(({ upload: first }) => {
              cy.signInAs("head_of_department");
              callRefused("medilab.laboratory.file.version", "action_reject", [[first.version.id], "  "]).then((message) =>
                expect(message).to.contain("needs a reason"),
              );
              cy.visit(`/odoo/laboratory-file-versions/${first.version.id}`);
              cy.rejectRecord("The lead value does not match the instrument printout.");
              cy.get(".o_form_view .o_field_widget[name=approval_state]").should("contain", "Rejected");

              callAs(
                ADMINISTRATOR,
                "mail.message",
                "search_read",
                [
                  [
                    ["model", "=", "medilab.laboratory.file.version"],
                    ["res_id", "=", first.version.id],
                  ],
                ],
                { fields: ["body", "subject"] },
              ).then((messages) => {
                expect(messages).to.have.length(1);
                expect(messages[0].body).to.contain("was rejected: The lead value does not match the instrument printout.");
                expect(messages[0].subject).to.contain(`result-${tag}.xlsx`);
              });
              callAs(
                ADMINISTRATOR,
                "mail.notification",
                "search_read",
                [
                  [
                    ["mail_message_id.res_id", "=", first.version.id],
                    ["mail_message_id.model", "=", "medilab.laboratory.file.version"],
                  ],
                ],
                {
                  fields: ["res_partner_id"],
                },
              ).then((notified) => {
                callAs(ADMINISTRATOR, "res.users", "read", [[tester.id], ["partner_id"]]).then(([user]) =>
                  expect(notified.map(({ res_partner_id }) => res_partner_id[0])).to.deep.eq([user.partner_id[0]]),
                );
              });

              upload(saver, results, `result-${tag}.xlsx`, "result-b.xlsx", { baseVersionId: first.version.id }).then(({ upload: corrected }) => {
                expect(corrected.status).to.eq("completed");
                cy.signInAs("head_of_department");
                cy.visit(`/odoo/laboratory-file-versions/${corrected.version.id}`);
                cy.get("button[name=action_sign]").click();
                confirmDialog();
                cy.get(".o_form_view .o_field_widget[name=approval_state]").should("contain", "Signed");
                callAs(ADMINISTRATOR, "medilab.laboratory.file.version", "read", [
                  [first.version.id, corrected.version.id],
                  ["approval_state", "number"],
                ]).then((read) => {
                  expect(read.find(({ number }) => number === 1).approval_state, "the rejected version stays rejected").to.eq("rejected");
                  expect(read.find(({ number }) => number === 2).approval_state).to.eq("approved");
                });
              });
            });
          }),
        );
      }),
    );
  });

  // Online editing and the saves of the desktop programs are not covered: the service is declared down or up for the
  // stack, and only the server's side of its absence is asserted.
  it("TC-WF04-E6 with the editing service down, saving, history, download and restore still work", function () {
    cy.env(["editingService"]).then(({ editingService = "down" }) => {
      if (editingService !== "down") this.skip();
      const tag = runTag();
      person(TESTER).then((tester) =>
        sampleWithoutFolders().then((sample) => {
          callAs(HEAD, "medilab.sample", "action_create_laboratory_folders", [[sample.id]]);
          foldersOfSample(sample).then((folders) =>
            devices(tag, HEAD, TESTER).then(([head, saver]) => {
              const results = folders.find(({ category }) => category === "result");
              addMember(head, results, tester);
              upload(saver, results, `result-${tag}.xlsx`, "result-a.xlsx").then(({ upload: first }) =>
                upload(saver, results, `result-${tag}.xlsx`, "result-b.xlsx", { baseVersionId: first.version.id }).then(({ upload: second }) => {
                  expect(second.status).to.eq("completed");
                  fileAt(saver, results, `result-${tag}.xlsx`).then((file) => {
                    cy.signInAs("tester");
                    cy.request({ url: `/medilab/laboratory-files/${file.id}/edit`, failOnStatusCode: false }).then((page) => {
                      expect(page.status, "the editor page").to.eq(503);
                      expect(page.body).to.contain("Online editing is unavailable");
                    });
                    cy.request("/medilab/api/v1/ready").its("status").should("eq", 200);
                    api(saver, "GET", `/folders/${results.id}/files/${file.id}/versions`).then((response) =>
                      expect(ok(response, "history").versions.map(({ number }) => number)).to.deep.eq([2, 1]),
                    );
                    fixture("result-a.xlsx").then((content) => {
                      downloaded(saver, results, file, first.version.id).then((bytes) =>
                        expect(bytes).to.deep.eq({ size: content.size, sha256: content.sha256 }),
                      );
                      api(saver, "POST", `/folders/${results.id}/files/${file.id}/versions/${first.version.id}/restore`, {
                        headers: { "Idempotency-Key": `${tag}-restore` },
                      }).then((response) =>
                        expect(ok(response, "restore").version).to.include({ number: 3, source: "restored", sha256: content.sha256 }),
                      );
                    });
                  });
                }),
              );
            }),
          );
        }),
      );
    });
  });

  it("TC-SF11-A3 an archived folder keeps its versions for download and refuses new uploads", () => {
    const tag = runTag();
    devices(tag, HEAD).then(([owner]) =>
      ownFolder(owner, `A3 ${tag}`).then((folder) =>
        upload(owner, folder, "result.xlsx", "result-a.xlsx").then(({ upload: saved }) => {
          cy.signInAs("administrator");
          cy.openRecord({ model: "medilab.laboratory.folder", id: folder.id });
          cy.get("button[name=action_archive_folder]").click();
          confirmDialog();
          cy.get(".o_form_view .o_statusbar_status").should("contain", "Archived");
          callAs(ADMINISTRATOR, "medilab.laboratory.folder", "read", [[folder.id], ["archived_at", "retention_until"]]).then(([read]) => {
            expect(read.archived_at, "archived at").to.be.a("string");
            expect(read.retention_until, "retention date").to.be.a("string");
            expect(new Date(read.retention_until).getTime(), "retention after the archiving").to.be.greaterThan(
              new Date(`${read.archived_at.replace(" ", "T")}Z`).getTime(),
            );
          });

          fileAt(owner, folder, "result.xlsx").then((file) => {
            api(owner, "GET", `/folders/${folder.id}/files/${file.id}/versions`).then((response) =>
              expect(ok(response, "versions").versions.map(({ id }) => id)).to.deep.eq([saved.version.id]),
            );
            downloaded(owner, folder, file, saved.version.id).then((bytes) =>
              expect(bytes).to.deep.eq({ size: saved.version.size, sha256: saved.version.sha256 }),
            );
          });
          upload(owner, folder, "result.xlsx", "result-b.xlsx", { baseVersionId: saved.version.id }).then(({ refused: response }) =>
            refused(response, 409, "folder_archived", "upload to an archived folder"),
          );
        }),
      ),
    );
  });

  it("TC-SF11-A4 a folder turned off refuses uploads but not downloads, and accepts uploads again once turned on", () => {
    const tag = runTag();
    devices(tag, HEAD).then(([owner]) =>
      ownFolder(owner, `A4 ${tag}`).then((folder) =>
        upload(owner, folder, "result.xlsx", "result-a.xlsx").then(({ upload: first }) => {
          cy.signInAs("administrator");
          cy.openRecord({ model: "medilab.laboratory.folder", id: folder.id });
          cy.get("button[name=action_turn_off]").click();
          confirmDialog();
          cy.get(".o_form_view .o_statusbar_status").should("contain", "Turned Off");

          upload(owner, folder, "result.xlsx", "result-b.xlsx", { baseVersionId: first.version.id }).then(({ refused: response }) =>
            refused(response, 409, "folder_disabled", "upload to a folder turned off"),
          );
          fileAt(owner, folder, "result.xlsx").then((file) =>
            downloaded(owner, folder, file, first.version.id).then((bytes) =>
              expect(bytes).to.deep.eq({ size: first.version.size, sha256: first.version.sha256 }),
            ),
          );

          cy.signInAs("administrator");
          cy.openRecord({ model: "medilab.laboratory.folder", id: folder.id });
          cy.get("button[name=action_turn_on]").click();
          cy.get(".o_form_view .o_statusbar_status").should("contain", "In Use");
          upload(owner, folder, "result.xlsx", "result-b.xlsx", { baseVersionId: first.version.id }).then(({ upload: second }) =>
            expect(second.status, "upload once turned on").to.eq("completed"),
          );
        }),
      ),
    );
  });

  it("TC-SF11-E1 an administrator releases a lock a tester left, and its audit entry names them", () => {
    const tag = runTag();
    const path = `notes-${tag}.txt`;
    person(TESTER).then((tester) =>
      person(ADMINISTRATOR).then((administrator) =>
        devices(tag, HEAD, TESTER).then(([owner, holder]) =>
          ownFolder(owner, `E1 ${tag}`).then((folder) => {
            addMember(owner, folder, tester);
            upload(owner, folder, path, "notes-1.txt").then(({ upload: first }) =>
              fileAt(owner, folder, path).then((file) => {
                api(holder, "POST", `/folders/${folder.id}/files/${file.id}/lock`).then((response) => {
                  const { lock } = ok(response, "lock");
                  upload(owner, folder, path, "notes-2.txt", { baseVersionId: first.version.id }).then(({ refused: refusal }) =>
                    refused(refusal, 409, "locked", "upload to a locked file"),
                  );

                  cy.signInAs("administrator");
                  cy.visit("/odoo/laboratory-file-locks");
                  search(path);
                  cy.contains(".o_data_row", path).find("button[name=action_release]").click();
                  cy.contains(".o_data_row", path).should("not.exist");

                  upload(owner, folder, path, "notes-2.txt", { baseVersionId: first.version.id }).then(({ upload: saved }) =>
                    expect(saved.status, "upload after the release").to.eq("completed"),
                  );
                  callAs(
                    ADMINISTRATOR,
                    "medilab.audit.entry",
                    "search_read",
                    [
                      [
                        ["document_model", "=", "medilab.laboratory.file.lock"],
                        ["document_id", "=", lock.id],
                      ],
                    ],
                    {
                      fields: ["action", "source", "user_id"],
                      order: "id",
                    },
                  ).then((entries) => {
                    expect(entries.map(({ action }) => action)).to.deep.eq(["create", "edit"]);
                    expect(entries[0]).to.deep.include({ source: "api", user_id: [tester.id, tester.name] });
                    expect(entries[1]).to.deep.include({ source: "screen", user_id: [administrator.id, administrator.name] });
                  });
                });
              }),
            );
          }),
        ),
      ),
    );
  });

  // Only the editor page's answer to a file that is not edited online is the same in every state of the service.
  it("TC-F55-03 an Office file of a raw-data folder is not edited online, whatever the state of the service", () => {
    const tag = runTag();
    person(TESTER).then((tester) =>
      sampleWithoutFolders().then((sample) => {
        callAs(HEAD, "medilab.sample", "action_create_laboratory_folders", [[sample.id]]);
        foldersOfSample(sample).then((folders) =>
          devices(tag, HEAD, TESTER).then(([head, saver]) => {
            const raw = folders.find(({ category }) => category === "raw");
            const results = folders.find(({ category }) => category === "result");
            [raw, results].forEach((folder) => addMember(head, folder, tester));
            upload(saver, raw, `raw-${tag}.xlsx`, "result-a.xlsx");
            upload(saver, results, `result-${tag}.xlsx`, "result-a.xlsx");
            fileAt(saver, raw, `raw-${tag}.xlsx`).then((rawFile) =>
              fileAt(saver, results, `result-${tag}.xlsx`).then((resultFile) => {
                cy.signInAs("tester");
                cy.request({ url: `/medilab/laboratory-files/${rawFile.id}/edit`, failOnStatusCode: false }).then((page) => {
                  expect(page.status, "raw-data folder").to.eq(409);
                  expect(page.body).to.contain("Only Word, Excel and PowerPoint files of result and working folders");
                });
                // The same file in a result folder is edited online, so what it answers is the service's own: its page or its absence.
                cy.request({ url: `/medilab/laboratory-files/${resultFile.id}/edit`, failOnStatusCode: false })
                  .its("status")
                  .should("be.oneOf", [200, 503]);
              }),
            );
          }),
        );
      }),
    );
  });

  // The thirty minutes are read from the lock; waiting them out, and the job that expires locks, are not exercised.
  it("TC-F56-02 a lock lasts thirty minutes, renewing extends it, and an expired lock no longer blocks", () => {
    const tag = runTag();
    const path = `notes-${tag}.txt`;
    person(TESTER).then((tester) =>
      devices(tag, HEAD, TESTER).then(([owner, holder]) =>
        ownFolder(owner, `F56 ${tag}`).then((folder) => {
          addMember(owner, folder, tester);
          upload(owner, folder, path, "notes-1.txt").then(({ upload: first }) =>
            fileAt(owner, folder, path).then((file) => {
              api(holder, "POST", `/folders/${folder.id}/files/${file.id}/lock`).then((response) => {
                const { lock } = ok(response, "lock");
                expect(minutesFromNow(lock.expires_at), "minutes until expiry").to.be.within(LOCK_MINUTES - 2, LOCK_MINUTES + 0.5);

                // Shorten the lock, as time passing would, then renew it.
                setLockExpiry(lock.id, 5);
                api(holder, "POST", `/folders/${folder.id}/files/${file.id}/lock/renew`).then((renewed) => {
                  expect(minutesFromNow(ok(renewed, "renew").lock.expires_at), "minutes until expiry once renewed").to.be.within(
                    LOCK_MINUTES - 2,
                    LOCK_MINUTES + 0.5,
                  );
                });

                // An expired lock is not in force: the other member saves.
                setLockExpiry(lock.id, -1);
                fileAt(owner, folder, path).then((listed) => expect(listed.lock, "lock in force").to.be.null);
                upload(owner, folder, path, "notes-2.txt", { baseVersionId: first.version.id }).then(({ upload: saved }) =>
                  expect(saved.status).to.eq("completed"),
                );
              });
            }),
          );
        }),
      ),
    );
  });
});
