# Hermes Agent + Open WebUI（可独立部署版）

这是一个把 `Hermes Agent` 和 `Open WebUI` 打包到同一套 Docker Compose 里的独立项目。

它适合下面这些场景：

- 你想在本地快速启动一个 OpenAI 兼容入口
- 你想让 Open WebUI 始终只连接 Hermes，而不是直接连外部模型服务
- 你想在后台页面里切换多套上游模型配置
- 你想把部署、运行数据、后台管理入口都放在一个仓库里管理

## 功能概览

- `Hermes Agent` 对外提供 OpenAI 兼容接口
- `Open WebUI` 作为前端聊天界面
- 本地管理后台：`http://localhost:18642/`
- 多套上游配置档案管理
- 默认配置档案启动物化
- 一键测试上游连通性
- 一键应用到运行时
- Open WebUI 自动保持指向 Hermes
- 应用失败自动回滚到上一份运行配置

## 目录结构

```text
.
├─ docker-compose.yml                 # 顶层编排
├─ .env.example                       # 环境变量示例（安全占位值）
├─ README.md                          # 当前说明文档
├─ docker/
│  └─ hermes-agent/
│     ├─ Dockerfile                   # Hermes 镜像构建文件
│     └─ hermes-agent-src/            # Hermes 源码（含本项目修改）
├─ docs/
│  └─ superpowers/                    # 设计与实施文档
└─ data/                              # 运行时数据（已忽略，不应提交）
```

## 快速开始

### 1）复制环境变量

```bash
cp .env.example .env
```

然后修改 `.env`，至少设置：

```dotenv
HERMES_API_KEY=replace-with-a-long-random-password
```

这个值是 **后台控制台登录口令**，不是上游模型服务的 API Key。

### 2）启动服务

```bash
docker compose up -d --build
```

### 3）访问地址

- Hermes 健康检查：`http://localhost:18642/health`
- Hermes 管理控制台：`http://localhost:18642/`
- Open WebUI：`http://localhost:13000`

## 后台控制台怎么登录

打开：`http://localhost:18642/`

登录时输入 `.env` 里的：

```dotenv
HERMES_API_KEY=replace-with-a-long-random-password
```

注意：

- 这里输入的是 `HERMES_API_KEY`
- 不是上游模型服务的 API Key
- 不是模型名
- 不是 Open WebUI 的密码

## 如何添加上游模型配置

登录控制台后，你可以维护多套**配置档案**。

每个配置档案包含：

- 配置名称
- 提供方类型
- 接口地址（Base URL）
- 密钥（API Key）
- 模型名称

例如下面是一组**假的示例值**，只用于说明格式：

- 名称：`示例 GLM 线路`
- 提供方类型：`OpenAI 兼容接口`
- 接口地址（Base URL）：`https://example-llm-gateway.invalid/v1`
- 密钥（API Key）：`demo-api-key-not-real-123456`
- 模型名称：`glm-5`

你可以：

- `测试连接`：测试上游是否可连通
- `保存档案`：保存当前配置
- `设为默认`：设置为默认启动档案
- `立即应用`：立即生效
- `回滚上一版运行配置`：恢复上一份运行配置

## 运行机制说明

### 1）Open WebUI 始终连接 Hermes

Open WebUI 不会直接连接外部大模型服务。

它始终连接：

```text
http://hermes-agent:8642/v1
```

真正的上游切换由 Hermes 后台控制台完成。

### 2）为什么要挂载 Docker Socket

`hermes-agent` 容器会挂载：

```text
/var/run/docker.sock
```

这样后台在应用配置时，才能：

- 重启 `open-webui`
- 等待 `open-webui` 健康恢复
- 在失败时执行回滚

### 3）配置什么时候生效

- 切换上游后，Hermes 新请求会读取新的运行配置
- 后台会同步修正 Open WebUI 配置
- 然后自动重启 Open WebUI
- 整体完成后状态会变成 `ready`

## 常见问题

### 登录不上后台

请确认你输入的是 `.env` 里的 `HERMES_API_KEY`。

如果刚改过 `.env`，重启服务：

```bash
docker compose up -d --build hermes-agent
```

然后刷新页面重试。

### Open WebUI 里选不到模型

这是因为 Open WebUI 前端始终只连 Hermes。

请到后台确认：

- 配置档案是否已经 `立即应用`
- 状态是否为 `ready`
- 上游 `测试连接` 是否通过

### 如何停止服务

```bash
docker compose down
```

## 提交到 GitHub 前的安全说明

这个仓库默认**不应提交**以下内容：

- 根目录 `.env`
- `data/` 下所有运行时数据
- 浏览器快照、日志、数据库文件
- 本地虚拟环境

如果你要公开仓库，请确保：

- 所有真实密钥都保留在本地 `.env`
- README 里的 URL、账号、密钥都使用示例值
- 运行数据目录不要提交

## 致谢

- [Hermes Agent](https://github.com)（源码已作为本项目的一部分放在 `docker/hermes-agent/hermes-agent-src/`）
- [Open WebUI](https://github.com/open-webui/open-webui)
