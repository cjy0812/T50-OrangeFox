# Artifact 清理与优化计划

> 状态: 待执行
> 优先级: P1
> 影响文件: `build-test-slimhub.yml`, `build.yml`

## 问题诊断

### 问题1: staging 目录被二次打包

**根因**: `actions/upload-artifact` 的 `*.zip` glob **递归匹配**子目录中的 zip 文件

```
workspace/out/.../DEVICE/*.zip  匹配到:
  ✅ OrangeFox-R12.0-Unofficial-tb8786p1.zip     (正确 - 刷机包)
  ❌ OrangeFox-.../sdcard/Fox/FoxFiles/AromaFM/AromaFM.zip  (递归匹配)
  ❌ OrangeFox-.../sdcard/Fox/FoxFiles/Magisk.zip           (递归匹配)
  ❌ OrangeFox-.../sdcard/Fox/FoxFiles/uninstall.zip        (递归匹配)
```

这些递归匹配把整个 staging 目录树 `OrangeFox-R12.0-Unofficial-tb8786p1/` 拉入 artifact

**影响**: artifact 135MB, 其中 staging 目录约占 30-40MB 冗余

### 问题2: vendor_boot.img 与 OrangeFox-*.img 哈希相同

**根因**: A/B 设备 (FOX_AB_DEVICE=1) 构建时, OrangeFox 构建系统生成:
- `vendor_boot.img` — Android 标准产物
- `OrangeFox-R12.0-Unofficial-tb8786p1.img` — OrangeFox 命名惯例产物

两者是硬链接或复制, 内容完全相同 (用户已验证哈希一致)

**影响**: 每个 img 约 30MB, 冗余一份 = 浪费 30MB 存储 + 下载带宽

### 问题3: artifact 压缩效率

**现状**: `upload-artifact@v7` 默认 `compression-level: 6` (zlib/zip)
**用户需求**: 7z 最大压缩

**技术约束**:
- `upload-artifact` 只支持 zlib/zip 格式 (compression-level 0-9)
- 不支持 7z 格式
- img 镜像本身是稀疏/压缩格式, zip 压缩效果有限

## 修复方案

### Step 1: 排除 staging 目录 (使用 `!` 排除模式)

`actions/upload-artifact@v7` 原生支持 `!` 排除 glob

**test yml Artifacts 修改:**
```yaml
- name: 上传产物到 Artifacts
  uses: actions/upload-artifact@v7
  with:
    name: ${{ github.event.inputs.BUILD_MODE }}-build-${{ github.run_id }}
    path: |
      workspace/out/target/product/${{ github.event.inputs.DEVICE_NAME }}/*.img
      workspace/out/target/product/${{ github.event.inputs.DEVICE_NAME }}/*.zip
      workspace/out/target/product/${{ github.event.inputs.DEVICE_NAME }}/obj/PACKAGING/vendor_ramdisk_fragments_intermediates/recovery.cpio.gz
      !workspace/out/target/product/${{ github.event.inputs.DEVICE_NAME }}/OrangeFox-*/**
    if-no-files-found: warn
    retention-days: ${{ github.event.inputs.BUILD_MODE == 'debug' && 14 || 90 }}
    compression-level: 9
```

**test yml Release 修改:**
```yaml
- name: 上传到 Release
  uses: softprops/action-gh-release@v3
  with:
    files: |
      workspace/out/target/product/${{ github.event.inputs.DEVICE_NAME }}/*.img
```
Release 只上传 .img, 不涉及 staging 目录问题, 无需修改

### Step 2: 删除重复的 vendor_boot.img

**构建步骤末尾添加:**
```bash
DEVICE_OUT="out/target/product/${{ github.event.inputs.DEVICE_NAME }}"

# OrangeFox-*.img 与 vendor_boot.img 内容相同 (A/B 设备硬链接/复制)
# 保留 OrangeFox 命名 (用户辨识度高), 删除 vendor_boot.img
if [ -f "$DEVICE_OUT/vendor_boot.img" ]; then
  FOX_IMG=$(ls "$DEVICE_OUT"/OrangeFox-*.img 2>/dev/null | head -1)
  if [ -n "$FOX_IMG" ] && [ -f "$FOX_IMG" ]; then
    rm "$DEVICE_OUT/vendor_boot.img"
    echo "Removed duplicate vendor_boot.img (identical to $(basename "$FOX_IMG"))"
  fi
fi
```

**保留策略:**
- ✅ `OrangeFox-R12.0-Unofficial-tb8786p1.img` — 保留 (用户辨识度高, OrangeFox 命名惯例)
- ✅ `ramdisk.img` — 保留 (独立有用, flash-ramdisk 脚本需要)
- ❌ `vendor_boot.img` — 删除 (与 OrangeFox-*.img 重复)

**Release body 刷机说明:**
```yaml
body: |
  OrangeFox 分支: ${{ github.event.inputs.FOX_BRANCH }}
  设备: ${{ github.event.inputs.DEVICE_NAME }}
  构建目标: ${{ github.event.inputs.BUILD_TARGET }}
  构建模式: ${{ github.event.inputs.BUILD_MODE }}

  刷机命令: fastboot flash vendor_boot OrangeFox-*.img
```

### Step 3: compression-level: 9

`upload-artifact@v7` 参数:
- `compression-level: 9` — zlib/zip 最大压缩
- 对 img 镜像效果有限 (已是压缩格式), 但对 .zip 刷机包和 .cpio.gz 有一定效果
- 压缩时间增加约 10-20%, 但 artifact 存储费用降低

**不采用 7z 方案的原因:**
- 需要额外安装 p7zip-full + 手动压缩 + 二次解压体验差
- compression-level: 9 已是 zip 格式最大压缩, 足够用

## 执行顺序

1. **修改 test yml** — 先在 `build-test-slimhub.yml` 实施 3 个修复
2. **触发测试构建** — 验证 artifact 不含 staging 目录、不含重复 img
3. **验证通过后** — 合并到生产 `build.yml`

## 验证清单

- [ ] artifact 不包含 `OrangeFox-*/` staging 目录树
- [ ] artifact 不包含 `vendor_boot.img` (已删除重复)
- [ ] artifact 包含 `OrangeFox-*.img` + `ramdisk.img` + `OrangeFox-*.zip` + `recovery.cpio.gz`
- [ ] Release 只包含 `*.img` 文件
- [ ] Release body 包含刷机命令说明
- [ ] compression-level: 9 生效 (artifact 大小合理)
- [ ] 构建成功, 产物完整可刷入

## 回退方案

如果排除模式导致文件缺失:
- 移除 `!` 排除行, 改为构建步骤末尾 `rm -rf` staging 目录
- 恢复 vendor_boot.img 保留
- 恢复 compression-level: 6