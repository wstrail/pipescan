# PipeScan Git / GitHub 使用指南

本文档记录本项目常用 Git 操作，适合在 Windows PowerShell 中执行。

## 1. 进入项目目录

```powershell
cd D:\PythonProjects\pipescan
```

## 2. 查看当前状态

```powershell
git status
```

常见状态：

```text
working tree clean
```

表示没有未提交修改。

如果看到很多 `modified` 或 `untracked files`，表示有文件还没有提交。

## 3. 第一次配置 Git 安全目录

如果遇到：

```text
fatal: detected dubious ownership in repository
```

执行：

```powershell
git config --global --add safe.directory D:/PythonProjects/pipescan
```

然后再执行 Git 命令。

## 4. 查看远程仓库

```powershell
git remote -v
```

本项目远程仓库应该是：

```text
origin  https://github.com/wstrail/pipescan.git
```

如果没有远程仓库，添加：

```powershell
git remote add origin https://github.com/wstrail/pipescan.git
```

如果已经存在但地址不对，修改：

```powershell
git remote set-url origin https://github.com/wstrail/pipescan.git
```

## 5. 第一次推送到 GitHub

如果本地分支不是 `main`，先改名：

```powershell
git branch -M main
```

推送：

```powershell
git push -u origin main
```

## 6. 如果推送提示 fetch first

错误示例：

```text
! [rejected] main -> main (fetch first)
```

说明 GitHub 上已经有你本地没有的提交。

推荐做法：

```powershell
git pull origin main --allow-unrelated-histories
git push -u origin main
```

如果只是想覆盖 GitHub 上已有内容，谨慎执行：

```powershell
git fetch origin main
git push -u origin main --force-with-lease
```

更强硬的覆盖方式：

```powershell
git push -u origin main --force
```

注意：`--force` 会覆盖远程仓库历史，确认远程内容不需要时再用。

## 7. 日常提交代码

每次修改代码后，按这个流程提交：

```powershell
git status
git add .
git commit -m "Update project"
git push
```

建议提交信息写清楚，例如：

```powershell
git commit -m "Improve camera console layout"
git commit -m "Add PostgreSQL inspection tables"
git commit -m "Update startup guide"
```

## 8. 拉取 GitHub 最新代码

在开始改代码前，建议先拉取远程最新版本：

```powershell
git pull
```

如果你本地有未提交修改，先提交或暂存：

```powershell
git status
git add .
git commit -m "Save local changes"
git pull
```

## 9. 查看提交记录

```powershell
git log --oneline --graph --decorate -10
```

查看最近 10 条提交。

## 10. 查看具体修改

查看未提交的代码差异：

```powershell
git diff
```

查看已经暂存的差异：

```powershell
git diff --cached
```

## 11. 不要提交的内容

本项目 `.gitignore` 已经排除了：

```text
.venv/
frontend/node_modules/
frontend/dist/
backend/reports/
backend/frames/
backend/*.log
backend/.env
```

注意：

- `backend/.env` 包含数据库连接密码，不应该提交。
- `.venv` 和 `node_modules` 很大，不应该提交。
- `frontend/dist` 是构建产物，不建议提交。

## 12. 如果误提交了敏感文件

如果还没有 push，可以从暂存区移除：

```powershell
git rm --cached backend/.env
git commit -m "Remove env file from repository"
```

如果已经 push 到 GitHub，应该立即更换密码，并清理 Git 历史。

## 13. 推荐日常流程

开始工作：

```powershell
cd D:\PythonProjects\pipescan
git pull
```

修改代码。

检查：

```powershell
git status
```

提交并推送：

```powershell
git add .
git commit -m "Describe your change"
git push
```

## 14. 当前项目仓库

GitHub 地址：

```text
https://github.com/wstrail/pipescan
```

