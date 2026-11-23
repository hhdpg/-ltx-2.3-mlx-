# 验收记录 · 2026-11-19

环境：MacBook Pro M5 Pro / 24 GB / macOS 27.0.1 (arm64)
推理引擎：ltx-2-mlx v0.18.0-5-g747b30e
模型：dgrauet/ltx-2.3-mlx-q4（HF 本地缓存，55.6 GiB）

---

## 11.1 环境测试

| 项 | 结果 | 证据 |
| --- | --- | --- |
| Web 后端可启动 | ✅ | uvicorn `Application startup complete` |
| 前端可启动 | ✅ | Vite 6.4.6 ready，`/generate` 返回 200 |
| MLX 可 import | ✅ | 推理 venv 内 `import mlx.core` 成功 |
| `mx.default_device()` | ✅ | `Device(gpu, 0)` |
| `ltx-2-mlx --help` | ✅ | 退出码 0，子命令列表正常 |
| 本地模型路径存在 | ✅ | 快照目录存在，20 个非空权重文件 |
| FFmpeg 可执行 | ✅ | 9.0.2 |
| 运行期不请求第三方推理 API | ✅ | 所有命令均调用本地 CLI，网络侧无推理调用 |

## 11.2 T2V 测试

| 项 | 结果 |
| --- | --- |
| 有效提示词提交 | ✅ |
| 默认 512×320 / 25 帧 / 24 FPS | ✅ |
| 点击生成 → QUEUED | ✅ 202 + `{"status":"QUEUED"}` |
| worker 启动 → RUNNING | ✅ 观测到 RUNNING 且 pid 回写 |
| 日志持续写入 | ✅ 31 行日志，含 denoise 进度与 VAE 解码 |
| CLI 正常退出 | ✅ `process exited code=0` |
| 输出 MP4 存在且 > 0 | ✅ 57860 字节 |
| 任务 → SUCCEEDED | ✅ 32.6s |
| 浏览器播放视频 | ✅ 任务详情页 `<video>` 正常播放（0:01 / 1.04s） |
| 下载正常 | ✅ 206 Range + attachment 下载 57860 字节 |

实际执行命令：

```
ltx-2-mlx generate --prompt 'A cinematic sunset over the ocean, ...' --distilled \
  -H 320 -W 512 -f 25 --frame-rate 24 --model <本地快照> -o <output>/<uuid>.mp4
```

## 11.3 I2V 测试

| 项 | 结果 |
| --- | --- |
| 上传 PNG | ✅ |
| 超大文件被拒绝 | ✅ 单元测试覆盖（>15MB → `file_too_large` → HTTP 413） |
| 伪装成 JPG 的非图片被拒 | ✅ HTML 内容 → HTTP 415「文件内容不是有效的图片」 |
| SVG 被拒绝 | ✅ HTTP 415 |
| 图片预览正确 | ✅ 前端展示尺寸/大小/缩略图 |
| CLI 收到正确本地图片路径 | ✅ `--image /…/uploads/<uuid>.png 0 1 auto` |
| 生成视频成功 | ✅ 49.5s，85674 字节 |
| 详情可查看输入图片与输出视频 | ✅ `image_url` + `video_url` 均可访问 |

## 11.4 队列与异常测试

| 项 | 结果 |
| --- | --- |
| 连续提交两个任务，第二个排队 | ✅ 同屏观测到 1 个 RUNNING + N 个 QUEUED |
| 取消排队任务 | ✅ QUEUED → CANCELED |
| 取消运行任务后进程结束 | ✅ CANCELING → CANCELED，进程已退出 |
| CLI 失败显示 FAILED + 日志 | ✅ |
| 服务重启不误报 RUNNING | ✅ kill -9 后重启，状态变为 FAILED「服务异常退出，任务未能恢复」 |
| 输出缺失不标记成功 | ✅ `output_ready()` 三重校验 |
| 队列满返回 429 | ✅ 第 12 个任务 `HTTP 429 队列已满（最多 10 个等待任务）` |
| 路径穿越不可读外部文件 | ✅ `../../../../etc/passwd`、`..%2F..%2F`、`abc/def` 均 404 |

附加验证：

- 删除进行中任务 → `HTTP 409`
- 删除不存在任务 → `HTTP 404`
- 空提示词 → 422「提示词不能为空」
- 超长提示词（4001 字符）→ 422
- 帧数 30 → 422（8k+1 规则）
- 分辨率 1920×1080 → 422（白名单）
- 帧率 30 → 422
- 模式 two-stage → 422
- I2V 缺图片 → 422
- SSE `/api/tasks/{id}/events` → 正常推送 hello / update / final
- `GET /api/system/logs` → 200，返回 app.log 尾部

## 11.5 离线验收

`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1` 全程注入子进程；
模型以本地快照目录传入（不传仓库 ID）。
T2V、I2V 两次真实生成均在离线变量下完成，
执行环境变量中已移除 `HF_TOKEN` 等令牌，代码路径中不存在任何第三方推理请求。

## 单元测试

```
37 passed in 0.43s
```

覆盖帧数规则、提示词、分辨率/帧率/模式白名单、种子、命令构造（含注入防护）、
路径穿越、上传真实类型、输出文件校验、日志尾读、设置校验。

## 前端构建

```
vue-tsc --noEmit  → 0 error
vite build        → ✓ built in 3.13s
```

---

# V1.1 连续续写验收记录（2026-11-19）

引擎：ltx-2-mlx v0.18.0-5-g747b30e / Q4 本地快照 / 全程 `HF_HUB_OFFLINE=1`

## 终端冒烟

| 项 | 结果 |
| --- | --- |
| `extend --help` 参数核对 | ✅ 确认 `--video` / `--extend-frames` / `--distilled` / `--image` |
| 默认模型是 Q8 | ✅ 因此后端强制显式传 Q4 本地路径 |
| distilled 拒绝 CFG 参数 | ✅ `--steps/--cfg-scale/--stg-scale/--negative-prompt` 均报错 |
| 终端 extend（extend_frames=1） | ✅ 58.7s，输出 33 帧 / 1.375s（25 源帧 + 8 新增） |

## 数据库迁移

| 项 | 结果 |
| --- | --- |
| 迁移前备份 | ✅ `data/backups/studio-20261119-171525.db` |
| 新增表 | ✅ `generation_project`、`generation_segment` |
| `generation_task` 新增列 | ✅ project_id / source_segment_id / extend_frames / source_video_path / final_prompt / anchor_* / segment_id |
| 旧数据兼容 | ✅ 历史任务记录全部保留，新列可空 |
| 幂等性 | ✅ 重复启动不再重复 ALTER |

## 连续两轮 Extend（后端 API 驱动）

| 轮次 | 源 | extend_frames | 结果 | 时长 | 父子关系 |
| --- | --- | --- | --- | --- | --- |
| 初始 | T2V 任务 | — | SUCCEEDED | 1.042s | root |
| 第 1 轮 | 第 1 段 | 1 | SUCCEEDED（38.5s） | 1.375s | parent = 第 1 段 |
| 第 2 轮 | **第 2 段（第 1 轮输出）** | 1 | SUCCEEDED（39.0s） | 1.708s | parent = 第 2 段 |

第 2 轮 `--video` 确认取自第 1 轮的完整输出，而非最初视频。

## 分支与 UI 驱动

| 项 | 结果 |
| --- | --- |
| 从第 1 段分支续写 | ✅ 第 4 段 parent = 第 1 段，第 1 段 child_count = 2 |
| 分支不覆盖当前版本 | ✅ 分支完成后当前指针仍指向原链末端 |
| 浏览器 UI 提交续写 | ✅ 生成第 5 段（extend_frames=4，+32 帧，1.71s → 3.04s） |
| 创作链树形渲染 | ✅ 第 1 段标记「2 个分支」，子版本缩进，「当前版本」高亮 |
| Prompt 预览 | ✅ Project continuity 各区块 + Next action 分区正确 |

## 命令合规性

| 检查 | 结果 |
| --- | --- |
| 含 `extend --distilled` | ✅ |
| 显式 Q4 本地模型路径 | ✅ |
| 无 `--steps/--cfg-scale/--stg-scale/--negative-prompt` | ✅ 单测断言 |
| 无 `-H/-W/-f/--frame-rate` | ✅ 单测断言 |
| 无 `--direction before` | ✅ |
| 输出使用新路径（不覆盖源） | ✅ `output/projects/{id}/segments/segment_{task_id}.mp4` |
| 不使用 `shell=True` | ✅ 全程 `create_subprocess_exec` |

## 异常用例

| 场景 | 预期 | 实际 |
| --- | --- | --- |
| Segment 不存在 | 404 | ✅ |
| Segment 不属于该项目 | 404 | ✅ |
| 源任务未成功 | 拒绝 | ✅ 409 |
| 源视频缺失 | 拒绝 | ✅ 409 |
| 宽高非 64 倍数 | 拒绝并提示 | ✅ 422 `video_size_invalid` |
| Prompt 为空 | 422 | ✅ |
| extend_frames 不在白名单 | 422 | ✅「续写长度只能是 1、2、4」 |
| 队列已满 | 429 | ✅ |
| 重复提交同源 | 不创建重复任务 | ✅ 409「该版本已有进行中的续写任务」 |
| 删除有子版本的 Segment | 拒绝 | ✅ 409 |
| 删除被项目引用的任务 | 保留视频文件 | ✅ `deleted_output: false` |
| 失败/取消 | 不创建 Segment | ✅ 仅在 SUCCEEDED 且文件有效时创建 |
| 执行中切换项目版本 | 不覆盖用户选择 | ✅ 仅当 current 仍等于本次源版本才推进 |

## 回归与持久化

| 项 | 结果 |
| --- | --- |
| T2V 回归 | ✅ 34.4s，SUCCEEDED |
| I2V 回归 | ✅ 76.9s，SUCCEEDED，可加入项目成为初始版本 |
| 刷新页面后创作链 | ✅ 保留 |
| 重启服务后创作链 | ✅ 5 个版本 + 当前指针 + 分支关系全部保留 |
| 单任务串行 | ✅ 全局队列未变，同源去重生效 |

## 单元测试

```
59 passed（原有 37 项 + 新增 22 项 Extend/项目测试）
```

新增覆盖：Prompt 组合规则（含剧情摘要不入 Prompt）、extend 命令构造
（禁传参数断言、白名单、注入防护、锚点）、ffprobe 校验、时长按源的 FPS 换算、
64 倍数校验、版本链 children 映射。

## 已知限制

1. **锚点图片（`--image`）未在 UI 开放**：后端命令构造与上传通道已就绪，
   但本机尚未独立验证 distilled extend 锚点的实际效果，因此按文档要求
   先不暴露给用户，避免产生"承诺身份不变"的错误预期。
2. **`--low-ram` 对 Extend 未做本机实测**：沿用全局设置开关，
   开启后会传给 extend；建议先在小长度任务上验证内存表现。
3. **视觉连续性属于模型质量问题**：任务成功只代表链路正确，
   人物/服装/光照的一致程度需人工观看判断，不做自动评分。
4. **未做视频自动拼接**：每次续写产生独立文件，创作链是版本关系，
   不是一条合并后的长视频。

---

# V1.1.1 修复记录（2026-11-20）

## 修复的问题

### 1. 新建项目后无法开始续写

**现象：** 新建项目后，页面显示「当前源视频 — 该版本视频不可用」，
源版本下拉为空，「开始续写」按钮无任何反应，也没有提示。

**根因：** 新项目没有任何 Segment，`canSubmit` 依赖
`sourceSegment.video_ready`，条件恒为 false，按钮被静默禁用；
界面没有告诉用户「需要先有一段视频」。

**修复：**
- 空项目改为显示「先创建第一段视频」表单：可直接 T2V / I2V 生成首段，
  通过新增的 `POST /api/generations` 的 `project_id` 字段直接入库本项目，
  成功后自动创建第 1 段并设为当前版本。
- 「开始续写」按钮改为点击后给出明确原因（无源视频 / 未选版本 / 文件不可用），
  不再静默禁用。
- 提示词为空时显示「↑ 先在…里写下一步动作」。

### 2. 续写时长最多只有 1.33 秒

**现象：** 续写长度只有 1 / 2 / 4 三档，最长 1.33 秒。

**根因：** `allowed_extend_frames` 白名单写死为 `(1, 2, 4)`。

**修复：** 实测扩展白名单为 `(1, 2, 4, 8, 12)`，并通过 `/api/settings`
下发到前端，前端不再硬编码。

## 本机实测（extend_frames 上限验证）

| extend_frames | 新增帧 | 输出帧数 | 时长 | 耗时 | 峰值 Metal 内存 |
| --- | --- | --- | --- | --- | --- |
| 1 | 8 | 33 | 1.375s | 58.7s | 8.86 GB |
| 8 | 64 | 89 | 3.708s | 142.5s | 11.47 GB |
| 12 | 96 | 121 | 5.042s | 202.0s | 12.17 GB |

`12` 档峰值 12.17 GB，正好落在 VAE 解码预算 12.0 GB 内，
因此作为 24GB 机器的保守上限；不再向上开放。

## 回归验证

| 项 | 结果 |
| --- | --- |
| 空项目显示「生成第一段」表单 | ✅ |
| 通过 `project_id` 生成的首段自动入库为第 1 段 | ✅ 24.9s，ready=true |
| 有源视频时 5 档长度全部可选 | ✅ 0.33 / 0.67 / 1.33 / 2.67 / 4.00 秒 |
| 浏览器 UI 提交续写 | ✅ EXTEND RUNNING → SUCCEEDED，2.375s（+32 帧） |
| 12 档真实续写 | ✅ 84s，成片 5.04s，当前版本正确推进 |
| 无源视频时按钮给出明确提示 | ✅ |
| 单元测试 | ✅ 59 passed |
| 前端类型检查 / 构建 | ✅ 0 error / build 成功 |

---

# V1.2 局部重拍（Retake）验收记录（2026-11-20）

引擎：ltx-2-mlx v0.18.0，`retake --distilled`

## 终端冒烟

| 项 | 结果 |
| --- | --- |
| `retake --help` 参数核对 | ✅ `--video` / `--start` / `--end` / `--distilled` / `--no-regen-audio` |
| 真实运行（25 帧源，区间 [0,2)） | ✅ 170.3s，输出仍为 25 帧 / 1.04s，峰值 8.17 GB |
| 结论 | 只重算指定 latent 区间，视频总长与尺寸不变 |

## 实现

| 组件 | 说明 |
| --- | --- |
| 任务类型 | 新增 `RETAKE` |
| 数据字段 | `retake_start` / `retake_end` / `keep_audio`（幂等迁移） |
| 命令构造 | `build_retake_command()`：强制 `--distilled`、显式 Q4 路径 |
| 区间换算 | latent = (帧数-1)//8+1；1 latent = 8 视频帧 |
| 单条入口 | `POST /api/retake`（针对任意成功任务） |
| 连续入口 | `POST /api/projects/{id}/segments/{sid}/retake`（结果成为新版本） |
| 区间查询 | `GET /api/retake/source/{task_id}` 与 `/segment/{segment_id}` |
| 前端 | `RetakeDialog.vue`：源视频预览 + 双滑块 + 秒数输入联动 |

## 命令合规性

| 检查 | 结果 |
| --- | --- |
| 含 `retake --distilled` | ✅ |
| 显式 Q4 本地模型路径 | ✅ |
| 无 `-H/-W/-f/--frame-rate` | ✅ 单测断言 |
| 无 `--steps/--cfg-scale/--stg-scale/--negative-prompt` | ✅ 单测断言 |
| 无 `--extend-frames` | ✅ 单测断言 |
| 输出用新路径，不覆盖源 | ✅ |
| `--no-regen-audio` 仅在勾选时传 | ✅ |

## 单条路径实测

| 项 | 结果 |
| --- | --- |
| 源：25 帧 T2V 视频（4 个 latent） | ✅ |
| 区间 [0,2) = 0–0.67s | ✅ 37.9s 完成，输出 65 KB |
| 实际命令含 `--start 0 --end 2` | ✅ |
| 输出可播放 | ✅ `/api/files/{id}/video` |

## 连续路径实测

| 项 | 结果 |
| --- | --- |
| 源：项目第 1 段 | ✅ |
| 区间 [1,3) = 0.33–1.0s | ✅ 44.1s 完成 |
| Prompt 附带项目设定 | ✅ Final Prompt 含 Characters / Setting 区块 |
| 创建新版本并自动设为当前 | ✅ 第 2 段，父级指向第 1 段 |
| 视频时长保持不变 | ✅ 重拍前后均为 1.0417s |
| 浏览器 UI 提交 | ✅ 重拍成功并加入创作链，当前版本推进到第 5 段 |
| `--distilled` 通过 | ✅ |

## 异常用例

| 场景 | 结果 |
| --- | --- |
| 区间超出视频长度 | ✅ 422「重拍区间超出源视频长度」 |
| end <= start | ✅ 422「结束帧必须大于开始帧」 |
| 空提示词 | ✅ 422「请描述这一段要改成什么」 |
| 任务不存在 | ✅ 404 |
| 任务未成功 | ✅ 409 |
| Segment 不属于该项目 | ✅ 404 |
| 重复提交同源（有进行中任务） | ✅ 409 |
| 源视频缺失 | ✅ 409 |

## 回归

| 项 | 结果 |
| --- | --- |
| T2V / I2V | ✅ 未受影响（沿用原路径） |
| Extend | ✅ 续写链路未变 |
| 单任务串行 | ✅ 重拍进入同一全局队列 |
| 失败/取消不创建版本 | ✅（同 Extend 逻辑） |
| 单元测试 | ✅ 68 passed（原 59 + 新增 9 项 Retake） |
| 前端类型检查 | ✅ 0 error |
| 前端构建 | ✅ 成功 |
| 无 shell=True / 无私硬编码路径 | ✅ |

## 已知限制

1. 最小重拍粒度是 **8 个视频帧（1 latent 帧）**，界面会把秒数吸附到整格。
2. 计算成本按**整段视频总长**计算，不随区间变小而降低（CLI 的 preserved frames
   每轮仍参与 attention）——当前 1~5 秒短片影响很小，长视频需注意。
3. 重拍结果是独立新版本，不做自动拼接，也不自动删除被替换的旧版本。
