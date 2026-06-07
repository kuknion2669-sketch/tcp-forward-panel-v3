# TCP Forward Panel v3 — 多服务器联动管理

## 核心定位

**v3 是 v2 的集中管理层。** 不修改 v2 一行代码，通过 v2 已有的 HTTP API 实现统一管理。

## 架构

```
┌──────────────────────────────────────────────┐
│           v3 Master Panel                    │
│  Flask + SQLite + requests                   │
│                                               │
│  ├── 服务器管理（注册 v2 实例）               │
│  ├── 链路编排（跨服务器规则链）               │
│  ├── 统一视图（所有服务器状态汇总）           │
│  └── 配置推送（通过 v2 API 同步）             │
└──────────┬───────────────────────────────────┘
           │ HTTP API（带 Session Cookie）
     ┌─────┼──────────────┬──────────────┐
     ▼     ▼              ▼              ▼
  ┌────┐ ┌────┐       ┌────┐        ┌────┐
  │v2  │ │v2  │  ...  │v2  │        │非v2│
  │节点│ │节点│       │节点│        │节点│
  └────┘ └────┘       └────┘        └────┘
                         ↑          (agent.py)
                    全部通过 HTTP API 管理
```

## v2 已有 API（v3 直接利用）

v2 已经提供了完整的 HTTP API，v3 通过 requests 调用：

| v2 API | 用途 |
|--------|------|
| `POST /login` | 认证，获取 session |
| `POST /add` | 新增规则 |
| `POST /batch_add` | 批量导入 |
| `GET /del/<idx>` | 删除规则 |
| `POST /edit/<idx>` | 编辑规则 |
| `GET /check/<idx>` | 单节点检测 |
| `GET /check_all` | 全部检测 |
| `POST /api/toggle/<local>` | 启用/停用 |
| `GET /api/haproxy` | HAProxy 状态 |
| `GET /api/connections` | 连接详情 |
| `GET /backup` | 导出配置 |

**零侵入** — v3 不做任何 v2 代码修改。

## 链路编排

### 场景：客户端 → 入口A → 中转B → 落地C

```
v3 创建一条链路 "广东→美区"
    │
    ├── 在 Server A 上创建规则：
    │     name: "广东→美区(入口)"
    │     local: 45887
    │     ip: Server_B
    │     port: 45887
    │
    ├── 在 Server B 上创建规则：
    │     name: "广东→美区(中转)"
    │     local: 45887
    │     ip: 103.179.142.128
    │     port: 45887
    │
    └── 端口自动映射保证一致性
```

## 项目结构

```
├── run.py               入口（Flask 启动）
├── config.py            配置（DB路径、监听端口等）
├── master/
│   ├── panel.py         主路由（dashboard + servers + chains）
│   ├── server_mgr.py    服务器管理（CRUD + 连接测试）
│   ├── chain_mgr.py     链路编排（规则链自动组合）
│   ├── sync_engine.py   v2 API 通信层（认证 + 请求 + 重试）
│   └── templates/
│       ├── index.html       总控面板（多服务器状态一览）
│       ├── servers.html     服务器管理
│       ├── chains.html      链路管理
│       └── chains_edit.html 链路编辑
├── agent/
│   ├── agent.py         轻量代理（非 v2 节点用）
│   └── requirements.txt
└── requirements.txt     Python 依赖
```

## 数据表

### servers — 管理的 v2 节点

| 字段 | 说明 |
|------|------|
| id | 自增主键 |
| name | 节点名称（湖南、中转、东京等） |
| host | 服务器 IP |
| port | v2 面板端口 |
| username | v2 登录账号 |
| password | v2 登录密码 |
| role | 角色（入口/中转/落地） |
| enabled | 是否启用 |
| note | 备注 |
| last_seen | 最后在线时间 |

### chains — 转发链路

| 字段 | 说明 |
|------|------|
| id | 自增主键 |
| name | 链路名称 |
| entry_server | 入口服务器 ID → servers.id |
| entry_port | 入口本地端口 |
| trans_server | 中转服务器 ID → servers.id |
| dest_ip | 最终目标 IP |
| dest_port | 最终目标端口 |
| enabled | 是否启用 |

## 开发路线

1. **v3 基础框架** — server_mgr + 认证 + 登录 v2
2. **同步引擎** — 通过 v2 API 增删改规则
3. **链路编排** — 自动创建多级转发链
4. **统一视图** — 所有服务器状态汇总展示
5. **agent** — 非 v2 节点适配
