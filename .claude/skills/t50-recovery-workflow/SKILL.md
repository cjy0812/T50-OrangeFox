---
name: "t50-recovery-workflow"
description: "T50 OrangeFox Recovery build workflow: Phase 1-7, first-build diagnostics, status checkpoints. Invoke when building recovery, switching phases, or verifying images."
---

# T50 Recovery 构建工作流

## 1. "第一次构建"是主动诊断工具

对于 Recovery 构建，不要求：

> 在第一次 `mka recoveryimage` 之前把所有 BoardConfig 参数研究到 100%。

合理流程是：

```text
镜像分析
   ↓
最小 BoardConfig
   ↓
构建
   ↓
构建错误
   ↓
针对错误补参数
   ↓
重新构建
   ↓
得到 recovery/vendor_boot
   ↓
检查镜像结构
   ↓
再决定是否刷机
```

**构建系统本身就是验证工具。**

---

## 2. T50 项目专用工作流

### Phase 1：设备画像

使用：

```text
Scrcpy MCP
```

获取：

```text
getprop
cmdline
/proc/partitions
/dev/block/by-name
mount
fstab
boot/vendor_boot/vbmeta
```

---

### Phase 2：镜像分析

本地分析：

```text
boot_a.bin
vendor_boot_a.bin
vbmeta_a.bin
dtbo.img
super.img
```

重点确认：

```text
header
kernel
ramdisk
DTB
DTBO
cmdline
partition size
compression
```

---

### Phase 3：OrangeFox 源码验证

使用：

```text
GitHub MCP
```

追踪：

```text
FOX_VENDOR_BOOT_RECOVERY
TARGET_NO_KERNEL
BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT
BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT
vendor_boot
mkbootimg
```

不要只找"同 SoC Device Tree"。

优先理解：

> OrangeFox 到底如何生成 vendor_boot recovery。

---

### Phase 4：建立最小 Device Tree

目标：

```text
最少变量
最少文件
最少猜测
```

不要一开始追求完整 ROM Device Tree。

首先目标只是：

> **生成能够被设备接受的 recovery/vendor_boot。**

---

### Phase 5：第一次构建

执行：

```text
mka recoveryimage
```

或者 OrangeFox 对应构建目标。

如果构建失败：

```text
读取错误
 ↓
判断属于：
  BoardConfig
  Soong
  Make
  recovery
  vendor_boot
  missing dependency
 ↓
针对错误解决
```

不要重新搜索整个 Android 源码。

---

### Phase 6：镜像结构验证

构建完成后，不立即刷。

先比较：

```text
原厂 vendor_boot
vs
OrangeFox vendor_boot
```

检查：

```text
header version
page size
ramdisk
compression
DTB
cmdline
size
slot
AVB
```

---

### Phase 7：首次启动测试

优先：

```text
fastboot boot
```

如果设备/bootloader支持。

其次才考虑：

```text
临时刷入
```

最后才：

```text
正式写入 vendor_boot_a/b
```

---

## 3. 每次任务结束必须留下状态

格式：

```text
## 当前状态

阶段：
xxx

已确认：
- xxx
- xxx

未知：
- xxx

已推迟：
- xxx

当前是否阻塞：
YES / NO

下一步：
xxx

下一步应该调用：
MCP 名称 / 无需 MCP
```

这部分非常重要。

它是 Agent 在长上下文中防止"失忆"的检查点。
