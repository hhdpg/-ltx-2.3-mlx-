# LTX Studio · 本地视频生成工作台

在 MacBook Pro（Apple Silicon / 24GB 统一内存）上运行的 LTX-2.3 视频生成网页工作台。
网页只负责交互与任务管理，**所有推理均由本机 MLX 进程执行**，不调用任何云端推理 API。

```text
浏览器 (Vue 3)  →  FastAPI (127.0.0.1:8000)  →  单任务队列  →  ltx-2-mlx CLI  →  MLX / Apple GPU
                          ↓
                     SQLite / 本地文件
```

---

## 1. 快速开始

```bash
cd ~/AI/app/web-studio

# 1) 后端依赖（首次）
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cd ..

# 2) 前端依赖（首次）
cd frontend && npm install && cd ..

# 3) 配置
cp .env.example .env
$EDITOR .env          # 按本机实际路径修改 LTX_* 与目录

# 4) 启动
./scripts/start.sh
```

访问：

| 入口 | 地址 |
| --- | --- |
| 网页 | http://127.0.0.1:5173 |
| 后端 | http://127.0.0.1:8000 |
| 接口文档 | http://127.0.0.1:8000/docs |

停止 / 查看日志：

```bash
./scripts/stop.sh              # 停止前后端，并清理 8000/5173 残留进程
./scripts/logs.sh              # 列出可用日志与最近任务
./scripts/logs.sh backend      # 后端输出
./scripts/logs.sh frontend     # 前端输出
./scripts/logs.sh app          # 应用日志 logs/app.log
./scripts/logs.sh task <id>    # 单个任务的推理日志
```

重启：`./scripts/stop.sh && ./scripts/start.sh`

---

## 2. 配置说明（`.env`）

| 变量 | 说明 |
| --- | --- |
| `APP_HOST` / `APP_PORT` | 后端监听地址，默认 `127.0.0.1:8000`，不要改成 `0.0.0.0` |
| `LTX_PROJECT_ROOT` | 推理项目目录（作为子进程 `cwd`） |
| `LTX_EXECUTABLE` | CLI 可执行文件路径 |
| `LTX_PYTHON` | 推理虚拟环境的 Python（用于 MLX 检测） |
| `LTX_MODEL_PATH` | 本地模型目录；留空则回退到设置页目录 → HF 本地缓存 |
| `LTX_LOW_RAM` | 默认关闭；开启后 CLI 追加 `--low-ram` |
| `UPLOAD_DIR` / `OUTPUT_DIR` / `LOG_DIR` | 存储目录，全部按 `expanduser()` + 绝对路径解析 |
| `DATABASE_URL` | SQLite 地址；相对路径按项目根目录解析 |
| `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` | 强制离线，默认 `1` |
| `MAX_UPLOAD_MB` | 上传图片大小上限，默认 15 |
| `MAX_PROMPT_LENGTH` | 提示词上限，默认 4000 |
| `MAX_QUEUE_SIZE` | 等待队列上限，默认 10（超出返回 429） |
| `GENERATION_TIMEOUT_SECONDS` | 单任务超时，默认 7200 |
| `IMAGE_FRAME` / `IMAGE_STRENGTH` / `IMAGE_MODE` | I2V 图片条件参数，默认 `0 / 1.0 / auto` |

`.env` 已在 `.gitignore` 中，不会被提交。

---

## 3. 功能范围

### V1.0

- 文字生成视频（T2V）、图片生成视频（I2V）
- 分辨率白名单、帧数 8k+1 校验、24 FPS、Distilled 模式
- 单任务串行队列（同一时刻仅 1 个推理进程），队列满返回 429
- 任务状态机：`QUEUED → STARTING → RUNNING → SUCCEEDED / FAILED / CANCELING / CANCELED`
- 任务持久化、重启恢复（残留运行任务标记失败，排队任务重新入队）
- 实时日志（2 秒轮询 + SSE 接口）、取消（SIGTERM → 宽限 → SIGKILL 进程组）
- MP4 在线播放（支持 Range 拖动）、下载、删除（可连带删除输出）
- 环境检测（macOS / 架构 / Python / MLX GPU / CLI / 模型完整性 / FFmpeg / 磁盘 / 内存）
- 设置页：默认分辨率、帧数、帧率、低内存模式、模型目录

### V1.1 连续续写（Extend）

- 新增 `EXTEND` 任务类型，调用本机 `ltx-2-mlx extend --distilled`
- 创作项目（Project）与视频版本链（Segment），支持从任意历史版本分支
- 用户只填「下一步动作」，视觉上下文由源视频承担
- 项目级角色 / 场景 / 风格 / 连续性设定，可选是否拼进 Prompt
- 续写长度按源视频真实 FPS 换算展示（`extend_frames=1/2/4/8/12` → 8~96 帧）
- 成功后自动创建版本并推进当前版本（用户中途切换则不覆盖）
- 失败 / 取消不创建版本；删除仍被子版本引用的版本会被拒绝

### V1.2 局部重拍（Retake）

- 新增 `RETAKE` 任务类型，调用本机 `ltx-2-mlx retake --distilled`
- 只改写已有视频中的指定区间，其余帧保持原样，视频总长不变
- **单条入口**：任务详情页「局部重拍」，对任意成功视频生效
- **连续入口**：创作链每个版本卡片上的「重拍」，结果作为该项目的新版本
- 时间轴双滑块 + 秒数输入联动，最小粒度 1 个 latent 帧（8 个视频帧）
- 可选「保留原音轨」（`--no-regen-audio`）与「附带项目设定」
- 提交前可查看实际传给 CLI 的完整 Prompt

### 不实现

- 多任务并发推理、用户账号、公网访问、云端推理 API
- 视频剪辑时间线、多段自动拼接、LoRA 训练、超分 / 插帧
- 自动多轮 Extend、在线 Prompt 优化
- 伪造生成百分比进度

---

## 4. 目录结构

```text
web-studio/
├── backend/
│   ├── app/
│   │   ├── core/        config / paths / logging
│   │   ├── api/         health / generation / tasks / files / settings / projects
│   │   ├── schemas/     Pydantic 模型（含 project）
│   │   ├── services/    mlx / model / environment / generation / task_queue /
│   │   │                process_runner / file / video / project
│   │   ├── db/          database / migrations / models / repositories /
│   │   │                project_repositories
│   │   └── utils/       validators / command_builder（generate + extend）
│   ├── tests/           59 项单元测试
│   ├── requirements.txt
│   └── run.py
├── frontend/            Vue 3 + TS + Vite + Element Plus
│   └── src/pages/       Generate / Projects / ProjectDetail / Tasks /
│                        TaskDetail / Videos / Settings / SystemLogs
├── data/studio.db       SQLite（迁移前自动备份到 data/backups/）
├── uploads/             上传图片（UUID 命名）
├── output/
│   ├── {task_id}.mp4            普通生成输出
│   └── projects/{project_id}/
│       ├── segments/            续写版本视频（不覆盖源文件）
│       └── anchors/             锚点图片
├── logs/                app.log / backend.out / frontend.out / tasks/*.log
├── scripts/             start.sh / stop.sh / logs.sh
├── docs/CLI-NOTES.md    本机 CLI 实测参数笔记
├── docs/ACCEPTANCE.md   V1.0/V1.1 验收记录
└── .env.example
```

---

## 5. HTTP API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查（`?force=true` 强制重新探测） |
| GET | `/api/system/info` | 系统信息与逐项检查 |
| GET | `/api/system/logs` | 应用日志尾部（固定文件，不接受任意路径） |
| POST | `/api/generations` | 提交生成（multipart） |
| GET | `/api/tasks` | 任务列表（分页 / 状态 / 类型筛选） |
| GET | `/api/tasks/{id}` | 任务详情 |
| POST | `/api/tasks/{id}/cancel` | 取消 |
| DELETE | `/api/tasks/{id}?delete_output=true` | 删除 |
| GET | `/api/tasks/{id}/logs?lines=200` | 日志尾部 |
| GET | `/api/tasks/{id}/events` | SSE 事件流 |
| GET | `/api/files/{id}/video` | 视频流（Range） |
| GET | `/api/files/{id}/download` | 附件下载 |
| POST | `/api/files/upload` | 独立上传 |
| GET | `/api/settings` / PUT | 读写白名单设置 |

错误码约定：`413` 文件过大、`415` 格式不支持、`422` 参数非法、`429` 队列满、`409` 状态冲突。

### 5.1 连续续写接口（V1.1）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/projects` | 创建创作项目 |
| GET | `/api/projects` | 项目列表 |
| GET | `/api/projects/{id}` | 项目详情 |
| PUT | `/api/projects/{id}` | 修改项目设定 |
| DELETE | `/api/projects/{id}?delete_videos=false` | 删除项目（可选删文件） |
| GET | `/api/projects/{id}/segments` | 版本链 + 父子映射 |
| POST | `/api/projects/{id}/segments` | 把已有成功视频加入项目 |
| PUT | `/api/projects/{id}/current-segment` | 切换当前版本 |
| POST | `/api/projects/{id}/prompt-preview` | 预览最终 CLI Prompt |
| POST | `/api/projects/{id}/extend` | 创建续写任务（multipart） |
| DELETE | `/api/segments/{id}?delete_video=false` | 删除版本（有子版本时 409） |
| GET | `/api/segments/{id}/video` | 版本视频流（Range） |
| GET | `/api/segments/{id}/download` | 版本视频下载 |

`POST /api/projects/{id}/extend` 使用 `multipart/form-data`：

```text
source_segment_id        源版本 UUID（必填）
prompt                   本次动作提示词（必填）
extend_frames            1 / 2 / 4 / 8 / 12（latent frames）
append_project_prompt    true / false
seed                     可选
anchor_frame             可选（新增帧内的帧索引，0 = 第一新增帧）
anchor_strength          可选 0~1
anchor_image             可选图片文件
```

返回 `final_prompt`（实际传给 CLI 的完整文本）与
`estimated_added_seconds` / `estimated_added_frames` 估算值。

### 5.2 Extend 命令约定

```bash
ltx-2-mlx extend --distilled \
  --prompt "<final_prompt>" \
  --video "<源 Segment 视频>" \
  --extend-frames 4 \
  --model "<本地 Q4 模型目录>" \
  -o "<output/projects/{project_id}/segments/segment_{task_id}.mp4>"
```

约束（由后端强制，前端无法覆盖）：

- `--model` 必须显式传本地路径，不依赖 CLI 默认的 Q8
- distilled 下**不传** `--steps` / `--cfg-scale` / `--stg-scale` / `--negative-prompt`
- **不传** generate 专属的 `-H` / `-W` / `-f` / `--frame-rate`
- 不传 `--direction before`（distilled 只支持 after）
- 源视频只读；每次续写输出到新路径，绝不覆盖
- 提交前用 ffprobe 校验：可读、宽高均为 64 的倍数、extend_frames 在白名单内

---

### 5.3 局部重拍接口（V1.2）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/retake` | 单条任务重拍（multipart） |
| POST | `/api/projects/{id}/segments/{sid}/retake` | 项目版本重拍，结果成为新版本 |
| GET | `/api/retake/source/{task_id}` | 查询单条任务的可用区间与总长 |
| GET | `/api/retake/source/segment/{segment_id}` | 查询项目版本的可用区间 |

表单字段：`prompt`、`start_latent`、`end_latent`、`keep_audio`、`seed`、
`append_project_prompt`（单条入口另需 `task_id`）。

区间以 **latent 帧**为单位（左闭右开）：1 个 latent 帧 = 8 个视频帧，
`total_latent = (帧数 - 1) // 8 + 1`。
- 重拍同样只读源视频，输出到新路径
- distilled 拒绝 `--cfg-scale` / `--stg-scale` / `--negative-prompt`
- 不传 generate 专属参数与 `--extend-frames`
- `--start` / `--end` 为 latent 帧索引，左闭右开，须在源视频长度内

---

## 6. 安全设计

- 后端仅绑定 `127.0.0.1`，Vite 开发服务器同样只监听 loopback
- 命令通过 `asyncio.create_subprocess_exec` 以**数组**形式传入，从不使用 `shell=True`
- 输出文件名、日志名由后端 UUID 生成，不接受前端指定路径
- 文件访问一律经任务 ID 映射 + `assert_within_allowed()` 目录边界校验（防 `../`）
- 上传采用 UUID 命名，并用 Pillow 完整解码校验真实图片类型（拒绝 SVG / HTML / 伪装图片）
- 子进程环境移除 `HF_TOKEN` 等令牌；日志写入前经过正则脱敏
- 前端不能传 `--model` / `--output` 或额外 CLI 参数

---

## 7. 测试

```bash
cd backend
.venv/bin/python -m pytest tests/ -q
```

覆盖：帧数 8k+1、提示词长度、分辨率/帧率/模式白名单、种子边界、
T2V/I2V 命令构造（含注入防护）、路径穿越、上传真实类型校验、
输出文件校验、日志尾读、设置校验。

---

## 8. 故障处理对照

| 现象 | 处理 |
| --- | --- |
| MLX import 失败 | 检查 `LTX_PYTHON` 是否指向 `.venv/bin/python`（注意不能写成软链的真实解释器） |
| MLX 设备非 GPU | 确认 Apple Silicon + `mlx` 安装在推理虚拟环境 |
| CLI 不存在 | 检查 `LTX_EXECUTABLE` 及执行权限 |
| 模型未配置 | 设置页选择模型目录，或填 `LTX_MODEL_PATH` |
| 模型权重不完整 | 提示检查本地文件，程序不会自动下载 |
| FFmpeg 缺失 | `brew install ffmpeg` |
| 队列满 (429) | 等待前序任务完成 |
| 输出文件缺失 | 即便退出码为 0 也标记失败 |
| 服务重启 | 运行中任务标记失败，排队任务重新入队 |
| OOM | 降低分辨率 / 帧数，或开启低内存模式 |

---

## 9. 单入口部署（可选）

前端构建后可由 FastAPI 直接托管：

```bash
cd frontend && npm run build
# 重启后端后访问 http://127.0.0.1:8000/
```
