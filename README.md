# Medilab

![MediLab banner](docs/assets/banner.svg)

Laboratory Information Management System — LIMS for testing laboratories, built on Odoo 19.0. Featuring modules:

- [E-commerce](docs/functional/ecommerce_module/overview.md)
- [Analysis](docs/functional/analysis_module/overview.md)
- [Inventory](docs/functional/inventory_module/overview.md)

## Prerequisites

| Công cụ                                    | Mục đích                                               |
| ------------------------------------------ | ------------------------------------------------------ |
| Docker hoặc Podman                         | Chạy container stack                                   |
| [Task](https://taskfile.dev/installation/) | CLI `task` cho lệnh setup / lệnh hằng ngày             |
| [Node.js](https://nodejs.org/)             | `npx` cho MCP server (`.cursor/mcp.json`, `.mcp.json`) |
| [Bun](https://bun.com/docs/installation)   | Cài và chạy Cypress, Playwright Test                   |

## Quick start

```powershell
task setup # or: task up
```

Mở http://localhost:8069 — đăng nhập `admin` / `admin`.

Lần chạy đầu build image `localhost/medilab/odoo:19.0` và cài module từ `src/modules.txt` (có thể mất vài phút).

## Services

| Dịch vụ       | URL                                    | Thông tin đăng nhập                                                                                                                                     |
| ------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Odoo          | http://localhost:8069                  | `admin` / `admin`                                                                                                                                       |
| Postgres      | `localhost:15432`                      | xem [Environment](#environment)                                                                                                                         |
| MinIO console | http://localhost:29001 (API: `29000`)  | xem [Environment](#environment)                                                                                                                         |
| Mailpit       | http://localhost:28025 (SMTP: `21025`) | —                                                                                                                                                       |
| CloudBeaver   | http://localhost:28978                 | `medilab` / `medilab123` — `task dbeaver:up` để khởi động                                                                                               |
| ONLYOFFICE    | http://localhost:28880                 | JWT từ `ONLYOFFICE_JWT_SECRET` — `task sync-app:onlyoffice-up` để khởi động (dùng cho `applications/laboratory-file-sync-application`, editor tùy chọn) |

## Commands

| Lệnh                                                            | Khi nào dùng                                                                                                                                                 |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `task` / `task --list`                                          | Liệt kê các task có sẵn                                                                                                                                      |
| `task setup` / `task up`                                        | Khởi động Odoo + Postgres + MinIO + Mailpit (cài module nếu DB trống)                                                                                        |
| `task restart`                                                  | Khởi động lại Odoo sau khi đổi Python/XML/config                                                                                                             |
| `task rebuild`                                                  | Build lại image sau khi đổi Dockerfile / `requirements.txt`                                                                                                  |
| `task upgrade`                                                  | Cài module mới từ `src/modules.txt` và upgrade module đã có                                                                                                  |
| `task stop`                                                     | Dừng container, **giữ** volume                                                                                                                               |
| `task reset`                                                    | Xóa sạch volume DB/app, khởi động lại từ đầu, và seed `tpc_demo` (chỉ cục bộ)                                                                                |
| `task demo`                                                     | Cài seed UAT (User Acceptance Testing — kiểm thử chấp nhận với người dùng) `tpc_demo` (chỉ cục bộ). Mọi login demo dùng mật khẩu `demo`                      |
| `task onlyoffice-health`                                        | Kiểm tra Document Server sẵn sàng (Odoo **không** lỗi nếu nó down)                                                                                           |
| `task dbeaver:up` / `task dbeaver:down`                         | Khởi động / dừng CloudBeaver (DB admin UI, tách khỏi `task up`)                                                                                              |
| `task sync-app:onlyoffice-up` / `task sync-app:onlyoffice-down` | Khởi động / dừng ONLYOFFICE — chỉ cần khi làm việc với `applications/laboratory-file-sync-application`                                                       |
| `task cypress-setup`                                            | Cài dependency JavaScript đã khóa phiên bản và chuẩn bị binary Cypress                                                                                       |
| `task cypress`                                                  | Mở Cypress end-to-end test runner                                                                                                                            |
| `task playwright-setup`                                         | Cài dependency JavaScript đã khóa phiên bản và Chromium cho Playwright Test                                                                                  |
| `task playwright-test` / `task playwright`                      | Chạy test e2e trong `e2e/` (headless) / mở Playwright UI                                                                                                     |
| `task playwright-coa-walk`                                      | Đi trọn luồng báo giá → COA bằng các login demo trên Odoo local; **ghi dữ liệu thật vào DB**, cần `tpc_demo`. Ảnh chụp và file COA nằm trong `test-results/` |

### Fresh reset

```powershell
task reset   # wipe + install modules.txt + tpc_demo seed (password: demo)
```

`tpc_demo` không có trong `src/modules.txt` (production không bao giờ nhận nó). `task reset` cục bộ chạy `task demo` sau khi database trống đã lên. Sau `task setup` / `task up` không xóa sạch, tự chạy `task demo`.

## Layout

```
medilab/
  Taskfile.yml                    # entrypoint: sets COMPOSE_FILE=src/docker-compose.yml (default scope),
                                   # loads src/.env(.local), includes tools/taskfiles/*
  tools/                          # reference/tooling — not part of the running app
    dockerfiles/
      dev.dockerfile              # odoo:19.0 + Python deps (bind-mounted src/)
      prod.dockerfile             # same, but bakes src/modules + src/config into the image
    taskfiles/
      app.taskfile.yml            # task setup / up / stop / restart / rebuild / reset
      infra.taskfile.yml          # task tf-init / plan / apply / output (deployment only)
      deps.taskfile.yml           # task upgrade + module install/upgrade internals
      dbeaver.taskfile.yml        # task dbeaver:up / dbeaver:down
      sync-app.taskfile.yml       # task sync-app:dev/build/ci + sync-app:onlyoffice-up/down
      cypress.taskfile.yml        # task cypress / cypress-setup
      playwright.taskfile.yml     # task playwright / playwright-setup / playwright-test / playwright-coa-walk
    dbeaver/                      # its own compose unit — CloudBeaver, opt-in via `task dbeaver:up`
      docker-compose.yml          # name: medilab — dbeaver service, merged with src/docker-compose.yml
  src/                            # the app — fully self-contained, this is where you dev
    docker-compose.yml            # name: medilab — odoo + postgres + minio + mailpit (default `task up` scope)
    requirements.txt
    modules.txt                   # modules installed on first init
    .env / .env.local             # DB + MinIO credentials
    config/odoo.conf              # mounted as /etc/odoo
    modules/                      # Odoo addons (mounted as /mnt/extra-addons)
    templates/                    # mounted as /mnt/templates (read-only)
  infra/                          # deployment management only — not used by local dev
    main.tf, providers.tf, ...    # Cloudflare DNS, Doppler secrets, GitHub Actions secrets
    modules/                      # dns, secrets, app_secrets, github
  applications/                   # other apps (mobile, sync-app, etc.) — separate from the core Odoo app in src/
    laboratory-file-sync-application/
      docker-compose.yml          # name: medilab — ONLYOFFICE, opt-in via `task sync-app:onlyoffice-up`
```

`src/modules/` chứa mọi addon đi kèm repo này; `src/modules.txt` chỉ liệt kê những addon tự cài ở lần chạy đầu — mọi addon khác trong `src/modules/` (ví dụ theme) phải cài tay từ Apps.

## Environment

Giá trị mặc định trong `src/.env.local` (tạo file nếu chưa có):

```
MEDILAB_DB_NAME=medilab
MEDILAB_DB_USER=root
MEDILAB_DB_PASSWORD=root

MAIN_BUCKET_ROOT_USER=medilab
MAIN_BUCKET_ROOT_PASSWORD=medilab123
MEDILAB_MAIN_BUCKET=medilab
MAIN_BUCKET_ENDPOINT=http://minio:9000
PUBLIC_ENDPOINT=http://localhost:29000

ONLYOFFICE_JWT_SECRET=medilab-onlyoffice-local
ONLYOFFICE_PUBLIC_URL=http://localhost:28880
ONLYOFFICE_INTERNAL_URL=http://onlyoffice
ONLYOFFICE_CALLBACK_BASE=http://odoo:8069
```

## Deployment

`infra/` quản lý bản ghi Cloudflare DNS, secret Doppler và secret GitHub Actions cho lần deploy cluster tạm — không liên quan dev cục bộ, `task setup`/`up` không đụng tới. Mọi lệnh Terraform nằm trong `tools/taskfiles/infra.taskfile.yml`, dưới namespace `infra:`:

| Lệnh                | Khi nào dùng                                                                                                 |
| ------------------- | ------------------------------------------------------------------------------------------------------------ |
| `task infra:setup`  | Lần đầu: xác thực Doppler (dán token hoặc đăng nhập qua trình duyệt), phạm vi `infra/`, rồi `terraform init` |
| `task infra:plan`   | Xem trước thay đổi infra                                                                                     |
| `task infra:apply`  | Áp dụng thay đổi infra                                                                                       |
| `task infra:output` | Hiện output Terraform                                                                                        |

`plan`/`apply`/`output` chạy qua `doppler run --project medilab --config tf --name-transformer tf-var --`, lệnh này kéo mọi secret trong config đó và expose thành `TF_VAR_<name>` — kể cả chính `DOPPLER_TOKEN`, trở thành `var.doppler_token`. Cần `doppler login` trên máy nào chạy các lệnh này.
