# TCP Forward Panel v3 — 多服务器联动设计

## 架构总览

```
客户端 → Server A (入口层) → Server B (中转层) → 落地机
           ↑                         ↑
           └───── 主管理面板 ─────────┘
                 (任意一台)
```

## 角色

| 角色 | 运行组件 | 职责 |
|------|---------|------|
| **主管理面板** | Flask + DB | 统一配置入口，管理所有节点和链路 |
| **节点代理** | 轻量 Python 服务 | 每台服务器各一个，接受主面板指令，管理本地 HAProxy |
| **转发节点** | HAProxy | 实际的 TCP 转发，由代理控制 |

## 使用流程

1. 在主面板添加服务器（IP、端口、密钥）
2. 添加转发规则时选择链路：
   - 入口服务器 A 的本地端口
   - 中转服务器 B 的目标端口（自动映射）
   - 落地机 IP:端口
3. 主面板自动推送到各节点：
   - Server A：`localhost:1234 → Server_B:1234`
   - Server B：`localhost:1234 → 落地机:端口`

## API 设计

### 主面板 → 节点代理

```
POST /api/agent/sync    推送全量配置（rules list）
GET  /api/agent/status  获取代理运行状态（uptime, rules, traffic）
GET  /api/agent/ping    健康检查（alive check）
```

### 节点代理端

- 轻量，无数据库，依赖主面板推送
- 收到配置后写入本地 HAProxy 配置并 reload
- 定时上报流量状态给主面板

## 配置流转

```
主面板新增规则
    ↓
生成各节点的 HAProxy 配置片段
    ↓
分别推送到 Server A 代理 / Server B 代理
    ↓
各代理写入 /etc/haproxy/haproxy.cfg
    ↓
systemctl restart haproxy
```

## 流量流向

```
[客户端]:443
    ↓
Server A:1234  (入口层，接收客户端连接)
    ↓
Server B:1234  (中转层，HAProxy 转发)
    ↓
落地机:443    (最终目标)
```

## 链路自动映射

主面板自动保证链路端口一致性：
- Server A 的本地端口 = Server B 的本地端口
- 用户只需配置一次，两端同步

## 状态

- [ ] 节点代理（agent/agent.py）
- [ ] 主面板服务器管理模块
- [ ] 规则链路配置 UI
- [ ] 配置推送同步
- [ ] 多服务器拓扑视图
