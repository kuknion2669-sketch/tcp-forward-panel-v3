# TCP Forward Panel v3

多服务器联动管理面板 — 基于 v14 的多级转发编排系统。

## 定位

**v14（单机面板）** → 管理一台服务器的转发规则
**v3（联动面板）** → 在 v14 基础上追加多服务器集中管理和链路自动编排

v2/v14 作为底层引擎不动，v3 在其之上构建分布式管理能力。

## 关系

```
┌──────────────────────────────────────┐
│         v3 主管理面板                 │
│  （Flask 扩展，管理多台服务器）       │
├──────────────────────────────────────┤
│ 依赖 v14 的核心模块                   │
│  ├── database.py    (数据层)         │
│  ├── haproxy_ctl.py (HAProxy 控制)   │
│  └── stats_collector.py (流量统计)   │
├──────────────────────────────────────┤
│ 每台节点服务器运行 agent.py           │
│ 接受主面板指令 → 管理本地 HAProxy    │
└──────────────────────────────────────┘
```

## 架构

```
客户端 → Server A (入口) → Server B (中转) → 落地机
           ↑                    ↑
           └── 主面板统一推送 ───┘
```

## 开发原则

1. **v2 不动**，核心代码在 v2 仓库迭代，v3 通过 pip 或 git submodule 引入
2. **增量扩展**，v3 只加分布式管理相关逻辑，不重复造轮子
3. **agent 轻量**，无数据库，依赖主面板推送配置

## 状态

- [x] 设计文档 (DESIGN.md)
- [x] 节点代理 (agent/agent.py) 
- [ ] v2 核心模块引入
- [ ] 主面板服务器管理模块
- [ ] 链路自动编排
- [ ] 多服务器拓扑视图

## 快速开始

```bash
# 1. 安装 v14 面板（每台节点服务器）
curl -sL https://raw.githubusercontent.com/kuknion2669-sketch/tcp-forward-panel-v2/main/install.sh | bash

# 2. 在管理节点部署 v3
git clone https://github.com/kuknion2669-sketch/tcp-forward-panel-v3.git /root/tcp-panel-v3
cd /root/tcp-panel-v3

# 3. 配置节点服务器信息（开发中...）
```
