# GitCode API 参考

## 基础信息

- API Base URL: `https://api.gitcode.com/api/v5`
- 认证方式: `Authorization: Bearer {token}` 或 `PRIVATE-TOKEN: {token}` 或 `?access_token={token}`

## 常用接口

### 获取仓库Issues

```
GET /repos/{owner}/{repo}/issues?state=all&per_page=100&page=1
```

参数:
- `state`: `open`, `closed`, `all`
- `per_page`: 每页数量，最大100
- `page`: 页码

### 获取仓库Pull Requests (Merge Requests)

```
GET /repos/{owner}/{repo}/pulls?state=all&per_page=100&page=1
```

参数与Issues相同。GitCode中PR也称为Merge Request，URL路径使用 `/merge_requests/`。

### 获取单个Issue详情

```
GET /repos/{owner}/{repo}/issues/{number}
```

### 获取仓库Releases

```
GET /repos/{owner}/{repo}/releases
```

## 响应字段说明

### Issue/PR 通用字段

- `number`: 编号
- `title`: 标题
- `body`: 内容
- `state`: 状态 (`open`, `closed`)
- `html_url`: 页面链接
- `created_at`: 创建时间 (ISO 8601格式)
- `updated_at`: 更新时间
- `user.login`: 创建者用户名
- `user.name`: 创建者显示名
- `labels`: 标签列表，每个标签有 `name`, `color`

### PR特有字段

- `head.ref`: 源分支
- `base.ref`: 目标分支
- `merged`: 是否已合并
- `merge_commit_sha`: 合并提交SHA

## 速率限制

默认 400请求/分钟，4000请求/小时。超过限制返回 429。
