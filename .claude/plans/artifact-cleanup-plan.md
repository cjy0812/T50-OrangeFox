# Artifact 与 Release 产物优化计划 v4

> 状态: 待执行
> 优先级: P1
> 影响文件: `build-test-slimhub.yml`, `build.yml`
> 更新: 版本号方案改为 github-tag-action (v+1 语义化递增)

## 问题诊断

### 问题1: artifact 下载后目录嵌套 + staging 目录残留

**现状**: 用户下载 artifact 后得到:
```
release-build-xxx.zip (二次压缩)
└── workspace/out/target/product/tb8786p1_64_k510_wifi/
    ├── vendor_boot.img
    ├── ramdisk.img
    ├── OrangeFox-R12.0-Unofficial-tb8786p1.zip
    ├── OrangeFox-R12.0-Unofficial-tb8786p1/    ← staging 目录 (应排除)
    └── obj/PACKAGING/.../recovery.cpio.gz
```

**用户预期**: 下载解压后扁平展示:
```
├── obj/PACKAGING/vendor_ramdisk_fragments_intermediates/recovery.cpio.gz
├── OrangeFox-R12.0-Unofficial-tb8786p1.zip
├── ramdisk.img
└── vendor_boot_v12.1-abc1234.img              ← 带版本号和短哈希
```

### 问题2: Release 与 Artifacts 产物分配

| 目标             | Release (可刷入镜像)   | Artifacts (辅助/调试)                                   |
| ---------------- | ---------------------- | ------------------------------------------------------- |
| **release 模式** | `.img` 文件 (带版本号) | `.zip` + `cpio.gz` + `.img` (全部, 排除已在 Release 的) |
| **debug 模式**   | 不发布                 | 全部产物                                                |

### 问题3: Release 命名混乱 + 版本号无递增

**现状**: `tag_name: ${{ github.run_id }}` → 随机数字 `33893842253`

**社区最佳实践**: 使用 [anothrNick/github-tag-action](https://github.com/anothrNick/github-tag-action) (⭐880)
- 自动获取最新 tag → 语义化版本 +1 (v1.0.0 → v1.0.1 → v1.1.0 → v2.0.0)
- 支持 commit message 控制: `#major`, `#minor`, `#patch`
- 输出: `new_tag`, `old_tag`, `tag`, `part`

**目标格式** (全半角符号):
- Release tag: `v{MAJOR}.{MINOR}.{PATCH}` (自动递增)
- Debug tag: `v{MAJOR}.{MINOR}.{PATCH}-{SHORT_HASH}`
- Release name: `OrangeFox_R{BRANCH}_{DEVICE}_{TAG}`

**示例** (假设上次 release 为 `v1.2.3`):
| 触发方式           | new_tag          | 说明              |
| ------------------ | ---------------- | ----------------- |
| 正常构建 (default) | `v1.2.4`         | patch +1 (可配置) |
| commit 含 `#minor` | `v1.3.0`         | minor +1          |
| commit 含 `#major` | `v2.0.0`         | major +1          |
| debug 模式         | `v1.2.4-63f8b24` | 追加短哈希        |

## 修复方案

### Step -1: 触发方式配置 (新增 schedule + workflow_dispatch)

**当前**: 仅 `workflow_dispatch` (手动触发)
**目标**: 手动 + 每14天自动构建 (双模式)

```yaml
on:
  workflow_dispatch:                    # 手动触发
    inputs:
      FOX_BRANCH:
        description: 'OrangeFox 分支'
        required: true
        default: '12.1'
      DEVICE_NAME:
        description: '设备代号'
        required: true
        default: 'tb8786p1_64_k510_wifi'
      BUILD_TARGET:
        description: '构建目标'
        required: false
        default: 'recovery'
      BUILD_MODE:
        description: '构建模式'
        required: true
        default: 'debug'
        type: choice
        options:
          - debug
          - release
  schedule:
    # 每14天自动构建一次 (UTC 时间, 北京时间 +8)
    # cron: 分 时 日 月 周
    - cron: '0 4 */14 * *'              # 每14天 UTC 04:00 (北京 12:00)
```

**定时触发行为**：
| 配置项   | 值                       | 说明                                                         |
| -------- | ------------------------ | ------------------------------------------------------------ |
| 频率     | `*/14` (每14天)          | 可调整为 `* * * * 0` (每周日) 或 `0 4 1,15 * *` (每月1/15号) |
| 默认模式 | `debug`                  | 定时构建默认 debug（不占用版本号）                           |
| 版本递增 | 不调用 github-tag-action | 定时触发不创建 tag                                           |
| 输入参数 | 使用 defaults            | 无法手动指定，使用 input 的 default 值                       |

**如果希望定时构建也发 Release**：
```yaml
# 方案A: 定时构建固定用 release 模式
# 需要在构建步骤中判断触发来源
- name: 判断构建模式
  id: detect-mode
  run: |
    if [ "${{ github.event_name }}" = "schedule" ]; then
      echo "mode=release" >> $GITHUB_OUTPUT
    else
      echo "mode=${{ github.event.inputs.BUILD_MODE }}" >> $GITHUB_OUTPUT
    fi
```

**建议**：定时构建先用 debug 模式验证构建是否成功，确认稳定后再改为 release。

### Step 0: 版本号自动递增 (使用 github-tag-action)

**工具**: [anothrNick/github-tag-action](https://github.com/anothrNick/github-tag-action) (⭐880)
**原理**: 查询仓库最新 tag → 语义化版本解析 → 根据规则 +1 → 输出 new_tag

```yaml
# Step 0a: 版本号自动递增 (仅 release 模式)
- name: Bump version (release模式)
  if: github.event.inputs.BUILD_MODE == 'release'
  id: tag_version
  uses: anothrNick/github-tag-action@v1.73.0
  with:
    github_token: ${{ secrets.GITHUB_TOKEN }}
    tag_prefix: "v"                              # tag 前缀: v1.2.3
    default_bump: "patch"                         # 默认 patch +1 (可改为 minor/major)
    initial_version: "1.0.0"                      # 首次构建的初始版本
    # 手动控制 (通过 commit message):
    #   #major → v1.2.3 → v2.0.0
    #   #minor → v1.2.3 → v1.3.0
    #   #patch → v1.2.3 → v1.2.4 (默认)

# Step 0b: 生成最终 tag 和 name (debug 追加短哈希)
- name: 生成发布名称
  id: release-info
  run: |
    BRANCH="${{ github.event.inputs.FOX_BRANCH }}"
    DEVICE="${{ github.event.inputs.DEVICE_NAME }}"
    MODE="${{ github.event.inputs.BUILD_MODE }}"
    SHORT_HASH=$(git rev-parse --short=7 HEAD)

    if [ "$MODE" = "release" ]; then
      TAG="${{ steps.tag_version.outputs.new_tag }}"
      PART="${{ steps.tag_version.outputs.part }}"
      echo "::notice::Version bumped: $PART → $TAG"
    else
      # debug 模式: 使用最新 tag + 短哈希
      LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
      TAG="${LATEST_TAG}-${SHORT_HASH}"
      echo "::notice::Debug mode: based on $LATEST_TAG"
    fi

    # 全半角符号命名
    NAME="OrangeFox_R${BRANCH}_${DEVICE}_${TAG}"

    echo "tag=$TAG" >> $GITHUB_OUTPUT
    echo "name=$NAME" >> $GITHUB_OUTPUT
    echo "short_hash=$SHORT_HASH" >> $GITHUB_OUTPUT

    echo "::notice::Final tag: $TAG"
    echo "::notice::Release name: $NAME"
```

**版本号递增逻辑**:
| 场景               | 行为              | 示例                |
| ------------------ | ----------------- | ------------------- |
| 首次构建           | 从 `v1.0.0` 开始  | `v1.0.0`            |
| 正常构建           | patch +1          | `v1.0.0` → `v1.0.1` |
| commit 含 `#minor` | minor +1          | `v1.0.1` → `v1.1.0` |
| commit 含 `#major` | major +1          | `v1.1.0` → `v2.0.0` |
| debug 模式         | 最新 tag + 短哈希 | `v1.0.1-abc1234`    |

**配置说明**:
- `default_bump`: 可选 `patch`(默认) / `minor` / `major`
- 对于 Recovery 构建, 建议 `patch` (小修小补频繁) 或 `minor` (功能更新)
- 可通过 workflow_dispatch input 覆盖: `DEFAULT_BUMP: ${{ github.event.inputs.VERSION_BUMP }}`

### Step 1: 扁平化产物目录 (解决嵌套 + staging + 回环)

构建步骤末尾添加"整理产物"逻辑:

```bash
DEVICE_OUT="out/target/product/${{ github.event.inputs.DEVICE_NAME }}"
STAGING="/tmp/upload-staging"
rm -rf "$STAGING"
mkdir -p "$STAGING/obj/PACKAGING/vendor_ramdisk_fragments_intermediates"

# img 文件 (带版本号和短哈希重命名)
VER_TAG="v${{ steps.release-info.outputs.ver_num }}-${{ steps.release-info.outputs.short_hash }}"
cp "$DEVICE_OUT"/vendor_boot.img "$STAGING/vendor_boot_${VER_TAG}.img" 2>/dev/null || true
cp "$DEVICE_OUT"/ramdisk.img "$STAGING/" 2>/dev/null || true

# zip 文件 (仅顶层, 不进入 staging 目录 → 无回环风险)
cp "$DEVICE_OUT"/OrangeFox-*.zip "$STAGING/" 2>/dev/null || true

# recovery.cpio.gz
cp "$DEVICE_OUT"/obj/PACKAGING/vendor_ramdisk_fragments_intermediates/recovery.cpio.gz \
   "$STAGING/obj/PACKAGING/vendor_ramdisk_fragments_intermediates/" 2>/dev/null || true

echo "=== Staged files (扁平化) ==="
ls -lhR "$STAGING"
echo "============================="
```

**回环问题防护**:
- ✅ 使用 `cp` 显式复制特定文件到 `/tmp/upload-staging/`
- ✅ 不使用 glob 递归匹配 → staging 目录不会被拉入
- ✅ `/tmp/upload-staging/` 是干净目录 → 上传内容完全可控

### Step 2: Artifacts 按模式分离上传

**Release 模式 - Artifacts (辅助产物, 排除已发到 Release 的 img)**:
```yaml
- name: 上传辅助产物到 Artifacts (release模式)
  if: github.event.inputs.BUILD_MODE == 'release'
  uses: actions/upload-artifact@v7
  with:
    name: release-aux-${{ steps.release-info.outputs.tag }}
    path: |
      /tmp/upload-staging/OrangeFox-*.zip
      /tmp/upload-staging/ramdisk.img
      /tmp/upload-staging/obj/**
    retention-days: 90
    compression-level: 9
```

**Debug 模式 - Artifacts (全部产物)**:
```yaml
- name: 上传全部产物到 Artifacts (debug模式)
  if: github.event.inputs.BUILD_MODE == 'debug'
  uses: actions/upload-artifact@v7
  with:
    name: debug-build-${{ steps.release-info.outputs.tag }}
    path: /tmp/upload-staging/**
    retention-days: 14
    compression-level: 9
```

### Step 3: Release 发布 (只发 img)

```yaml
- name: 上传到 Release
  if: github.event.inputs.BUILD_MODE == 'release'
  uses: softprops/action-gh-release@v3
  with:
    files: |
      /tmp/upload-staging/vendor_boot_*.img
    fail_on_unmatched_files: false
    overwrite_files: true
    name: ${{ steps.release-info.outputs.name }}
    tag_name: ${{ steps.release-info.outputs.tag }}
    body: |
      OrangeFox Branch: ${{ github.event.inputs.FOX_BRANCH }}
      Device: ${{ github.event.inputs.DEVICE_NAME }}
      Build Target: ${{ github.event.inputs.BUILD_TARGET }}
      Version: ${{ steps.release-info.outputs.tag }}

      Flash Command: `fastboot flash vendor_boot vendor_boot_*.img`
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## 执行顺序

1. 修改 `build-test-slimhub.yml` 实施 Step 0-3
2. 触发测试构建 (release 模式), 验证:
   - [ ] artifact 下载解压后扁平展示 (无 workspace/out/... 嵌套)
   - [ ] artifact 不含 OrangeFox-*/ staging 目录树
   - [ ] vendor_boot.img 带版本号和短哈希
   - [ ] Release 只有 vendor_boot_*.img (可刷入镜像)
   - [ ] Release Artifacts 有 .zip + ramdisk.img + cpio.gz (无 vendor_boot)
   - [ ] Release tag 格式: v{MAJOR}.{MINOR}.{PATCH} (语义化递增)
   - [ ] Release name 全半角符号
   - [ ] 版本号正确递增 (v1.0.0 → v1.0.1 → ...)
3. 触发 debug 模式测试, 验证:
   - [ ] Debug Artifacts 有全部产物
   - [ ] Debug tag 带 short_hash (v1.0.1-abc1234)
   - [ ] Debug 不创建 Release/tag
4. 测试 commit message 控制 (`#minor`, `#major`)
5. 验证通过后合并到 `build.yml`

## 验证清单

### Artifact 结构验证
- [ ] 解压后扁平展示, 无嵌套目录
- [ ] 不含 OrangeFox-*/ staging 目录
- [ ] 不含重复 img
- [ ] vendor_boot_{version}-{hash}.img 命名正确

### Release 验证
- [ ] 只包含 vendor_boot_*.img
- [ ] tag: v{MAJOR}.{MINOR}.{PATCH} (语义化版本)
- [ ] name: OrangeFox_R{BRANCH}_{DEVICE}_{tag} (全半角)
- [ ] body 含刷机命令、版本信息
- [ ] overwrite_files: true (同 tag 可覆盖)

### 版本号验证
- [ ] 首次构建 → v1.0.0 (initial_version)
- [ ] 正常构建 → patch +1 (v1.0.0 → v1.0.1)
- [ ] commit 含 #minor → minor +1 (v1.0.1 → v1.1.0)
- [ ] commit 含 #major → major +1 (v1.1.0 → v2.0.0)
- [ ] debug 模式 → 最新 tag + 短哈希

### Artifacts 验证
- [ ] release 模式: .zip + ramdisk.img + cpio.gz (排除 vendor_boot)
- [ ] debug 模式: 全部产物 (含 vendor_boot)
- [ ] retention-days 正确 (release=90, debug=14)
- [ ] compression-level: 9

### 边界情况
- [ ] 首次发布 (无历史 tag) → 使用 initial_version (v1.0.0)
- [ ] 同一 commit 重复触发 → 不重复 bump (action 内置保护)
- [ ] debug 模式不调用 github-tag-action (不创建 tag)
- [ ] github-tag-action 失败时 fallback 到 v0.0.0-{hash}
- [ ] 手动控制: commit message 含 #major/#minor/#patch 生效

## 回退方案

- 移除 github-tag-action, 恢复手动版本号或 github.run_id
- 移除扁平化逻辑, 恢复直接从 workspace 上传
- 恢复 tag/name 为旧格式
- 恢复 compression-level: 6
- 恢复 vendor_boot.img 原始命名