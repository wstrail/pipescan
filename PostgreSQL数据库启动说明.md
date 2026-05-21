# PipeScan PostgreSQL 数据库启动说明

本项目推荐使用 Docker 启动 PostgreSQL。这样不需要在 Windows 系统里手动安装 PostgreSQL，也不需要单独配置系统服务。

## 1. 数据库配置

当前项目使用以下数据库配置：

```text
数据库类型：PostgreSQL
地址：localhost
端口：5432
数据库名：pipescan
用户名：pipescan
密码：pipescan
```

后端连接字符串写在：

```text
backend/.env
```

内容是：

```env
DATABASE_URL=postgresql+psycopg://pipescan:pipescan@localhost:5432/pipescan
```

## 2. 启动数据库

在项目根目录执行：

```powershell
docker compose up -d postgres
```

这个命令会自动：

- 下载 PostgreSQL 镜像
- 创建 PostgreSQL 容器
- 创建 `pipescan` 用户
- 创建 `pipescan` 数据库
- 把数据库数据保存到 Docker volume 中

## 3. 查看数据库是否启动成功

执行：

```powershell
docker compose ps
```

如果看到 `pipescan-postgres` 状态为 `running` 或 `healthy`，说明数据库已经启动。

也可以查看日志：

```powershell
docker compose logs postgres
```

## 4. 启动后端

先激活虚拟环境：

```powershell
cd D:\PythonProjects\pipescan
.\.venv\Scripts\Activate.ps1
```

然后启动后端：

```powershell
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

后端启动时会自动创建数据库表：

- `pipe_segments`
- `inspection_reports`

## 5. 检查后端是否连上数据库

打开：

```text
http://localhost:8000/api/db/health
```

如果返回：

```json
{
  "connected": true,
  "message": "database connected"
}
```

说明后端已经连上 PostgreSQL。

## 6. 测试保存管道数据

打开 FastAPI 文档：

```text
http://localhost:8000/docs
```

测试接口：

```text
POST /api/pipes
```

请求示例：

```json
{
  "pipe_code": "P-001",
  "length_m": 30,
  "diameter_mm": 800,
  "region_type": "traffic",
  "soil_type": "medium",
  "location": "测试路段",
  "remark": "首次建档"
}
```

然后调用：

```text
GET /api/pipes
```

如果能查到刚才的数据，说明数据库写入和读取都正常。

## 7. 停止数据库

停止容器：

```powershell
docker compose stop postgres
```

再次启动：

```powershell
docker compose start postgres
```

## 8. 删除数据库容器但保留数据

```powershell
docker compose down
```

数据仍然保存在 Docker volume 中。

## 9. 删除数据库和所有数据

谨慎执行：

```powershell
docker compose down -v
```

这个命令会删除数据库数据卷，所有管道数据和报告记录都会丢失。

