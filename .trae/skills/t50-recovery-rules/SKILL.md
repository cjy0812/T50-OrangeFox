---
name: "t50-recovery-rules"
description: "T50 Recovery research standards: evidence levels, BoardConfig rules, reference search, stop conditions. Invoke when editing BoardConfig, analyzing images, or researching parameters."
---

# T50 Recovery 研究规范

## 1. 参考设备搜索规则

搜索同 SoC / 同平台设备时必须遵守：

```text
T50
 ↓
同设备
 ↓
同厂商/同平台
 ↓
同 MTK boot 架构
 ↓
同 Android/vendor_boot 版本
 ↓
同 SoC
 ↓
其他 MTK
 ↓
通用 AOSP
```

而不是：

```text
MT6768
 ↓
随便找一个 MT6768
 ↓
照抄 BoardConfig
```

参考设备只能回答：

> "别人是怎么实现的？"

不能直接回答：

> "T50 就应该这么配置。"

---

## 2. Android Recovery 项目的证据等级

所有关键参数必须标记证据等级：

### A — 直接设备证据

例如：

```text
boot_a.bin header
vendor_boot_a.bin
DTB
fstab
/dev/block/by-name
设备 shell
```

这是最高等级。

### B — 官方源码证据

例如：

```text
OrangeFox source
AOSP build system
mkbootimg
TWRP source
```

用于确定：

> 某变量到底是什么意思、构建系统如何处理。

### C — 同类设备实例

例如：

```text
Infinix X6886
Xiaomi klee
Unihertz Jelly Max
```

只能作为参考。

### D — 社区经验

论坛、博客、帖子。

### E — 推测

例如：

```text
MTK 一般这样
这个 SoC 通常这样
应该是这样
```

必须明确标记为推测。

---

## 3. BoardConfig 参数处理规则

每个参数必须回答：

```text
1. 这个变量是谁读取的？
2. 它影响什么？
3. T50 是否真的需要？
4. T50 的证据是什么？
5. 如果不设置会发生什么？
6. 是否可以等第一次构建后再决定？
```

如果：

```text
不设置也能构建
且不会明显影响镜像结构
且无法从设备确认
```

优先：

> 暂时不设置，进入第一次构建。

不要无限研究。

---

## 4. 研究停止条件

如果一个问题满足：

```text
□ 不阻塞当前构建
□ 没有直接设备证据
□ 只有参考设备差异
□ 可以通过构建错误验证
□ 不涉及刷机安全
```

则停止继续研究。

标记：

```text
DEFERRED
```

并进入下一阶段。

例如：

```text
BOARD_KERNEL_BASE
```

如果 OrangeFox 当前构建流程根本没有要求它：

> 不要为了追求理论完整性研究 2 小时。

直接先构建。

---

## 5. 但以下问题不能随便 DEFER

涉及实际刷机/启动风险时必须提高证据要求：

```text
- AVB
- vbmeta
- boot/vendor_boot header
- ramdisk
- DTB
- DTBO
- 分区大小
- boot slot
- A/B
- AVB rollback
- recovery ramdisk 所在位置
```

这些参数如果错误，可能导致：

```text
无法启动
bootloop
无法进入 recovery
刷坏镜像
```

因此：

> 构建阶段可以容忍 UNKNOWN；刷机阶段不能。

---

## 6. 关于"没有源码"的原则

没有厂商 kernel/device tree source **并不等于不能做 Recovery**。

传统大佬常用的路线实际上是：

```text
官方镜像
   ↓
boot/vendor_boot 分析
   ↓
提取 ramdisk/fstab/DTB
   ↓
读取设备运行时信息
   ↓
参考其他设备的 Device Tree
   ↓
建立最小 Device Tree
   ↓
编译 TWRP/OrangeFox
   ↓
构建失败 → 修
   ↓
镜像结构验证
   ↓
设备测试
   ↓
根据 dmesg/logcat 修复
```

核心不是：

> "找到一个和 T50 完全一样的源码。"

而是：

> **从二进制和运行时环境恢复构建系统需要的最小信息。**

---

## 7. 防止 Agent 无休止研究

当连续搜索超过一个阶段，必须主动问：

```text
这个问题现在是否阻塞构建？
```

如果答案是：

```text
否
```

则停止研究。

输出：

```text
【结论】
当前问题暂不阻塞构建。

【处理】
暂时保留 UNKNOWN。

【下一步】
进入第一次构建。

【验证方式】
如果构建报错，再针对错误补充证据。
```

禁止：

```text
继续寻找 10 个同 SoC 设备
继续寻找更多 AOSP 源码
继续寻找"完美 BoardConfig"
```
