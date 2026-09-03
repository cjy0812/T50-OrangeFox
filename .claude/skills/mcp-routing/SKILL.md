---
name: "mcp-routing"
description: "Routes technical queries to the correct MCP tool (GitHub/Symdex/Scrcpy/JADX/Context7/Playwright). Invoke for any MCP-related technical work in the T50 project."
---

# MCP 工具路由规则

## 1. MCP 使用是强制路由，不是可选项

### 1.1 GitHub 源码问题 → 优先 GitHub MCP

凡是涉及：

- OrangeFox 源码
- TWRP 源码
- AOSP Build System
- `BoardConfig.mk`
- `orangefox.mk`
- `AndroidProducts.mk`
- `mkbootimg`
- `vendor_boot`
- `TARGET_NO_KERNEL`
- `BOARD_*`
- 参考设备 Device Tree
- GitHub 上已有实现

**必须优先使用 GitHub MCP。**

禁止在已经知道 GitHub MCP 可用的情况下，直接使用普通 Web Search 来替代 GitHub MCP。

推荐顺序：

```text
GitHub MCP
    ↓
获取源码
    ↓
定位变量/函数
    ↓
追踪调用关系
    ↓
形成结论
```

只有以下情况才允许使用普通 Web：

- GitHub MCP 无法找到目标内容
- 需要 GitHub 之外的资料
- 需要最新新闻/公告
- 需要厂商网页、论坛、文档等非 GitHub 信息

如果必须使用 Web，应明确说明：

> GitHub MCP 未能提供所需信息，因此退回 Web。

---

## 2. 本地源码问题 → 优先 Symdex

如果已经存在本地源码/解包目录并且已经索引：

优先：

```text
Symdex
```

工具选择：

| 需求             | 工具                          |
| ---------------- | ----------------------------- |
| 找函数/类        | `search_symbols`              |
| 获取函数完整代码 | `get_symbol`                  |
| 找字符串/变量    | `search_text`                 |
| 查看文件结构     | `get_file_outline`            |
| 查看仓库结构     | `get_repo_outline`            |
| 找调用关系       | `get_callers` / `get_callees` |
| 语义搜索         | `semantic_search`             |

不要为了一个简单变量重新 Web 搜索。

---

## 3. Android 设备实际状态 → 优先 Scrcpy MCP

凡是需要知道**T50 当前真实状态**：

- Android 版本
- 分区
- `/dev/block/by-name`
- mount
- fstab
- properties
- cmdline
- SELinux
- recovery
- bootloader
- DTBO
- super
- AVB
- 当前启动状态
- adb shell 输出

优先使用：

```text
Scrcpy MCP
```

尤其是：

```text
shell_exec
device_info
file_list
file_pull
```

原则：

> 能从设备直接测出来，就不要用同 SoC 机型猜。

---

## 4. JADX → 仅用于 APK/Framework 逆向

如果目标是：

- APK
- framework
- SystemUI
- AndroidManifest
- Java/Kotlin
- Smali
- 类/方法调用关系

使用 JADX MCP。

不要用 JADX 解决 boot.img/vendor_boot/DTB 等镜像问题。

---

## 5. Context7 → 仅用于"官方文档/框架 API"问题

Context7 不是 GitHub 搜索替代品。

只有在需要：

- Android API 文档
- 某个框架 API
- 构建工具文档
- 库的官方使用方式

时使用。

流程必须是：

```text
resolve-library-id
        ↓
query-docs
```

不要跳过 `resolve-library-id`。

---

## 6. Playwright → Web 页面无法直接访问时使用

Playwright 用于：

- 需要真实网页交互
- GitLab/GitHub 页面无法直接获取
- 动态页面
- 登录后网页
- 必须点击/展开才能看到的信息

它不是普通源码搜索工具。

---

## 7. Sequential Thinking → 复杂问题才使用

Sequential Thinking 用于：

- 多阶段逆向
- 构建架构设计
- 参数冲突分析
- 多个证据互相矛盾
- 需要回溯假设

不要因为任务复杂就无脑使用。

最重要的是：

> Sequential Thinking 负责"怎么想"，MCP 负责"拿证据"。

不能用思考工具代替实际工具调用。

---

## 8. 工具调用前的强制路由检查

每当准备回答一个技术问题时，先在内部执行：

```text
【工具路由检查】

这是：
□ T50 实际设备问题
□ 本地源码问题
□ GitHub/AOSP/OrangeFox 源码问题
□ 官方文档问题
□ APK 逆向问题
□ 网页交互问题
□ 单纯理论问题
```

然后选择工具。

如果勾选了：

```text
T50 实际设备
```

优先 Scrcpy MCP。

如果勾选了：

```text
GitHub/AOSP/OrangeFox 源码
```

优先 GitHub MCP。

如果勾选了：

```text
本地源码
```

优先 Symdex。

**不得因为"我已经知道答案"而跳过工具验证。**

---

## 9. 防止 MCP"失忆"

在连续研究超过一个阶段后，必须重新读取以下状态：

```text
当前目标：
当前阶段：
已经确认：
尚未确认：
当前阻塞：
下一步：
应该使用的 MCP：
```

例如：

```text
当前目标：
构建 T50 OrangeFox vendor_boot recovery

当前阶段：
BoardConfig 最小化

已经确认：
- boot header v4
- vendor_boot header v4
- vendor_boot = 64 MiB
- ramdisk = gzip
- DTB 位于 MTK pool
- 无独立 recovery 分区

尚未确认：
- DTBO 分区实际内容
- 某些 OrangeFox 变量是否真的需要

当前阻塞：
无

下一步：
先尝试第一次构建

应该使用的 MCP：
本阶段不需要继续搜索源码；
如果构建报错，再根据错误调用 GitHub MCP/Symdex。
```

### 9.1 禁止"重新开始研究"

如果已经有明确结论：

```text
CONFIRMED
```

不得因为发现一个类似机型而重新研究同一问题。

除非出现：

- 新证据冲突
- 构建错误
- 实机启动失败
- 新源码与旧结论矛盾

否则保持结论。
