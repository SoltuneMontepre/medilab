import { describe, expect, test } from "bun:test";
import { renderToString } from "react-dom/server";
import { LocaleProvider } from "../../locale";
import { createStatusFixture } from "../../test/syncFixtures";
import type { StatusDto } from "../../types";
import { AppHeader } from "./AppHeader";

/** Render header (tiếng Việt) với trạng thái và hai cờ bận cho trước. */
function renderHeader(status: StatusDto, busy: boolean, toggleBusy: boolean): string {
  return renderToString(
    <LocaleProvider locale="vi">
      <AppHeader
        status={status}
        busy={busy}
        toggleBusy={toggleBusy}
        locale="vi"
        onLocaleChange={() => {}}
        onToggleSync={() => {}}
        onLogout={() => {}}
      />
    </LocaleProvider>,
  );
}

/** Thẻ mở của nút có nhãn `label`; lỗi nếu không có nút đó. */
function buttonTag(html: string, label: string): string {
  const match = html.match(new RegExp(`<button([^>]*)>${label}</button>`));
  if (!match) {
    throw new Error(`button "${label}" not found in ${html}`);
  }
  return match[1];
}

describe("AppHeader Pause/Resume", () => {
  test("A: việc khác của app đang chạy (busy) khi đang upload — Tạm dừng vẫn bấm được", () => {
    const status = createStatusFixture({ paused: false, uploading: 2, pending: 2 });
    const tag = buttonTag(renderHeader(status, true, false), "Tạm dừng");
    expect(tag).not.toContain("disabled");
  });

  test("B: lệnh tạm dừng/tiếp tục đang chạy — nút bị khóa", () => {
    const status = createStatusFixture({ paused: false, uploading: 2 });
    const tag = buttonTag(renderHeader(status, false, true), "Tạm dừng");
    expect(tag).toContain("disabled");
  });

  test("C: đang tạm dừng, việc khác đang chạy — Tiếp tục vẫn bấm được", () => {
    const status = createStatusFixture({ paused: true });
    const tag = buttonTag(renderHeader(status, true, false), "Tiếp tục");
    expect(tag).not.toContain("disabled");
  });
});
