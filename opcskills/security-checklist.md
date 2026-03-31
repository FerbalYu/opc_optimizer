---
keywords: []
always: true
---
# Security Checklist (All Projects)

## 注入防护
- SQL：使用参数化查询 / ORM，禁止字符串拼接 SQL
- XSS：用户输入必须转义后再渲染到 HTML（框架自带除外）
- 命令注入：禁止 `shell=True` + 用户输入拼接，改用列表参数

## 敏感信息
- API Key / 密码 / Token 不要硬编码，用环境变量或密钥管理服务
- `.env` / credential 文件必须加入 `.gitignore`
- 日志中不要打印敏感信息（密码、Token、个人数据）

## 认证与授权
- 密码存储用 bcrypt / argon2，不要 md5 / sha1
- JWT 检查过期时间 + 签名算法限制（禁止 `alg: none`）
- API 端点做权限校验，不要只靠前端隐藏

## 文件 & 路径
- 用户提供的文件名/路径做 `os.path.realpath` 校验，防止路径遍历
- 文件上传限制类型和大小
- 临时文件用 `tempfile.mkstemp` 创建并及时清理

## 依赖
- 定期审查依赖版本，修复已知 CVE
- 锁定依赖版本（lock 文件提交到 Git）
