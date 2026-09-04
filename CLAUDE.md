# T50 OrangeFox Recovery 项目

## 核心原则

本项目的目标是：

> 在**无厂商源码、无现成 TWRP/OrangeFox Recovery**的情况下，仅依靠 T50 自身镜像、设备运行时信息、公开源码和参考设备，逐步构建可启动的 TWRP/OrangeFox Recovery，并进一步为第三方 ROM（如 Infinity-X 等）建立基础。

必须遵守：

1. **T50 自身证据 > 同 SoC 设备 > 同平台设备 > 通用 AOSP 文档 > 网络经验帖**
2. **设备实际镜像 > 推测**
3. **源码追踪 > 猜变量**
4. **参考机只能证明"这种方案存在"，不能直接证明"T50 必须这样配置"**
5. 不因为"同 SoC"就默认硬件、bootloader、vendor_boot 布局相同。
6. 不为了得到一个看似完整的 BoardConfig 而强行填 UNKNOWN 参数。
7. 构建错误本身就是后续证据，不需要在第一次构建前解决所有理论问题。
8. 每完成一个阶段，都必须判断：

   * 这个问题是否真的阻塞当前阶段？
   * 是否可以通过第一次构建/打包结果验证？
   * 如果可以，应停止继续理论研究并进入构建。

---

## 证据优先级

```text
实际设备证据
    ↓
本地源码证据
    ↓
GitHub MCP 源码证据
    ↓
官方文档
    ↓
参考设备
    ↓
Web 搜索
    ↓
模型自身知识
    ↓
推测
```

如果高等级证据可获得，不得用低等级证据替代。

---

## 当前项目默认目标

默认项目目标为：

```text
台电 T50
tb8786p1_64_k510_wifi
MTK MT8786 / MT6768
A/B
vendor_boot recovery
```

当前主要目标：

```text
OrangeFox Recovery
    ↓
vendor_boot recovery
    ↓
最小可启动 Recovery
```

之后再考虑：

```text
TWRP
OrangeFox 完善
Infinity-X
LineageOS
其他 AOSP ROM
Kernel / LK / DTB
```

不要在 Recovery 尚未启动前同时研究 ROM、Kernel、LK、超频等无关问题。

**当前阶段只解决当前阶段的问题。**

---

## Skills 索引

本项目已拆分以下专项 Skills（按需自动加载）：

| Skill                   | 用途                                 | 触发条件                             |
| ----------------------- | ------------------------------------ | ------------------------------------ |
| `mcp-routing`           | MCP 工具路由规则                     | 涉及 MCP 工具调用的技术任务          |
| `t50-recovery-rules`    | 研究规范、证据等级、BoardConfig 规则 | 编辑 BoardConfig、分析镜像、研究参数 |
| `t50-recovery-workflow` | Phase 1-7 构建工作流、状态检查点     | 构建 Recovery、切换 Phase、验证镜像  |

如果用户要求：

> "用 MCP 搜索"
> "用 GitHub MCP"
> "检查本地源码"
> "从设备实际读取"

必须立即执行对应 MCP。**不能回复一段分析后再考虑使用工具。**

---

## 双 Agent 同步机制

本项目同时支持 **Claude Code**（`.claude/`）和 **Trae IDE**（`.trae/`），通过 Git Hook 自动保持 `.claude/skills/` ↔ `.trae/skills/` 双向同步。

> **如果当前 Agent 是 Trae，请务必在项目创建 `.trae` 文件夹，以保证 Git Hook 正常同步 Agent 数据！**

同步规则：

- `.claude/skills/` 是 Git 中的权威副本（提交到仓库）
- `.trae/skills/` 是 Trae IDE 的本地工作副本（已加入 `.gitignore`，不提交）
- `pre-commit`：自动将 `.trae/skills/` 的变更同步到 `.claude/skills/`
- `pre-push`：验证双端同步，未同步时阻止 push；同时阻止 `.trae/` 被提交
- `post-checkout`：自动将 `.claude/skills/` 同步到 `.trae/skills/`