# CI 优化计划 (Phase 3) — apt 修复 + debug/release 模式

> 创建: 2026-09-04
> 状态: 执行中 — test yml 已修改并触发测试 (Run 33864667585)
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

**修复方案: `apt-mark hold` + `apt upgrade` + `apt-mark unhold`**

用 `apt-mark hold` 锁定无用服务包，然后 `apt upgrade` 升级其余所有包，最后 `unhold` 解锁。

**调查依据:**
- GitHub 官方 `actions/runner-images` 的 `configure-apt.sh` 在构建镜像时做了 `apt-get purge unattended-upgrades` + `apt-get upgrade -y`，说明官方也认为这些服务包不需要
- `apt-mark hold` 是 dpkg 原生功能，Kubernetes 社区广泛使用（`apt-mark hold kubelet kubeadm kubectl`）
- 社区无标准排除列表，需自行根据 runner 环境确定

**Hold 列表（只 hold 肯定不用的包，不确定的不 hold）：**

| 分类          | 包名                                     | 原因          |
| ------------- | ---------------------------------------- | ------------- |
| Snap 生态     | `snapd` `snapcraft`                      | 构建不用 snap |
| LXD/LXC 容器  | `lxd` `lxcfs`                            | 不用容器管理  |
| 云初始化      | `cloud-init`                             | CI 环境不用   |
| 错误报告/遥测 | `apport` `popularity-contest` `whoopsie` | 不用          |
| Ubuntu Pro    | `ubuntu-advantage-tools`                 | 不用          |
| 自动升级      | `unattended-upgrades`                    | CI 不需要     |
| 固件更新      | `fwupd`                                  | CI 环境不用   |
| 包管理抽象层  | `packagekit`                             | 不用          |
| 调制解调器    | `modemmanager`                           | 不用          |

**实现:**
```yaml
- name: 更新系统包至最新
  run: |
    sudo apt update -qq
    HOLD_PKGS=(
      snapd snapcraft
      lxd lxcfs
      cloud-init
      apport popularity-contest whoopsie
      ubuntu-advantage-tools
      unattended-upgrades
      fwupd
      packagekit
      modemmanager
    )
    sudo apt-mark hold "${HOLD_PKGS[@]}"
    UPGRADES=$(apt list --upgradable 2>/dev/null | grep -v '^Listing' | wc -l)
    echo "::notice::升级 $UPGRADES 个包（已排除无用服务包）"
    sudo apt upgrade -yq
    sudo apt-mark unhold "${HOLD_PKGS[@]}"
```

**方案对比:**

| 方案                                | 升级包数 |        维护成本        | 风险  | 推荐度 |
| ----------------------------------- | :------: | :--------------------: | :---: | :----: |
| `apt upgrade`（当前）               |   110    |           无           | 中高  |   ❌    |
| `apt install --only-upgrade <30个>` |   0-3    |   高（需同步包列表）   | 最低  |   🟡    |
| **`apt-mark hold` + `apt upgrade`** |   ~98    | **低（hold列表稳定）** |  低   |   ✅    |

**推荐理由:**
1. 不用手动维护包白名单（构建工具链自动升级）
2. hold 列表很稳定（snapd/cloud-init 这些不会变）
3. dpkg 原生功能，Kubernetes 等大型项目在用
4. unhold 在 upgrade 后执行，不影响后续步骤
5. 构建相关包（gcc/make/python/libc 等）自动升级，不会漏

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

### Step A: 修复 apt upgrade → apt-mark hold + apt upgrade (P0 紧急)

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

# ✅ 修复：hold 无用服务包 + apt upgrade + unhold
- name: 更新系统包至最新
  run: |
    sudo apt update -qq
    HOLD_PKGS=(
      snapd snapcraft
      lxd lxcfs
      cloud-init
      apport popularity-contest whoopsie
      ubuntu-advantage-tools
      unattended-upgrades
      fwupd
      packagekit
      modemmanager
    )
    sudo apt-mark hold "${HOLD_PKGS[@]}"
    UPGRADES=$(apt list --upgradable 2>/dev/null | grep -v '^Listing' | wc -l)
    echo "::notice::升级 $UPGRADES 个包（已排除无用服务包）"
    sudo apt upgrade -yq
    sudo apt-mark unhold "${HOLD_PKGS[@]}"
```

**验证:**
- 日志中确认 hold 生效（snapd 等包被跳过）
- 升级包数从 110 降至 ~98（排除了 12 个无用服务包）
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
    retention-days: ${{ github.event.inputs.BUILD_MODE == 'debug' && 14 || 90 }}
```

**retention-days 策略:**
- Debug: 14 天（调试用，短期保留）
- Release: 90 天（长期保留原始产物）

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

- [ ] Step A: 日志中确认 hold 生效（snapd 等包被跳过）
- [ ] Step A: 升级包数从 110 降至 ~98
- [ ] Step B: BUILD_MODE input 正确显示在运行参数中
- [ ] Step C (debug): 不触发 Release 上传，所有产物在 Artifacts
- [ ] Step C (release): .img 在 Release，.zip/.cpio.gz 在 Artifacts
- [ ] Step C: retention-days debug=14, release=90
- [ ] 合并: build.yml 与 test yml 逻辑一致
- [ ] 所有: YAML 语法通过