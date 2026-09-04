# OrangeFox Recovery CI/CD 构建流程详解

> 本文档详细描述 T50 (tb8786p1_64_k510_wifi) 设备的 OrangeFox Recovery 自动化构建流程。
> 涵盖从触发到产物发布的每一个阶段，适合新贡献者理解整个 CI/CD 管线。

---

## 目录

1. [全局架构概览](#1-全局架构概览)
2. [触发方式](#2-触发方式)
3. [阶段 0: 模式判定与参数展示](#3-阶段-0-模式判定与参数展示)
4. [阶段 1: 环境准备](#4-阶段-1-环境准备)
5. [阶段 2: 源码同步](#5-阶段-2-源码同步)
6. [阶段 3: 构建](#6-阶段-3-构建)
7. [阶段 4: 版本号与产物整理](#7-阶段-4-版本号与产物整理)
8. [阶段 5: 产物发布](#8-阶段-5-产物发布)
9. [缓存策略详解](#9-缓存策略详解)
10. [Debug vs Release 模式对比](#10-debug-vs-release-模式对比)
11. [故障排查指南](#11-故障排查指南)

---

## 1. 全局架构概览

### 流程总览图

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GitHub Actions Runner (Ubuntu)                    │
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐        │
│  │ 触发判定  │──▶│ 环境准备  │──▶│ 源码同步  │──▶│  编译构建  │        │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘        │
│       │                                              │             │
│       │              ┌──────────┐   ┌──────────┐     │             │
│       │              │ 产物发布  │◀──│ 版本+整理  │◀───┘             │
│       │              └──────────┘   └──────────┘                    │
│       │                    │                                        │
│       ▼                    ▼                                        │
│  ┌─────────┐        ┌───────────┐                                  │
│  │  Artifacts │      │  Release   │                                  │
│  │ (调试产物) │      │ (刷入镜像) │                                  │
│  └─────────┘        └───────────┘                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 时间分布 (典型构建)

```
总耗时 ≈ 3~4 小时

环境准备  ████░░░░░░░░░░░░░░░░░░  ~15 min   (5%)
源码同步  ████████░░░░░░░░░░░░░░  ~30 min   (15%)
编译构建  ████████████████████░░  ~180 min  (75%)
产物发布  ███░░░░░░░░░░░░░░░░░░░  ~5 min    (2%)
缓存操作  ██░░░░░░░░░░░░░░░░░░░░  ~10 min   (3%)
```

> 💡 **比喻**: 整个流程就像在工厂造一辆汽车——
> - **环境准备** = 准备工具和车间
> - **源码同步** = 运进所有零件和图纸
> - **编译构建** = 流水线上组装 (最耗时)
> - **产物发布** = 质检合格后入库发货

---

## 2. 触发方式

### 2.1 手动触发 (workflow_dispatch)

在 GitHub Actions 页面点击 **"Run workflow"**，可选择以下参数：

| 参数                 | 说明                  | 默认值                                                 | 是否必填 |
| -------------------- | --------------------- | ------------------------------------------------------ | -------- |
| `FOX_BRANCH`         | OrangeFox 分支        | `12.1`                                                 | ✅        |
| `DEVICE_TREE_URL`    | 设备树仓库 URL        | `https://github.com/cjy0812/T50_OrangeFox_Device_Tree` | ✅        |
| `DEVICE_TREE_BRANCH` | 设备树分支            | `main`                                                 | ✅        |
| `DEVICE_PATH`        | 设备在源码中的路径    | `device/alps/tb8786p1_64_k510_wifi`                    | ✅        |
| `DEVICE_NAME`        | 设备代号              | `tb8786p1_64_k510_wifi`                                | ✅        |
| `MAKEFILE_NAME`      | Android.mk 中的目标名 | `twrp_tb8786p1_64_k510_wifi`                           | ✅        |
| `BUILD_TARGET`       | 构建目标类型          | `vendorbootimage`                                      | ✅        |
| `ENABLE_SSH`         | SSH 调试开关          | `false`                                                | ✅        |
| `BUILD_MODE`         | **debug / release**   | `release`                                              | ✅        |

### 2.2 定时触发 (schedule)

```yaml
schedule:
  - cron: "0 4 */14 * *"
```

| 字段 | 值     | 含义                       |
| ---- | ------ | -------------------------- |
| 分   | `0`    | 第 0 分钟                  |
| 时   | `4`    | UTC 04:00 (北京时间 12:00) |
| 日   | `*/14` | 每 14 天                   |
| 月   | `*`    | 每月                       |
| 星期 | `*`    | 任意                       |

> 定时触发默认使用 **release** 模式。

### 2.3 安全限制

```yaml
if: github.event.repository.owner.id == github.event.sender.id
```

仅仓库所有者可触发构建，防止外部用户消耗 Actions 资源。

---

## 3. 阶段 0: 模式判定与参数展示

### 判定逻辑

```
触发类型判断:
  ├── schedule (定时)  →  固定使用 release 模式
  └── workflow_dispatch (手动)  →  使用用户选择的 BUILD_MODE
```

### Debug vs Release 的本质区别

```
                    Debug                           Release
                    ─────                           ──────
版本号:             v1.0.0-abc1234                  v1.0.1
                    (最新tag + 短哈希)               (语义化递增)
创建 Git Tag:       ❌ 不创建                        ✅ 创建
上传 Release:       ❌ 不上传                        ✅ 上传可刷入镜像
Artifacts 保留:     14 天                            90 天
Artifacts 内容:     全部产物                          仅辅助产物 (zip + cpio.gz)
用途:               开发调试/验证                     正式发布给用户
```

> 💡 **比喻**: Debug 像草稿纸——写完就扔；Release 像正式文件——归档保存。

---

## 4. 阶段 1: 环境准备

### 4.1 磁盘空间清理

GitHub Actions Runner 自带约 70GB 磁盘，但预装了大量不需要的软件：

```
清理前:                          清理后:
├── /usr/share/dotnet    2.5GB   ├── (已删除)
├── /usr/local/lib/android 12GB   ├── (已删除)
├── /opt/ghc             1.5GB   ├── (已删除)
├── /usr/local/.ghcup    500MB   ├── (已删除)
├── /usr/local/share/boost 100MB ├── (已删除)
├── /usr/lib/jvm         800MB   ├── (已删除)
└── /opt/hostedtoolcache  2GB    └── (已删除)

释放约 ~20GB 空间
```

> 💡 **比喻**: 就像搬家前先清空不需要的旧家具，腾出空间放新东西。

### 4.2 代码检出

```yaml
- uses: actions/checkout@v7
  with:
    fetch-depth: "0"     # 获取完整 git 历史
```

为什么需要 `fetch-depth: "0"`？

| fetch-depth | 获取的提交数    | 用途                         |
| ----------- | --------------- | ---------------------------- |
| `1` (默认)  | 仅最新 1 个提交 | 普通项目够用                 |
| `"0"`       | **全部历史**    | 版本号递增需要查找上一个 tag |

> `github-tag-action` 需要遍历 git 历史找到最新的语义化 tag 来计算 v+1。

### 4.3 apt 包缓存

使用 `cache-apt-pkgs-action` 缓存编译工具链，避免每次重新下载安装：

```
首次构建:  apt install 30+ 个包  →  ~5 min  →  存入 GitHub Cache
后续构建:  从 Cache 恢复          →  ~30 sec →  跳过下载安装
```

缓存键格式: `apt-cache-{week}` — 每周自动刷新，跟随上游包更新。

### 4.4 apt 升级策略

```
升级流程:
  1. purge snapd, unattended-upgrades  (彻底卸载不需要的)
  2. apt update                        (刷新包列表)
  3. apt-mark hold × 6 个无用服务包     (锁定不升级)
  4. apt upgrade                       (升级其余包)
  5. apt-mark unhold                   (解除锁定)
```

**被 hold 的包** (构建用不到的服务):

| 包名           | 说明             | 为什么 hold              |
| -------------- | ---------------- | ------------------------ |
| `snapd`        | Snap 包管理器    | 已 purge，防止被重新拉入 |
| `cloud-init`   | 云初始化         | CI 环境不需要            |
| `apport`       | 崩溃报告         | 构建不需要               |
| `fwupd`        | 固件更新守护进程 | 构建不需要               |
| `packagekit`   | 包管理抽象层     | 构建不需要               |
| `modemmanager` | 调制解调器管理   | 构建不需要               |

### 4.5 ccache 验证

```
ccache 可用?
  ├── 是 → 继续
  └── 否 → sudo apt-get install -yq ccache  (重新安装)
```

> 这是为了防止 apt 缓存命中但 manifest 缺失导致 ccache 丢失的边缘情况。

### 4.6 交换空间

```yaml
- uses: pierotofy/set-swap-space@master
  with:
    swap-size-gb: 12
```

Android 编译峰值内存可达 16GB+，Runner 物理内存约 16GB，12GB swap 确保不 OOM。

```
物理内存:  ████████████████  16 GB
Swap:      ████████████░░░  12 GB
总计:      ████████████████████████████  28 GB
```

---

## 5. 阶段 2: 源码同步

### 5.1 整体数据流

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  OrangeFox Sync  │────▶│  AOSP + TWRP 源码 │────▶│   workspace/    │
│  (GitLab)        │     │  (数百个 git 仓库) │     │  (完整工作树)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                        │
                              ┌──────────────────┐      │
                              │    设备树 + 通用树  │─────┘
                              │  (GitHub)         │
                              └──────────────────┘
```

### 5.2 浅克隆 git wrapper

Android 源码包含数百个 git 仓库，完整克隆需要下载大量历史数据。浅克隆 wrapper 拦截 `git clone` 命令，自动添加 `--depth=1`：

```
正常 git clone:     下载全部历史  →  数 GB, 数分钟
Wrapper 拦截后:     git clone --depth=1  →  仅最新快照, 数秒

节省: ~80% 下载量和时间
```

> 💡 **比喻**: 就像看书只看最新版，不需要把每一版修订记录都搬回家。

### 5.3 源码同步步骤

```
步骤 1: orangefox_sync.sh
  ├── repo init  (初始化 manifest)
  └── repo sync  (同步数百个仓库)

步骤 2: 克隆设备树
  └── git clone T50_OrangeFox_Device_Tree → device/alps/tb8786p1_64_k510_wifi/

步骤 3: 克隆通用树 (可选)
  └── git clone Common_Tree → common/路径/

步骤 4: 同步设备依赖
  ├── 读取 twrp.dependencies
  ├── convert.sh 转换为 manifest
  └── repo sync  (同步依赖仓库)
```

### 5.4 磁盘占用

同步完成后，workspace 约占 30~40GB：

```
workspace/
├── .repo/          ~15GB  (git objects, 清单, 工具)
├── system/         ~3GB
├── frameworks/     ~2GB
├── vendor/         ~5GB
├── device/         ~1GB   (含设备树)
├── bootable/       ~1GB   (recovery/)
├── kernel/         ~2GB
├── build/          ~500MB
└── ...             ~数GB
```

---

## 6. 阶段 3: 构建

### 6.1 构建环境变量

| 变量                              | 值           | 作用                                 |
| --------------------------------- | ------------ | ------------------------------------ |
| `USE_CCACHE=1`                    | 启用 ccache  | 编译加速                             |
| `CCACHE_EXEC`                     | ccache 路径  | 指定 ccache 可执行文件               |
| `CCACHE_DIR`                      | `~/.ccache`  | 缓存存储目录                         |
| `LC_ALL=C`                        | C locale     | 避免排序/编码问题                    |
| `ALLOW_MISSING_DEPENDENCIES=true` | 允许缺失依赖 | TWRP minimal manifest 允许缺少部分包 |
| `FOX_BUILD_DEVICE`                | 设备名       | OrangeFox 识别目标设备               |
| `FOX_AB_DEVICE=1`                 | AB 设备      | 启用 A/B 分区支持                    |
| `FOX_VIRTUAL_AB_DEVICE=1`         | 虚拟 AB      | 启用虚拟 A/B 支持                    |

### 6.2 envsetup.sh 的"假失败"问题

OrangeFox 的 `orangefox_envsetup()` 函数最后一行：

```bash
[ -s $FOX_MANIFEST_ROOT/frameworks/base/services/core/xsd/vts/Android.mk ] && echo -n "" > ...
```

在 TWRP minimal manifest 中，`Android.mk` 不存在 → `[ -s ... ]` 返回 1 → 整个函数返回 1。

```
实际情况:
  source build/envsetup.sh  →  退出码 1  (看似失败)
  但 'lunch' 函数已定义     →  环境实际正常  (假失败)

修复方案:
  source build/envsetup.sh 2>&1 || true     # 忽略退出码
  type -t lunch >/dev/null 2>&1 || exit 1   # 验证 lunch 是否可用
```

> 💡 **比喻**: 就像汽车仪表盘亮了故障灯，但发动机运转正常——
> 我们不靠故障灯判断，而是直接听发动机声音 (`type -t lunch`)。

### 6.3 构建命令

```bash
lunch twrp_tb8786p1_64_k510_wifi-eng   # 选择构建目标
mka adbd vendorbootimage -j$(nproc)     # 并行编译
```

`mka` 是 Android 的 `make` 封装，自动利用所有 CPU 核心。

### 6.4 产物去重

对于 AB 设备 (vendorbootimage)，构建系统会同时生成：
- `vendor_boot.img` — 真正的刷入镜像
- `OrangeFox-R12.0-*.img` — 与 `vendor_boot.img` **完全相同**的副本

```
构建输出:
  ├── vendor_boot.img          ← 保留
  ├── OrangeFox-R12.0-*.img   ← 删除 (与 vendor_boot.img 相同)
  ├── ramdisk.img              ← 保留
  └── OrangeFox-R12.0-*.zip   ← 保留 (刷机包)
```

### 6.5 构建验证

```
验证 1: mka 退出码 = 0?
验证 2: 至少存在 1 个 .img 文件?
  ├── 通过 → "SUCCESS: N image(s) produced"
  └── 失败 → exit 1 (构建失败)
```

---

## 7. 阶段 4: 版本号与产物整理

### 7.1 版本号递增 (github-tag-action)

仅 **release** 模式触发版本号递增：

```
Release 模式:
  ┌─────────────────────────────────────────────┐
  │  github-tag-action@v1                       │
  │                                             │
  │  1. 获取最新 tag (如 v1.0.0)                │
  │  2. 分析 commit message:                    │
  │     ├── 含 #major → v1.0.0 → v2.0.0        │
  │     ├── 含 #minor → v1.0.0 → v1.1.0        │
  │     ├── 含 #patch → v1.0.0 → v1.0.1        │
  │     └── 无标记    → DEFAULT_BUMP (patch)    │
  │  3. 创建并推送新 tag                        │
  └─────────────────────────────────────────────┘

Debug 模式:
  1. 获取最新 tag (如 v1.0.1)
  2. 追加短哈希: v1.0.1-abc1234
  3. 不创建新 tag (不占用版本号)
```

**版本号时间线示例**:

```
T1: release → v1.0.0 (首次, INITIAL_VERSION)
T2: debug   → v1.0.0-abc1234 (借用, 不创建 tag)
T3: release → v1.0.1 (patch +1)
T4: debug   → v1.0.1-def5678
T5: release → v1.0.2
```

### 7.2 产物整理 (扁平化)

将散落在不同目录的构建产物复制到统一的临时目录：

```
原始目录:                              /tmp/upload-staging/:
out/target/product/tb8786p1.../        (扁平化后)
├── vendor_boot.img                    ├── vendor_boot_v1.0.1-abc1234.img
├── ramdisk.img                  ──▶   ├── ramdisk.img
├── OrangeFox-R12.0-*.zip              ├── OrangeFox-R12.0-*.zip
└── obj/PACKAGING/.../                 └── obj/PACKAGING/.../
    └── recovery.cpio.gz                   └── recovery.cpio.gz
```

**关键设计**:
- `vendor_boot.img` 重命名为 `vendor_boot_v1.0.1-abc1234.img` (带版本号+短哈希)
- `cpio.gz` 保留目录结构 `obj/PACKAGING/.../` (便于理解来源)
- 使用 `cp` 显式复制，避免 glob 递归匹配导致回环

---

## 8. 阶段 5: 产物发布

### 8.1 发布策略总览

```
                    ┌──────────────────────────────────────┐
                    │         产物分发决策树                │
                    └──────────────────────────────────────┘
                                      │
                            ┌─────────┴─────────┐
                            │   BUILD_MODE?     │
                            └─────────┬─────────┘
                      ┌───────────────┴───────────────┐
                      │                               │
                 ┌────┴────┐                     ┌────┴────┐
                 │  debug  │                     │ release │
                 └────┬────┘                     └────┬────┘
                      │                               │
                      ▼                               ▼
            ┌─────────────────┐           ┌─────────────────────┐
            │  Artifacts only  │           │  Release + Artifacts │
            │                 │           │                     │
            │  全部产物:       │           │  Release:           │
            │  - vendor_boot  │           │  - vendor_boot_*.img│
            │  - ramdisk      │           │  - ramdisk.img      │
            │  - zip          │           │                     │
            │  - cpio.gz      │           │  Artifacts:         │
            │                 │           │  - zip              │
            │  保留 14 天     │           │  - cpio.gz          │
            └─────────────────┘           │                     │
                                          │  保留 90 天         │
                                          └─────────────────────┘
```

### 8.2 Release 发布

使用 `softprops/action-gh-release@v3` 创建 GitHub Release：

| 配置项             | 值                                             | 说明              |
| ------------------ | ---------------------------------------------- | ----------------- |
| `tag_name`         | `v1.0.1`                                       | 版本号 tag        |
| `target_commitish` | `github.sha`                                   | tag 指向的 commit |
| `name`             | `OrangeFox_R12.1_tb8786p1_64_k510_wifi_v1.0.1` | Release 显示名    |
| `files`            | `vendor_boot_*.img` + `ramdisk.img`            | 上传的文件        |

**Release 页面展示效果**:

```
Release: OrangeFox_R12.1_tb8786p1_64_k510_wifi_v1.0.1
Tag: v1.0.1

Assets:
  ├── vendor_boot_v1.0.1-abc1234.img    (主镜像, 必刷)
  └── ramdisk.img                        (备用, 可选)

Body:
  OrangeFox Branch: 12.1
  Device: tb8786p1_64_k510_wifi
  Build Target: vendorbootimage
  Version: v1.0.1

  Flash Commands:
  - fastboot flash vendor_boot vendor_boot_*.img (主镜像, 必刷)
  - fastboot flash ramdisk ramdisk.img (备用, 可选)
```

### 8.3 Artifacts 上传

使用 `actions/upload-artifact@v7`，`compression-level: 9` (最大压缩)：

| 模式    | Artifact 名称                | 内容          | 保留天数 |
| ------- | ---------------------------- | ------------- | -------- |
| debug   | `debug-build-v1.0.1-abc1234` | 全部产物      | 14       |
| release | `release-aux-v1.0.1`         | zip + cpio.gz | 90       |

**下载 Artifact 后的目录结构**:

```
.
├── obj/
│   └── PACKAGING/
│       └── vendor_ramdisk_fragments_intermediates/
│           └── recovery.cpio.gz
├── OrangeFox-R12.0-Unofficial-tb8786p1.zip
├── ramdisk.img
└── vendor_boot_v1.0.1-abc1234.img
```

> 💡 **比喻**: Release 是商店货架 (面向用户)，Artifacts 是仓库 (面向开发者)。
> 货架只放成品 (img)，仓库存所有原材料 (zip, cpio.gz)。

---

## 9. 缓存策略详解

### 9.1 三层缓存体系

```
┌─────────────────────────────────────────────────────┐
│                    缓存体系                          │
│                                                     │
│  Layer 1: apt 包缓存                                │
│  ├── 工具: cache-apt-pkgs-action                    │
│  ├── 键:  apt-cache-2026-W36                        │
│  ├── 刷新: 每周 (version = week)                    │
│  └── 内容: gcc, ccache, build-essential 等 30+ 包   │
│                                                     │
│  Layer 2: ccache 编译缓存                           │
│  ├── 工具: actions/cache + ccache                   │
│  ├── 键:  ccache-fox-tb8786p1-12.1-2026-W36        │
│  ├── 刷新: 每周 + LRU 淘汰                          │
│  └── 内容: .o 目标文件 (hash = 源码+头文件+参数)    │
│                                                     │
│  Layer 3: repo 源码缓存                             │
│  ├── 工具: repo sync (内置)                         │
│  ├── 刷新: 每次全量同步                              │
│  └── 内容: .repo/ 目录 (git objects)                │
└─────────────────────────────────────────────────────┘
```

### 9.2 ccache 安全性

**ccache 不会导致"旧代码没生效"**：

```
编译决策流程:
  ┌──────────┐
  │ make/mka │  检查: 源码改了?
  └────┬─────┘
       │
  ┌────┴────────────────────┐
  │                         │
  │ 没改 → 跳过编译          │ 改了 → 调用编译器
  │                         │
  │                    ┌────┴────┐
  │                    │  ccache │  检查: hash(源码+头文件+参数) 命中?
  │                    └────┬────┘
  │                         │
  │                    ┌────┴────────────┐
  │                    │                 │
  │                    │ 命中 → 返回缓存  │ 未命中 → 正常编译+存缓存
  │                    │ .o (跳过编译)    │
  │                    └─────────────────┘
```

关键: **make 决定"要不要编译"，ccache 只决定"编译时能不能跳过"**。

### 9.3 GitHub Cache 特性

| 特性     | 说明                                     |
| -------- | ---------------------------------------- |
| 不可变性 | 缓存一旦创建不可修改，只能创建新的       |
| LRU 淘汰 | 总量超限 (10GB) 时淘汰最久未用的         |
| 分支隔离 | 默认分支的缓存可被其他分支读取，反之不行 |
| 并发安全 | 同一 key 只有一个写者，其他等待          |

---

## 10. Debug vs Release 模式对比

### 完整对比表

| 维度               | Debug                       | Release               |
| ------------------ | --------------------------- | --------------------- |
| **触发**           | 手动选择                    | 手动选择 / 定时触发   |
| **版本号**         | `v1.0.1-abc1234` (tag+哈希) | `v1.0.1` (语义化递增) |
| **创建 Git Tag**   | ❌                           | ✅                     |
| **Release 发布**   | ❌                           | ✅ (两个 img)          |
| **Artifacts 内容** | 全部产物                    | zip + cpio.gz         |
| **Artifacts 保留** | 14 天                       | 90 天                 |
| **用途**           | 开发调试                    | 正式发布              |
| **ccache**         | ✅ 使用                      | ✅ 使用                |
| **SSH 调试**       | 可开启                      | 可开启                |

### 典型使用场景

```
开发流程:
  1. 修改设备树代码
  2. 触发 debug 构建 → 验证修改是否正确
  3. 重复 1-2 直到满意
  4. 触发 release 构建 → 发布正式版本
```

---

## 11. 故障排查指南

### 常见问题与解决方案

| 问题              | 症状                              | 原因                          | 解决                                |
| ----------------- | --------------------------------- | ----------------------------- | ----------------------------------- |
| envsetup.sh 失败  | `source build/envsetup.sh` 返回 1 | OrangeFox 误报 (假失败)       | 已用 `                              |  | true` + `type -t lunch` 修复 |
| ccache not found  | `ccache: command not found`       | apt 缓存命中但 manifest 缺失  | 已有验证步骤自动重装                |
| snapd 被升级      | 升级日志出现 snapd                | apt upgrade 拉入被 purge 的包 | 已用 `apt-mark hold` 锁定           |
| 构建失败无 img    | mka 成功但无 .img                 | 静默失败                      | 已有 img 数量验证                   |
| Release 认证失败  | `Bad credentials 401`             | GITHUB_TOKEN 权限不足         | 已有 `permissions: contents: write` |
| 版本号不递增      | 每次都是 v1.0.0                   | fetch-depth 不够              | 已设 `fetch-depth: "0"`             |
| Artifact 二次打包 | 下载后是嵌套 zip                  | glob `**` 递归匹配            | 已改为逐文件显式指定                |

### 调试技巧

**开启 SSH 调试**:
- 触发构建时设置 `ENABLE_SSH: true`
- 构建会在 `Debug SSH` 步骤暂停
- 查看日志获取 SSH 连接命令
- 连接后可手动排查问题

**查看 ccache 命中率**:
- 构建日志中搜索 `ccache -s` 输出
- 关注 `cache hit rate` 百分比
- 首次构建 ~0%，后续通常 60~80%

---

## 附录 A: Runner 硬件规格

| 资源 | 规格                        |
| ---- | --------------------------- |
| CPU  | 4 核 (x86_64)               |
| RAM  | ~16 GB                      |
| 磁盘 | ~70 GB (清理后 ~50 GB 可用) |
| Swap | 12 GB (额外配置)            |
| OS   | Ubuntu 22.04 LTS            |
| 网络 | 高速 (GitHub CDN)           |

## 附录 B: 构建产物说明

| 文件                | 格式               | 大小   | 用途                                                                  |
| ------------------- | ------------------ | ------ | --------------------------------------------------------------------- |
| `vendor_boot_*.img` | Android Boot Image | ~32 MB | **主镜像** — 包含 kernel + ramdisk，`fastboot flash vendor_boot` 刷入 |
| `ramdisk.img`       | cpio.gz            | ~16 MB | 纯 recovery 根文件系统，无法单独刷入 (备用/调试)                      |
| `OrangeFox-*.zip`   | ZIP                | ~30 MB | 刷机包 (含 updater-script，通过 recovery 刷入)                        |
| `recovery.cpio.gz`  | cpio.gz            | ~16 MB | 原始 ramdisk 归档 (调试/分析用)                                       |

## 附录 C: 刷机命令

```bash
# 方式 1: fastboot 直刷 (推荐)
fastboot flash vendor_boot vendor_boot_v1.0.1-abc1234.img

# 方式 2: 通过 recovery 刷 zip
# 1. 先刷入 vendor_boot 进入 recovery
# 2. 在 recovery 中选择 "Install" → 选择 OrangeFox-*.zip

# 验证
fastboot reboot
# 重启后按音量上+电源 进入 recovery
```