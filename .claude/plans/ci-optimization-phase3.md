# CI 优化计划 (Phase 3) — apt 修复 + debug/release 模式

> 创建: 2026-09-04
> 状态: Plan Mode — 未经允许禁止修改任何文件
> 前置: Phase 2 Step 1 已实施 (56aff5d), Step 2 测试中

---

## 问题诊断

### 问题 1: apt upgrade 升级 110 个无关系统包

**日志实证 (Run 33860626731):**
```
110 packages can be upgraded. Run 'apt list --upgradable' to see them.
110 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
```

**根因:** `apt upgrade -yq` 是全量升级，不区分包。我们只缓存约 30 个构建相关包，但升级了 runner 预装的 80 个无关包（snapd, cloud-init 等）。

**影响:**
- 浪费 CI 时间（升级 110 个包 vs 0-3 个缓存包）
- 可能破坏 GitHub Actions runner 预装环境
- 无任何收益（无关包的升级对构建无帮助）

**修复方案:** `apt install --only-upgrade -yq <packages>`
- `--only-upgrade`: 只升级已安装的包，不安装新包
- 只指定我们缓存的 30 个包名
- apt 自动跳过无需升级的包，无需手动计数

### 问题 2: 缺少 debug/release 模式区分

**当前:** 只有一种模式，所有产物都上传到 GitHub Release

**需求:**
- **Debug 模式:** 编译产物分类(可刷入镜像/原始)放入 Actions Artifacts，不上传 Release
- **Release 模式:** 可刷入镜像必须上传 Release，原始产物放 Actions Artifacts

**产物分类:**
| 类型          | 文件                        | 用途                         |
| ------------- | --------------------------- | ---------------------------- |
| 可刷入镜像    | `*.img`                     | 直接 fastboot flash 刷入设备 |
| 原始/调试产物 | `*.zip`, `recovery.cpio.gz` | 调试分析、ramdisk 解包       |

---

## 安全流程

**核心原则: 禁止直接修改生产 yml，先在 test yml 验证通过再合并**

```
1. 修改 build-test-slimhub.yml（测试 workflow）
2. Push → 触发测试构建
3. 测试通过 → 将改动合并到 build.yml（生产 workflow）
4. 再次 push 验证生产 workflow
5. 测试失败 → 回退 test yml，分析日志
```

---

## 执行步骤

### Step A: 修复 apt upgrade → apt install --only-upgrade (P0 紧急)

**修改文件:** `build-test-slimhub.yml`（先测试）

**改动:**

```yaml
# ❌ 当前：升级 110 个无关包
- name: 更新 apt 包至最新
  run: |
    sudo apt update -qq
    UPGRADES=$(apt list --upgradable 2>/dev/null | grep -v "^Listing" | wc -l)
    if [ "$UPGRADES" -gt 0 ]; then
      echo "::notice::有 $UPGRADES 个包可升级，升级中..."
      sudo apt upgrade -yq
    else
      echo "所有包已是最新"
    fi

# ✅ 修复：只升级缓存的 30 个包
- name: 更新缓存包至最新
  run: |
    sudo apt update -qq
    sudo apt install --only-upgrade -yq \
      gperf gcc-multilib gcc-10-multilib \
      g++-multilib g++-10-multilib \
      libc6-dev lib32ncurses-dev \
      x11proto-core-dev libx11-dev tree \
      lib32z-dev libgl1-mesa-dev libxml2-utils \
      xsltproc bc ccache \
      lib32readline-dev lib32z1-dev \
      liblz4-tool libncurses-dev \
      libsdl1.2-dev build-essential \
      libgtk-3-dev libglu1-mesa-dev \
      freeglut3-dev git libxml2 lzop \
      pngcrush schedtool squashfs-tools \
      imagemagick libbz2-dev lzma \
      ncftp qemu-user-static \
      libstdc++-10-dev libncurses6 \
      python3 tar
```

**验证:**
- 日志中 `apt install --only-upgrade` 只升级 0-3 个缓存包
- 不再出现 110 个包升级
- 构建正常完成

---

### Step B: 新增 BUILD_MODE input (P1)

**修改文件:** `build-test-slimhub.yml`（先测试）

**改动:**

```yaml
on:
  workflow_dispatch:
    inputs:
      # ... 现有 inputs ...
      BUILD_MODE:
        description: "构建模式 (debug: 产物放artifacts / release: 可刷入镜像上传Release)"
        required: true
        default: "release"
```

**显示参数步骤增加:**
```yaml
echo "构建模式: ${{ github.event.inputs.BUILD_MODE }}"
```

---

### Step C: 产物上传逻辑重构 (P1)

**修改文件:** `build-test-slimhub.yml`（先测试）

**产物分发矩阵:**

| 模式        | 可刷入镜像 (*.img)  | 原始产物 (*.zip, *.cpio.gz) |
| ----------- | :-----------------: | :-------------------------: |
| **Debug**   | → Actions Artifacts |     → Actions Artifacts     |
| **Release** | → GitHub Release ✅  |     → Actions Artifacts     |

**改动 1: Release 上传步骤加条件 + 只上传 .img**

```yaml
- name: 上传到 Release
  if: github.event.inputs.BUILD_MODE == 'release'
  uses: softprops/action-gh-release@v3
  with:
    files: |
      workspace/out/target/product/${{ github.event.inputs.DEVICE_NAME }}/*.img
    fail_on_unmatched_files: false
    overwrite_files: true
    name: OrangeFox-R12.1-${{ github.event.inputs.DEVICE_NAME }}-${{ github.run_id }}
    tag_name: ${{ github.run_id }}
    body: |
      OrangeFox 分支: ${{ github.event.inputs.FOX_BRANCH }}
      设备: ${{ github.event.inputs.DEVICE_NAME }}
      构建目标: ${{ github.event.inputs.BUILD_TARGET }}
      构建模式: ${{ github.event.inputs.BUILD_MODE }}
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**改动 2: 新增 Artifacts 上传步骤**

```yaml
- name: 上传产物到 Artifacts
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: ${{ github.event.inputs.BUILD_MODE }}-build-${{ github.run_id }}
    path: |
      workspace/out/target/product/${{ github.event.inputs.DEVICE_NAME }}/*.img
      workspace/out/target/product/${{ github.event.inputs.DEVICE_NAME }}/*.zip
      workspace/out/target/product/${{ github.event.inputs.DEVICE_NAME }}/obj/PACKAGING/vendor_ramdisk_fragments_intermediates/recovery.cpio.gz
    if-no-files-found: warn
    retention-days: ${{ github.event.inputs.BUILD_MODE == 'debug' && 7 || 30 }}
```

**retention-days 策略:**
- Debug: 7 天（调试用，短期保留）
- Release: 30 天（长期保留原始产物）

---

## 执行顺序

| 序号  | Step                | 优先级 | 修改文件  | 验证方式                       |
| :---: | ------------------- | :----: | --------- | ------------------------------ |
|   1   | A: 修复 apt upgrade |  🔴 P0  | test yml  | 触发构建，日志确认只升级缓存包 |
|   2   | B: 新增 BUILD_MODE  |  🟡 P1  | test yml  | YAML 语法 + 逻辑审查           |
|   3   | C: 产物上传重构     |  🟡 P1  | test yml  | 触发 debug 构建确认 artifacts  |
|   4   | 合并到生产 yml      |  🟢 P2  | build.yml | A+B+C 全部验证通过后合并       |

---

## 合并到生产 yml 的条件

- [ ] test yml 构建成功（Step A 验证通过）
- [ ] debug 模式构建成功，产物在 artifacts 区
- [ ] release 模式构建成功，.img 在 Release，其余在 artifacts
- [ ] apt upgrade 日志确认只升级缓存包
- [ ] YAML 语法通过

---

## 验证清单

- [ ] Step A: 日志中 `apt install --only-upgrade` 只升级 0-3 个包（非 110 个）
- [ ] Step B: BUILD_MODE input 正确显示在运行参数中
- [ ] Step C (debug): 不触发 Release 上传，所有产物在 Artifacts
- [ ] Step C (release): .img 在 Release，.zip/.cpio.gz 在 Artifacts
- [ ] Step C: retention-days debug=7, release=30
- [ ] 合并: build.yml 与 test yml 逻辑一致
- [ ] 所有: YAML 语法通过