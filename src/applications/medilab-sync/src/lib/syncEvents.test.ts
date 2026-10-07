import { expect, test } from "bun:test";
import type { ProgressDeltaDto, RemoteFileRow, StatusDto } from "../types";
import {
  applyProgressDelta,
  createRemoteFilesRefreshController,
  isFolderEqual,
  isJobEqual,
  isRemoteFileEqual,
  mergeFolders,
  mergeJobs,
  mergeRemoteFiles,
  mergeStatusSnapshot,
} from "./syncEvents";
import { createRemoteFilesFixture, createStatusFixture } from "../test/syncFixtures";

/** Tạo promise có thể điều khiển thủ công thời điểm giải quyết. */
function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

test("progress event cập nhật chính xác một job và giữ nguyên reference các phần còn lại", () => {
  const initial = createStatusFixture();
  const delta: ProgressDeltaDto = {
    jobId: 101,
    done: 500,
    total: 1000,
  };

  const next = applyProgressDelta(initial, delta);

  // Job mục tiêu được cập nhật
  expect(next.jobs[0].bytes_done).toBe(500);
  expect(next.jobs[0].bytes_total).toBe(1000);
  expect(next.jobs[0]).not.toBe(initial.jobs[0]);

  // Job không liên quan giữ nguyên identity
  expect(next.jobs[1]).toBe(initial.jobs[1]);

  // Mảng folders giữ nguyên identity
  expect(next.folders).toBe(initial.folders);
});

test("progress event của nhiều job đang chạy song song không ghi đè tiến độ của nhau", () => {
  const base = createStatusFixture();
  const running = (id: number, operation: string): StatusDto["jobs"][number] => ({
    ...base.jobs[0],
    id,
    file_id: id + 100,
    relative_path: `f${id}.bin`,
    operation,
    status: "running",
    bytes_done: 0,
    bytes_total: 1000,
  });
  let status: StatusDto = {
    ...base,
    uploading: 2,
    downloading: 2,
    jobs: [running(1, "upload"), running(2, "upload"), running(3, "download"), running(4, "download")],
  };
  // Delta đến xen kẽ như khi 2 upload + 2 download chạy cùng lúc.
  const deltas: ProgressDeltaDto[] = [
    { jobId: 1, done: 100, total: 1000 },
    { jobId: 3, done: 300, total: 1000 },
    { jobId: 2, done: 200, total: 1000 },
    { jobId: 4, done: 400, total: 1000 },
    { jobId: 1, done: 500, total: 1000 },
  ];
  for (const delta of deltas) {
    status = applyProgressDelta(status, delta);
  }

  expect(status.jobs.map((job) => [job.id, job.bytes_done])).toEqual([
    [1, 500],
    [2, 200],
    [3, 300],
    [4, 400],
  ]);
  expect(status.uploading).toBe(2);
  expect(status.downloading).toBe(2);
});

test("progress event với job không tồn tại là no-op và giữ nguyên reference ban đầu", () => {
  const initial = createStatusFixture();
  const delta: ProgressDeltaDto = {
    jobId: 999,
    done: 100,
    total: 1000,
  };

  const next = applyProgressDelta(initial, delta);
  expect(next).toBe(initial);
});

test("progress event với giá trị done và total không đổi là no-op", () => {
  const initial = createStatusFixture();
  const delta: ProgressDeltaDto = {
    jobId: 101,
    done: 200,
    total: 1000,
  };

  const next = applyProgressDelta(initial, delta);
  expect(next).toBe(initial);
});

test("refresh controller: một invalidation kích hoạt một lượt fetch và cập nhật kết quả", async () => {
  const fakeFiles: RemoteFileRow[] = [
    {
      id: 1,
      folder_id: 1,
      relative_path: "file1.txt",
      remote_file_id: 10,
      remote_version_id: 20,
      status: "synced",
    },
  ];

  let fetchCount = 0;
  const loadedList: RemoteFileRow[][] = [];

  const controller = createRemoteFilesRefreshController({
    fetcher: async () => {
      fetchCount += 1;
      return fakeFiles;
    },
    onLoaded: (files) => {
      loadedList.push(files);
    },
  });

  await controller.invalidate();

  expect(fetchCount).toBe(1);
  expect(loadedList).toHaveLength(1);
  expect(loadedList[0]).toEqual(fakeFiles);
});

test("refresh controller: nhiều invalidation dồn dập trong lúc fetch chỉ tạo tối đa một lượt follow-up", async () => {
  let fetchCount = 0;
  const deferred1 = createDeferred<RemoteFileRow[]>();
  const deferred2 = createDeferred<RemoteFileRow[]>();
  const loadedList: RemoteFileRow[][] = [];

  const controller = createRemoteFilesRefreshController({
    fetcher: async () => {
      fetchCount += 1;
      if (fetchCount === 1) {
        return deferred1.promise;
      }
      return deferred2.promise;
    },
    onLoaded: (files) => {
      loadedList.push(files);
    },
  });

  // Lần gọi 1 bắt đầu và đang in-flight
  const firstPromise = controller.invalidate();
  expect(controller.isInFlight()).toBe(true);
  expect(fetchCount).toBe(1);

  // 3 lần invalidation dồn dập tới khi lần 1 chưa xong
  const p2 = controller.invalidate();
  const p3 = controller.invalidate();
  const p4 = controller.invalidate();

  expect(controller.isQueued()).toBe(true);
  // Không được phát thêm fetch mới trong lúc fetch cũ chưa xong
  expect(fetchCount).toBe(1);

  // Kết thúc lượt 1
  deferred1.resolve([{ id: 1, folder_id: 1, relative_path: "a.txt", remote_file_id: 1, remote_version_id: 1, status: "synced" }]);
  await firstPromise;

  // Lượt 2 follow-up bắt đầu chạy
  expect(fetchCount).toBe(2);

  // Kết thúc lượt 2
  deferred2.resolve([{ id: 2, folder_id: 1, relative_path: "b.txt", remote_file_id: 2, remote_version_id: 2, status: "synced" }]);
  await Promise.all([p2, p3, p4]);

  expect(fetchCount).toBe(2);
  expect(loadedList).toHaveLength(2);
  expect(controller.isInFlight()).toBe(false);
  expect(controller.isQueued()).toBe(false);
});

test("refresh controller: cancel hủy bỏ việc tiếp nhận kết quả và ngăn follow-up", async () => {
  let fetchCount = 0;
  const deferred = createDeferred<RemoteFileRow[]>();
  const loadedList: RemoteFileRow[][] = [];

  const controller = createRemoteFilesRefreshController({
    fetcher: async () => {
      fetchCount += 1;
      return deferred.promise;
    },
    onLoaded: (files) => {
      loadedList.push(files);
    },
  });

  const p1 = controller.invalidate();
  void controller.invalidate(); // Queued follow-up
  expect(controller.isQueued()).toBe(true);

  // Hủy controller trước khi response trả về
  controller.cancel();

  deferred.resolve([]);
  await p1;

  expect(loadedList).toHaveLength(0);
  expect(fetchCount).toBe(1);
  expect(controller.isQueued()).toBe(false);
  expect(controller.isInFlight()).toBe(false);
});

test("sự kiện trạng thái độc lập không tự động gọi fetch danh sách tệp", () => {
  let fetchCalled = false;
  const controller = createRemoteFilesRefreshController({
    fetcher: async () => {
      fetchCalled = true;
      return [];
    },
    onLoaded: () => {},
  });

  // Mô phỏng nhận sự kiện status thông thường
  const status = createStatusFixture();
  expect(status.logged_in).toBe(true);

  // Không gọi controller.invalidate(), fetcher không được kích hoạt
  expect(fetchCalled).toBe(false);
  expect(controller.isInFlight()).toBe(false);
});

test("mergeStatusSnapshot: snapshot giống hệt giá trị trả về chính xác reference cũ (prev === next)", () => {
  const initial = createStatusFixture();
  // Tạo một snapshot mới hoàn toàn với các object mới nhưng cùng giá trị
  const clonedSnapshot: StatusDto = {
    ...initial,
    folders: initial.folders.map((f) => ({ ...f })),
    jobs: initial.jobs.map((j) => ({ ...j })),
  };

  const merged = mergeStatusSnapshot(initial, clonedSnapshot);

  // Khẳng định reference identity hoàn toàn không đổi
  expect(merged).toBe(initial);
  expect(merged.folders).toBe(initial.folders);
  expect(merged.jobs).toBe(initial.jobs);
});

test("mergeStatusSnapshot: chỉ thay đổi counter thì tái sử dụng mảng folders và jobs cũ", () => {
  const initial = createStatusFixture();
  const nextSnapshot: StatusDto = {
    ...initial,
    pending: initial.pending + 1,
    folders: initial.folders.map((f) => ({ ...f })),
    jobs: initial.jobs.map((j) => ({ ...j })),
  };

  const merged = mergeStatusSnapshot(initial, nextSnapshot);

  expect(merged).not.toBe(initial);
  expect(merged.pending).toBe(initial.pending + 1);
  // Mảng folders và jobs không có phần tử đổi phải giữ nguyên reference cũ
  expect(merged.folders).toBe(initial.folders);
  expect(merged.jobs).toBe(initial.jobs);
});

test("mergeStatusSnapshot: thay đổi 1 job thì giữ nguyên reference của các job còn lại và mảng folders", () => {
  const initial = createStatusFixture();
  const nextSnapshot: StatusDto = {
    ...initial,
    jobs: [
      {
        ...initial.jobs[0],
        status: "completed",
        bytes_done: 1000,
      },
      { ...initial.jobs[1] },
    ],
    folders: initial.folders.map((f) => ({ ...f })),
  };

  const merged = mergeStatusSnapshot(initial, nextSnapshot);

  expect(merged).not.toBe(initial);
  // Folders không đổi
  expect(merged.folders).toBe(initial.folders);
  // Mảng jobs được tạo mới nhưng job thứ hai giữ nguyên reference
  expect(merged.jobs).not.toBe(initial.jobs);
  expect(merged.jobs[0]).not.toBe(initial.jobs[0]);
  expect(merged.jobs[0].status).toBe("completed");
  expect(merged.jobs[1]).toBe(initial.jobs[1]);
});

test("mergeStatusSnapshot: thay đổi 1 folder thì giữ nguyên mảng jobs và các folder còn lại", () => {
  const initial = createStatusFixture();
  const nextSnapshot: StatusDto = {
    ...initial,
    folders: [
      {
        ...initial.folders[0],
        access_state: "denied",
      },
      { ...initial.folders[1] },
    ],
    jobs: initial.jobs.map((j) => ({ ...j })),
  };

  const merged = mergeStatusSnapshot(initial, nextSnapshot);

  expect(merged).not.toBe(initial);
  // Jobs không đổi
  expect(merged.jobs).toBe(initial.jobs);
  // Folder thay đổi
  expect(merged.folders).not.toBe(initial.folders);
  expect(merged.folders[0].access_state).toBe("denied");
  expect(merged.folders[0]).not.toBe(initial.folders[0]);
  expect(merged.folders[1]).toBe(initial.folders[1]);
});

test("mergeRemoteFiles: danh sách tệp giống hệt nhau trả về chính xác reference cũ (prev === next)", () => {
  const initialFiles = createRemoteFilesFixture();

  const clonedFiles: RemoteFileRow[] = initialFiles.map((f) => ({ ...f }));
  const merged = mergeRemoteFiles(initialFiles, clonedFiles);

  // Phải giữ nguyên mảng cũ
  expect(merged).toBe(initialFiles);
});

test("mergeRemoteFiles: thay đổi 1 hàng tệp thì giữ nguyên reference các hàng không đổi", () => {
  const initialFiles = createRemoteFilesFixture();

  const nextFiles: RemoteFileRow[] = [
    {
      ...initialFiles[0],
      status: "conflict",
    },
    { ...initialFiles[1] },
  ];

  const merged = mergeRemoteFiles(initialFiles, nextFiles);

  expect(merged).not.toBe(initialFiles);
  expect(merged[0]).not.toBe(initialFiles[0]);
  expect(merged[0].status).toBe("conflict");
  // Hàng thứ hai không đổi phải giữ nguyên identity
  expect(merged[1]).toBe(initialFiles[1]);
});

test("mergeRemoteFiles: thêm tệp mới bảo toàn reference các tệp hiện có", () => {
  const initialFiles: RemoteFileRow[] = [
    {
      id: 1,
      folder_id: 1,
      relative_path: "file1.txt",
      remote_file_id: 10,
      remote_version_id: 20,
      status: "synced",
    },
  ];

  const nextFiles: RemoteFileRow[] = [
    { ...initialFiles[0] },
    {
      id: 2,
      folder_id: 1,
      relative_path: "file2.txt",
      remote_file_id: 11,
      remote_version_id: 21,
      status: "synced",
    },
  ];

  const merged = mergeRemoteFiles(initialFiles, nextFiles);

  expect(merged).toHaveLength(2);
  expect(merged[0]).toBe(initialFiles[0]);
  expect(merged[1]).toBe(nextFiles[1]);
});

test("isFolderEqual, isJobEqual, isRemoteFileEqual kiểm tra chính xác từng trường", () => {
  const initial = createStatusFixture();
  const folder = initial.folders[0];
  expect(isFolderEqual(folder, { ...folder })).toBe(true);
  expect(isFolderEqual(folder, { ...folder, enabled: !folder.enabled })).toBe(false);

  const job = initial.jobs[0];
  expect(isJobEqual(job, { ...job })).toBe(true);
  expect(isJobEqual(job, { ...job, bytes_done: job.bytes_done + 1 })).toBe(false);

  const file: RemoteFileRow = {
    id: 1,
    folder_id: 1,
    relative_path: "a.txt",
    remote_file_id: 10,
    remote_version_id: 20,
    status: "synced",
  };
  expect(isRemoteFileEqual(file, { ...file })).toBe(true);
  expect(isRemoteFileEqual(file, { ...file, status: "conflict" })).toBe(false);
});

test("mergeFolders và mergeJobs trả về mảng gốc nếu toàn bộ phần tử giống hệt", () => {
  const initial = createStatusFixture();
  expect(mergeFolders(initial.folders, initial.folders.map((f) => ({ ...f })))).toBe(
    initial.folders,
  );
  expect(mergeJobs(initial.jobs, initial.jobs.map((j) => ({ ...j })))).toBe(initial.jobs);
});



