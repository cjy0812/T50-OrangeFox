# T50 OrangeFox vendor_boot Bootloop 修复计划

> **目标**: 修复 T50 刷入 OrangeFox vendor_boot.img 后 bootloop 问题
> **根因**: MediaTek bootloader 仅加载 PLATFORM fragment，当前构建产生空 PLATFORM + 大 RECOVERY → 启动失败
> **方案**: 设置 `BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT` 为空值，让所有内容进入 PLATFORM fragment

---

## 证据基础

| 证据                                                                                           | 等级 | 来源             |
| ---------------------------------------------------------------------------------------------- | ---- | ---------------- |
| stock vendor_boot 只有 1 个 PLATFORM fragment (20.9MB)                                         | A级  | 设备实际镜像解析 |
| 刷入含 RECOVERY fragment 的镜像后 bootloop                                                     | A级  | 实际刷入测试     |
| OrangeFox 构建产物: PLATFORM=20bytes, RECOVERY=21.2MB                                          | A级  | 构建日志         |
| unihertz-jelly-max (MT6878) 设 BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT 为空              | B级  | GitHub 代码搜索  |
| alioth (Qualcomm) 设 BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT := true                     | C级  | 不同 SoC，不适用 |
| OrangeFox_A12.sh: IS_VENDOR_BOOT_RECOVERY 不依赖 BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT | B级  | OrangeFox 源码   |

---

## Step 1: 修改 BoardConfig.mk 配置

**依赖**: 无
**模型**: default
**文件**: `Device_Tree/BoardConfig.mk`

### 上下文简报

T50 的 MediaTek MT8786 bootloader 在正常启动时仅加载 vendor_boot 的 PLATFORM ramdisk fragment。当前配置 `BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT := true` 导致 AOSP 构建系统将 recovery ramdisk 拆分为空的 PLATFORM fragment 和单独的 RECOVERY fragment，而 MediaTek bootloader 不加载 RECOVERY fragment，导致 bootloop。

### 任务

1. 将 `BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT := true` 改为空值
2. 更新注释说明修改原因和证据
3. 确认 `BOARD_VENDOR_RAMDISK_FRAGMENTS` 未设置（不采用 jelly-max 方案，因 T50 bootloader 不支持 RECOVERY fragment）

### 具体修改

```makefile
# 修改前
BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT := true

# 修改后
# Evidence: stock vendor_boot 只有 1 个 PLATFORM fragment，无 RECOVERY fragment
# Evidence: 刷入含 RECOVERY fragment 的镜像后 bootloop
# Evidence: MediaTek bootloader 仅加载 PLATFORM fragment
# 设置为空 → AOSP 不创建 RECOVERY fragment → 所有内容进入 PLATFORM (与 stock 一致)
BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT :=
```

### 验证命令

```bash
grep "BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT" Device_Tree/BoardConfig.mk
```

### 退出标准

- `BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT` 行末尾为空（无 `true`）
- 注释包含 Evidence 标记

---

## Step 2: 创建 vendor_boot fragment 结构验证脚本

**依赖**: Step 1
**模型**: default
**文件**: `verify_fragments.py` (新建)

### 上下文简报

需要一个可重复使用的验证脚本，解析 vendor_boot v4 镜像的 ramdisk fragment 表，输出每个 fragment 的类型、名称和大小。此脚本将用于验证构建产物是否只包含 PLATFORM fragment（无 RECOVERY fragment）。

### 任务

1. 实现 vendor_boot v4 header 解析（magic, header_version, page_size, vendor_ramdisk_size, vendor_ramdisk_table_size/num/entry_size）
2. 实现 ramdisk fragment 表解析（每个 fragment 的 size, offset, type, name, compression）
3. 输出格式化的 fragment 信息表
4. 支持对比模式：同时解析 stock 和 OrangeFox 镜像并对比

### 验证命令

```bash
wsl python3 verify_fragments.py Device_Tree/Raw_img/vendor_boot_a.bin
```

### 退出标准

- 脚本可正确解析 stock vendor_boot_a.bin，显示 1 个 PLATFORM fragment (~20.9MB)
- 脚本可正确解析当前 OrangeFox vendor_boot.img，显示 2 个 fragment（修改前）

---

## Step 3: 推送代码并触发 CI 构建

**依赖**: Step 1, Step 2
**模型**: default
**文件**: `.github/workflows/build.yml`

### 上下文简报

T50 OrangeFox 使用 GitHub Actions CI 构建。需要将 Step 1 的修改推送到远程仓库并触发构建 workflow。

### 任务

1. `git add Device_Tree/BoardConfig.mk`
2. `git commit -m "fix(vendor_boot): set BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT to empty to prevent RECOVERY fragment"`
3. `git push origin main`
4. 使用 GitHub MCP 监控构建状态

### 验证命令

```bash
git log --oneline -1
```

### 退出标准

- 代码已推送到远程
- GitHub Actions workflow 已触发

---

## Step 4: 等待构建完成并下载产物

**依赖**: Step 3
**模型**: default

### 上下文简报

CI 构建通常需要 1-2 小时。需要监控构建状态，构建完成后下载 vendor_boot.img 产物。

### 任务

1. 使用 GitHub MCP 轮询 workflow run 状态
2. 构建成功后，下载 vendor_boot.img 到 release_output/
3. 构建失败则分析日志，回退到备选方案

### 验证命令

```bash
ls -la release_output/vendor_boot.img
```

### 退出标准

- vendor_boot.img 存在且大小 > 0
- 构建日志无 error

---

## Step 5: 验证构建产物 fragment 结构

**依赖**: Step 2, Step 4
**模型**: default

### 上下文简报

使用 Step 2 创建的验证脚本检查新构建的 vendor_boot.img 的 fragment 结构。关键验证：只有 1 个 PLATFORM fragment，无 RECOVERY fragment。

### 任务

1. 运行 `verify_fragments.py release_output/vendor_boot.img`
2. 确认 fragment 数量为 1
3. 确认 fragment 类型为 PLATFORM
4. 确认 fragment 大小接近 stock (20.9MB ± 5MB)
5. 对比 stock 和新构建的 fragment 结构

### 验证命令

```bash
wsl python3 verify_fragments.py release_output/vendor_boot.img
```

### 退出标准

- ✅ 只有 1 个 PLATFORM fragment
- ✅ 无 RECOVERY fragment
- ✅ PLATFORM fragment 大小在 15-30MB 范围内

**如果验证失败**:
- 如果仍有 RECOVERY fragment → 进入 Step 7 (备选方案)
- 如果 PLATFORM fragment 仍为空 → 进入 Step 7 (备选方案)

---

## Step 6: 刷入设备测试

**依赖**: Step 5
**模型**: default
**前提**: 用户已进入 bootloader 模式

### 上下文简报

将验证通过的 vendor_boot.img 刷入设备 vendor_boot_a 分区，重启观察是否正常启动。

### 任务

1. 确认设备连接: `fastboot devices`
2. 刷入镜像: `fastboot flash vendor_boot_a release_output/vendor_boot.img`
3. 重启: `fastboot reboot`
4. 观察启动行为:
   - 正常启动到 Android → ✅ bootloop 修复
   - 进入 recovery 模式 → 验证 OrangeFox UI
   - 反复重启 → ❌ 需要进一步排查

### 验证命令

```bash
fastboot devices
```

### 退出标准

- 设备正常启动到 Android 系统
- 可通过 key combo 进入 OrangeFox Recovery

**如果刷入失败**:
- 使用 stock vendor_boot_a.bin 恢复: `fastboot flash vendor_boot_a Device_Tree/Raw_img/vendor_boot_a.bin`
- 进入 Step 7 (备选方案)

---

## Step 7: 备选方案 — repack_vendor_boot.py 后处理

**依赖**: Step 5 (验证失败时)
**模型**: strongest
**文件**: `repack_vendor_boot.py` (已存在，需完善)

### 上下文简报

如果方案 D-3（空值配置）无法阻止 AOSP 创建 RECOVERY fragment，则需要后处理方案：合并 stock PLATFORM fragment 与 OrangeFox recovery 内容，重新打包 vendor_boot.img。

### 任务

1. 完善 repack_vendor_boot.py 的纯 Python 实现
2. 实现 vendor_boot v4 header 重写逻辑
3. 实现 fragment 表重写
4. 实现合并逻辑: 提取 stock PLATFORM 内容 + OrangeFox recovery 内容 → 合并为单一 PLATFORM fragment
5. 重写 header 中的 vendor_ramdisk_size、vendor_ramdisk_table_num 等字段
6. 测试重打包后的镜像结构

### 验证命令

```bash
wsl python3 repack_vendor_boot.py --stock Device_Tree/Raw_img/vendor_boot_a.bin --fox release_output/vendor_boot.img --output release_output/vendor_boot_repacked.img
wsl python3 verify_fragments.py release_output/vendor_boot_repacked.img
```

### 退出标准

- 重打包后的镜像只有 1 个 PLATFORM fragment
- PLATFORM fragment 包含 stock vendor 内容 + OrangeFox recovery 内容
- 镜像大小不超过分区限制 (64MB)

---

## 依赖图

```
Step 1 (修改 BoardConfig.mk)
  │
  ├──→ Step 2 (创建验证脚本)
  │       │
  │       └──→ (并行等待 Step 3)
  │
  └──→ Step 3 (推送 + 触发 CI)
          │
          └──→ Step 4 (等待构建 + 下载产物)
                  │
                  └──→ Step 5 (验证 fragment 结构)
                          │
                          ├──→ [成功] → Step 6 (刷入测试)
                          │
                          └──→ [失败] → Step 7 (备选方案: repack)
```

## 并行步骤

- Step 1 和 Step 2 可并行执行（无文件依赖冲突）

## 回滚策略

| Step   | 回滚方式                                                             |
| ------ | -------------------------------------------------------------------- |
| Step 1 | `git checkout HEAD -- Device_Tree/BoardConfig.mk`                    |
| Step 3 | `git revert HEAD`                                                    |
| Step 6 | `fastboot flash vendor_boot_a Device_Tree/Raw_img/vendor_boot_a.bin` |
| Step 7 | 删除 repacked 镜像，回退到 Step 1 前状态                             |

## 不变量

- stock vendor_boot_a.bin 始终保留作为恢复手段
- 每次刷入前必须验证 fragment 结构
- 构建失败不修改设备