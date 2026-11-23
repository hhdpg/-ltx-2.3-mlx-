# LTX Studio · 模型与环境

本目录记录本机 `ltx-2-mlx` 的实际安装信息，作为后端命令构造的依据。

## 1. 本机实测信息（2026-11-19）

| 项目 | 值 |
| --- | --- |
| 设备 | MacBook Pro / Apple M5 Pro / 24 GB 统一内存 |
| 系统 | macOS 27.0.1 (arm64) |
| FFmpeg | 9.0.2 |
| 推理引擎 | `~/AI/LTX23/ltx-2-mlx` |
| 引擎版本 | `v0.18.0-5-g747b30e`（`git describe --tags`） |
| 推理 Python | `ltx-2-mlx/.venv/bin/python`（CPython 3.11.15） |
| CLI | `ltx-2-mlx/.venv/bin/ltx-2-mlx` |
| MLX 设备 | `Device(gpu, 0)` |
| 模型 | `dgrauet/ltx-2.3-mlx-q4`（HF 本地缓存快照） |
| 权重合计 | 约 55.6 GiB（含 dev / distilled / distilled-1.1 多个 transformer） |

## 2. 实测 `generate` 参数（v0.18.0）

以本机 `ltx-2-mlx generate --help` 为准，V1 使用到的参数均已确认存在：

```text
--prompt / -p          文本提示词（必填）
--output / -o          输出 MP4（必填）
--model / -m           模型权重（本地路径或 HF 仓库 ID）
--seed / -s            随机种子（-1 表示随机）
--height / -H          高度（默认 480）
--width / -W           宽度（默认 704）
--frames / -f          帧数（LTX-2.3 必须显式传入）
--frame-rate           帧率（必填）
--distilled            蒸馏两阶段模式
--low-ram              分块流式加载，降低峰值内存
--image / -i           形如：PATH [FRAME_IDX STRENGTH [BINDING] [CRF]]
```

### 2.1 I2V 图片参数结论

`--image` 后接的可变位置参数：

- `PATH` 单独出现 → 等价于 `FRAME_IDX=0 STRENGTH=1.0`（legacy 单图 I2V）
- `BINDING` 可为 `auto` / `replace` / `guide`，省略时由 CLI 决定（`FRAME_IDX=0` 时替换首个 latent）
- 末尾单个 token 若为整数则被解释为 `CRF`，因此 **不要**在不需要 CRF 时传数字

后端实现（`app/utils/command_builder.py`）固定传 `--image PATH 0 1 auto`，
即：首帧、强度 1.0、auto 绑定。这三个值可通过 `.env` 的
`IMAGE_FRAME` / `IMAGE_STRENGTH` / `IMAGE_MODE` 调整，但默认值已在本机实测通过。

实测命令（I2V，512×320 / 25 帧 / 24 FPS / 49 秒完成）：

```bash
ltx-2-mlx generate \
  --prompt "Animate the subject naturally, subtle motion, cinematic lighting" \
  --image /path/to/uploads/xxxx.png 0 1 auto \
  --distilled -H 320 -W 512 -f 25 --frame-rate 24 \
  --model <本地模型目录> \
  -o <输出目录>/xxxx.mp4
```

## 3. 帧数规则

LTX 视频帧数为 `8k + 1`。V1 后端白名单（`ALLOWED_FRAMES`）：

```text
9 / 25 / 41 / 49 / 65 / 81 / 97 / 121
```

默认 25 帧。24 GB 机器不默认开放 193 帧及以上；`193 = 8*24+1`
虽符合数学规则，但被排除在 V1 白名单外。

## 4. 模型路径优先级

1. `.env` 的 `LTX_MODEL_PATH`
2. 设置页保存的本地模型目录（`app_setting.model_path`）
3. Hugging Face 本地缓存（`snapshot_download(..., local_files_only=True)`）

三者皆无 → 健康接口返回模型未配置，前端禁止提交任务。
程序**不会**为了查找模型而联网。

## 5. 完整性检查

后端不只检查目录存在，还会：

- 递归统计权重类文件（`.safetensors/.npz/.bin/.gguf/.pt/.pth/.json`）
- 要求至少存在一个大小 > 0 的权重文件
- 检查核心配置文件（`model_index.json` / `config.json` / `config.yaml`）
- 报告 0 字节权重文件（视为不完整，返回 warning）

## 6. 离线运行

`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1` 由后端在启动子进程时注入，
且会从子进程环境中移除 `HF_TOKEN` / `HUGGINGFACE_TOKEN` / `HF_HUB_TOKEN`。
推理全程不访问网络；模型以本地目录传入，不传仓库 ID。

---

## 7. Extend 实测（v0.18.0）

### 7.1 参数结论

以本机 `ltx-2-mlx extend --help` 为准：

```text
--prompt / -p            文本提示词（必填）
--output / -o            输出 MP4（必填）
--model / -m             模型权重（默认 dgrauet/ltx-2.3-mlx-q8 ← 必须显式覆盖）
--video / -v             源视频（必填）
--extend-frames N        新增 latent frames（必填），新增视频帧 = 8 × N
--direction {before,after}  默认 after；distilled 只支持 after
--distilled              [experimental] 蒸馏两阶段路径，拒绝 CFG 参数
--low-ram                分块流式加载
--image PATH [FRAME_IDX STRENGTH [BINDING] [CRF]]   [仅 distilled] 新增帧的锚点
```

关键约束（已实测确认）：

| 约束 | 说明 |
| --- | --- |
| `--distilled` 拒绝 CFG 参数 | `--steps` / `--cfg-scale` / `--stg-scale` / `--negative-prompt` 全部报错 |
| 无 generate 专属参数 | help 中没有 `-H` / `-W` / `-f` / `--frame-rate`，尺寸由源视频决定 |
| distilled 仅 after | 传 `--direction before` 会被拒绝 |
| 默认模型是 Q8 | 必须显式 `--model` 指向本地 Q4 目录 |
| `--image` 帧索引只计新增帧 | `0` = 第一个新增帧，`last` / `-1` = 最后一个 |
| 源尺寸需 64 倍数 | 后端用 ffprobe 预检，不静默缩放 |

### 7.2 冒烟测试记录

源视频 `first_test.mp4`（704×448，25 帧，24fps，均满足 64 倍数）：

```bash
ltx-2-mlx extend --distilled \
  --prompt "The subject continues moving naturally. Preserve the same visual identity, clothing, environment and cinematic style." \
  --video "<...>/first_test.mp4" \
  --extend-frames 1 \
  --model "<HF 缓存中的 Q4 快照>" \
  -o "/tmp/extend_smoke_01.mp4"
```

结果：退出码 0，耗时 58.7s，输出 175,762 字节。
`ffprobe` 验证输出为 **33 帧 / 1.375s / 24fps / 704×448**，
即 25 源帧 + 8 新增帧，与 `8 × extend_frames` 公式一致。

### 7.3 工作台命令模板

后端 `build_extend_command()` 生成的固定形态：

```bash
ltx-2-mlx extend --distilled \
  --prompt "<final_prompt>" \
  --video "<source segment mp4>" \
  --extend-frames <1|2|4> \
  --model "<本地 Q4 模型目录>" \
  -o "<output/projects/{project_id}/segments/segment_{task_id}.mp4>"
```

可选追加：`--seed N`、`--low-ram`、`--image PATH FRAME STRENGTH`。
