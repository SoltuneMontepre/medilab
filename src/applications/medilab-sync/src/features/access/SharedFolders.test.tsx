import { describe, expect, test } from "bun:test";
import { renderToString } from "react-dom/server";
import { LocaleProvider } from "../../locale";
import { UnboundFolderList } from "./SharedFolders";

describe("UnboundFolderList", () => {
  test("names each folder, its owner and sample, and offers to choose a local folder", () => {
    const html = renderToString(
      <LocaleProvider locale="en">
        <UnboundFolderList
          rows={[
            { id: 7, name: "PTN.1-raw", logical_root: "PTN.1-raw", owner_name: "Lan", my_role: "upload", sample_code: "PTN.1", category: "raw" },
          ]}
          busy={false}
          onBind={() => {}}
        />
      </LocaleProvider>,
    );
    expect(html).toContain("PTN.1-raw");
    expect(html).toContain("Lan");
    expect(html).toContain("Raw data");
    expect(html).toContain(">Choose local folder</button>");
  });
});
