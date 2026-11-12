import { call, callAs, callRefused } from "../../../support/odoo";
import { openTab, pick, save, search } from "../../../support/form";
import { api, leaveBackOffice, ok, refused, sha256Of, signInAgain, signInDevice, signOutDevices } from "./device";
import {
  ADMINISTRATOR,
  HEAD,
  MICROBIOLOGY_TESTER,
  OTHER_TESTER,
  SALES,
  TESTER,
  foldersOfSample,
  membersOf,
  ownFolder,
  person,
  runTag,
  sampleWithoutFolders,
} from "./setup";

// The bottled water in testing and the result file of its folders, which the tests only read.
const SEEDED_SAMPLE = "sol_demo.demo_sample_bottled_water_testing";
const SEEDED_FILE = "Pb-ket-qua.xlsx";

function confirmDialog() {
  cy.get(".modal-footer .btn-primary").click();
}

// A person's device adds a person to a folder, as the owner's Medilab Sync does.
function addMember(device, folder, user) {
  return api(device, "POST", `/folders/${folder.id}/members`, { body: { user_id: user.id } }).then(
    (response) => ok(response, `add ${user.name}`).member,
  );
}

// The devices of the people, signed in as computers named after the test.
function devices(tag, ...logins) {
  const signedIn = [];
  logins.forEach((login, index) => signInDevice(login, `PC-${tag}-${index}`).then((device) => signedIn.push(device)));
  return cy.then(() => signedIn);
}

describe("WF-07 laboratory files", () => {
  afterEach(signOutDevices);

  // Medilab Sync only shows and binds the folders to local directories, which the Sync suite covers.
  it("TC-SF11-M the head creates the folders of a sample, adds a tester, and the tester sees both", () => {
    sampleWithoutFolders().then((sample) => {
      cy.signInAs("head_of_department");
      cy.openRecord({ model: "medilab.sample", id: sample.id });
      cy.get("button[name=action_open_laboratory_folders]").should("not.exist");
      cy.get("button[name=action_create_laboratory_folders]").click();

      cy.contains(".o_data_row", `${sample.code} Raw Data`).should("be.visible");
      cy.contains(".o_data_row", `${sample.code} Results`).should("be.visible");
      cy.get(".o_data_row").should("have.length", 2);

      // A second attempt adds none, and the sample no longer offers to create them.
      cy.openRecord({ model: "medilab.sample", id: sample.id });
      cy.get("button[name=action_open_laboratory_folders]").should("be.visible");
      cy.get("button[name=action_create_laboratory_folders]").should("not.exist");
      callAs(HEAD, "medilab.sample", "action_create_laboratory_folders", [[sample.id]]);
      foldersOfSample(sample).then((folders) => {
        expect(folders.map(({ category }) => category)).to.have.members(["raw", "result"]);
        leaveBackOffice();

        person(HEAD).then((owner) =>
          person(TESTER).then((tester) =>
            devices(runTag(), HEAD, TESTER).then(([head, testerDevice]) => {
              folders.forEach((folder) => expect(folder.owner_id[0], folder.name).to.eq(owner.id));
              folders.forEach((folder) => addMember(head, folder, tester));

              membersOf(folders.map(({ id }) => id)).then((members) => {
                folders.forEach((folder) => {
                  const roles = members.filter((member) => member.folder_id[0] === folder.id).map((member) => [member.user_id[0], member.role]);
                  expect(roles, folder.name).to.have.deep.members([
                    [folder.owner_id[0], "owner"],
                    [tester.id, "member"],
                  ]);
                });
              });
              api(testerDevice, "GET", "/folders").then((response) => {
                const listed = ok(response, "tester lists folders").folders.filter(({ sample: own }) => own?.id === sample.id);
                expect(listed.map(({ id }) => id)).to.have.members(folders.map(({ id }) => id));
                listed.forEach((folder) => expect(folder, folder.name).to.include({ role: "member", can_share: false }));
              });
              folders.forEach((folder) =>
                api(testerDevice, "GET", `/folders/${folder.id}/files`).then((response) => ok(response, `tester reads ${folder.name}`)),
              );
            }),
          ),
        );
      });
    });
  });

  // The owner's own screen is Medilab Sync; the administrator's Members tab is the back-office view of the same members.
  it("TC-SF11-A1 the owner adds and removes members, and a removed member loses the folder", () => {
    const tag = runTag();
    person(HEAD).then((head) =>
      person(OTHER_TESTER).then((chemist) =>
        devices(tag, HEAD, OTHER_TESTER).then(([owner, member]) => {
          ownFolder(owner, `A1 ${tag}`).then((folder) => {
            expect(folder).to.include({ role: "owner", can_share: true });

            api(owner, "GET", `/folders/${folder.id}/member-candidates`, { qs: { q: "chem" } }).then((response) => {
              expect(ok(response, "candidates").candidates.map(({ id }) => id)).to.include(chemist.id);
            });
            // Somebody who may not use the laboratory files is not offered and is refused.
            person(SALES).then((sales) =>
              api(owner, "POST", `/folders/${folder.id}/members`, { body: { user_id: sales.id } }).then((response) =>
                refused(response, 422, "not_eligible", "add sales"),
              ),
            );
            api(member, "GET", `/folders/${folder.id}`).then((response) => refused(response, 404, "not_found", "before being added"));

            addMember(owner, folder, chemist).then((added) => {
              expect(added).to.deep.include({ role: "member", user: { id: chemist.id, name: chemist.name } });
              api(member, "GET", `/folders/${folder.id}`).then((response) => {
                expect(ok(response, "member reads folder").folder).to.include({ role: "member", can_share: false });
              });
              api(member, "POST", `/folders/${folder.id}/members`, { body: { user_id: chemist.id } }).then((response) =>
                refused(response, 403, "permission_denied", "member adds"),
              );

              api(owner, "GET", `/folders/${folder.id}/members`).then((response) => {
                const owning = ok(response, "members").members.find(({ role }) => role === "owner");
                expect(owning.user.id).to.eq(head.id);
                api(owner, "DELETE", `/folders/${folder.id}/members/${owning.id}`).then((deleted) =>
                  refused(deleted, 400, "invalid_request", "remove owner"),
                );
              });

              api(owner, "DELETE", `/folders/${folder.id}/members/${added.id}`).then((response) => expect(response.status).to.eq(204));
              api(member, "GET", `/folders/${folder.id}`).then((response) => refused(response, 404, "not_found", "after removal"));
              api(member, "GET", "/folders").then((response) => {
                expect(ok(response, "member lists folders").folders.map(({ id }) => id)).not.to.include(folder.id);
              });
            });

            cy.signInAs("administrator");
            cy.openRecord({ model: "medilab.laboratory.folder", id: folder.id });
            openTab("members");
            cy.get(".o_field_widget[name=member_ids] .o_data_row").should("have.length", 1).and("contain", head.name);
            cy.get(".o_field_widget[name=member_ids]").should("not.contain", chemist.name);
          });
        }),
      ),
    );
  });

  // Binding each computer's local folder is Medilab Sync's; the server knows the two computers and gives both the folders.
  it("TC-SF11-A2 a tester signs in a second computer and both reach the folders", () => {
    const tag = runTag();
    person(TESTER).then((tester) =>
      devices(tag, HEAD, TESTER, TESTER).then(([owner, first, second]) => {
        expect(first.clientUid, "installation ids").not.to.eq(second.clientUid);
        ownFolder(owner, `A2 ${tag}`).then((folder) => {
          addMember(owner, folder, tester);
          [first, second].forEach((device) => {
            api(device, "GET", "/folders").then((response) => {
              expect(ok(response, `${device.name} lists folders`).folders.find(({ id }) => id === folder.id)).to.include({ role: "member" });
            });
            api(device, "GET", `/folders/${folder.id}/files`).then((response) => ok(response, `${device.name} lists files`));
          });
          api(first, "GET", "/devices").then((response) => {
            const listed = ok(response, "devices").devices;
            expect(listed.find(({ id }) => id === first.id)).to.include({ current: true });
            expect(listed.find(({ id }) => id === second.id)).to.include({ current: false });
          });
          callAs(ADMINISTRATOR, "medilab.laboratory.device", "read", [
            [first.id, second.id],
            ["client_uid", "user_id", "status"],
          ]).then((devicesRead) => {
            expect(devicesRead.map(({ client_uid }) => client_uid)).to.have.members([first.clientUid, second.clientUid]);
            devicesRead.forEach((device) => expect(device).to.deep.include({ user_id: [tester.id, tester.name], status: "signed_in" }));
          });

          cy.signInAs("administrator");
          cy.visit("/odoo/laboratory-devices");
          search(`PC-${tag}`);
          [first, second].forEach((device) => cy.contains(".o_data_row", device.name).should("contain", tester.name).and("contain", "Signed In"));
        });
      }),
    );
  });

  it("TC-SF11-E2 an administrator revokes one computer and the other keeps working", () => {
    const tag = runTag();
    person(TESTER).then((tester) =>
      devices(tag, HEAD, TESTER, TESTER).then(([owner, revoked, other]) => {
        ownFolder(owner, `E2 ${tag}`).then((folder) => {
          addMember(owner, folder, tester);
          [revoked, other].forEach((device) => api(device, "GET", "/folders").then((response) => ok(response, `${device.name} before`)));

          cy.signInAs("administrator");
          cy.visit("/odoo/laboratory-devices");
          search(revoked.name);
          cy.contains(".o_data_row", revoked.name).find("button[name=action_revoke]").click();
          confirmDialog();
          cy.contains(".o_data_row", revoked.name).should("contain", "Revoked").find("button[name=action_revoke]").should("not.exist");
          search(other.name);
          cy.contains(".o_data_row", other.name).should("contain", "Signed In");
          leaveBackOffice();

          api(revoked, "GET", "/folders").then((response) => refused(response, 401, "invalid_key", "revoked key"));
          api(revoked, "GET", `/folders/${folder.id}/files`).then((response) => refused(response, 401, "invalid_key", "revoked key on files"));
          signInAgain(revoked).then((response) => {
            expect(response.status).to.eq(403);
            expect(response.body.error.code).to.eq("device_revoked");
          });
          api(other, "GET", "/folders").then((response) => {
            expect(ok(response, "other computer").folders.map(({ id }) => id)).to.include(folder.id);
          });
          api(other, "GET", `/folders/${folder.id}/files`).then((response) => ok(response, "other computer files"));
        });
      }),
    );
  });

  it("TC-WF04-A10 a member browses a sample's folders, files and versions and downloads the exact bytes", () => {
    cy.signInAs("tester");
    cy.openRecord(SEEDED_SAMPLE).then((sample) => {
      call("medilab.laboratory.folder", "search_read", [[["sample_id", "=", sample.id]]], { fields: ["name"] }).then((folders) => {
        expect(folders, "folders of the sample").not.to.be.empty;
        cy.get("button[name=action_open_laboratory_folders]").click();
        folders.forEach(({ name }) => cy.contains(".o_data_row", name).should("be.visible"));
      });

      call(
        "medilab.laboratory.file",
        "search_read",
        [
          [
            ["path", "=", SEEDED_FILE],
            ["folder_id.sample_id", "=", sample.id],
          ],
        ],
        { fields: ["folder_id", "current_version_id"] },
      ).then(([file]) => {
        cy.visit(`/odoo/laboratory-folders/${file.folder_id[0]}`);
        openTab("files");
        cy.contains(".o_field_widget[name=file_ids] .o_data_row", SEEDED_FILE).should("be.visible");

        // A file is opened by its address; a click on its row is for the editor where the Files list has one.
        cy.visit(`/odoo/laboratory-files/${file.id}`);
        call("medilab.laboratory.file.version", "search_read", [[["file_id", "=", file.id]]], { fields: ["number", "sha256", "size"] }).then(
          (versions) => {
            const current = versions.find(({ id }) => id === file.current_version_id[0]);
            expect(current.number, "current version is the newest").to.eq(Math.max(...versions.map(({ number }) => number)));
            cy.get(".o_field_widget[name=version_ids] .o_data_row td[name=number]")
              .should("have.length", versions.length)
              .then((cells) =>
                expect(cells.toArray().map((cell) => cell.textContent.trim())).to.have.members(versions.map(({ number }) => String(number))),
              );

            cy.visit(`/odoo/laboratory-file-versions/${current.id}`);
            cy.get(".o_field_widget[name=sha256]").should("contain", current.sha256);
            cy.window().then((win) => cy.stub(win, "open").as("open"));
            cy.get("button[name=action_download]").click();
            cy.get("@open").should("have.been.calledOnce");
            cy.get("@open")
              .its("firstCall.args.0")
              .then((url) => cy.request({ url, encoding: "binary" }))
              .then((response) => {
                expect(response.status).to.eq(200);
                expect(response.body.length, "downloaded size").to.eq(current.size);
                return sha256Of(response.body);
              })
              .then((digest) => expect(digest, "downloaded bytes").to.eq(current.sha256));
          },
        );
      });
    });
  });

  // Partial: the member of a hidden sample is not covered, since every holder of the files permission sees every sample.
  it("TC-F53-03 a person who is not a member neither sees nor reaches a folder", () => {
    const tag = runTag();
    person(OTHER_TESTER).then((chemist) =>
      devices(tag, HEAD, OTHER_TESTER).then(([owner, outsider]) => {
        ownFolder(owner, `F53 ${tag} hidden`).then((hidden) =>
          ownFolder(owner, `F53 ${tag} shared`).then((shared) => {
            addMember(owner, shared, chemist);

            [`/folders/${hidden.id}`, `/folders/${hidden.id}/members`, `/folders/${hidden.id}/files`, `/folders/${hidden.id}/changes`].forEach(
              (path) => api(outsider, "GET", path).then((response) => refused(response, 404, "not_found", path)),
            );
            api(outsider, "POST", `/folders/${hidden.id}/members`, { body: { user_id: chemist.id } }).then((response) =>
              refused(response, 404, "not_found", "join the folder"),
            );
            api(outsider, "GET", "/folders").then((response) => {
              const ids = ok(response, "outsider lists folders").folders.map(({ id }) => id);
              expect(ids).to.include(shared.id);
              expect(ids).not.to.include(hidden.id);
            });
            callAs(OTHER_TESTER, "medilab.laboratory.folder", "search_read", [[["id", "in", [hidden.id, shared.id]]]], { fields: ["name"] }).then(
              (read) => {
                expect(read.map(({ id }) => id)).to.deep.eq([shared.id]);
              },
            );

            cy.signInAs("chemistry_tester");
            cy.visit("/odoo/laboratory-folders");
            search(`F53 ${tag}`);
            cy.contains(".o_data_row", shared.name).should("be.visible");
            cy.contains(".o_data_row", hidden.name).should("not.exist");
          }),
        );
      }),
    );
  });

  it("TC-F54-03 a saved version never changes and the back office has nothing to change it with", () => {
    const protectedWrites = [{ sha256: "0".repeat(64) }, { size: 1 }, { number: 99 }, { source: "restored" }];
    cy.signInAs("administrator");
    cy.openRecord(SEEDED_SAMPLE).then((sample) => {
      call(
        "medilab.laboratory.file",
        "search_read",
        [
          [
            ["path", "=", SEEDED_FILE],
            ["folder_id.sample_id", "=", sample.id],
          ],
        ],
        { fields: ["id"] },
      ).then(([file]) => {
        const fields = ["file_id", "number", "source", "size", "sha256", "user_id", "device_id", "create_date"];
        call("medilab.laboratory.file.version", "search_read", [[["file_id", "=", file.id]]], { fields }).then((before) => {
          const [version] = before;
          ["administrator", "tester"].forEach((role) => {
            cy.signInAs(role);
            protectedWrites.forEach((values) =>
              callRefused("medilab.laboratory.file.version", "write", [[version.id], values]).then((message) =>
                expect(message, `${role} writes ${Object.keys(values)}`).to.contain("never change"),
              ),
            );
            callRefused("medilab.laboratory.file.version", "unlink", [[version.id]]).then((message) =>
              expect(message, `${role} deletes`).to.match(/not allowed to delete/),
            );
            callRefused("medilab.laboratory.file.version", "create", [
              { file_id: file.id, number: 99, source: "restored", size: 1, sha256: "0".repeat(64) },
            ]).then((message) => expect(message, `${role} creates`).to.match(/not allowed to create/));
          });
          call("medilab.laboratory.file.version", "search_read", [[["file_id", "=", file.id]]], { fields }).then((after) =>
            expect(after).to.deep.eq(before),
          );

          cy.visit(`/odoo/laboratory-file-versions/${version.id}`);
          cy.get("button[name=action_download]").should("be.visible");
          cy.get(".o_form_view input, .o_form_view textarea").should("not.exist");
          cy.get(".o_form_button_save").should("not.exist");
          cy.visit("/odoo/laboratory-file-versions");
          cy.get(".o_data_row").should("be.visible");
          cy.get(".o_list_button_add").should("not.exist");
        });
      });
    });
  });

  // Who the previous owner still is follows the folder-access rules; what is kept after the retention date is not asserted.
  it("TC-F58-02 changing the owner keeps the previous owner as a member", () => {
    const tag = runTag();
    person(MICROBIOLOGY_TESTER).then((successor) =>
      person(HEAD).then((previous) =>
        devices(tag, HEAD, MICROBIOLOGY_TESTER, OTHER_TESTER).then(([oldOwner, newOwner, other]) =>
          person(OTHER_TESTER).then((chemist) =>
            ownFolder(oldOwner, `F58 ${tag}`).then((folder) => {
              cy.signInAs("administrator");
              cy.openRecord({ model: "medilab.laboratory.folder", id: folder.id });
              pick("owner_id", successor.name);
              save();
              openTab("members");
              cy.get(".o_field_widget[name=member_ids] .o_data_row").should("have.length", 2);
              cy.contains(".o_field_widget[name=member_ids] .o_data_row", successor.name).invoke("text").should("match", /owner/i);
              cy.contains(".o_field_widget[name=member_ids] .o_data_row", previous.name)
                .invoke("text")
                .should("match", /member/i);

              // An owner who may not use the laboratory files is refused, and the folder keeps its owner.
              person(SALES).then((sales) =>
                callRefused("medilab.laboratory.folder", "write", [[folder.id], { owner_id: sales.id }]).then(
                  (message) => expect(message).to.be.a("string").and.not.be.empty,
                ),
              );
              callAs(ADMINISTRATOR, "medilab.laboratory.folder", "read", [[folder.id], ["owner_id"]]).then(([read]) =>
                expect(read.owner_id[0]).to.eq(successor.id),
              );
              membersOf([folder.id]).then((members) =>
                expect(members.map(({ user_id, role }) => [user_id[0], role])).to.have.deep.members([
                  [successor.id, "owner"],
                  [previous.id, "member"],
                ]),
              );
              leaveBackOffice();

              api(oldOwner, "GET", `/folders/${folder.id}`).then((response) =>
                expect(ok(response, "previous owner reads").folder).to.include({ role: "member", can_share: false }),
              );
              api(oldOwner, "POST", `/folders/${folder.id}/members`, { body: { user_id: chemist.id } }).then((response) =>
                refused(response, 403, "permission_denied", "previous owner shares"),
              );
              api(newOwner, "GET", `/folders/${folder.id}`).then((response) =>
                expect(ok(response, "new owner reads").folder).to.include({ role: "owner", can_share: true }),
              );
              addMember(newOwner, folder, chemist);
              api(other, "GET", `/folders/${folder.id}`).then((response) =>
                expect(ok(response, "added by the new owner").folder).to.include({ role: "member" }),
              );
            }),
          ),
        ),
      ),
    );
  });
});
